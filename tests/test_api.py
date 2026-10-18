# tests/test_api.py
"""The web API: the whole story over HTTP, the approval check enforced at the
endpoints themselves, private sessions, and failing closed without FalkorDB."""
import json
import time

import pytest
import redis
from fastapi.testclient import TestClient
from redis.backoff import NoBackoff
from redis.retry import Retry

from api import server
from api.server import MemoryProbe, Walkthrough, create_app
from api.session_store import SessionStore
from app import memory
from app.db import get_db
from app.schema import QUARANTINED

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

    # The check runs before the Buyer decides: the page goes under review, Vantor is
    # suspended, and the Buyer orders from the cheapest supplier on what still counts.
    alert = next(e["data"] for e in events if e["type"] == "security_alert")
    assert alert["document_id"] == "s_vantor_page" and alert["suspended"] == ["Vantor Motion"]
    assert "hidden instructions" in alert["reason"] and "contradicts a trusted document" in alert["reason"]
    assert {f["rule"] for f in alert["findings"]} >= {"conflict"}
    assert kinds.index("security_alert") < kinds.index("decision_recorded")
    verdict = next(e["data"] for e in events if e["type"] == "gate_verdict")
    assert (verdict["decision_id"], verdict["state"]) == ("d_po_1001", "pending_approval")

    state = client.get("/api/state", headers=h).json()
    assert state["has_run"] and state["alerts"][0]["resolution"] == "open"
    assert {v["id"]: v["status"] for v in state["vendors"]}["v_vantor"] == "suspended"
    assert not next(d for d in state["documents"] if d["id"] == "s_vantor_page")["supported"]
    order = next(d for d in state["decisions"] if d["id"] == "d_po_1001")
    assert "Boltline" in order["summary"] and order["state"] == "pending_approval"
    assert order["held_by"] == [] and order["reasoning"]
    assert "d_shortlist_vantor" not in {d["id"] for d in state["decisions"]}

    # The preview shows what the page holds up: what blacklisting removes for good.
    impact = client.post("/api/impact", headers=h, json={"document_id": "s_vantor_page"}).json()
    assert {"b_vantor_offer", "b_vantor_qualifies"} <= {i["id"] for i in impact["lost"]}
    assert [s["id"] for s in impact["survived"]] == ["b_vantor_makes_servos"]
    assert impact["orders_blocked"] == []

    # Distrusting it blacklists Vantor; the Boltline order was never at risk.
    repaired = client.post("/api/quarantine", headers=h).json()
    assert repaired["quarantined"] == ["s_vantor_page"] and repaired["blacklisted"] == ["Vantor Motion"]
    state = client.get("/api/state", headers=h).json()
    assert {v["id"]: v["status"] for v in state["vendors"]}["v_vantor"] == "blacklisted"
    assert state["alerts"][0]["resolution"] == "distrusted"
    assert client.post("/api/orders/d_po_1001/approve", headers=h).json()["state"] == "authorized"
    assert client.post("/api/orders/d_po_1001/execute", headers=h).json()["state"] == "executed"


def test_a_false_alarm_can_be_cleared_and_the_verification_hold_still_applies(client):
    h = start(client)
    stream(client, "/api/run", h)
    cleared = client.post("/api/review/clear", headers=h, json={"document_id": "s_vantor_page"}).json()
    assert cleared["reinstated"] == ["Vantor Motion"]
    state = client.get("/api/state", headers=h).json()
    assert {v["id"]: v["status"] for v in state["vendors"]}["v_vantor"] is None
    assert state["alerts"][0]["resolution"] == "cleared"

    # Its page counts again, so a re-plan follows it to Vantor; but nothing trusted
    # confirms Vantor's certificate, so the $48,000 order waits for verification.
    replan = stream(client, "/api/replan", h)
    new = next(e["data"] for e in replan if e["type"] == "decision_recorded")
    assert new["decision_id"] == "d_po_1002" and "Vantor" in new["summary"]
    held = client.post("/api/orders/d_po_1002/approve", headers=h).json()
    assert (held["outcome"], held["state"]) == ("held", "pending_approval")
    r = client.post("/api/review/clear", headers=h, json={"document_id": "s_vantor_page"})
    assert r.status_code == 400 and r.json()["error"] == "not_under_review"


