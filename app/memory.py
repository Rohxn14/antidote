# app/memory.py
"""The write path. Every change to shared memory goes through this module.

Each public write is ONE parameterized Cypher query, so it is atomic: it either
fully happens or does not happen at all. The same query bumps Meta.revision
(used to reject stale repair previews). Every write query starts with
MATCH on the Meta node, so if the schema was never set up it writes nothing.

After a write that can change support we run a full recompute
(app/support.py). Bulk loaders may pass recompute=False and call
support.recompute() once at the end.

Labels and property names come from app/schema.py via f-strings; values are
always query parameters, never pasted into the query text. The queries are
module-level constants so scripts/export_cypher.py can document all of them.
"""
from app import support
from app.schema import (ABOUT, AGENT, AGENT_ROLES, AUTHORED, BELIEF, CHANGED,
                        DECIDED, DECISION, DECISION_KINDS, DECISION_STATES,
                        DRAFT, EXTRACTION, JUSTIFICATION, JUSTIFICATION_KINDS,
                        META, META_ID, PREMISE, PURCHASE_ORDER, REPAIR, SOURCE,
                        SUPPORTS, TARGETED, TRUST_LEVELS, VALID, VENDOR)


class WriteRejected(ValueError):
    """A write was refused; nothing was written."""


# --- Queries ------------------------------------------------------------------------------

REVISION = f"MATCH (m:{META} {{id: $meta}}) RETURN m.revision"

ADD_AGENT = f"""
MATCH (m:{META} {{id: $meta}})
MERGE (a:{AGENT} {{id: $id}})
ON CREATE SET a.name = $name, a.role = $role
SET m.revision = m.revision + 1
RETURN a.id"""

ADD_VENDOR = f"""
MATCH (m:{META} {{id: $meta}})
MERGE (v:{VENDOR} {{id: $id}})
ON CREATE SET v.name = $name
SET m.revision = m.revision + 1
RETURN v.id"""

ADD_SOURCE = f"""
MATCH (m:{META} {{id: $meta}})
MERGE (s:{SOURCE} {{id: $id}})
ON CREATE SET s.uri = $uri, s.title = $title, s.trust = $trust,
              s.origin = $origin
SET m.revision = m.revision + 1
RETURN s.trust"""

SET_TRUST = f"""
MATCH (m:{META} {{id: $meta}})
MATCH (s:{SOURCE} {{id: $id}})
WITH m, s, s.trust AS before
SET s.trust = $trust, m.revision = m.revision + 1
RETURN before"""


def _guard(label: str, field: str) -> str:
    """Query prefix shared by beliefs and decisions. Writes nothing unless the
    node is new (or identical in `field`) and every ABOUT vendor exists:
    collect() skips vendors that were not found, so the sizes would differ."""
    return f"""
MATCH (m:{META} {{id: $meta}})
OPTIONAL MATCH (existing:{label} {{id: $id}})
WITH m, existing WHERE existing IS NULL OR existing.{field} = ${field}
OPTIONAL MATCH (v:{VENDOR}) WHERE v.id IN $about
WITH m, collect(v) AS vendors
WHERE size(vendors) = size($about)"""


ADD_BELIEF = _guard(BELIEF, "claim") + f"""
MERGE (b:{BELIEF} {{id: $id}})
ON CREATE SET b.claim = $claim, b.created_at = timestamp()
SET m.revision = m.revision + 1
FOREACH (v IN vendors | MERGE (b)-[:{ABOUT}]->(v))
RETURN b.id"""

ADD_DECISION = _guard(DECISION, "kind") + f"""
MERGE (d:{DECISION} {{id: $id}})
ON CREATE SET d.kind = $kind, d.summary = $summary, d.amount = $amount,
              d.reversible = $reversible, d.state = $state,
              d.created_at = timestamp()
SET m.revision = m.revision + 1
FOREACH (v IN vendors | MERGE (d)-[:{ABOUT}]->(v))
RETURN d.id"""

SET_DECISION_STATE = f"""
MATCH (m:{META} {{id: $meta}})
MATCH (d:{DECISION} {{id: $id}})
WITH m, d, d.state AS before
SET d.state = $state, d.note = $note,
    d.approved_by = coalesce($approved_by, d.approved_by),
    m.revision = m.revision + 1
RETURN before"""


