# tests/test_api.py
"""The web API: the whole story over HTTP, the approval check enforced at the
endpoints themselves, private sessions, and failing closed without FalkorDB."""
import json

import pytest
import redis
from fastapi.testclient import TestClient
from redis.backoff import NoBackoff
from redis.retry import Retry

from api.server import MemoryProbe, create_app
from api.session_store import SessionStore
from app.db import get_db

PREFIX = "antidote_test_u_"  # conftest deletes every antidote_test_* graph


@pytest.fixture
def client(g):
    return TestClient(create_app(SessionStore(prefix=PREFIX, cap=5)))


def start(client) -> dict:
    return {"X-Antidote-Session": client.post("/api/session").json()["token"]}


def stream(client, path, headers, body=None) -> list[dict]:
    with client.stream("POST", path, headers=headers, json=body or {"pace": 0}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/x-ndjson")
        assert r.headers["cache-control"] == "no-cache"
        assert r.headers["x-accel-buffering"] == "no"
        events = [json.loads(line) for line in r.iter_lines() if line]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    return events


def test_full_story_over_http(client):
    h = start(client)
    events = stream(client, "/api/run", h)
    kinds = [e["type"] for e in events]
    assert kinds[-1] == "run_complete" and "error" not in kinds
    verdict = next(e["data"] for e in events if e["type"] == "gate_verdict")
    assert (verdict["decision_id"], verdict["state"]) == ("d_po_1001", "pending_approval")
    alert = next(e["data"] for e in events if e["type"] == "security_alert")
    assert alert["document_id"] == "s_vantor_page"

    state = client.get("/api/state", headers=h).json()
    assert state["has_run"] and state["alerts"][0]["document_id"] == "s_vantor_page"
    order = next(d for d in state["decisions"] if d["id"] == "d_po_1001")
    assert (order["state"], order["evidence"]) == ("pending_approval", "unverified only")

    impact = client.post("/api/impact", headers=h, json={"document_id": "s_vantor_page"}).json()
    assert "d_po_1001" in {i["id"] for i in impact["orders_blocked"]}
    assert [s["id"] for s in impact["survived"]] == ["b_vantor_makes_servos"]

    repaired = client.post("/api/quarantine", headers=h).json()
    assert repaired["quarantined"] == ["s_vantor_page"] and "d_po_1001" in repaired["withdrawn"]

    blocked = client.post("/api/orders/d_po_1001/approve", headers=h).json()
    assert (blocked["outcome"], blocked["state"]) == ("blocked", "blocked")
    assert "cannot override missing support" in blocked["message"]

    replan = stream(client, "/api/replan", h)
    new = next(e["data"] for e in replan if e["type"] == "decision_recorded")
    assert new["decision_id"] == "d_po_1002" and "Boltline" in new["summary"]
    assert client.post("/api/orders/d_po_1002/approve", headers=h).json()["state"] == "authorized"
    assert client.post("/api/orders/d_po_1002/execute", headers=h).json()["state"] == "executed"


def test_approve_and_execute_endpoints_reject_an_unsupported_order(client):
    h = start(client)
    stream(client, "/api/run", h)
    # Approved while still supported, then its support is taken away...
    assert client.post("/api/orders/d_po_1001/approve", headers=h).json()["state"] == "authorized"
    client.post("/api/impact", headers=h, json={"document_id": "s_vantor_page"})
    client.post("/api/quarantine", headers=h)
    # ...so execute, called directly with no UI involved, refuses it.
    executed = client.post("/api/orders/d_po_1001/execute", headers=h).json()
    assert (executed["outcome"], executed["state"]) == ("blocked", "blocked")
    # And a blocked order cannot be approved through the endpoint either.
    r = client.post("/api/orders/d_po_1001/approve", headers=h)
    assert r.status_code == 409 and r.json()["error"] == "wrong_state"


def test_sessions_are_private_and_never_take_a_graph_name(client):
    a, b = start(client), start(client)
    stream(client, "/api/run", a)
    assert client.get("/api/state", headers=b).json()["facts"] == []
    assert client.get("/api/state", headers=a).json()["facts"]
    graph_name = next(n for n in get_db().list_graphs() if n.startswith(PREFIX))
    for token in ("", "nope", graph_name):
        r = client.get("/api/state", headers={"X-Antidote-Session": token})
        assert r.status_code == 401 and r.json()["error"] == "session_expired"


def test_session_cap_evicts_the_least_recent_and_never_refuses(g):
    client = TestClient(create_app(SessionStore(prefix=PREFIX, cap=2)))
    first, second = start(client), start(client)
    client.get("/api/state", headers=second)       # second is now the most recent
    third = start(client)                          # over the cap: first is evicted
    assert client.get("/api/state", headers=first).status_code == 401
    assert client.get("/api/state", headers=second).status_code == 200
    assert client.get("/api/state", headers=third).status_code == 200
    assert len([n for n in get_db().list_graphs() if n.startswith(PREFIX)]) == 2


def test_document_view_marks_what_a_person_cannot_see(client):
    h = start(client)
    page = client.get("/api/documents/s_vantor_page", headers=h).json()
    hidden = [s for s in page["segments"] if s["hidden"]]
    assert {s["kind"] for s in hidden} == {"comment", "hidden_element"}
    assert any("<INFORMATION>" in s["text"] for s in hidden)
    assert any("Ignore all previous instructions" in s["text"] for s in hidden)
    assert page["html"].lstrip().startswith("<!doctype html>")
    request = client.get("/api/documents/s_policy", headers=h).json()
    assert [s["hidden"] for s in request["segments"]] == [False] and request["html"] is None


def test_live_ai_is_refused_when_unavailable(client, monkeypatch):
    monkeypatch.setenv("ANTIDOTE_LIVE_AI", "off")
    h = start(client)
    r = client.post("/api/run", headers=h, json={"mode": "live", "request": "anything", "pace": 0})
    assert r.status_code == 400 and r.json()["error"] == "live_ai_unavailable"
    assert client.get("/api/health").json()["live_ai"] is False


def test_without_falkordb_every_api_endpoint_fails_closed(g):
    nowhere = redis.Redis(host="memory.invalid", port=1, socket_connect_timeout=0.5,
                          socket_timeout=0.5, retry=Retry(NoBackoff(), 0))
    client = TestClient(create_app(SessionStore(prefix=PREFIX), MemoryProbe(client=nowhere)))
    h = {"X-Antidote-Session": "any"}
    calls = [("post", "/api/session"), ("get", "/api/state"), ("get", "/api/documents/s_policy"),
             ("post", "/api/run"), ("post", "/api/replan"), ("post", "/api/impact"),
             ("post", "/api/impact/cancel"), ("post", "/api/quarantine"),
             ("post", "/api/orders/d_po_1001/approve"), ("get", "/api/why/d_po_1001"),
             ("get", "/api/cypher"), ("get", "/api/benchmark"), ("post", "/api/capabilities"),
             ("get", "/api/stream-test")]
    for method, path in calls:
        r = getattr(client, method)(path, headers=h, **({"json": {}} if method == "post" else {}))
        assert r.status_code == 503, path
        assert r.json()["error"] == "memory_unreachable", path
        assert "memory.invalid" not in r.text, path  # never reveal where the database lives
    health = client.get("/api/health")
    assert health.status_code == 503 and health.json()["falkordb"] == "down"
    assert "memory.invalid" not in health.text
    assert client.get("/").status_code == 200  # the web app itself still loads
