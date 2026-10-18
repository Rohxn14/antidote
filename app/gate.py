# app/gate.py
"""The action gate: the last check before a purchase order moves forward.

It runs at submit, approve and execute time, always against the CURRENT
graph: it recomputes support first and never trusts an earlier answer.

    not valid                                    -> blocked
    amount >= AUTO_MAX_AMOUNT, or not reversible,
    or not robust to losing a trusted origin      -> needs a human approval
    otherwise                                     -> may proceed automatically

A human approval can accept the stakes policy, but it can never override
missing support: an order with no valid justification is blocked even when
someone approves it.

Order states: draft -> pending_approval -> authorized -> executed, or blocked.
"""
from dataclasses import dataclass, field
from itertools import combinations
from uuid import uuid4

from app import memory, support
from app.db import copy_graph
from app.config import AUTO_MAX_AMOUNT, MIN_INDEPENDENT_TRUSTED_ROOTS
from app.schema import (AUTHORIZED, BELIEF, BLOCKED, DECISION, DRAFT, EXECUTED,
                        JUSTIFICATION, PENDING_APPROVAL, PREMISE, PURCHASE_ORDER,
                        QUARANTINED, SOURCE, SUPPORTS, TRUSTED, VALID)

BLOCK = "blocked"
NEEDS_APPROVAL = "needs_approval"
AUTO = "auto"
HELD = "held"  # it rests on a document under review (e.g. a security alert): not yet


class GateError(Exception):
    """An action was attempted from the wrong state."""


@dataclass
class Verdict:
    decision_id: str
    outcome: str                       # BLOCK, NEEDS_APPROVAL or AUTO
    reasons: list[str] = field(default_factory=list)
    state: str | None = None           # the order's state after the action


READ_DECISION = f"""
MATCH (d:{DECISION} {{id: $id}})
RETURN d.kind, d.amount, d.reversible, d.state, d.{VALID} = true, d.approved_by
"""

# What a node rests on, one level per query: the premises of the reasons for the
# nodes found so far. (A reason points at its premises and at its conclusion, so the
# way down alternates edge directions; walked in rounds, like support.recompute.)
ONE_LEVEL_DOWN = f"""
MATCH (t)<-[:{SUPPORTS}]-(:{JUSTIFICATION})-[:{PREMISE}]->(p)
WHERE t.id IN $frontier
RETURN DISTINCT p.id
"""

# The premises of an order's reasons that no longer hold.
INVALID_PREMISES = f"""
MATCH (:{DECISION} {{id: $id}})<-[:{SUPPORTS}]-(:{JUSTIFICATION})-[:{PREMISE}]->(b:{BELIEF})
WHERE coalesce(b.{VALID}, false) = false
RETURN DISTINCT b.id, b.claim
ORDER BY b.id
"""

# Which of these ids are documents, with their trust.
DOCUMENTS_AMONG = f"""
MATCH (s:{SOURCE}) WHERE s.id IN $ids
RETURN s.id, s.title, s.trust
ORDER BY s.title
"""

TRUSTED_ORIGINS = f"""
MATCH (s:{SOURCE}) WHERE s.trust = $trusted
RETURN DISTINCT s.origin ORDER BY s.origin
"""

# What-if worlds are built on a throwaway copy. We remember each source's real
# trust once, then each scenario rewrites trust from it: only trusted sources
# count as roots, minus the origins being removed in this scenario.
REMEMBER_TRUST = f"MATCH (s:{SOURCE}) SET s.real_trust = s.trust"
SET_SCENARIO = f"""
MATCH (s:{SOURCE})
SET s.trust = CASE WHEN s.real_trust = $trusted AND NOT (s.origin IN $removed)
                   THEN $trusted ELSE $quarantined END
"""


def _read(g, decision_id: str) -> dict:
    rows = g.ro_query(READ_DECISION, {"id": decision_id}).result_set
    if not rows:
        raise GateError(f"decision {decision_id!r} not found")
    kind, amount, reversible, state, valid, approved_by = rows[0]
    return {"kind": kind, "amount": amount, "reversible": reversible,
            "state": state, "valid": bool(valid), "approved_by": approved_by}


def trusted_root_gap(g, decision_id: str) -> str | None:
    """None if the decision stays valid when only trusted sources count AND
    any (MIN_INDEPENDENT_TRUSTED_ROOTS - 1) trusted origins are removed.
    Otherwise, the reason it is not robust. Runs on a throwaway graph copy."""
    k = MIN_INDEPENDENT_TRUSTED_ROOTS
    if k <= 0:
        return None
    origins = [row[0] for row in g.ro_query(TRUSTED_ORIGINS, {"trusted": TRUSTED}).result_set]
    # () is the baseline: trusted sources only, nothing removed. Origins not
    # behind this decision simply never change its validity.
    scenarios = [()] + [c for c in combinations(origins, k - 1) if c]

    copy = copy_graph(g, f"{g.name}_whatif_{uuid4().hex[:8]}")
    try:
        copy.query(REMEMBER_TRUST)
        for removed in scenarios:
            copy.query(SET_SCENARIO, {"trusted": TRUSTED, "quarantined": QUARANTINED,
                                      "removed": list(removed)})
            support.recompute(copy)
            if not _read(copy, decision_id)["valid"]:
                if not removed:
                    return "not supported by trusted sources alone"
                return "depends on a single trusted origin: " + ", ".join(removed)
        return None
    finally:
        copy.delete()


