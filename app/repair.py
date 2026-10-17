# app/repair.py
"""Surgical repair: quarantine one source, previewed on a copy first.

1. preview(): copy the main graph, quarantine the source ON THE COPY,
   recompute there, and diff before/after with Cypher on the copy.
2. A human reviews the preview and approves the repair. This approval is
   about memory only; it never approves a purchase.
3. apply(): reject the preview if the main graph changed since it was made
   (Meta.revision), quarantine on the main graph, recompute, verify the
   result matches the preview, write the Repair audit record, drop the copy.

Operations are sequential; we do not claim consistency under concurrent writers.
"""
from dataclasses import dataclass, field

from app import memory, support
from app.db import drop_graph
from app.schema import (AUTHORIZED, BELIEF, DECISION, DRAFT, EXECUTED, HOLDS,
                        JUSTIFICATION, PENDING_APPROVAL, PREMISE, PURCHASE_ORDER,
                        QUARANTINED, SOURCE, SUPPORTS, VALID)

OPEN_STATES = [DRAFT, PENDING_APPROVAL, AUTHORIZED]


class StalePreview(Exception):
    """The main graph changed after the preview was made; regenerate it."""


class PreviewMismatch(Exception):
    """Applying the repair did not produce the previewed result."""


@dataclass
class Preview:
    source_id: str
    base_revision: int
    graph_name: str
    lost: list[dict] = field(default_factory=list)      # lose all support
    survived: list[dict] = field(default_factory=list)  # lose a reason, keep another
    orders_blocked: list[dict] = field(default_factory=list)   # open orders the gate will stop
    executed_affected: list[dict] = field(default_factory=list)  # too late: needs a human
    expected: dict[str, bool] = field(default_factory=dict)    # every flag after the repair


# --- Cypher on the preview copy ------------------------------------------------------
SNAPSHOT_CONCLUSIONS = f"""
MATCH (n) WHERE n:{BELIEF} OR n:{DECISION}
SET n.was_valid = coalesce(n.{VALID}, false)
"""

SNAPSHOT_JUSTIFICATIONS = f"""
MATCH (j:{JUSTIFICATION})
SET j.was_holding = coalesce(j.{HOLDS}, false)
"""

LOST = f"""
MATCH (n) WHERE (n:{BELIEF} OR n:{DECISION})
  AND n.was_valid = true AND n.{VALID} = false
RETURN n.id, labels(n)[0], coalesce(n.claim, n.summary), n.kind, n.state, n.amount
ORDER BY n.id
"""

# Conclusions that lost at least one reason but are still valid, with the
# justifications that still hold them up (and those justifications' premises).
SURVIVED = f"""
MATCH (gone:{JUSTIFICATION})-[:{SUPPORTS}]->(n)
WHERE gone.was_holding = true AND gone.{HOLDS} = false AND n.{VALID} = true
MATCH (kept:{JUSTIFICATION})-[:{SUPPORTS}]->(n)
WHERE kept.{HOLDS} = true
MATCH (kept)-[:{PREMISE}]->(p)
RETURN n.id, coalesce(n.claim, n.summary), kept.id, kept.kind, collect(DISTINCT p.id)
ORDER BY n.id, kept.id
"""

SOURCE_TRUST = f"MATCH (s:{SOURCE} {{id: $id}}) RETURN s.trust"


def preview(g, source_id: str) -> Preview:
    """Show what quarantining `source_id` would change, without changing it."""
    rows = g.ro_query(SOURCE_TRUST, {"id": source_id}).result_set
    if not rows:
        raise ValueError(f"source {source_id!r} not found")
    if rows[0][0] == QUARANTINED:
        raise ValueError(f"source {source_id!r} is already quarantined")

    support.recompute(g)  # make sure the main graph's cache is fresh first
    base = memory.revision(g)
    name = f"{g.name}_preview_{base}"
    drop_graph(name)
    copy = g.copy(name)

    copy.query(SNAPSHOT_CONCLUSIONS)
    copy.query(SNAPSHOT_JUSTIFICATIONS)
    memory.set_trust(copy, source_id, QUARANTINED)  # on the copy, with recompute

    p = Preview(source_id=source_id, base_revision=base, graph_name=name,
                expected=support.status(copy))
    for node_id, label, text, kind, state, amount in copy.ro_query(LOST).result_set:
        item = {"id": node_id, "label": label, "text": text, "kind": kind,
                "state": state, "amount": amount}
        p.lost.append(item)
        if kind == PURCHASE_ORDER and state in OPEN_STATES:
            p.orders_blocked.append(item)
        elif kind == PURCHASE_ORDER and state == EXECUTED:
            p.executed_affected.append(item)
    for node_id, text, kept_id, kept_kind, premises in copy.ro_query(SURVIVED).result_set:
        p.survived.append({"id": node_id, "text": text, "kept_by": kept_id,
                           "kept_kind": kept_kind, "premises": premises})
    return p


def apply(g, p: Preview, approved_by: str) -> str:
    """Apply an approved preview to the main graph. Returns the Repair id."""
    current = memory.revision(g)
    if current != p.base_revision:
        discard(p)
        raise StalePreview(f"graph changed since the preview (revision {p.base_revision} "
                           f"-> {current}); regenerate the preview")

    memory.set_trust(g, p.source_id, QUARANTINED)  # bumps revision, recomputes
    actual = support.status(g)
    if actual != p.expected:
        diff = sorted(k for k in actual.keys() | p.expected.keys()
                      if actual.get(k) != p.expected.get(k))
        raise PreviewMismatch(f"repair result differs from preview on {diff}")

    quarantine_revision = memory.revision(g)
    repair_id = f"repair_{p.source_id}_{quarantine_revision}"
    memory.record_repair(g, repair_id, source_id=p.source_id, approved_by=approved_by,
                         quarantine_revision=quarantine_revision,
                         changes=[{"id": n["id"], "before": True, "after": False}
                                  for n in p.lost])
    drop_graph(p.graph_name)
    return repair_id


def discard(p: Preview) -> None:
    drop_graph(p.graph_name)
