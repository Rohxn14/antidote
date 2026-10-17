# tests/reference.py
"""An independent reference implementation of the support rule, used ONLY to
check the Cypher engine. It never runs in the product.

Valid beliefs are the least model of a propositional Horn program: each
justification is a clause `conclusion <- premise1 AND premise2 ...` and each
non-quarantined source is a fact. This is the classic linear-time algorithm
(Dowling & Gallier, 1984): every clause counts its premises that are not yet
known to be true; when the count reaches zero the clause fires.

It shares no code and no strategy with app/support.py (which runs rounds of
Cypher queries), so agreement between the two is meaningful evidence.
"""
from collections import defaultdict, deque


def least_model(trust: dict[str, str], conclusions: set[str],
                justifications: dict[str, tuple[str, list[str]]]):
    """trust: {source_id: trust}; conclusions: belief/decision ids;
    justifications: {jid: (conclusion_id, premise_ids)}.
    Returns ({node_id: valid}, {jid: holds})."""
    valid = {s: t != "quarantined" for s, t in trust.items()}
    valid.update({c: False for c in conclusions})
    holds = {j: False for j in justifications}

    unmet = {}
    watchers = defaultdict(list)  # premise id -> justifications waiting on it
    for jid, (_, premises) in justifications.items():
        unmet[jid] = len(premises)
        for p in premises:
            watchers[p].append(jid)

    queue = deque(n for n, ok in valid.items() if ok)
    while queue:
        node = queue.popleft()
        for jid in watchers[node]:
            unmet[jid] -= 1
            if unmet[jid] == 0:
                holds[jid] = True
                target = justifications[jid][0]
                if not valid[target]:
                    valid[target] = True
                    queue.append(target)
    return valid, holds
