# app/evidence.py
"""How strong is the evidence behind each belief and decision?

    unsupported            no justification holds
    unverified only        supported, but only through unverified sources
    single trusted origin  still supported by trusted sources alone, but it
                           falls if that one trusted origin is lost
    robust                 supported by trusted sources alone, even after
                           losing any single trusted origin (what the gate
                           asks of an automatic action)

Antidote cannot tell what is true. This tells you how much each conclusion
rests on sources you do not trust. It is computed on one throwaway
GRAPH.COPY with the gate's what-if queries: the real world, the trusted-only
world, and the trusted-only world minus each trusted origin in turn.
"""
from uuid import uuid4

from app import gate, support
from app.db import copy_graph
from app.schema import BELIEF, DECISION, QUARANTINED, TRUSTED, VALID

UNSUPPORTED = "unsupported"
UNVERIFIED_ONLY = "unverified only"
SINGLE_TRUSTED = "single trusted origin"
ROBUST = "robust"
LEVELS = (UNSUPPORTED, UNVERIFIED_ONLY, SINGLE_TRUSTED, ROBUST)

# Each world's answer is written onto the copy, and the level is worked out by one
# final query: FalkorDB both computes every world and combines them.
REMEMBER_REAL = f"""
MATCH (n) WHERE n:{BELIEF} OR n:{DECISION}
SET n.real_ok = coalesce(n.{VALID}, false), n.trusted_ok = false, n.weak_origin = null
"""
AFTER_TRUSTED_ONLY = f"""
MATCH (n) WHERE n:{BELIEF} OR n:{DECISION}
SET n.trusted_ok = coalesce(n.{VALID}, false)
"""
AFTER_LOSING_ORIGIN = f"""
MATCH (n) WHERE (n:{BELIEF} OR n:{DECISION})
  AND n.trusted_ok = true AND coalesce(n.{VALID}, false) = false AND n.weak_origin IS NULL
SET n.weak_origin = $origin
"""
LEVEL_OF = f"""
MATCH (n) WHERE n:{BELIEF} OR n:{DECISION}
RETURN n.id,
       CASE WHEN NOT n.real_ok THEN '{UNSUPPORTED}'
            WHEN NOT n.trusted_ok THEN '{UNVERIFIED_ONLY}'
            WHEN n.weak_origin IS NOT NULL THEN '{SINGLE_TRUSTED}'
            ELSE '{ROBUST}' END,
       n.weak_origin
"""


def strength(g) -> dict[str, dict]:
    """{id: {"level": one of LEVELS, "weak_origin": the trusted origin whose
    loss would bring it down, or None}} for every belief and decision."""
    support.recompute(g)
    origins = [r[0] for r in g.ro_query(gate.TRUSTED_ORIGINS, {"trusted": TRUSTED}).result_set]

    copy = copy_graph(g, f"{g.name}_evidence_{uuid4().hex[:8]}")
    try:
        copy.query(REMEMBER_REAL)  # the real world, as computed on the main graph
        copy.query(gate.REMEMBER_TRUST)

        def world(removed) -> None:
            copy.query(gate.SET_SCENARIO, {"trusted": TRUSTED, "quarantined": QUARANTINED,
                                           "removed": list(removed)})
            support.recompute(copy)

        world([])
        copy.query(AFTER_TRUSTED_ONLY)
        for origin in origins:
            world([origin])
            copy.query(AFTER_LOSING_ORIGIN, {"origin": origin})
        rows = copy.ro_query(LEVEL_OF).result_set
    finally:
        copy.delete()
    return {node_id: {"level": level, "weak_origin": weak} for node_id, level, weak in rows}
