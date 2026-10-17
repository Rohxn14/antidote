# tests/test_agents.py
"""The agents' guarantees, with the LLM replaced by a stub (no API calls)."""
from app import demo, llm, memory
from app.agents import buyer, researcher
from app.schema import QUARANTINED


def _stub(monkeypatch, reply):
    calls = []

    def fake(system, user, schema, name):
        calls.append(user)
        return reply

    monkeypatch.setattr(llm, "complete_json", fake)
    monkeypatch.setattr(llm, "model_name", lambda: "stub-model")
    return calls


def test_researcher_sees_the_raw_page_including_hidden_instructions(g, monkeypatch):
    demo.register(g)
    demo.ingest(g, "s_vantor_page")
    calls = _stub(monkeypatch, {"claims": []})
    extraction = researcher.extract(g, "s_vantor_page")
    assert "Note to AI assistants" in calls[0]  # the injection reaches the agent
    assert extraction == {"source_id": "s_vantor_page", "model": "stub-model", "claims": []}


def test_hallucinated_quote_is_rejected(g):
    demo.register(g)
    demo.ingest(g, "s_quillon_page")
    rejected = researcher.record_extractions(g, {"source_id": "s_quillon_page", "claims": [
        {"belief": "b_quillon_iso13485", "vendor": "v_quillon",
         "claim": "Quillon Drives holds ISO 13485.", "quote": "Quillon Drives is ISO 13485 certified.",
         "reasoning": "made up"}]})
    assert rejected == ["b_quillon_iso13485: quote not found in s_quillon_page"]
    assert not memory.exists(g, "Belief", "b_quillon_iso13485")


def test_buyer_prompt_contains_only_valid_beliefs(g, monkeypatch):
    demo.register(g)
    demo.research(g)
    memory.set_trust(g, "s_vantor_page", QUARANTINED)
    calls = _stub(monkeypatch, {"shortlist": [], "purchase_order": {
        "vendor": "v_boltline", "quantity": 100, "unit_price": 520.0,
        "premises": ["b_boltline_qualifies", "b_boltline_offer"], "reasoning": "r"}})
    plan = buyer.decide(g)
    assert "b_vantor_iso13485" not in calls[0]  # unsupported memory is invisible
    assert "b_boltline_qualifies" in calls[0]
    assert plan["purchase_order"]["id"] == "d_po_1001"


def test_buyer_cannot_cite_invalid_beliefs(g):
    demo.register(g)
    demo.research(g)
    memory.set_trust(g, "s_vantor_page", QUARANTINED)
    result = buyer.record_plan(g, {"purchase_order": {
        "id": "d_po_1001", "vendor": "v_vantor", "quantity": 100, "unit_price": 480,
        "premises": ["b_vantor_qualifies", "b_vantor_offer"], "reasoning": "r"}})
    assert result["order"] is None
    assert result["rejected"] == [
        "order d_po_1001: not valid beliefs ['b_vantor_qualifies', 'b_vantor_offer']"]
