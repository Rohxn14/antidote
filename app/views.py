# app/views.py
"""Read-only queries for the UI and the MCP tools. Nothing here writes."""
from app.schema import (ABOUT, AGENT, AUTHORED, BELIEF, CHANGED, DECISION, HOLDS,
                        JUSTIFICATION, PREMISE, REPAIR, SOURCE, SUPPORTS, TARGETED,
                        VALID, VENDOR)

NODES = f"""
MATCH (n) WHERE n:{SOURCE} OR n:{BELIEF} OR n:{DECISION} OR n:{JUSTIFICATION}
OPTIONAL MATCH (n)-[:{ABOUT}]->(v:{VENDOR})
RETURN n.id, labels(n)[0], coalesce(n.claim, n.summary, n.title, n.reasoning),
       coalesce(n.{VALID}, n.{HOLDS}, false), n.trust, n.kind, n.state, collect(v.id)
"""

EDGES = f"""
MATCH (j:{JUSTIFICATION})-[r]->(x)
RETURN j.id, type(r), x.id
"""

# One level of the "why?" tree: the justifications for a node, each with its
# author and premises. The UI walks it level by level (cycles are cut there).
WHY = f"""
MATCH (n) WHERE n.id = $id AND (n:{BELIEF} OR n:{DECISION})
MATCH (n)<-[:{SUPPORTS}]-(j:{JUSTIFICATION})
OPTIONAL MATCH (a:{AGENT})-[:{AUTHORED}]->(j)
OPTIONAL MATCH (j)-[:{PREMISE}]->(p)
RETURN j.id, j.kind, coalesce(j.{HOLDS}, false), j.reasoning, j.quote, j.model,
       a.name, collect(p.id)
ORDER BY j.id
"""

NODE = f"""
MATCH (n) WHERE n.id = $id
RETURN labels(n)[0], coalesce(n.claim, n.summary, n.title), coalesce(n.{VALID}, false),
       n.trust, n.uri
"""

DECISIONS = f"""
MATCH (d:{DECISION})
OPTIONAL MATCH (d)-[:{ABOUT}]->(v:{VENDOR})
RETURN d.id, d.kind, d.summary, d.amount, d.state, coalesce(d.{VALID}, false),
       d.note, d.approved_by, v.name
ORDER BY d.kind DESC, d.id
"""

SOURCES = f"""
MATCH (s:{SOURCE})
RETURN s.id, s.title, s.trust, s.origin, coalesce(s.{VALID}, false), s.uri
ORDER BY s.id
"""

REPAIRS = f"""
MATCH (r:{REPAIR})-[:{TARGETED}]->(s:{SOURCE})
OPTIONAL MATCH (r)-[c:{CHANGED}]->(n)
RETURN r.id, r.approved_by, r.revision, s.id, s.title, collect(n.id)
ORDER BY r.revision
"""

COUNTS = f"""
MATCH (n) WHERE n:{BELIEF} OR n:{DECISION}
RETURN labels(n)[0], coalesce(n.{VALID}, false), count(n)
"""


def nodes(g) -> list[dict]:
    return [{"id": i, "label": label, "text": text, "ok": ok, "trust": trust,
             "kind": kind, "state": state, "vendors": vendors}
            for i, label, text, ok, trust, kind, state, vendors in g.ro_query(NODES).result_set]


def edges(g) -> list[tuple[str, str, str]]:
    return [tuple(row) for row in g.ro_query(EDGES).result_set]


def node(g, node_id: str) -> dict | None:
    rows = g.ro_query(NODE, {"id": node_id}).result_set
    if not rows:
        return None
    label, text, ok, trust, uri = rows[0]
    return {"id": node_id, "label": label, "text": text, "ok": ok, "trust": trust, "uri": uri}


def why(g, node_id: str, depth: int = 6, _seen=None) -> dict:
    """The support tree of a belief or decision: its justifications, their
    premises, and recursively the premises' own justifications."""
    seen = _seen if _seen is not None else set()
    tree = node(g, node_id) or {"id": node_id}
    tree["justifications"] = []
    if node_id in seen or depth == 0:
        tree["cut"] = True  # already shown above (a cycle) or too deep
        return tree
    seen = seen | {node_id}
    for jid, kind, holds, reasoning, quote, model, author, premises in g.ro_query(
            WHY, {"id": node_id}).result_set:
        tree["justifications"].append({
            "id": jid, "kind": kind, "holds": holds, "reasoning": reasoning,
            "quote": quote, "model": model, "author": author,
            "premises": [why(g, p, depth - 1, seen) if not p.startswith("s_")
                         else (node(g, p) or {"id": p}) for p in premises]})
    return tree


def decisions(g) -> list[dict]:
    return [{"id": i, "kind": k, "summary": s, "amount": a, "state": st, "valid": v,
             "note": n, "approved_by": ab, "vendor": vn}
            for i, k, s, a, st, v, n, ab, vn in g.ro_query(DECISIONS).result_set]


def sources(g) -> list[dict]:
    return [{"id": i, "title": t, "trust": tr, "origin": o, "valid": v, "uri": u}
            for i, t, tr, o, v, u in g.ro_query(SOURCES).result_set]


def repairs(g) -> list[dict]:
    return [{"id": i, "approved_by": a, "revision": r, "source": s, "title": t, "changed": c}
            for i, a, r, s, t, c in g.ro_query(REPAIRS).result_set]


def counts(g) -> dict[tuple[str, bool], int]:
    return {(label, ok): n for label, ok, n in g.ro_query(COUNTS).result_set}


QUERIES = {"nodes": NODES, "edges": EDGES, "why": WHY, "decisions": DECISIONS,
           "repairs": REPAIRS}
