# tests/test_demo.py
"""The whole demo story, end to end, on the test graph."""
from app import demo, support
from app.schema import BLOCKED, PENDING_APPROVAL, AUTHORIZED

VANTOR_LOST = {"b_vantor_offer", "b_vantor_iso13485", "b_vantor_only_certified",
               "b_vantor_qualifies", "d_shortlist_vantor", "d_po_1001"}


def test_full_story(g):
    # Act 1: normal work.
    result = demo.seed(g)
    assert result["rejected"] == []
    assert result["shortlisted"] == ["d_shortlist_vantor", "d_shortlist_boltline",
                                     "d_shortlist_ferrocraft"]
    assert result["verdict"].state == PENDING_APPROVAL
    before = support.status(g)
    assert all(before[n] for n in VANTOR_LOST)  # the poison is believed

    # Detection flags only the poisoned page.
    assert {f.source_id for f in demo.detect(g)} == {demo.POISONED}

    # Preview: Vantor's page-only beliefs and decisions fall; the registry
    # keeps "Vantor manufactures servo actuators" alive.
    p = demo.preview(g)
    assert {n["id"] for n in p.lost} == VANTOR_LOST
    assert [(s["id"], s["kept_by"]) for s in p.survived] == [
        ("b_vantor_makes_servos", "j_vantor_makes_servos__s_registry")]
    assert [o["id"] for o in p.orders_blocked] == [demo.FIRST_ORDER]

    # Repair: surgical, everything else untouched.
    demo.approve_repair(g, p)
    after = support.status(g)
    changed = {k for k in before if not k.startswith("j_") and before[k] != after[k]}
    assert changed == VANTOR_LOST | {demo.POISONED}

    # Climax: the human approves the poisoned order; the gate still blocks it.
    assert demo.approve_order(g, demo.FIRST_ORDER).state == BLOCKED

    # The Buyer re-decides on clean memory.
    result = demo.redecide(g)
    assert result["rejected"] == []
    assert result["verdict"].state == PENDING_APPROVAL
    assert demo.approve_order(g, demo.SECOND_ORDER).state == AUTHORIZED


def test_seed_if_empty_detection(g):
    assert not demo.is_seeded(g)
    demo.seed(g)
    assert demo.is_seeded(g)