def _add_justification(target: str) -> str:
    """One query: check everything, then create the justification and ALL its
    edges. The premise guard compares how many premises were found with how
    many were cited, so a typo can never create a justification with fewer
    premises (which would be easier to satisfy)."""
    return f"""
MATCH (m:{META} {{id: $meta}})
MATCH (t:{target} {{id: $supports}})
OPTIONAL MATCH (dup:{JUSTIFICATION} {{id: $id}})
WITH m, t, dup WHERE dup IS NULL
OPTIONAL MATCH (a:{AGENT} {{id: $agent}})
WITH m, t, a WHERE $agent IS NULL OR a IS NOT NULL
UNWIND $premises AS pid
OPTIONAL MATCH (ps:{SOURCE} {{id: pid}})
OPTIONAL MATCH (pb:{BELIEF} {{id: pid}})
WITH m, t, a, collect(coalesce(ps, pb)) AS found
WHERE size(found) = size($premises)
CREATE (j:{JUSTIFICATION} {{id: $id, kind: $kind, reasoning: $reasoning,
                            quote: $quote, model: $model,
                            premise_count: size($premises),
                            created_at: timestamp()}})
CREATE (j)-[:{SUPPORTS}]->(t)
FOREACH (p IN found | CREATE (j)-[:{PREMISE}]->(p))
FOREACH (x IN CASE WHEN a IS NULL THEN [] ELSE [a] END |
         CREATE (x)-[:{AUTHORED}]->(j))
SET m.revision = m.revision + 1
RETURN j.id"""


ADD_JUSTIFICATION = {BELIEF: _add_justification(BELIEF),
                     DECISION: _add_justification(DECISION)}

RECORD_REPAIR = f"""
MATCH (m:{META} {{id: $meta}})
MATCH (s:{SOURCE} {{id: $source}})
CREATE (r:{REPAIR} {{id: $id, created_at: timestamp(),
                     approved_by: $approved_by, revision: $revision}})
CREATE (r)-[:{TARGETED}]->(s)
SET m.revision = m.revision + 1
WITH r
UNWIND $changes AS c
MATCH (n {{id: c.id}}) WHERE n:{BELIEF} OR n:{DECISION}
CREATE (r)-[:{CHANGED} {{before: c.before, after: c.after}}]->(n)
RETURN count(n)"""

VALID_BELIEFS = f"""
MATCH (b:{BELIEF}) WHERE b.{VALID} = true
OPTIONAL MATCH (b)-[:{ABOUT}]->(v:{VENDOR})
WITH b, v WHERE $vendor IS NULL OR v.id = $vendor
RETURN b.id, b.claim, v.id, v.name
ORDER BY b.id"""

BELIEF_CLAIM = f"MATCH (b:{BELIEF} {{id: $id}}) RETURN b.claim"

# An agent may name a vendor by id or by its exact name (case-insensitive).
RESOLVE_VENDOR = f"""
MATCH (v:{VENDOR}) WHERE v.id = $value OR toLower(v.name) = toLower($value)
RETURN v.id ORDER BY v.id LIMIT 1"""

QUERIES = {
    "add_agent": ADD_AGENT, "add_vendor": ADD_VENDOR, "add_source": ADD_SOURCE,
    "set_trust": SET_TRUST, "add_belief": ADD_BELIEF, "add_decision": ADD_DECISION,
    "set_decision_state": SET_DECISION_STATE,
    "add_justification (for a belief)": ADD_JUSTIFICATION[BELIEF],
    "add_justification (for a decision)": ADD_JUSTIFICATION[DECISION],
    "record_repair": RECORD_REPAIR, "valid_beliefs": VALID_BELIEFS, "revision": REVISION,
    "belief_claim": BELIEF_CLAIM, "resolve_vendor": RESOLVE_VENDOR,
}


# --- Helpers --------------------------------------------------------------------------------

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WriteRejected(message)


def _write(g, query: str, **params) -> list:
    """Run a write query that starts with MATCH (m:Meta ...); return its rows."""
    return g.query(query, {"meta": META_ID, **params}).result_set


def exists(g, label: str, node_id: str) -> bool:
    rows = g.ro_query(f"MATCH (n:{label} {{id: $id}}) RETURN count(n)", {"id": node_id})
    return rows.result_set[0][0] > 0


