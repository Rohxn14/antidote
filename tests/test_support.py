# tests/test_support.py
"""The support rule: AND inside a justification, OR across justifications,
least fixed point (cycles need a real root)."""
import pytest

from app import memory, support
from app.schema import QUARANTINED, TRUSTED, UNVERIFIED
from tests.builders import belief, flag, justify, source, trusted


def test_alternative_justifications_one_fails_belief_survives(g):
    source(g, "s1")
    trusted(g, "s2")
    belief(g, "b")
    justify(g, "j1", "b", ["s1"])
    justify(g, "j2", "b", ["s2"])
    assert flag(g, "b")

    memory.set_trust(g, "s1", QUARANTINED)

    assert not flag(g, "j1")
    assert flag(g, "j2")
    assert flag(g, "b")  # still supported through j2


def test_multi_premise_justification_fails_if_any_premise_fails(g):
    source(g, "s1")
    source(g, "s2")
    belief(g, "b")
    justify(g, "j", "b", ["s1", "s2"])
    assert flag(g, "b")

    memory.set_trust(g, "s2", QUARANTINED)

    assert not flag(g, "j")
    assert not flag(g, "b")


def test_cycle_without_independent_root_stays_invalid(g):
    belief(g, "a")
    belief(g, "b")
    justify(g, "j_ab", "b", ["a"])  # a -> b
    justify(g, "j_ba", "a", ["b"])  # b -> a
    assert not flag(g, "a")
    assert not flag(g, "b")


def test_cycle_loses_its_only_root_and_does_not_sustain_itself(g):
    # The case a naive "mark everything downstream invalid, keep anything that
    # still has a holding justification" approach gets wrong: after s goes,
    # a and b each still have a justification from the other.
    source(g, "s")
    belief(g, "a")
    belief(g, "b")
    justify(g, "j_sa", "a", ["s"])
    justify(g, "j_ab", "b", ["a"])
    justify(g, "j_ba", "a", ["b"])
    assert flag(g, "a") and flag(g, "b")

    memory.set_trust(g, "s", QUARANTINED)

    assert not flag(g, "a")
    assert not flag(g, "b")


def test_cycle_with_independent_valid_root_becomes_valid(g):
    trusted(g, "root")
    belief(g, "a")
    belief(g, "b")
    justify(g, "j_ab", "b", ["a"])
    justify(g, "j_ba", "a", ["b"])
    assert not flag(g, "a")

    justify(g, "j_root", "a", ["root"])  # the loop gets a real root

    assert flag(g, "a")
    assert flag(g, "b")


def test_trusted_source_added_after_repair_restores_downstream(g):
    source(g, "page")
    belief(g, "cert")
    belief(g, "best_choice")
    justify(g, "j_cert", "cert", ["page"])
    justify(g, "j_best", "best_choice", ["cert"])
    memory.add_decision(g, "po", kind="purchase_order", summary="PO", amount=900)
    justify(g, "j_po", "po", ["best_choice"], kind="decision")
    assert flag(g, "po")

    memory.set_trust(g, "page", QUARANTINED)  # the repair
    assert not flag(g, "cert") and not flag(g, "best_choice") and not flag(g, "po")

    trusted(g, "registry")  # new trusted evidence arrives later
    justify(g, "j_cert_registry", "cert", ["registry"])

    assert flag(g, "cert") and flag(g, "best_choice") and flag(g, "po")


def test_status_moves_both_ways_with_trust(g):
    source(g, "s")
    belief(g, "b")
    justify(g, "j", "b", ["s"])
    memory.set_trust(g, "s", QUARANTINED)
    assert not flag(g, "b")
    memory.set_trust(g, "s", UNVERIFIED)  # quarantine lifted
    assert flag(g, "b")


def test_deleting_a_premise_fails_closed(g):
    # Deleting evidence (instead of quarantining it) must not turn "s1 AND s2"
    # into "s1 alone": the justification remembers it needs two premises.
    source(g, "s1")
    source(g, "s2")
    belief(g, "b")
    justify(g, "j", "b", ["s1", "s2"])
    g.query("MATCH (s:Source {id: 's2'}) DETACH DELETE s")
    support.recompute(g)
    assert not flag(g, "j")
    assert not flag(g, "b")


def test_unsupported_belief_is_invalid(g):
    belief(g, "b")
    assert not flag(g, "b")


