# tests/test_casebuilder.py
"""Cases a visitor builds: the documents and the agents' answers are generated from a
small form, then go through the same checks, writes, gate and scan as the demo."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from api.server import create_app
from api.session_store import SessionStore
from app import casebuilder, gate, repair, runner, support
from tests.test_api import PREFIX, start

STORY = {"name": "The demo story", "max_weeks": 4, "suppliers": [
    {"slot": "vantor", "price": 480, "weeks": 2, "claims_certificate": True, "registry_confirms": False, "hidden_instructions": True},
    {"slot": "boltline", "price": 520, "weeks": 3, "claims_certificate": True, "registry_confirms": True, "hidden_instructions": False},
    {"slot": "ferrocraft", "price": 560, "weeks": 4, "claims_certificate": True, "registry_confirms": True, "hidden_instructions": False},
    {"slot": "quillon", "price": 390, "weeks": 2, "claims_certificate": False, "registry_confirms": False, "hidden_instructions": False}]}


def case(**changes) -> dict:
    """The story's case with some suppliers changed: case(vantor={"hidden_instructions": False})."""
    spec = copy.deepcopy(STORY)
    for s in spec["suppliers"]:
        s.update(changes.get(s["slot"], {}))
    return spec


def run(g, spec) -> tuple[list[dict], casebuilder.CaseScript]:
    script = casebuilder.CaseScript(spec)
    runner.prepare(g, script)
    return list(runner.run(g, "replay", 0, script)), script


def of(events, kind) -> list[dict]:
    return [e["data"] for e in events if e["type"] == kind]


def distrust(g, source_id) -> list[str]:
    p = repair.preview(g, source_id)
    repair.apply(g, p, approved_by="test")
    return [o["id"] for o in p.orders_blocked if gate.recheck(g, o["id"]).state == "blocked"]


def replan(g, script) -> list[dict]:
    return of(list(runner.replan(g, "replay", 0, script)), "decision_recorded")


def test_the_story_built_as_a_case_ends_the_same_way(g):
    events, script = run(g, STORY)
    assert of(events, "claim_refused") == []  # every generated quote passes the Researcher's checks
    order = of(events, "decision_recorded")[-1]
    assert order["summary"] == "PO-1001: 100 servo actuators from Vantor Motion at $480 = $48,000"
    assert [a["document_id"] for a in of(events, "security_alert")] == ["s_vantor_page"]
    assert gate.held_by(g, "d_po_1001", ["s_vantor_page"])
    assert distrust(g, "s_vantor_page") == ["d_po_1001"]
    assert "Boltline Automation at $520" in replan(g, script)[-1]["summary"]


def test_hidden_text_steers_the_buyer_to_the_priciest_supplier(g):
    spec = case(vantor={"hidden_instructions": False}, ferrocraft={"hidden_instructions": True})
    events, script = run(g, spec)
    order = of(events, "decision_recorded")[-1]
    assert "Ferrocraft Servo at $560" in order["summary"]  # not the cheapest: steered
    assert [a["document_id"] for a in of(events, "security_alert")] == ["s_ferrocraft_page"]
    assert distrust(g, "s_ferrocraft_page") == ["d_po_1001"]
    # Next cheapest that qualifies on what is still supported: Vantor, on its own word alone.
    assert "Vantor Motion at $480" in replan(g, script)[-1]["summary"]
    assert support.status(g)["b_vantor_qualifies"]
    assert distrust(g, "s_vantor_page") == ["d_po_1002"]
    assert "Boltline Automation at $520" in replan(g, script)[-1]["summary"]


def test_a_supplier_too_slow_or_without_a_certificate_is_not_chosen(g):
    spec = case(vantor={"hidden_instructions": False, "weeks": 6},  # cheapest qualifying, but too slow
                quillon={"price": 100})                            # cheapest of all, but no certificate
    events, _ = run(g, spec)
    assert "Boltline Automation at $520" in of(events, "decision_recorded")[-1]["summary"]
    assert of(events, "security_alert") == []