def foundations(g, node_id: str) -> set[str]:
    """Every node `node_id` rests on, through any chain of reasons (cycle-safe)."""
    seen: set[str] = set()
    frontier = [node_id]
    while frontier:
        rows = g.ro_query(ONE_LEVEL_DOWN, {"frontier": frontier}).result_set
        frontier = [r[0] for r in rows if r[0] not in seen]
        seen.update(frontier)
    return seen


def _documents(g, ids) -> list[tuple[str, str, str]]:
    return [tuple(r) for r in g.ro_query(DOCUMENTS_AMONG, {"ids": sorted(ids)}).result_set]


def lost_support(g, decision_id: str) -> list[str]:
    """Why a decision is not valid: one sentence per premise that no longer holds,
    naming the distrusted documents it rested on."""
    reasons = []
    for fact_id, claim in g.ro_query(INVALID_PREMISES, {"id": decision_id}).result_set:
        distrusted = [t for _, t, trust in _documents(g, foundations(g, fact_id)) if trust == QUARANTINED]
        if distrusted:
            verb = "is" if len(distrusted) == 1 else "are"
            reasons.append(f"“{claim}” no longer holds: it rested on "
                           f"{' and '.join(distrusted)}, which {verb} no longer trusted")
        else:
            reasons.append(f"“{claim}” no longer holds")
    return reasons or ["no justification holds on the current graph"]


def held_by(g, decision_id: str, under_review) -> list[dict]:
    """The documents under review (not yet distrusted) that this decision rests on."""
    review = set(under_review)
    if not review:
        return []
    return [{"id": i, "title": t} for i, t, trust in _documents(g, foundations(g, decision_id) & review)
            if trust != QUARANTINED]


def _hold(decision_id: str, held: list[dict], state: str) -> Verdict:
    titles = " and ".join(h["title"] for h in held)
    return Verdict(decision_id, HELD, [f"it rests on {titles}, which is under review"], state=state)


def evaluate(g, decision_id: str) -> Verdict:
    """Classify an order against the current graph. Changes nothing but the
    computed cache."""
    support.recompute(g)
    d = _read(g, decision_id)
    if not d["valid"]:
        return Verdict(decision_id, BLOCK, lost_support(g, decision_id))
    reasons = []
    if d["amount"] is not None and d["amount"] >= AUTO_MAX_AMOUNT:
        reasons.append(f"amount ${d['amount']:,.0f} is at or above ${AUTO_MAX_AMOUNT:,}")
    if not d["reversible"]:
        reasons.append("not reversible")
    if not reasons:  # the what-if test only matters if nothing else requires a human
        gap = trusted_root_gap(g, decision_id)
        if gap:
            reasons.append(gap)
    return Verdict(decision_id, NEEDS_APPROVAL if reasons else AUTO, reasons)


def _require_order(g, decision_id: str, allowed_states) -> dict:
    d = _read(g, decision_id)
    if d["kind"] != PURCHASE_ORDER:
        raise GateError(f"{decision_id!r} is a {d['kind']}, not a purchase order")
    if d["state"] not in allowed_states:
        raise GateError(f"{decision_id!r} is {d['state']}; expected one of {list(allowed_states)}")
    return d


def _move(g, verdict: Verdict, state: str, approved_by: str | None = None) -> Verdict:
    memory.set_decision_state(g, verdict.decision_id, state,
                              note="; ".join(verdict.reasons) or None,
                              approved_by=approved_by)
    verdict.state = state
    return verdict


def submit(g, decision_id: str) -> Verdict:
    """The Buyer submits a draft (or re-submits a blocked) purchase order."""
    _require_order(g, decision_id, (DRAFT, BLOCKED))
    verdict = evaluate(g, decision_id)
    next_state = {BLOCK: BLOCKED, NEEDS_APPROVAL: PENDING_APPROVAL, AUTO: AUTHORIZED}
    return _move(g, verdict, next_state[verdict.outcome])


def approve(g, decision_id: str, approver: str, under_review=()) -> Verdict:
    """A human approves a pending order. This is the PURCHASE approval; it is
    separate from approving a memory repair and never implied by it.

    `under_review`: documents a person must deal with first (e.g. flagged by the
    security scan). An order resting on one of them is held, not approved."""
    _require_order(g, decision_id, (PENDING_APPROVAL,))
    verdict = evaluate(g, decision_id)
    if verdict.outcome == BLOCK:
        return _move(g, verdict, BLOCKED)
    held = held_by(g, decision_id, under_review)
    if held:
        return _hold(decision_id, held, PENDING_APPROVAL)
    return _move(g, verdict, AUTHORIZED, approved_by=approver)


def recheck(g, decision_id: str) -> Verdict:
    """After the memory changed (a repair): an open order that lost its support is
    blocked now, before anyone tries to approve or place it. Others are untouched."""
    d = _require_order(g, decision_id, (DRAFT, PENDING_APPROVAL, AUTHORIZED))
    verdict = evaluate(g, decision_id)
    if verdict.outcome == BLOCK:
        return _move(g, verdict, BLOCKED)
    verdict.state = d["state"]
    return verdict


def execute(g, decision_id: str, under_review=()) -> Verdict:
    """Execute an authorized order, re-checking support one last time."""
    d = _require_order(g, decision_id, (AUTHORIZED,))
    verdict = evaluate(g, decision_id)
    if verdict.outcome == BLOCK:
        return _move(g, verdict, BLOCKED)
    held = held_by(g, decision_id, under_review)
    if held:
        return _hold(decision_id, held, AUTHORIZED)
    if verdict.outcome == NEEDS_APPROVAL and not d["approved_by"]:
        # Auto-authorized earlier, but it no longer qualifies: ask a human.
        return _move(g, verdict, PENDING_APPROVAL)
    return _move(g, verdict, EXECUTED)
