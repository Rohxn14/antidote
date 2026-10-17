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
from app.schema import BELIEF, DECISION, QUARANTINED, TRUSTED, VALID

UNSUPPORTED = "unsupported"
UNVERIFIED_ONLY = "unverified only"
SINGLE_TRUSTED = "single trusted origin"
ROBUST = "robust"
LEVELS = (UNSUPPORTED, UNVERIFIED_ONLY, SINGLE_TRUSTED, ROBUST)

CONCLUSIONS = f"""
MATCH (n) WHERE n:{BELIEF} OR n:{DECISION}
RETURN n.id, coalesce(n.{VALID}, false)
"""


def _valid(g) -> set[str]:
    return {node_id for node_id, ok in g.ro_query(CONCLUSIONS).result_set if ok}


def strength(g) -> dict[str, dict]:
    """{id: {"level": one of LEVELS, "weak_origin": the trusted origin whose
    loss would bring it down, or None}} for every belief and decision."""
    support.recompute(g)
    real = dict(g.ro_query(CONCLUSIONS).result_set)
    origins = [r[0] for r in g.ro_query(gate.TRUSTED_ORIGINS, {"trusted": TRUSTED}).result_set]

    copy = g.copy(f"{g.name}_evidence_{uuid4().hex[:8]}")
    try:
        copy.query(gate.REMEMBER_TRUST)

        def world(removed) -> set[str]:
            copy.query(gate.SET_SCENARIO, {"trusted": TRUSTED, "quarantined": QUARANTINED,
                                           "removed": list(removed)})
            support.recompute(copy)
            return _valid(copy)

        trusted_only = world([])
        weak = {}
        for origin in origins:
            for node_id in trusted_only - world([origin]):
                weak.setdefault(node_id, origin)
    finally:
        copy.delete()

    result = {}
    for node_id, ok in real.items():
        if not ok:
            level = UNSUPPORTED
        elif node_id not in trusted_only:
            level = UNVERIFIED_ONLY
        elif node_id in weak:
            level = SINGLE_TRUSTED
        else:
            level = ROBUST
        result[node_id] = {"level": level, "weak_origin": weak.get(node_id)}
    return result