def test_approve_and_execute_endpoints_reject_an_unsupported_order(client):
    h = start(client)
    stream(client, "/api/run", h)
    # A blocked order cannot be approved through the endpoint.
    client.post("/api/impact", headers=h, json={"document_id": "s_boltline_page"})
    assert client.post("/api/quarantine", headers=h).json()["orders_blocked"] == ["d_po_1001"]
    r = client.post("/api/orders/d_po_1001/approve", headers=h)
    assert r.status_code == 409 and r.json()["error"] == "wrong_state"
    # An approved order whose support disappears afterwards (here: changed directly in
    # the graph, with no repair to block it) is refused when someone tries to place it.
    new = next(e["data"] for e in stream(client, "/api/replan", h) if e["type"] == "decision_recorded")
    assert new["decision_id"] == "d_po_1002" and "Nexapoint" in new["summary"]
    assert client.post("/api/orders/d_po_1002/approve", headers=h).json()["state"] == "authorized"
    token = h["X-Antidote-Session"]
    graph = get_db().select_graph(client.app.state.store.sessions[token].graph_name)
    memory.set_trust(graph, "s_nexapoint_page", QUARANTINED)
    executed = client.post("/api/orders/d_po_1002/execute", headers=h).json()
    assert (executed["outcome"], executed["state"]) == ("blocked", "blocked")
    assert "Nexapoint Actuation product page" in " ".join(executed["reasons"])


def test_an_order_for_a_suspended_supplier_is_blocked(client):
    """Suspension is checked by the gate itself, not only through support: put the
    trusted registry under review and Boltline is suspended, though its order still
    has support from Boltline's own page."""
    h = start(client)
    stream(client, "/api/run", h)
    token = h["X-Antidote-Session"]
    graph = get_db().select_graph(client.app.state.store.sessions[token].graph_name)
    assert "Boltline Automation" in memory.set_review(graph, "s_registry", "reported by hand")
    r = client.post("/api/orders/d_po_1001/approve", headers=h).json()
    assert r["state"] == "blocked"
    assert "Boltline Automation is suspended while a document about it is under review" in r["reasons"]


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


def test_memory_pressure_evicts_the_least_recent_session(g):
    readings = iter([None, None, 90 * 2**20, 10 * 2**20])  # MB in use as each session starts
    store = SessionStore(prefix=PREFIX, cap=10, memory_used=lambda: next(readings, None),
                         memory_limit=70 * 2**20)
    client = TestClient(create_app(store))
    first, second = start(client), start(client)
    client.get("/api/state", headers=second)
    third = start(client)                          # 90 MB > 70 MB: first goes, then 10 MB: stop
    assert client.get("/api/state", headers=first).status_code == 401
    assert client.get("/api/state", headers=second).status_code == 200
    assert client.get("/api/state", headers=third).status_code == 200


def test_capability_walkthrough_is_rationed_and_cleans_up(g):
    client = TestClient(create_app(SessionStore(prefix=PREFIX, cap=5), walkthrough=Walkthrough(gap_s=60)))
    events = stream(client, "/api/capabilities", {}, body={})
    assert sum(e["type"] == "capability_result" and e["data"]["ok"] for e in events) == 7
    again = client.post("/api/capabilities")
    assert again.status_code == 429 and again.json()["error"] == "too_soon"
    assert not [n for n in get_db().list_graphs() if n.startswith(Walkthrough.SCRATCH)]


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


def test_a_run_whose_browser_left_does_not_block_the_next(client, monkeypatch):
    """A reload or "Skip to result" leaves the old run waiting, unread, at its last
    event. The next run waits for it to stop counting instead of being refused; a run
    that is still being read keeps the case busy."""
    h = start(client)
    session = client.app.state.store.sessions[h["X-Antidote-Session"]]
    session.run, session.parked = object(), time.monotonic()  # left waiting just now
    assert stream(client, "/api/run", h)[-1]["type"] == "run_complete"
    assert session.run is None

    monkeypatch.setattr(server, "RUN_HANDOVER_S", 0.2)
    session.run, session.parked = object(), None  # still being read
    r = client.post("/api/run", headers=h, json={"pace": 0})
    assert r.status_code == 409 and r.json()["error"] == "busy"


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
