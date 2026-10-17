# app/sessions.py
"""Each visitor of the web demo gets a private copy of the demo memory.

At start-up the app seeds a pristine template graph (Act 1 of the story).
Every new browser session gets its own GRAPH.COPY of it, so two people
clicking at the same time never change each other's demo. Copies older than
MAX_AGE_S are deleted, together with their preview and what-if copies.
"""
import os
import secrets
import time

from app import demo
from app.db import DEFAULT_GRAPH, drop_graph, get_db

BASE = os.getenv("FALKORDB_GRAPH", DEFAULT_GRAPH)
TEMPLATE = f"{BASE}_template"
SESSION_PREFIX = f"{BASE}_s_"
MAX_AGE_S = 3 * 3600


def seed_template():
    """Seed (or re-seed) the pristine template. Returns the graph."""
    g = get_db().select_graph(TEMPLATE)
    demo.seed(g)
    return g


def cleanup(now: float | None = None) -> int:
    """Delete session graphs (and their copies) older than MAX_AGE_S."""
    now = now or time.time()
    removed = 0
    for name in get_db().list_graphs():
        if not name.startswith(SESSION_PREFIX):
            continue
        try:
            created = int(name[len(SESSION_PREFIX):].split("_")[0])
        except ValueError:
            continue
        if now - created > MAX_AGE_S:
            drop_graph(name)
            removed += 1
    return removed


def new_session_graph():
    """A fresh private copy of the template for one visitor. Re-seeds the
    template if it is gone (FalkorDB Cloud's free tier does not persist data)."""
    cleanup()
    if TEMPLATE not in get_db().list_graphs():
        seed_template()
    name = f"{SESSION_PREFIX}{int(time.time())}_{secrets.token_hex(4)}"
    return get_db().select_graph(TEMPLATE).copy(name)
