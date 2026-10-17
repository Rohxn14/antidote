"""Why FalkorDB is the core of Antidote.

Each capability below runs the product's real code on a scratch copy of the demo. 
The graph is wrapped in a Recorder that writes down every statement
FalkorDB executes for it, with timings, so you can see the exact Cypher behind each capability.

Run it on a graph with no server behind it and every capability fails. Nothing in Antidote can stand
in for the graph.
"""

import time
from uuid import uuid4

import redis
from falkordb import Graph
from redis.backoff import NoBackoff
from redis.retry import Retry

from app import demo, evidence, gate, memory, repair, support, views
from app.db import drop_graph, get_db
from app.schema import INFERENCE, TRUSTED

class Recorder:
    """Stands in for a FalkorDB graph and writes down every statement it runs.

    Antidote's modules only use query. ro_query, copy, delete, and name on a graph
    so they cannot tell the difference.
    """

    def __init__(self, graph, log=None):
        self.graph = graph
        self.log = [] if log is None else log

    @property
    def name(self):
        return self.graph.name

    def _timed(self, statement, call):
        started = time.perf_counter()
        result = call()
        self.log.append({
            "cypher": " ".join(statement.split()),
            "ms": round((time.perf_counter()-started) * 1000,2),
            "rows": len(getattr(result, "result_set", None)or []),
        })
        return result

    def query(self, cypher, params = None, timeout = None):
        return self._timed(cypher, lambda:self.graph.query(cypher, params,timeout=timeout))

    def ro_query(self, cypher, params = None, timeout = None):
        return self._timed(cypher, lambda:self.graph.ro_query(cypher, params,timeout=timeout))

    def copy(self, clone):
        copied = self._timed(f"GRAPH.COPY {self.name} {clone}", lambda: self.graph.copy(clone))
        return Recorder(copied, self.log)

    def delete(self):
        return self._timed(f"GRAPH.DELETE {self.name}", self.graph.delete)

# --- The capabilities, each through the product's real code -------------------------

def remember(g):
    memory.add_source(g, "s_note", uri="note://centrality", title="A note",
                      trust=TRUSTED, recompute=False)
    memory.add_belief(g, "b_note", claim="The note says so", recompute=False)
    memory.add_justification(g, "j_note", supports="b_note", premises=["s_note"],
                             kind=INFERENCE, reasoning="stated in the note")
    return "stored a fact, its reason and their links, one atomic query each"


def decide(g):
    rounds = support.recompute(g)
    believed = len(memory.valid_beliefs(g))
    return f"{rounds} rounds of the same query until nothing changed; {believed} facts supported"


def _reasons(tree):
    return sum(1 + sum(_reasons(p) for p in j["premises"])
               for j in tree.get("justifications", []))


def explain(g):
    tree = views.why(g, demo.FIRST_ORDER)
    return f"traced PO-1001 through {_reasons(tree)} reasons back to its documents"


def preview(g):
    p = repair.preview(g, demo.POISONED)
    repair.discard(p)
    return f"on a copy, {len(p.lost)} facts and decisions would fall; nothing real changed"


def check_order(g):
    verdict = gate.evaluate(g, demo.FIRST_ORDER)
    return f"PO-1001: {verdict.outcome} ({'; '.join(verdict.reasons)})"


def measure(g):
    level = evidence.strength(g)["b_vantor_iso13485"]["level"]
    return f"'Vantor holds ISO 13485' rests on: {level}"


def agents_read(g):
    facts = memory.valid_beliefs(g, "v_vantor")
    return f"an agent asking about Vantor gets {len(facts)} supported facts and nothing else"


CAPABILITIES = [
    ("Remember a fact and its reason", "atomic Cypher writes (app/memory.py)", remember),
    ("Decide what is still believable", "a fixed point computed by Cypher (app/support.py)", decide),
    ("Explain a decision", "following reasons through the graph (app/views.py)", explain),
    ("Preview a repair", "GRAPH.COPY, then Cypher on the copy (app/repair.py)", preview),
    ("Check an order before acting", "recompute in FalkorDB, then read (app/gate.py)", check_order),
    ("Measure evidence strength", "what-if worlds on graph copies (app/evidence.py)", measure),
    ("Let agents read memory", "Cypher read of supported facts (app/memory.py)", agents_read),
]


def missing_graph():
    """A real FalkorDB graph object with no server behind it: what Antidote would
    have if FalkorDB were removed. No retries, so it fails fast."""
    nowhere = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.5,
                          socket_timeout=0.5, retry=Retry(NoBackoff(), 0))
    return Graph(nowhere, "antidote_without_falkordb")


def run(with_falkordb=True):
    """Yield one result per capability: what it did, and every statement FalkorDB ran."""
    if with_falkordb:
        graph = get_db().select_graph(f"antidote_centrality_{uuid4().hex[:8]}")
    else:
        graph = missing_graph()
    try:
        if with_falkordb:
            demo.seed(graph)  # the demo up to the poisoned order (not recorded)
        for capability, feature, step in CAPABILITIES:
            recorder = Recorder(graph)
            started = time.perf_counter()
            try:
                result, error = step(recorder), None
            except Exception as e:  # without FalkorDB, this is where every capability ends
                result, error = "failed", f"{type(e).__name__}: {e}"
            yield {"capability": capability, "feature": feature, "ok": error is None,
                   "ms": round((time.perf_counter() - started) * 1000, 1),
                   "result": result, "statements": recorder.log, "error": error}
    finally:
        if with_falkordb:
            drop_graph(graph.name)