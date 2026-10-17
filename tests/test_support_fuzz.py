# tests/test_support_fuzz.py
"""Random graphs (with cycles) built through memory.py: the Cypher engine
must agree with the independent reference on every node and justification,
also after random quarantines and restorations."""
import random

import pytest

from app import memory, support
from app.schema import DECIDED, INFERENCE, QUARANTINED, TRUSTED, UNVERIFIED
from tests.reference import least_model

GRAPHS = 25


def _build_random_graph(g, rng: random.Random):
    trust = {f"s{i}": rng.choice([TRUSTED, UNVERIFIED, UNVERIFIED, QUARANTINED])
             for i in range(rng.randint(2, 6))}
    beliefs = [f"b{i}" for i in range(rng.randint(3, 14))]
    decisions = [f"d{i}" for i in range(rng.randint(0, 3))]
    justifications = {}

    for sid, level in trust.items():
        memory.add_source(g, sid, uri=sid, title=sid, trust=level, recompute=False)
    for bid in beliefs:
        memory.add_belief(g, bid, claim=bid, recompute=False)
    for did in decisions:
        memory.add_decision(g, did, kind="shortlist", summary=did, recompute=False)

    def add(target, pool, kind):
        jid = f"j{len(justifications)}"
        premises = rng.sample(pool, rng.randint(1, min(3, len(pool))))
        memory.add_justification(g, jid, supports=target, premises=premises,
                                 kind=kind, reasoning="fuzz", recompute=False)
        justifications[jid] = (target, premises)

    # Beliefs may cite any source or any OTHER belief, so cycles happen often.
    for bid in beliefs:
        for _ in range(rng.randint(0, 3)):
            add(bid, list(trust) + [b for b in beliefs if b != bid], INFERENCE)
    for did in decisions:
        for _ in range(rng.randint(1, 2)):
            add(did, beliefs, DECIDED)
    return trust, set(beliefs) | set(decisions), justifications


def _assert_matches_reference(g, trust, conclusions, justifications):
    expected_valid, expected_holds = least_model(trust, conclusions, justifications)
    actual = support.status(g)
    assert {n: actual[n] for n in expected_valid} == expected_valid
    assert {j: actual[j] for j in expected_holds} == expected_holds


@pytest.mark.parametrize("seed", range(GRAPHS))
def test_cypher_engine_matches_reference(g, seed):
    rng = random.Random(seed)
    trust, conclusions, justifications = _build_random_graph(g, rng)
    support.recompute(g)
    _assert_matches_reference(g, trust, conclusions, justifications)

    for _ in range(4):  # random quarantines and restorations, both directions
        sid = rng.choice(list(trust))
        trust[sid] = rng.choice([TRUSTED, UNVERIFIED, QUARANTINED])
        memory.set_trust(g, sid, trust[sid])
        _assert_matches_reference(g, trust, conclusions, justifications)
