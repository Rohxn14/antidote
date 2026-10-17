# app/mcp_server.py
"""Antidote's shared memory as MCP tools.

Any MCP host (or our own tool-using agent, app/agents/tool_agent.py) can read
supported memory, record beliefs and reasons, check an order against the
gate, and preview a quarantine. There is deliberately NO tool to approve a
repair or a purchase: those stay with humans, and the tool surface is what
enforces it.

    python -m app.mcp_server        # stdio transport, for MCP hosts

Every tool calls the same tested functions as the UI. Rejections are returned
as readable results, so an agent learns why it was refused.
"""
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from app import detector, gate, memory, repair, views
from app.agents import buyer, researcher
from app.db import get_graph

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False)

INSTRUCTIONS = """Shared memory for a procurement team's agents, backed by a FalkorDB graph.
Beliefs are only usable while a justification supports them; unsupported memory
is hidden. Cite belief ids as premises for everything you record. You can propose
and check purchase orders, but only a human can approve them or approve a repair."""


def create_server(graph=get_graph) -> MCPServer:
    """`graph` returns the FalkorDB graph to work on (tests pass their own)."""
    server = MCPServer("antidote", instructions=INSTRUCTIONS)

    @server.tool(annotations=READ_ONLY)
    def supported_beliefs(vendor_id: str | None = None) -> dict:
        """Beliefs the shared memory currently supports. Unsupported beliefs are
        never returned. Optionally only those about one vendor (e.g. v_boltline)."""
        return {"beliefs": memory.valid_beliefs(graph(), vendor_id)}

    @server.tool(annotations=READ_ONLY)
    def explain(node_id: str) -> dict:
        """Why a belief or decision is supported, or not: every justification,
        whether it holds, its premises, and recursively their support down to
        the sources."""
        return views.why(graph(), node_id)

    @server.tool(annotations=READ_ONLY)
    def list_orders() -> dict:
        """Purchase orders with their state (draft, pending_approval,
        authorized, executed, blocked) and whether they are still supported."""
        return {"orders": [d for d in views.decisions(graph()) if d["kind"] == "purchase_order"]}

    @server.tool(annotations=READ_ONLY)
    def check_order(order_id: str) -> dict:
        """Re-check an order against the current graph without changing its
        state: blocked, needs_approval or auto, with reasons."""
        try:
            v = gate.evaluate(graph(), order_id)
        except gate.GateError as e:
            return {"error": str(e)}
        return {"order_id": order_id, "outcome": v.outcome, "reasons": v.reasons}

    @server.tool(annotations=READ_ONLY)
    def scan_sources() -> dict:
        """Rule-based scan of the sources for prompt-injection signs. Findings
        only propose a quarantine; a human decides."""
        return {"findings": [f.__dict__ for f in detector.scan_sources(graph())]}

    @server.tool(annotations=READ_ONLY)
    def preview_quarantine(source_id: str) -> dict:
        """What would lose support if this source were quarantined, computed on
        a throwaway copy of the graph. Nothing changes; a human must approve
        the actual repair."""
        try:
            p = repair.preview(graph(), source_id)
        except ValueError as e:
            return {"error": str(e)}
        repair.discard(p)
        return {"source_id": source_id, "lost": p.lost, "survived": p.survived,
                "orders_blocked": [o["id"] for o in p.orders_blocked],
                "executed_affected": [o["id"] for o in p.executed_affected]}

    @server.tool(annotations=WRITES)
    def record_extraction(source_id: str, belief_id: str, claim: str, quote: str,
                          reasoning: str, vendor_id: str | None = None) -> dict:
        """Record a claim that a source makes. `quote` must be copied verbatim
        from the source, or the claim is rejected. Reuse an existing belief_id
        when another source states the same claim (that corroborates it)."""
        rejected = researcher.record_extractions(graph(), {
            "source_id": source_id, "model": "mcp-agent",
            "claims": [{"belief": belief_id, "vendor": vendor_id, "claim": claim,
                        "quote": quote, "reasoning": reasoning}]})
        return {"recorded": not rejected, "rejected": rejected}

    @server.tool(annotations=WRITES)
    def record_inference(belief_id: str, claim: str, premises: list[str], reasoning: str,
                         vendor_id: str | None = None) -> dict:
        """Record a conclusion drawn from existing beliefs. List as premises the
        ids of ALL beliefs it depends on; it stays supported only while all of
        them are."""
        rejected = researcher.record_inferences(graph(), {
            "model": "mcp-agent",
            "inferences": [{"belief": belief_id, "vendor": vendor_id, "claim": claim,
                            "premises": premises, "reasoning": reasoning}]})
        return {"recorded": not rejected, "rejected": rejected}

    @server.tool(annotations=WRITES)
    def propose_purchase_order(vendor_id: str, quantity: int, unit_price: float,
                               premises: list[str], reasoning: str) -> dict:
        """Draft a purchase order justified by supported beliefs (cite their
        ids as premises, including the requirements you follow) and submit it
        to the action gate. Returns the gate's verdict. You cannot approve it."""
        g = graph()
        order_id = buyer.next_order_id(g)
        result = buyer.record_plan(g, {"model": "mcp-agent", "purchase_order": {
            "id": order_id, "vendor": vendor_id, "quantity": quantity,
            "unit_price": unit_price, "premises": premises, "reasoning": reasoning}})
        v = result["verdict"]
        return {"order_id": result["order"], "rejected": result["rejected"],
                "outcome": v.outcome if v else None, "state": v.state if v else None,
                "reasons": v.reasons if v else []}

    return server


server = create_server()

if __name__ == "__main__":
    server.run("stdio")
