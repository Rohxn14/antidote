# app/db.py
"""Connection helper: the one place that knows how to reach FalkorDB."""
import os
import threading
import time
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from falkordb import FalkorDB
from redis.exceptions import ResponseError

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GRAPH = "antidote"

# Loads .env by default; set ENV_FILE=.env.cloud to target FalkorDB Cloud instead.
# The path is resolved against the repo root so scripts work from any directory.
load_dotenv(ROOT / os.getenv("ENV_FILE", ".env"))


@lru_cache(maxsize=1)
def get_db() -> FalkorDB:
    """One shared client (it holds a connection pool) for the whole process."""
    return FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        username=os.getenv("FALKORDB_USERNAME") or None,
        password=os.getenv("FALKORDB_PASSWORD") or None,
    )


def get_graph(name: str | None = None):
    return get_db().select_graph(name or os.getenv("FALKORDB_GRAPH", DEFAULT_GRAPH))


def drop_graph(name: str) -> None:
    """Delete a graph if it exists (copies, previews, test graphs)."""
    db = get_db()
    if name in db.list_graphs():
        db.select_graph(name).delete()


# GRAPH.COPY forks the FalkorDB server, and only one fork can run at a time: a
# copy made while another is in progress fails with "could not fork". Copies
# from this process wait their turn; a clash with another process (a second
# app server, the tests, Redis's own background save) is retried with backoff.
_COPY_LOCK = threading.Lock()


def copy_graph(g, name: str, attempts: int = 12):
    """GRAPH.COPY `g` to `name`, safely under concurrency. Returns the copy."""
    for attempt in range(attempts):
        try:
            with _COPY_LOCK:
                return g.copy(name)
        except ResponseError as e:
            if "could not fork" not in str(e) or attempt == attempts - 1:
                raise
            time.sleep(min(0.05 * 2 ** attempt, 1.0))
