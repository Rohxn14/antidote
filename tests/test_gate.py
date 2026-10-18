# tests/test_gate.py
"""The action gate: blocked / needs a human / automatic, always on the
current graph."""
import pytest

from app import gate, memory
from app.db import get_db
from app.schema import (AUTHORIZED, BLOCKED, DECIDED, EXECUTED, PENDING_APPROVAL,
                        QUARANTINED)
from tests.builders import belief, justify, source, trusted


def _order(g, premises, amount=900, reversible=True, oid="po"):
    memory.add_decision(g, oid, kind="purchase_order", summary=f"order {oid}",
                        amount=amount, reversible=reversible)
    justify(g, f"j_{oid}", oid, premises, kind=DECIDED)


def _state(g, oid="po"):
    return g.ro_query("MATCH (d:Decision {id: $id}) RETURN d.state", {"id": oid}).result_set[0][0]


def test_queued_order_whose_support_is_revoked_is_blocked(g):
    source(g, "page")
    belief(g, "cert")
    justify(g, "j_cert", "cert", ["page"])
    _order(g, ["cert"], amount=48_000)

    v = gate.submit(g, "po")
    assert (v.outcome, v.state) == (gate.NEEDS_APPROVAL, PENDING_APPROVAL)

    memory.set_trust(g, "page", QUARANTINED)  # repair happens while it waits
    v = gate.approve(g, "po", approver="manager")  # even a human approval...

    assert (v.outcome, v.state) == (gate.BLOCK, BLOCKED)  # ...cannot push it through
    assert _state(g) == BLOCKED


def test_small_reversible_order_with_two_independent_trusted_origins_is_automatic(g):
    trusted(g, "registry", origin="A")
    trusted(g, "audit", origin="B")
    belief(g, "cert")
    justify(g, "j1", "cert", ["registry"])
    justify(g, "j2", "cert", ["audit"])
    _order(g, ["cert"])

    v = gate.submit(g, "po")
    assert (v.outcome, v.state) == (gate.AUTO, AUTHORIZED)


def test_copies_of_one_claim_count_once(g):
    trusted(g, "registry", origin="A")
    trusted(g, "registry_mirror", origin="A")  # same original claim
    belief(g, "cert")
    justify(g, "j1", "cert", ["registry"])
    justify(g, "j2", "cert", ["registry_mirror"])
    _order(g, ["cert"])

    v = gate.evaluate(g, "po")
    assert v.outcome == gate.NEEDS_APPROVAL
    assert v.reasons == ["depends on a single trusted origin: A"]


def test_unverified_sources_are_not_trusted_roots(g):
    trusted(g, "registry", origin="A")
    source(g, "vendor_page", origin="B")  # unverified
    belief(g, "cert")
    justify(g, "j1", "cert", ["registry"])
    justify(g, "j2", "cert", ["vendor_page"])
    _order(g, ["cert"])
    assert gate.evaluate(g, "po").reasons == ["depends on a single trusted origin: A"]


def test_order_backed_only_by_unverified_sources_needs_a_human(g):
    source(g, "page_1")
    source(g, "page_2")
    belief(g, "cert")
    justify(g, "j1", "cert", ["page_1"])
    justify(g, "j2", "cert", ["page_2"])
    _order(g, ["cert"])
    assert gate.evaluate(g, "po").reasons == ["not supported by trusted sources alone"]


def test_needing_both_origins_is_not_redundancy(g):
    trusted(g, "registry", origin="A")
    trusted(g, "audit", origin="B")
    belief(g, "cert")
    justify(g, "j_both", "cert", ["registry", "audit"])  # A AND B
    _order(g, ["cert"])
    v = gate.evaluate(g, "po")
    assert v.outcome == gate.NEEDS_APPROVAL
    assert v.reasons[0].startswith("depends on a single trusted origin")


@pytest.mark.parametrize("amount, reversible, reason", [
    (5_000, True, "amount $5,000 is at or above $5,000"),
    (900, False, "not reversible"),
])
def test_large_or_irreversible_orders_need_a_human(g, amount, reversible, reason):
    trusted(g, "registry", origin="A")
    trusted(g, "audit", origin="B")
    belief(g, "cert")
    justify(g, "j1", "cert", ["registry"])
    justify(g, "j2", "cert", ["audit"])
    _order(g, ["cert"], amount=amount, reversible=reversible)
    v = gate.evaluate(g, "po")
    assert (v.outcome, v.reasons) == (gate.NEEDS_APPROVAL, [reason])


def test_human_approval_then_execute(g):
    source(g, "page")
    belief(g, "cert")
    justify(g, "j_cert", "cert", ["page"])
    _order(g, ["cert"], amount=48_000)
    gate.submit(g, "po")
    v = gate.approve(g, "po", approver="manager")
    assert v.state == AUTHORIZED
    assert g.ro_query("MATCH (d:Decision {id:'po'}) RETURN d.approved_by").result_set == [["manager"]]
    assert gate.execute(g, "po").state == EXECUTED


