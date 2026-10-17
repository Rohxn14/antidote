# tests/test_repair.py
"""Preview on a copy, stale-preview rejection, apply + verify + audit trail."""
import pytest

from app import gate, memory, repair, support
from app.db import get_db
from app.schema import BLOCKED, DECIDED, EXTRACTION, QUARANTINED, TRUSTED, UNVERIFIED
from tests.builders import belief, justify, source, trusted


def _extract(g, jid, supports, src):
    memory.add_justification(g, jid, supports=supports, premises=[src],
                             kind=EXTRACTION, reasoning="stated on the page",
                             quote=f"quote for {supports}")


@pytest.fixture
def story(g):
    """A poisoned vendor page, a trusted registry, a clean second vendor."""
    source(g, "apex_page", UNVERIFIED)
    trusted(g, "registry")
    source(g, "bolt_page", UNVERIFIED)
    for b in ("apex_cert", "apex_price", "apex_makes_servos", "bolt_price"):
        belief(g, b)
    _extract(g, "j_cert", "apex_cert", "apex_page")
    _extract(g, "j_price", "apex_price", "apex_page")
    _extract(g, "j_makes_page", "apex_makes_servos", "apex_page")
    _extract(g, "j_makes_registry", "apex_makes_servos", "registry")  # independent
    _extract(g, "j_bolt_price", "bolt_price", "bolt_page")
    memory.add_decision(g, "po", kind="purchase_order", summary="100 servos from Apex",
                        amount=48_000)
    justify(g, "j_po", "po", ["apex_cert", "apex_price", "apex_makes_servos"], kind=DECIDED)
    gate.submit(g, "po")  # -> pending_approval
    return g


def test_preview_reports_blast_radius_without_touching_main(story):
    g = story
    before_rev = memory.revision(g)
    p = repair.preview(g, "apex_page")

    assert {n["id"] for n in p.lost} == {"apex_cert", "apex_price", "po"}
    assert p.survived == [{"id": "apex_makes_servos", "text": "claim apex_makes_servos",
                           "kept_by": "j_makes_registry", "kept_kind": EXTRACTION,
                           "premises": ["registry"]}]
    assert [o["id"] for o in p.orders_blocked] == ["po"]
    assert p.executed_affected == []
    # The main graph is untouched: same revision, source not quarantined.
    assert memory.revision(g) == before_rev
    assert support.status(g)["apex_cert"] is True
    assert p.graph_name in get_db().list_graphs()


def test_stale_preview_is_rejected_after_a_revision_change(story):
    g = story
    p = repair.preview(g, "apex_page")
    belief(g, "something_new")  # any write moves the revision on

    with pytest.raises(repair.StalePreview):
        repair.apply(g, p, approved_by="manager")
    assert g.ro_query("MATCH (s:Source {id:'apex_page'}) RETURN s.trust").result_set == [[UNVERIFIED]]
    assert p.graph_name not in get_db().list_graphs()


def test_apply_matches_preview_and_writes_audit_trail(story):
    g = story
    p = repair.preview(g, "apex_page")
    repair_id = repair.apply(g, p, approved_by="manager")

    assert support.status(g) == p.expected
    rows = g.ro_query("""
        MATCH (r:Repair {id: $id})-[:TARGETED]->(s:Source)
        MATCH (r)-[c:CHANGED]->(n)
        RETURN r.approved_by, s.id, s.trust, n.id, c.before, c.after ORDER BY n.id""",
        {"id": repair_id}).result_set
    assert rows == [["manager", "apex_page", QUARANTINED, n, True, False]
                    for n in ("apex_cert", "apex_price", "po")]
    assert p.graph_name not in get_db().list_graphs()
    # Approving the repair approved nothing else: the order still waits, and
    # the gate now blocks it.
    assert gate.approve(g, "po", approver="manager").state == BLOCKED


def test_executed_order_that_loses_support_is_flagged_for_a_human(story):
    g = story
    gate.approve(g, "po", approver="manager")
    gate.execute(g, "po")
    p = repair.preview(g, "apex_page")
    assert [o["id"] for o in p.executed_affected] == ["po"]
    assert p.orders_blocked == []
    repair.discard(p)


def test_quarantine_takes_mirrors_with_the_same_origin(g):
    source(g, "page", origin="vantor.example")
    source(g, "mirror", origin="vantor.example")  # a copy of the same page
    source(g, "other", origin="other.example")
    for b in ("from_page", "from_mirror", "from_other"):
        belief(g, b)
    justify(g, "j1", "from_page", ["page"])
    justify(g, "j2", "from_mirror", ["mirror"])
    justify(g, "j3", "from_other", ["other"])

    p = repair.preview(g, "page")
    assert p.sources == ["page", "mirror"]
    assert {n["id"] for n in p.lost} == {"from_page", "from_mirror"}

    repair_id = repair.apply(g, p, approved_by="manager")
    rows = g.ro_query("MATCH (:Repair {id: $id})-[:TARGETED]->(s) RETURN s.id ORDER BY s.id",
                      {"id": repair_id}).result_set
    assert rows == [["mirror"], ["page"]]
    assert support.status(g)["from_other"] is True


def test_origin_can_be_left_out(g):
    source(g, "page", origin="vantor.example")
    source(g, "mirror", origin="vantor.example")
    belief(g, "from_mirror")
    justify(g, "j", "from_mirror", ["mirror"])
    p = repair.preview(g, "page", include_origin=False)
    assert p.sources == ["page"] and p.lost == []
    repair.discard(p)


def test_preview_refuses_unknown_or_already_quarantined_sources(story):
    g = story
    with pytest.raises(ValueError):
        repair.preview(g, "nope")
    memory.set_trust(g, "apex_page", QUARANTINED)
    with pytest.raises(ValueError):
        repair.preview(g, "apex_page")
