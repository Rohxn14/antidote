# tests/test_scenario.py
"""The Playground: every example world loads and teaches what it says."""
import pytest

from app import gate, memory, repair, scenario, support

EXAMPLES = dict(scenario.examples())


def load(g, name):
    return scenario.load(g, EXAMPLES[name])


def test_every_example_loads_cleanly(g):
    for name in EXAMPLES:
        notes = load(g, name)
        if name != "4_agent_checks":
            assert notes == [], name


def test_and_inside_or_across(g):
    load(g, "1_and_or")
    p = repair.preview(g, "s_blog")
    assert {n["id"] for n in p.lost} == {"b_cheap", "b_good_deal", "d_po_acme"}
    assert [(s["id"], s["premises"]) for s in p.survived] == [("b_certified", ["s_registry"])]
    repair.discard(p)


def test_loops_fall_with_their_root_and_come_back(g):
    load(g, "2_loops")
    s = support.status(g)
    assert s["b_a"] and s["b_b"] and not s["b_c"] and not s["b_d"]
    repair.apply(g, repair.preview(g, "s_rumour"), approved_by="me")
    s = support.status(g)
    assert not s["b_a"] and not s["b_b"]
    memory.set_trust(g, "s_rumour", "unverified")  # lift the quarantine
    s = support.status(g)
    assert s["b_a"] and s["b_b"]


def test_what_the_gate_lets_through(g):
    load(g, "3_gate")
    outcomes = {o: gate.submit(g, o) for o in
                ("d_po_auto", "d_po_copies", "d_po_vendor", "d_po_big", "d_po_final")}
    assert outcomes["d_po_auto"].outcome == gate.AUTO
    assert outcomes["d_po_copies"].reasons == ["depends on a single trusted origin: registry"]
    assert outcomes["d_po_vendor"].reasons == ["not supported by trusted sources alone"]
    assert outcomes["d_po_big"].reasons == ["amount $20,000 is at or above $5,000"]
    assert outcomes["d_po_final"].reasons == ["not reversible"]
    p = repair.preview(g, "s_registry")
    assert p.sources == ["s_registry", "s_registry_mirror"]
    assert {n["id"] for n in p.lost} == {"b_cert_copies", "d_po_copies"}
    assert [s["id"] for s in p.survived] == ["b_cert"]  # through the audit
    repair.discard(p)


def test_agent_checks_refuse_laundering_and_fake_quotes(g):
    notes = load(g, "4_agent_checks")
    assert notes == [
        "b_acme_iso13485: the claim states ['13485'], which its quote does not",
        "b_acme_price: quote not found in s_acme_page",
    ]
    s = support.status(g)
    assert s["b_zenith_iso13485"] and not s["b_acme_iso13485"] and not s["b_acme_price"]


@pytest.mark.parametrize("spec, message", [
    ({"sources": [{"id": "blog"}]}, "must look like"),
    ({"sources": [{"id": "s_a"}, {"id": "s_a"}]}, "repeated"),
    ({"beliefs": [{"id": "b_x", "because": [["s_missing"]]}]}, "unknown premises"),
    ({"beliefs": [{"id": "b_x", "because": [["b_x"]]}]}, "cannot cite its own conclusion"),
    ({"decisions": [{"id": "d_po", "kind": "purchase_order"}]}, "positive amount"),
    ({"sources": [{"id": "s_a", "trust": "very"}]}, "trust must be"),
])
def test_mistakes_are_caught_before_anything_is_written(g, spec, message):
    load(g, "2_loops")
    with pytest.raises(scenario.ScenarioError, match=message):
        scenario.load(g, spec)
    assert memory.exists(g, "Belief", "b_a")  # the previous world is untouched
