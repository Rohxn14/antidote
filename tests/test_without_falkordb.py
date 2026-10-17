# tests/test_without_falkordb.py
"""FalkorDB is central: every capability works with it and shows the Cypher it
ran, and every capability fails without it. Uses app/centrality.py."""
import pytest

from app.db import ROOT, get_db

if not (ROOT / "app" / "centrality.py").exists():
    pytest.skip("app/centrality.py has not been typed in yet", allow_module_level=True)

from app import centrality  # noqa: E402


def test_with_falkordb_every_capability_works_and_shows_its_cypher():
    results = list(centrality.run(with_falkordb=True))
    assert [r["capability"] for r in results] == [c[0] for c in centrality.CAPABILITIES]
    for r in results:
        assert r["ok"], f"{r['capability']}: {r['error']}"
        assert r["statements"], f"{r['capability']} ran no statement in FalkorDB"
    by_name = {r["capability"]: r for r in results}
    copies = [s["cypher"] for s in by_name["Preview a repair"]["statements"]]
    assert any(c.startswith("GRAPH.COPY") for c in copies)  # the preview is a graph copy
    rounds = [s["cypher"] for s in by_name["Decide what is still believable"]["statements"]]
    assert any("SET j.holds = true" in c for c in rounds)    # the rule runs as Cypher
    assert not [n for n in get_db().list_graphs() if n.startswith("antidote_centrality_")]


def test_without_falkordb_every_capability_fails():
    results = list(centrality.run(with_falkordb=False))
    assert len(results) == len(centrality.CAPABILITIES)
    for r in results:
        assert not r["ok"], f"{r['capability']} worked without FalkorDB"
        assert "Timeout" in r["error"] or "Connection" in r["error"], r["error"]
