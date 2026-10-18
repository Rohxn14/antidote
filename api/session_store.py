# api/session_store.py
"""Private graphs for web visitors.

Each browser gets an unguessable token (secrets.token_urlsafe), mapped here to
a graph name. The client never sends a graph name, so a token can only ever
reach its own graph (and that graph's preview copies).

FalkorDB Cloud's free tier holds 100 MB, so sessions idle for more than two
hours are swept whenever a new one starts, and the least recently used idle
session is evicted when the cap is reached or the database uses more than
MEMORY_LIMIT. A new visitor is never refused.
"""
import os
import secrets
import threading
import time
from dataclasses import dataclass, field

from app import repair
from app.db import DEFAULT_GRAPH, drop_graph, get_db

PREFIX = f"{os.getenv('FALKORDB_GRAPH', DEFAULT_GRAPH)}_u_"
IDLE_S = 2 * 3600
CAP = int(os.getenv("ANTIDOTE_SESSION_CAP", "25"))
MEMORY_LIMIT = int(os.getenv("ANTIDOTE_MEMORY_LIMIT_MB", "70")) * 1024 * 1024
MEMORY_EVICTIONS = 3  # per new session: memory may be held by graphs that are not sessions
PARKED_S = 1.0


@dataclass
class Session:
    graph_name: str
    request: str
    last_used: float = field(default_factory=time.time)
    run: object | None = None          # the run streaming into this case, if any
    parked: float | None = None        # since when that run has waited for the browser to read
    has_run: bool = False
    preview: object = None             # the open repair.Preview, if any
    alerts: list = field(default_factory=list)
    evidence: tuple | None = None      # (revision, strength) cache
    case: dict | None = None           # a case the visitor built (None: the demo story)
    mode: str = "replay"               # how the last run got its answers (re-plans use the same)

    @property
    def busy(self) -> bool:
        """A run is streaming into this case. When its browser goes away (a reload, "Skip
        to result"), the server stops reading the run but does not close it: it waits at
        its last event until Python frees it. A live stream's event is read within
        milliseconds, so a run left waiting for PARKED_S no longer counts."""
        if self.run is None:
            return False
        return self.parked is None or time.monotonic() - self.parked < PARKED_S


class SessionStore:
    def __init__(self, prefix: str = PREFIX, cap: int = CAP, idle_s: float = IDLE_S,
                 memory_used=None, memory_limit: int = MEMORY_LIMIT):
        self.prefix, self.cap, self.idle_s = prefix, cap, idle_s
        self.memory_used = memory_used or (lambda: None)  # bytes in use, None if unknown
        self.memory_limit = memory_limit
        self.sessions: dict[str, Session] = {}
        self.lock = threading.RLock()

    def _memory_full(self) -> bool:
        used = self.memory_used()
        return used is not None and used > self.memory_limit

    def create(self, prepare, request: str) -> str:
        """A new session with its own graph, prepared by `prepare(graph)`."""
        with self.lock:
            self._sweep()
            while len(self.sessions) >= self.cap and self._evict_least_recent():
                pass  # if every session is busy we go over the cap rather than refuse
            for _ in range(MEMORY_EVICTIONS):
                if not (self._memory_full() and self._evict_least_recent()):
                    break
            token = secrets.token_urlsafe(24)
            name = f"{self.prefix}{int(time.time())}_{secrets.token_hex(4)}"
            self.sessions[token] = Session(graph_name=name, request=request)
        try:
            prepare(get_db().select_graph(name))
        except Exception:
            self.drop(token)
            raise
        return token

    def get(self, token: str | None) -> Session | None:
        with self.lock:
            session = self.sessions.get(token or "")
            if session:
                session.last_used = time.time()
            return session

    def drop(self, token: str) -> None:
        """Forget a session and delete its graph and every copy made from it."""
        with self.lock:
            session = self.sessions.pop(token, None)
        if not session:
            return
        if session.preview is not None:
            repair.discard(session.preview)
        for name in get_db().list_graphs():
            if name.startswith(session.graph_name):
                drop_graph(name)

    def count(self) -> int:
        return len(self.sessions)

    def _evict_least_recent(self) -> bool:
        idle = [(s.last_used, t) for t, s in self.sessions.items() if not s.busy]
        if not idle:
            return False
        self.drop(min(idle)[1])
        return True

    def _sweep(self) -> None:
        """Drop sessions idle too long, and graphs left behind by an earlier server."""
        now = time.time()
        for token, session in list(self.sessions.items()):
            if not session.busy and now - session.last_used > self.idle_s:
                self.drop(token)
        live = [s.graph_name for s in self.sessions.values()]
        for name in get_db().list_graphs():
            if not name.startswith(self.prefix) or any(name.startswith(n) for n in live):
                continue
            try:
                created = int(name[len(self.prefix):].split("_")[0])
            except ValueError:
                continue
            if now - created > self.idle_s:
                drop_graph(name)
