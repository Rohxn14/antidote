# tests/test_mcp.py
"""The MCP tool surface, called through a real MCP client (in-process)."""
import asyncio
import json

from mcp import Client

from app import demo, memory
from app.mcp_server import create_server
from app.schema import QUARANTINED


def call(server, name, args=None):
    async def go():
        async with Client(server) as client:
            result = await client.call_tool(name, args or {})
            return json.loads(result.content[0].text)
    return asyncio.run(go())


def tool_names(server):
    async def go():
        async with Client(server) as client:
            return {t.name: t for t in (await client.list_tools()).tools}
    return asyncio.run(go())


def test_agents_get_no_approval_tools(g):
    tools = tool_names(create_server(lambda: g))
    assert not [name for name in tools if "approve" in name or "apply" in name]
    assert tools["supported_beliefs"].annotations.read_only_hint is True
    assert tools["propose_purchase_order"].annotations.read_only_hint is False


def test_tools_drive_the_story(g):
    server = create_server(lambda: g)
    demo.register(g)
    demo.research(g)

    beliefs = call(server, "supported_beliefs", {"vendor_id": "v_vantor"})["beliefs"]
    assert "b_vantor_iso13485" in {b["id"] for b in beliefs}
    evidence = {b["id"]: b["evidence"] for b in beliefs}
    assert evidence["b_vantor_iso13485"] == "unverified only"      # only Vantor says so
    assert evidence["b_vantor_makes_servos"] == "single trusted origin"  # the registry

    proposed = call(server, "propose_purchase_order", {
        "vendor_id": "v_vantor", "quantity": 100, "unit_price": 480,
        "premises": ["b_vantor_qualifies", "b_vantor_offer", "b_req_quantity"],
        "reasoning": "cheapest qualifying supplier"})
    assert (proposed["order_id"], proposed["state"]) == ("d_po_1001", "pending_approval")

    revision = memory.revision(g)
    preview = call(server, "preview_quarantine", {"source_id": "s_vantor_page"})
    assert "d_po_1001" in preview["orders_blocked"]
    assert memory.revision(g) == revision  # the preview changed nothing...
    assert call(server, "check_order", {"order_id": "d_po_1001"})["outcome"] == "needs_approval"

    memory.set_trust(g, "s_vantor_page", QUARANTINED)  # ...a human approved the repair
    assert call(server, "check_order", {"order_id": "d_po_1001"})["outcome"] == "blocked"
    beliefs = call(server, "supported_beliefs", {"vendor_id": "v_vantor"})["beliefs"]
    assert "b_vantor_iso13485" not in {b["id"] for b in beliefs}

    refused = call(server, "propose_purchase_order", {
        "vendor_id": "v_vantor", "quantity": 100, "unit_price": 480,
        "premises": ["b_vantor_qualifies"], "reasoning": "try again"})
    assert refused["order_id"] is None
    assert "not valid beliefs" in refused["rejected"][0]


def test_explain_and_bad_quote_through_mcp(g):
    server = create_server(lambda: g)
    demo.register(g)
    demo.research(g)
    tree = call(server, "explain", {"node_id": "b_vantor_qualifies"})
    assert {j["kind"] for j in tree["justifications"]} == {"inference"}
    result = call(server, "record_extraction", {
        "source_id": "s_quillon_page", "belief_id": "b_quillon_iso13485",
        "claim": "Quillon holds ISO 13485", "quote": "Quillon Drives is ISO 13485 certified.",
        "reasoning": "made up", "vendor_id": "v_quillon"})
    assert result == {"recorded": False,
                      "rejected": ["b_quillon_iso13485: quote not found in s_quillon_page"]}
