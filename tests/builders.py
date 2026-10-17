# tests/builders.py
"""Short helpers so each test reads like the scenario it checks."""
from app import memory
from app.schema import INFERENCE, TRUSTED, UNVERIFIED


def source(g, sid, trust=UNVERIFIED, origin=None, recompute=True):
    memory.add_source(g, sid, uri=f"test://{sid}", title=sid, trust=trust,
                      origin=origin, recompute=recompute)


def trusted(g, sid, origin=None, recompute=True):
    source(g, sid, TRUSTED, origin, recompute)


def belief(g, bid, recompute=True):
    memory.add_belief(g, bid, claim=f"claim {bid}", recompute=recompute)


def justify(g, jid, supports, premises, kind=INFERENCE, recompute=True):
    memory.add_justification(g, jid, supports=supports, premises=premises,
                             kind=kind, reasoning=f"reason {jid}",
                             recompute=recompute)


def flag(g, node_id) -> bool:
    """valid for Source/Belief/Decision, holds for Justification."""
    from app import support
    return support.status(g)[node_id]
