# tests/test_db.py
"""GRAPH.COPY forks the FalkorDB server; only one fork can run at a time.
Unguarded, concurrent copies failed with "could not fork" (49 of 100 in a
4-thread stress test). copy_graph serializes and retries."""
import threading

from app import demo
from app.db import copy_graph


def test_concurrent_copies_all_succeed(g):
    demo.register(g)
    demo.ingest(g, "s_policy")
    failures = []

    def worker(t):
        for i in range(5):
            try:
                copy_graph(g, f"antidote_test_copy_{t}_{i}").delete()
            except Exception as e:  # recorded, asserted below
                failures.append(str(e))

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert failures == []