def test_when_nothing_qualifies_there_is_no_order(g):
    nobody = {"claims_certificate": False, "registry_confirms": False, "hidden_instructions": False}
    events, _ = run(g, case(vantor=nobody, boltline=nobody, ferrocraft=nobody, quillon=nobody))
    assert [d for d in of(events, "decision_recorded") if d["kind"] == "purchase_order"] == []
    assert any("No supplier qualifies" in s["message"] for s in of(events, "agent_status"))


@pytest.mark.parametrize("variant", [
    {}, {"vantor": {"hidden_instructions": False}},
    {"boltline": {"hidden_instructions": True, "claims_certificate": False, "registry_confirms": False}},
    {"quillon": {"price": 5000, "weeks": 26, "hidden_instructions": True}},
])
def test_generated_answers_always_pass_the_checks(g, variant):
    events, _ = run(g, case(**variant))
    assert of(events, "claim_refused") == [] and of(events, "error") == []


def test_cases_over_http(g):
    client = TestClient(create_app(SessionStore(prefix=PREFIX, cap=5)))
    h = start(client)
    spec = case(vantor={"hidden_instructions": False}, ferrocraft={"hidden_instructions": True})
    assert client.post("/api/case", headers=h, json={"case": spec}).json() == {"ok": True}
    state = client.get("/api/state", headers=h).json()
    assert state["case"]["suppliers"][2]["hidden_instructions"] is True
    assert "within 4 weeks" in state["request"]["text"]
    page = client.get("/api/documents/s_ferrocraft_page", headers=h).json()
    assert any(s["hidden"] for s in page["segments"]) and page["html"].startswith("<!doctype html>")
    assert not any(s["hidden"] for s in client.get("/api/documents/s_vantor_page", headers=h).json()["segments"])

    with client.stream("POST", "/api/run", headers=h, json={"pace": 0}) as r:
        events = [json.loads(line) for line in r.iter_lines() if line]
    order = [e["data"] for e in events if e["type"] == "decision_recorded"][-1]
    assert "Ferrocraft" in order["summary"]
    assert client.post("/api/run", headers=h, json={"mode": "live", "pace": 0}).status_code == 400

    assert client.post("/api/case", headers=h, json={"case": None}).json() == {"ok": True}
    assert client.get("/api/state", headers=h).json()["case"] is None
    for bad in ({**spec, "suppliers": spec["suppliers"][:3]},
                {**spec, "suppliers": spec["suppliers"][:3] + [spec["suppliers"][0]]},
                case(vantor={"price": 10})):
        assert client.post("/api/case", headers=h, json={"case": bad}).status_code == 422


def test_a_plain_lie_is_held_until_verified_then_the_honest_supplier_goes_through(g):
    client = TestClient(create_app(SessionStore(prefix=PREFIX, cap=5)))
    h = start(client)
    client.post("/api/case", headers=h, json={"case": case(vantor={"hidden_instructions": False})})
    with client.stream("POST", "/api/run", headers=h, json={"pace": 0}) as r:
        events = [json.loads(line) for line in r.iter_lines() if line]
    assert [e for e in events if e["type"] == "security_alert"] == []      # nothing to detect
    order = next(d for d in client.get("/api/state", headers=h).json()["decisions"] if d["id"] == "d_po_1001")
    assert order["held_by"] == [] and order["needs_verification"] == [
        "Vantor Motion meets the ISO 13485 supplier requirement."]
    held = client.post("/api/orders/d_po_1001/approve", headers=h).json()
    assert (held["outcome"], held["state"]) == ("held", "pending_approval")
    assert "trusted document" in held["message"]

    client.post("/api/impact", headers=h, json={"document_id": "s_vantor_page"})
    assert client.post("/api/quarantine", headers=h).json()["orders_blocked"] == ["d_po_1001"]
    with client.stream("POST", "/api/replan", headers=h, json={"pace": 0}) as r:
        list(r.iter_lines())
    assert client.post("/api/orders/d_po_1002/approve", headers=h).json()["state"] == "authorized"