def _unique(ids) -> list[str]:
    return list(dict.fromkeys(ids))  # de-duplicate, keep order


def revision(g) -> int:
    rows = g.ro_query(REVISION, {"meta": META_ID})
    _require(bool(rows.result_set), "graph has no Meta node; run ensure_schema() first")
    return rows.result_set[0][0]


# --- Agents and vendors (no effect on support, so no recompute) -----------------

def add_agent(g, agent_id: str, *, name: str, role: str) -> None:
    _require(role in AGENT_ROLES, f"unknown agent role {role!r}")
    rows = _write(g, ADD_AGENT, id=agent_id, name=name, role=role)
    _require(bool(rows), "graph has no Meta node; run ensure_schema() first")


def add_vendor(g, vendor_id: str, *, name: str) -> None:
    rows = _write(g, ADD_VENDOR, id=vendor_id, name=name)
    _require(bool(rows), "graph has no Meta node; run ensure_schema() first")


# --- Sources ----------------------------------------------------------------------

def add_source(g, source_id: str, *, uri: str, title: str, trust: str,
               origin: str | None = None, recompute: bool = True) -> None:
    """Register a document. `origin` is its lineage: two sources repeating the
    same original claim share an origin and count as ONE trusted root."""
    _require(trust in TRUST_LEVELS, f"unknown trust level {trust!r}")
    rows = _write(g, ADD_SOURCE, id=source_id, uri=uri, title=title, trust=trust,
                  origin=origin or source_id)
    _require(bool(rows), "graph has no Meta node; run ensure_schema() first")
    # An existing source keeps its trust: trust only changes through set_trust().
    _require(rows[0][0] == trust,
             f"source {source_id!r} already exists with trust {rows[0][0]!r}; use set_trust()")
    if recompute:
        support.recompute(g)


def set_trust(g, source_id: str, trust: str, *, recompute: bool = True) -> str:
    """Change a source's trust (quarantine, restore). Returns the previous trust."""
    _require(trust in TRUST_LEVELS, f"unknown trust level {trust!r}")
    rows = _write(g, SET_TRUST, id=source_id, trust=trust)
    _require(bool(rows), f"source {source_id!r} not found")
    if recompute:
        support.recompute(g)
    return rows[0][0]


# --- Beliefs and decisions ----------------------------------------------------------

def _why_conclusion_rejected(g, label: str, node_id: str, about) -> str:
    missing = [v for v in about if not exists(g, VENDOR, v)]
    if missing:
        return f"{label} {node_id!r} rejected: unknown vendors {missing}"
    if exists(g, label, node_id):
        return f"{label} {node_id!r} already exists with different content"
    return "graph has no Meta node; run ensure_schema() first"


def add_belief(g, belief_id: str, *, claim: str, about=(),
               recompute: bool = True) -> None:
    """Record a claim. It stays invalid until a justification supports it."""
    about = _unique(about)
    rows = _write(g, ADD_BELIEF, id=belief_id, claim=claim, about=about)
    _require(bool(rows), _why_conclusion_rejected(g, BELIEF, belief_id, about))
    if recompute:
        support.recompute(g)


def add_decision(g, decision_id: str, *, kind: str, summary: str,
                 amount: float | None = None, reversible: bool = True, about=(),
                 recompute: bool = True) -> None:
    """Record a decision. Purchase orders start in state 'draft'; only the
    action gate (app/gate.py) moves them on."""
    _require(kind in DECISION_KINDS, f"unknown decision kind {kind!r}")
    if kind == PURCHASE_ORDER:
        _require(amount is not None and amount > 0, "a purchase order needs a positive amount")
    about = _unique(about)
    rows = _write(g, ADD_DECISION, id=decision_id, kind=kind, summary=summary,
                  amount=amount, reversible=reversible, about=about,
                  state=DRAFT if kind == PURCHASE_ORDER else None)
    _require(bool(rows), _why_conclusion_rejected(g, DECISION, decision_id, about))
    if recompute:
        support.recompute(g)


def set_decision_state(g, decision_id: str, state: str, *, note: str | None = None,
                       approved_by: str | None = None) -> str:
    """Move a decision to a new state. Returns the previous state. Called by
    the action gate only; state does not affect support, so no recompute.
    `note` records why (shown in the UI); `approved_by` records the human."""
    _require(state in DECISION_STATES, f"unknown decision state {state!r}")
    rows = _write(g, SET_DECISION_STATE, id=decision_id, state=state, note=note,
                  approved_by=approved_by)
    _require(bool(rows), f"decision {decision_id!r} not found")
    return rows[0][0]


