# app/schema.py
"""The graph's vocabulary: every label, relationship type and allowed value.

Other modules import these constants instead of typing raw strings. A
misspelled label in Cypher is not an error, it silently matches nothing, so a
typo here fails loudly at import time instead of quietly breaking a query.
"""

# --- Node labels -------------------------------------------------------------
SOURCE = "Source"                # a document an agent read (vendor page, registry)
BELIEF = "Belief"                # a claim the shared memory may hold
DECISION = "Decision"            # a shortlist or purchase order made by the Buyer
JUSTIFICATION = "Justification"  # one reason: premises (AND) -> one conclusion
AGENT = "Agent"
VENDOR = "Vendor"
REPAIR = "Repair"                # audit record of an applied quarantine
META = "Meta"                    # single node {id: 'graph'} holding the revision

# --- Relationship types --------------------------------------------------------
AUTHORED = "AUTHORED"  # (Agent)-[:AUTHORED]->(Justification)
PREMISE = "PREMISE"    # (Justification)-[:PREMISE]->(Source or Belief), one or more
SUPPORTS = "SUPPORTS"  # (Justification)-[:SUPPORTS]->(Belief or Decision), exactly one
ABOUT = "ABOUT"        # (Belief or Decision)-[:ABOUT]->(Vendor)
TARGETED = "TARGETED"  # (Repair)-[:TARGETED]->(Source)
CHANGED = "CHANGED"    # (Repair)-[:CHANGED {before, after}]->(Belief or Decision)

# --- Computed properties --------------------------------------------------------
# A cache written ONLY by app/support.py. Never authoritative, never set by hand.
# Readers must compare with `= true`, so a missing value counts as "not valid".
VALID = "valid"  # on Source, Belief, Decision
HOLDS = "holds"  # on Justification

META_ID = "graph"

# --- Allowed values ----------------------------------------------------------------
TRUSTED = "trusted"
UNVERIFIED = "unverified"    # counts for support, but is never a trusted root
QUARANTINED = "quarantined"  # the only trust level that makes a source invalid
TRUST_LEVELS = (TRUSTED, UNVERIFIED, QUARANTINED)

EXTRACTION = "extraction"  # Source -> Belief, carries an exact quote
INFERENCE = "inference"    # Belief(s) -> Belief
DECIDED = "decision"       # Belief(s) -> Decision
JUSTIFICATION_KINDS = (EXTRACTION, INFERENCE, DECIDED)

SHORTLIST = "shortlist"
PURCHASE_ORDER = "purchase_order"
DECISION_KINDS = (SHORTLIST, PURCHASE_ORDER)

DRAFT = "draft"
PENDING_APPROVAL = "pending_approval"
AUTHORIZED = "authorized"
EXECUTED = "executed"
BLOCKED = "blocked"
DECISION_STATES = (DRAFT, PENDING_APPROVAL, AUTHORIZED, EXECUTED, BLOCKED)

RESEARCHER = "researcher"
BUYER = "buyer"
AGENT_ROLES = (RESEARCHER, BUYER)

# Range indexes: `id` on every label, plus Vendor.name for lookups by name.
INDEXES = [(label, "id") for label in (
    SOURCE, BELIEF, DECISION, JUSTIFICATION, AGENT, VENDOR, REPAIR, META)]
INDEXES.append((VENDOR, "name"))


def ensure_schema(g) -> None:
    """Create the Meta node and the range indexes. Safe to run repeatedly."""
    # MERGE first: it also creates the graph key if this is a fresh graph.
    g.query(f"MERGE (m:{META} {{id: $id}}) ON CREATE SET m.revision = 0",
            {"id": META_ID})
    # FalkorDB raises if an index already exists, so only create missing ones.
    rows = g.ro_query(
        "CALL db.indexes() YIELD label, properties RETURN label, properties").result_set
    existing = {(label, prop) for label, props in rows for prop in props}
    for label, prop in INDEXES:
        if (label, prop) not in existing:
            g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