def test_long_chain_takes_one_round_per_link(g):
    source(g, "s")
    previous = "s"
    for i in range(6):
        belief(g, f"b{i}", recompute=False)
        justify(g, f"j{i}", f"b{i}", [previous], recompute=False)
        previous = f"b{i}"
    rounds = support.recompute(g)
    assert flag(g, "b5")
    assert rounds == 7  # 6 links, plus the final round that changes nothing


# --- write path ----------------------------------------------------------------

def test_justification_with_missing_premise_is_rejected_and_writes_nothing(g):
    source(g, "s")
    belief(g, "b")
    before = memory.revision(g)
    with pytest.raises(memory.WriteRejected, match="premises not found: \\['typo'\\]"):
        justify(g, "j", "b", ["s", "typo"])
    assert memory.revision(g) == before
    assert "j" not in support.status(g)


def test_justification_id_is_append_only(g):
    source(g, "s")
    belief(g, "b")
    justify(g, "j", "b", ["s"])
    with pytest.raises(memory.WriteRejected, match="already exists"):
        justify(g, "j", "b", ["s"])


def test_justification_needs_premises_and_cannot_cite_itself(g):
    belief(g, "b")
    with pytest.raises(memory.WriteRejected):
        justify(g, "j0", "b", [])
    with pytest.raises(memory.WriteRejected):
        justify(g, "j1", "b", ["b"])


def test_extraction_requires_quote(g):
    source(g, "s")
    belief(g, "b")
    with pytest.raises(memory.WriteRejected, match="quote"):
        justify(g, "j", "b", ["s"], kind="extraction")


def test_justification_with_unknown_agent_is_rejected(g):
    source(g, "s")
    belief(g, "b")
    with pytest.raises(memory.WriteRejected, match="agent 'ghost' not found"):
        memory.add_justification(g, "j", supports="b", premises=["s"],
                                 kind="inference", reasoning="r", agent="ghost")


def test_agent_authorship_is_recorded(g):
    memory.add_agent(g, "researcher", name="Researcher", role="researcher")
    source(g, "s")
    belief(g, "b")
    memory.add_justification(g, "j", supports="b", premises=["s"],
                             kind="inference", reasoning="r", agent="researcher")
    rows = g.ro_query("MATCH (:Agent {id:'researcher'})-[:AUTHORED]->(j) RETURN j.id").result_set
    assert rows == [["j"]]


def test_each_write_bumps_revision(g):
    start = memory.revision(g)
    source(g, "s")
    belief(g, "b")
    justify(g, "j", "b", ["s"])
    memory.set_trust(g, "s", QUARANTINED)
    assert memory.revision(g) == start + 4


def test_existing_belief_with_different_claim_is_rejected_untouched(g):
    memory.add_vendor(g, "v", name="V")
    memory.add_belief(g, "b", claim="original")
    with pytest.raises(memory.WriteRejected, match="different content"):
        memory.add_belief(g, "b", claim="changed", about=["v"])
    rows = g.ro_query("MATCH (b:Belief {id:'b'}) OPTIONAL MATCH (b)-[r:ABOUT]->() "
                      "RETURN b.claim, count(r)").result_set
    assert rows == [["original", 0]]


def test_belief_about_unknown_vendor_is_rejected(g):
    with pytest.raises(memory.WriteRejected, match="unknown vendors"):
        memory.add_belief(g, "b", claim="c", about=["nope"])


def test_source_trust_changes_only_through_set_trust(g):
    source(g, "s", UNVERIFIED)
    with pytest.raises(memory.WriteRejected, match="set_trust"):
        source(g, "s", TRUSTED)


def test_writes_fail_closed_without_schema(g):
    g.query("MATCH (m:Meta) DELETE m")
    with pytest.raises(memory.WriteRejected, match="ensure_schema"):
        memory.add_vendor(g, "v", name="V")


def test_ensure_schema_is_idempotent(g):
    from app.schema import INDEXES, ensure_schema
    ensure_schema(g)
    ensure_schema(g)
    rows = g.ro_query("CALL db.indexes() YIELD label, properties RETURN label, properties").result_set
    assert len({(label, p) for label, props in rows for p in props}) == len(INDEXES)
    assert g.ro_query("MATCH (m:Meta) RETURN count(m), m.revision").result_set == [[1, 0]]