# --- Justifications -------------------------------------------------------------------

def add_justification(g, justification_id: str, *, supports: str, premises,
                      kind: str, reasoning: str, quote: str | None = None,
                      model: str | None = None, agent: str | None = None,
                      recompute: bool = True) -> None:
    """Record one reason: ALL `premises` together support ONE conclusion.

    Rejected (nothing written) if any premise ID does not exist, if the target
    does not exist, if the agent does not exist, or if the justification ID is
    already used. Justifications are append-only: to change a reason, add a
    new justification instead of editing an old one.
    """
    _require(kind in JUSTIFICATION_KINDS, f"unknown justification kind {kind!r}")
    premises = _unique(premises)
    _require(len(premises) > 0, "a justification needs at least one premise")
    _require(supports not in premises, "a justification cannot cite its own conclusion")
    if kind == EXTRACTION:
        _require(bool(quote), "an extraction must carry the exact quote it relies on")
    target = DECISION if kind == DECIDED else BELIEF
    rows = _write(g, ADD_JUSTIFICATION[target], id=justification_id, supports=supports,
                  premises=premises, kind=kind, reasoning=reasoning, quote=quote,
                  model=model, agent=agent)
    if not rows:
        raise WriteRejected(_why_rejected(g, justification_id, supports, target,
                                          premises, agent))
    if recompute:
        support.recompute(g)


def _why_rejected(g, justification_id, supports, target, premises, agent) -> str:
    """Explain a rejected justification (read-only; only runs on failure)."""
    reasons = []
    if exists(g, JUSTIFICATION, justification_id):
        reasons.append(f"justification {justification_id!r} already exists (append-only)")
    if not exists(g, target, supports):
        reasons.append(f"{target} {supports!r} not found")
    missing = [p for p in premises if not (exists(g, SOURCE, p) or exists(g, BELIEF, p))]
    if missing:
        reasons.append(f"premises not found: {missing}")
    if agent is not None and not exists(g, AGENT, agent):
        reasons.append(f"agent {agent!r} not found")
    if not exists(g, META, META_ID):
        reasons.append("graph has no Meta node; run ensure_schema() first")
    return f"justification {justification_id!r} rejected: " + "; ".join(reasons or ["unknown reason"])


# --- Repair audit trail ---------------------------------------------------------------

def record_repair(g, repair_id: str, *, source_id: str, approved_by: str,
                  quarantine_revision: int, changes) -> None:
    """Write the audit record of an applied quarantine. `changes` is a list of
    {"id", "before", "after"} for every belief/decision whose validity flipped."""
    # Checked up front: the query ends in an aggregate, which always returns a
    # row, so an empty result cannot signal "source not found".
    _require(exists(g, SOURCE, source_id), f"source {source_id!r} not found")
    _write(g, RECORD_REPAIR, id=repair_id, source=source_id, approved_by=approved_by,
           revision=quarantine_revision, changes=list(changes))
    _require(exists(g, REPAIR, repair_id), f"repair {repair_id!r} was not written")


# --- Reads the agents are allowed to do ---------------------------------------------

def valid_beliefs(g, vendor_id: str | None = None) -> list[dict]:
    """Beliefs that are currently supported. With `vendor_id`, only those
    ABOUT that vendor; without, all of them (vendor is None for general ones
    such as the procurement requirements)."""
    rows = g.ro_query(VALID_BELIEFS, {"vendor": vendor_id}).result_set
    return [{"id": b, "claim": c, "vendor_id": v, "vendor": n} for b, c, v, n in rows]


def belief_claim(g, belief_id: str) -> str | None:
    rows = g.ro_query(BELIEF_CLAIM, {"id": belief_id}).result_set
    return rows[0][0] if rows else None


def resolve_vendor(g, value: str | None) -> str | None:
    """The vendor id for an id or an exact vendor name; None if there is none."""
    if not value:
        return None
    rows = g.ro_query(RESOLVE_VENDOR, {"value": value.strip()}).result_set
    return rows[0][0] if rows else None
