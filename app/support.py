# app/support.py
"""The support engine: decides what shared memory may still believe.

The rule is AND inside a justification, OR across justifications:

    valid(Source)          = trust <> 'quarantined' AND it is not under review
    holds(Justification)   = every PREMISE of it is valid
    valid(Belief/Decision) = at least one Justification that SUPPORTS it holds

We compute the LEAST fixed point with a full recompute:

    1. Reset: Source.valid comes from trust; every other flag becomes false.
    2. Rounds: (a) justifications whose premises are all valid start to hold;
               (b) beliefs/decisions with at least one holding justification
                   become valid.
    3. Stop when a round changes nothing.

Starting from false and only ever switching flags to true is what makes this
cycle-safe: beliefs that justify each other in a loop can never switch
themselves on unless a real root (a non-quarantined source) feeds the loop.

A source under review (Source.review, set by the security scan or the conflict
check) counts for nothing until a person clears or distrusts it.

Everything runs as Cypher inside FalkorDB: one query for the reset and one
query per round. Python never evaluates the rule; it only repeats rounds
until FalkorDB reports that nothing changed.
"""
from app.schema import (BELIEF, DECISION, HOLDS, JUSTIFICATION, PREMISE,
                        QUARANTINED, SOURCE, SUPPORTS, VALID)

# --- Step 1: reset, as one atomic query ----------------------------------------------
# Each `WITH count(*)` collapses the rows to one, so the next MATCH runs once
# (and still runs when the previous MATCH found nothing: count(*) is then 0).
RESET = f"""
MATCH (s:{SOURCE})
SET s.{VALID} = (s.trust <> $quarantined AND s.review IS NULL)
WITH count(*) AS sources
MATCH (j:{JUSTIFICATION})
SET j.{HOLDS} = false
WITH count(*) AS justifications
MATCH (n) WHERE n:{BELIEF} OR n:{DECISION}
SET n.{VALID} = false
"""

# --- Step 2: one round, as one query -------------------------------------------------
# (a) AND inside a justification. FalkorDB does not allow pattern
#     comprehensions inside WHERE, so instead of all(...) we count: a
#     justification holds when its number of valid premises equals
#     premise_count, the number it was created with (app/memory.py stores it).
#     Comparing with the stored count, not with the edges present now, means
#     deleting a premise node can never weaken a justification: it fails closed.
# (b) OR across justifications: a belief or decision with any holding
#     justification becomes valid.
# If (b) did not yet see (a)'s writes, it would simply catch up next round;
# we only stop when both halves report zero changes in the same round.
# (b) uses OPTIONAL MATCH + collect so the query always returns one row, even
# when nothing new becomes valid (collect skips the null "no match" row).
ROUND = f"""
MATCH (j:{JUSTIFICATION})-[:{PREMISE}]->(p)
WHERE j.{HOLDS} = false
WITH j, sum(CASE WHEN p.{VALID} = true THEN 1 ELSE 0 END) AS valid_premises
WHERE valid_premises = j.premise_count
SET j.{HOLDS} = true
WITH count(j) AS held
OPTIONAL MATCH (j:{JUSTIFICATION})-[:{SUPPORTS}]->(n)
WHERE j.{HOLDS} = true AND n.{VALID} = false
WITH held, collect(DISTINCT n) AS newly_valid
FOREACH (n IN newly_valid | SET n.{VALID} = true)
RETURN held, size(newly_valid) AS validated
"""

# --- Reads ------------------------------------------------------------------------
STATUS = f"""
MATCH (n) WHERE n:{SOURCE} OR n:{BELIEF} OR n:{DECISION}
RETURN n.id AS id, coalesce(n.{VALID}, false) AS flag
UNION ALL
MATCH (j:{JUSTIFICATION})
RETURN j.id AS id, coalesce(j.{HOLDS}, false) AS flag
"""

# Every query this module depends on, for the README and the UI's Cypher panel.
QUERIES = {"reset": RESET, "round": ROUND, "status": STATUS}

# Each round switches at least one flag on and flags never switch off, so the
# loop ends after at most (#justifications + #beliefs + #decisions + 1) rounds.
# The cap only guards against a bug in this file.
MAX_ROUNDS = 10_000


def recompute(g) -> int:
    """Recompute every valid/holds flag from scratch. Returns rounds taken."""
    g.query(RESET, {"quarantined": QUARANTINED})
    for rounds in range(1, MAX_ROUNDS + 1):
        held, validated = g.query(ROUND).result_set[0]
        if held == 0 and validated == 0:
            return rounds
    raise RuntimeError("support engine did not converge; this is a bug")


def status(g) -> dict[str, bool]:
    """{id: flag} for every Source, Belief, Decision (valid) and Justification (holds)."""
    return {node_id: flag for node_id, flag in g.ro_query(STATUS).result_set}