def test_execute_rechecks_support(g):
    source(g, "page")
    belief(g, "cert")
    justify(g, "j_cert", "cert", ["page"])
    _order(g, ["cert"], amount=48_000)
    gate.submit(g, "po")
    gate.approve(g, "po", approver="manager")
    memory.set_trust(g, "page", QUARANTINED)  # support lost after authorization
    assert gate.execute(g, "po").state == BLOCKED


def test_auto_authorized_order_that_loses_robustness_goes_back_to_a_human(g):
    trusted(g, "registry", origin="A")
    trusted(g, "audit", origin="B")
    belief(g, "cert")
    justify(g, "j1", "cert", ["registry"])
    justify(g, "j2", "cert", ["audit"])
    _order(g, ["cert"])
    assert gate.submit(g, "po").state == AUTHORIZED
    memory.set_trust(g, "audit", QUARANTINED)  # still valid, but one root left
    v = gate.execute(g, "po")
    assert v.state == PENDING_APPROVAL
    assert v.reasons == ["depends on a single trusted origin: A"]


def test_blocked_order_can_be_resubmitted_when_support_returns(g):
    source(g, "page")
    belief(g, "cert")
    justify(g, "j_cert", "cert", ["page"])
    _order(g, ["cert"], amount=48_000)
    memory.set_trust(g, "page", QUARANTINED)
    assert gate.submit(g, "po").state == BLOCKED
    trusted(g, "registry")
    justify(g, "j_cert_registry", "cert", ["registry"])
    assert gate.submit(g, "po").state == PENDING_APPROVAL


def test_wrong_state_or_kind_is_refused(g):
    source(g, "page")
    belief(g, "cert")
    justify(g, "j_cert", "cert", ["page"])
    _order(g, ["cert"])
    with pytest.raises(gate.GateError):
        gate.execute(g, "po")  # still a draft
    memory.add_decision(g, "short", kind="shortlist", summary="shortlist")
    with pytest.raises(gate.GateError):
        gate.submit(g, "short")


def test_what_if_copies_are_cleaned_up(g):
    trusted(g, "registry", origin="A")
    belief(g, "cert")
    justify(g, "j1", "cert", ["registry"])
    _order(g, ["cert"])
    gate.evaluate(g, "po")
    assert [n for n in get_db().list_graphs() if "whatif" in n] == []


def test_blocked_order_names_the_fact_and_the_distrusted_document(g):
    source(g, "page")
    belief(g, "cert")
    justify(g, "j_cert", "cert", ["page"])
    _order(g, ["cert"], amount=48_000)
    gate.submit(g, "po")

    memory.set_trust(g, "page", QUARANTINED)
    v = gate.evaluate(g, "po")

    assert v.outcome == gate.BLOCK
    assert v.reasons == ["“claim cert” no longer holds: it rested on page, which is no longer trusted"]


def test_approval_is_held_while_the_order_rests_on_a_document_under_review(g):
    source(g, "page")
    trusted(g, "registry")
    belief(g, "cert")
    belief(g, "price")
    justify(g, "j_cert", "cert", ["registry"])
    justify(g, "j_price", "price", ["page"])
    _order(g, ["cert", "price"], amount=48_000)
    gate.submit(g, "po")

    v = gate.approve(g, "po", approver="manager", under_review=["page"])
    assert (v.outcome, v.state) == (gate.HELD, PENDING_APPROVAL)  # nothing moved
    assert _state(g) == PENDING_APPROVAL
    assert gate.held_by(g, "po", ["page", "elsewhere"]) == [{"id": "page", "title": "page"}]

    v = gate.approve(g, "po", approver="manager", under_review=["elsewhere"])
    assert v.state == AUTHORIZED  # a flag on a document it does not rest on changes nothing


def test_recheck_blocks_an_open_order_that_lost_its_support_and_leaves_the_rest(g):
    source(g, "page")
    trusted(g, "registry")
    belief(g, "a")
    belief(g, "b")
    justify(g, "j_a", "a", ["page"])
    justify(g, "j_b", "b", ["registry"])
    _order(g, ["a"], amount=48_000, oid="po1")
    _order(g, ["b"], amount=48_000, oid="po2")
    gate.submit(g, "po1")
    gate.submit(g, "po2")

    memory.set_trust(g, "page", QUARANTINED)

    assert gate.recheck(g, "po1").state == BLOCKED
    assert gate.recheck(g, "po2").state == PENDING_APPROVAL
    assert (_state(g, "po1"), _state(g, "po2")) == (BLOCKED, PENDING_APPROVAL)
