# app/demo.py
"""The demo scenario: who and what exists, and each step of the story.

The terminal script (scripts/seed_demo.py), the Streamlit UI and the tests all
call these same functions, so what the UI shows is what the tests check.
Agent outputs are replayed from data/fixtures/ (deterministic, no API calls).
"""
import json
import os

from app import detector, gate, memory, repair
from app.agents import buyer, researcher
from app.db import ROOT, get_db
from app.schema import BELIEF, BUYER, RESEARCHER, TRUSTED, UNVERIFIED, ensure_schema

# Hand-authored fixtures by default (deterministic; the tests rely on them).
# DEMO_FIXTURES=live replays outputs recorded from a real LLM instead.
FIXTURES = ROOT / "data" / "fixtures"
if os.getenv("DEMO_FIXTURES") == "live":
    FIXTURES = FIXTURES / "live"

AGENTS = [("a_researcher", "Researcher", RESEARCHER), ("a_buyer", "Buyer", BUYER)]
VENDORS = [("v_vantor", "Vantor Motion"), ("v_boltline", "Boltline Automation"),
           ("v_ferrocraft", "Ferrocraft Servo"), ("v_quillon", "Quillon Drives")]

# In ingestion order. The rollback baseline restores to just before the
# poisoned page, so everything after it is the "good knowledge" it would lose.
SOURCES = [  # id, uri, title, trust, origin
    ("s_policy", "data/policy.txt", "Procurement policy memo (user statement)",
     TRUSTED, "kestrel-procurement"),
    ("s_registry", "data/registry.html", "Medical Device Supplier Registry",
     TRUSTED, "md-registry"),
    ("s_vantor_page", "data/vendors/vantor.html", "Vantor Motion product page",
     UNVERIFIED, "vantor.example"),
    ("s_boltline_page", "data/vendors/boltline.html", "Boltline Automation product page",
     UNVERIFIED, "boltline.example"),
    ("s_ferrocraft_page", "data/vendors/ferrocraft.html", "Ferrocraft Servo product page",
     UNVERIFIED, "ferrocraft.example"),
    ("s_quillon_page", "data/vendors/quillon.html", "Quillon Drives product page",
     UNVERIFIED, "quillon.example"),
]
SOURCE_BY_ID = {s[0]: s for s in SOURCES}

POISONED = "s_vantor_page"
FIRST_ORDER, SECOND_ORDER = "d_po_1001", "d_po_1002"
MANAGER = "Head of Procurement"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def reset(g) -> None:
    """Wipe the graph and recreate the schema (Meta node + indexes)."""
    if g.name in get_db().list_graphs():
        g.delete()  # through this object, so its cached label/property ids are cleared
    ensure_schema(g)


def register(g) -> None:
    for agent_id, name, role in AGENTS:
        memory.add_agent(g, agent_id, name=name, role=role)
    for vendor_id, name in VENDORS:
        memory.add_vendor(g, vendor_id, name=name)


def ingest(g, source_id: str) -> list[str]:
    """Register one source and replay the Researcher's extraction from it."""
    sid, uri, title, trust, origin = SOURCE_BY_ID[source_id]
    memory.add_source(g, sid, uri=uri, title=title, trust=trust, origin=origin,
                      recompute=False)
    return researcher.record_extractions(g, fixture(f"researcher_{sid}"))


def research(g) -> list[str]:
    rejected = []
    for source in SOURCES:
        rejected += ingest(g, source[0])
    rejected += researcher.record_inferences(g, fixture("researcher_inference"))
    return rejected


def buy(g, plan: str = "buyer_initial") -> dict:
    return buyer.record_plan(g, fixture(plan))


def seed(g) -> dict:
    """Act 1, normal work. Ends with PO-1001 waiting for human approval."""
    reset(g)
    register(g)
    rejected = research(g)
    result = buy(g)
    result["rejected"] = rejected + result["rejected"]
    return result


def is_seeded(g) -> bool:
    if g.name not in get_db().list_graphs():
        return False
    return g.ro_query(f"MATCH (b:{BELIEF}) RETURN count(b)").result_set[0][0] > 0


# --- The rest of the story, one function per beat ------------------------------------

def detect(g) -> list[detector.Finding]:
    return detector.scan_sources(g)


def preview(g, source_id: str = POISONED) -> repair.Preview:
    return repair.preview(g, source_id)


def approve_repair(g, p: repair.Preview) -> str:
    return repair.apply(g, p, approved_by=MANAGER)


def approve_order(g, order_id: str) -> gate.Verdict:
    return gate.approve(g, order_id, approver=MANAGER)


def redecide(g) -> dict:
    """The Buyer decides again, on clean memory."""
    return buy(g, "buyer_after_repair")
