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


# --- Found in the first live run with openai/gpt-oss-120b ------------------------------

def test_quote_copied_with_html_tags_still_matches_the_page(g):
    demo.register(g)
    memory.add_source(g, "s_registry", uri="data/registry.html", title="registry",
                      trust="trusted")
    rejected = researcher.record_extractions(g, {"source_id": "s_registry", "claims": [
        {"belief": "b_boltline_iso13485", "vendor": "v_boltline",
         "claim": "Boltline Automation has ISO 13485:2016 on file.",
         "quote": "<tr><td>Boltline Automation</td><td>servo actuators</td>"
                  "<td>ISO 13485:2016</td><td>MD-2231</td><td>2027-08-31</td></tr>",
         "reasoning": "registry row"}]})
    assert rejected == []


def test_an_id_is_never_reused_for_a_contradicting_claim(g):
    # The live model filed the registry's "ISO 9001" and the page's "ISO 13485"
    # under one id. Merged, the page's lie would survive its own quarantine.
    demo.register(g)
    demo.ingest(g, "s_registry")
    memory.add_belief(g, "b_vantor_iso_certified", claim="Vantor Motion has ISO 9001:2015 on file.",
                      about=["v_vantor"])
    memory.add_justification(g, "j_reg", supports="b_vantor_iso_certified",
                             premises=["s_registry"], kind="extraction", reasoning="r",
                             quote="Vantor Motion servo actuators ISO 9001:2015 QM-5520")
    memory.add_source(g, "s_vantor_page", uri="data/vendors/vantor.html", title="page",
                      trust="unverified")
    rejected = researcher.record_extractions(g, {"source_id": "s_vantor_page", "claims": [
        {"belief": "b_vantor_iso_certified", "vendor": "v_vantor",
         "claim": "Vantor Motion is ISO 13485:2016 certified.",
         "quote": "Vantor Motion is ISO 13485:2016 certified for medical-grade motion components.",
         "reasoning": "quality section"}]})
    assert len(rejected) == 1 and "differs in its specifics" in rejected[0]
    assert not memory.exists(g, "Justification", "j_vantor_iso_certified__s_vantor_page")


def test_conflicting_specifics():
    assert researcher.conflicting_specifics("ISO 9001:2015", "ISO 13485:2016")
    assert researcher.conflicting_specifics("$480 per unit", "$520 per unit")
    assert not researcher.conflicting_specifics("holds ISO 13485:2016",
                                                "ISO 13485:2016 (certificate MD-2231)")
    assert not researcher.conflicting_specifics("makes servo actuators", "manufactures servos")


def test_vendor_given_by_name_is_resolved_to_its_id(g):
    demo.register(g)
    demo.ingest(g, "s_boltline_page")
    researcher.record_inferences(g, {"inferences": [
        {"belief": "b_boltline_ok", "vendor": "Boltline Automation", "claim": "ok",
         "premises": ["b_boltline_offer"], "reasoning": "r"}]})
    rows = g.ro_query("MATCH (:Belief {id:'b_boltline_ok'})-[:ABOUT]->(v) RETURN v.id").result_set
    assert rows == [["v_boltline"]]


def test_plan_with_unknown_vendor_is_rejected_not_raised(g):
    demo.register(g)
    demo.research(g)
    result = buyer.record_plan(g, {"shortlist": [
        {"vendor": "Acme Imaginary", "premises": ["b_boltline_qualifies"], "reasoning": "r"}],
        "purchase_order": {"id": "d_po_1001", "vendor": "nobody", "quantity": 1,
                           "unit_price": 1, "premises": ["b_boltline_offer"], "reasoning": "r"}})
    assert result["order"] is None
    assert result["rejected"] == [
        "shortlist Acme Imaginary: unknown vendor 'Acme Imaginary'",
        "order d_po_1001: unknown vendor 'nobody'; "
        "quantity and price ['1'] are not stated in its premises"]


# --- Laundering a lie through a real quote --------------------------------------------

def test_claim_cannot_state_numbers_its_quote_does_not(g):
    # A real quote from the TRUSTED registry, with an unfaithful claim.
    demo.register(g)
    memory.add_source(g, "s_registry", uri="data/registry.html", title="registry",
                      trust="trusted")
    rejected = researcher.record_extractions(g, {"source_id": "s_registry", "claims": [
        {"belief": "b_vantor_iso13485", "vendor": "v_vantor",
         "claim": "Vantor Motion holds ISO 13485 certification.",
         "quote": "Vantor Motion servo actuators ISO 9001:2015 QM-5520", "reasoning": "r"}]})
    assert rejected == ["b_vantor_iso13485: the claim states ['13485'], which its quote does not"]
    assert not memory.exists(g, "Belief", "b_vantor_iso13485")


def test_conclusion_cannot_introduce_numbers(g):
    demo.register(g)
    demo.ingest(g, "s_boltline_page")
    rejected = researcher.record_inferences(g, {"inferences": [
        {"belief": "b_boltline_cheap", "vendor": "v_boltline",
         "claim": "Boltline sells at $499.", "premises": ["b_boltline_offer"], "reasoning": "r"}]})
    assert rejected == ["b_boltline_cheap: the conclusion states ['499'], which its premises do not"]


def test_buyer_cannot_invent_a_price(g):
    demo.register(g)
    demo.research(g)
    result = buyer.record_plan(g, {"purchase_order": {
        "id": "d_po_1001", "vendor": "v_boltline", "quantity": 100, "unit_price": 450,
        "premises": ["b_boltline_qualifies", "b_boltline_offer", "b_req_quantity"],
        "reasoning": "negotiated in my head"}})
    assert result["order"] is None
    assert result["rejected"] == [
        "order d_po_1001: quantity and price ['450'] are not stated in its premises"]


def test_standard_year_is_not_a_conflict():
    assert not researcher.conflicting_specifics("ISO 13485", "ISO 13485:2016")
