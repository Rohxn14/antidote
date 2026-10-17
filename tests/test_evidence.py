# tests/test_evidence.py
"""Evidence strength: how much each conclusion rests on untrusted sources."""
from app import demo, evidence, memory
from app.db import get_db
from app.schema import QUARANTINED
from tests.builders import belief, justify, source, trusted


def level(g, node_id):
    return evidence.strength(g)[node_id]["level"]


def test_the_four_levels(g):
    trusted(g, "registry", origin="A")
    trusted(g, "audit", origin="B")
    source(g, "blog")  # unverified
    for b in ("robust", "single", "unverified", "unsupported"):
        belief(g, b)
    justify(g, "j1", "robust", ["registry"])
    justify(g, "j2", "robust", ["audit"])     # two independent trusted origins
    justify(g, "j3", "single", ["registry"])  # one trusted origin
    justify(g, "j4", "unverified", ["blog"])
    s = evidence.strength(g)
    assert s["robust"] == {"level": evidence.ROBUST, "weak_origin": None}
    assert s["single"] == {"level": evidence.SINGLE_TRUSTED, "weak_origin": "A"}
    assert s["unverified"]["level"] == evidence.UNVERIFIED_ONLY
    assert s["unsupported"]["level"] == evidence.UNSUPPORTED


def test_copies_of_one_claim_are_not_robust(g):
    trusted(g, "registry", origin="A")
    trusted(g, "mirror", origin="A")
    belief(g, "b")
    justify(g, "j1", "b", ["registry"])
    justify(g, "j2", "b", ["mirror"])
    assert level(g, "b") == evidence.SINGLE_TRUSTED


def test_needing_two_origins_is_not_robust(g):
    trusted(g, "registry", origin="A")
    trusted(g, "audit", origin="B")
    belief(g, "b")
    justify(g, "j", "b", ["registry", "audit"])  # A AND B
    assert level(g, "b") == evidence.SINGLE_TRUSTED


def test_demo_levels_and_cleanup(g):
    demo.register(g)
    demo.research(g)
    demo.buy(g)
    s = evidence.strength(g)
    assert s["b_vantor_iso13485"]["level"] == evidence.UNVERIFIED_ONLY  # only Vantor says so
    assert s["b_boltline_iso13485"] == {"level": evidence.SINGLE_TRUSTED, "weak_origin": "md-registry"}
    assert s["d_po_1001"]["level"] == evidence.UNVERIFIED_ONLY
    memory.set_trust(g, "s_vantor_page", QUARANTINED)
    assert level(g, "b_vantor_iso13485") == evidence.UNSUPPORTED
    assert [n for n in get_db().list_graphs() if "evidence" in n] == []
