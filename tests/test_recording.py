# tests/test_recording.py
"""The recorded real model run (data/recordings/) replays through the agents' own code:
every prompt is built from the same memory and gets the reply the model really gave
to it. The replay must reproduce what happened when it was recorded, and a step that
was never recorded must say so instead of inventing an answer."""
import json

import pytest
from fastapi.testclient import TestClient

from api.server import create_app
from api.session_store import SessionStore
from app import recording, repair, review, runner
from tests.test_api import PREFIX, start

REC = recording.default()
pytestmark = pytest.mark.skipif(REC is None, reason="no recorded model run")


class Counting:
    """The recording, counting which recorded replies were used."""

    def __init__(self, rec):
        self.rec, self.used = rec, []
        self.model = rec.model

    def complete_json(self, system, user, schema, name):
        self.used.append(recording.key(name, system, user))
        return self.rec.complete_json(system, user, schema, name)


def _order(events):
    orders = [e["data"] for e in events if e["type"] == "decision_recorded" and e["data"]["kind"] == "purchase_order"]
    return {"id": orders[-1]["decision_id"], "summary": orders[-1]["summary"],
            "vendor": orders[-1]["vendor_id"]} if orders else None


def _run(g, client):
    script = runner.StoryScript("recorded", client=client)
    runner.prepare(g, script)
    return script, list(runner.run(g, "recorded", 0, script))


def test_the_recording_is_intact_and_complete():
    p = REC.provenance
    assert REC.intact(), "exchanges.jsonl differs from the hash in provenance.json"
    assert p["status"] == "complete" and p["calls"] == len(REC.exchanges)
    assert {"model", "provider", "recorded_at", "code_commit", "prompts_sha256", "temperature",
            "attempt", "exchanges_sha256"} <= set(p)
    # The prompts today are the prompts the model answered; otherwise the replay would miss.
    from app.agents import buyer, researcher
    from scripts.record_run import sha
    assert p["prompts_sha256"] == {"extraction": sha(researcher.EXTRACT_SYSTEM),
                                   "inference": sha(researcher.INFER_SYSTEM),
                                   "decision": sha(buyer.DECIDE_SYSTEM)}


def test_replay_reproduces_the_recorded_run_using_every_recorded_call(g):
    client = Counting(REC)
    _, events = _run(g, client)
    assert not [e for e in events if e["type"] == "error"]
    expected = REC.provenance["outcome"]["run"]
    alerts = [e["data"]["document_id"] for e in events if e["type"] == "security_alert"]
    assert alerts == [x["document"] for x in expected["under_review"]]
    order = _order(events)
    assert order and (order["vendor"], order["summary"]) == (expected["order"]["vendor"], expected["order"]["summary"])
    run_keys = [e["key"] for e in REC.exchanges if e["path"] == "run"]
    assert client.used == run_keys  # the same questions, in the same order


def test_replay_reproduces_both_recorded_follow_ups(g):
    script, events = _run(g, REC)
    if "false_alarm" in REC.provenance["outcome"]:
        copy_name = f"{g.name}_distrust"
        from app.db import copy_graph, drop_graph
        copy = copy_graph(g, copy_name)
        try:
            for item in REC.provenance["outcome"]["run"]["under_review"]:
                review.clear(g, item["document"])
            replan = list(runner.replan(g, "recorded", 0, script))
            expected = REC.provenance["outcome"]["false_alarm"]["order"]
            assert (_order(replan) or {}).get("summary") == (expected or {}).get("summary")

            if "distrust" in REC.provenance["outcome"]:
                d = REC.provenance["outcome"]["distrust"]
                p = repair.preview(copy, d["distrusted"][0])
                repair.apply(copy, p, approved_by="test")
                replan = list(runner.replan(copy, "recorded", 0, script))
                assert (_order(replan) or {}).get("summary") == (d["order"] or {}).get("summary")
        finally:
            drop_graph(copy_name)


def test_a_step_that_was_never_recorded_says_so(g):
    script, _ = _run(g, REC)
    repair.apply(g, repair.preview(g, "s_registry"), approved_by="test")  # nobody recorded this
    with pytest.raises(recording.NotRecorded, match="never reached this step"):
        list(runner.replan(g, "recorded", 0, script))


def test_the_recorded_mode_over_http(g):
    client = TestClient(create_app(SessionStore(prefix=PREFIX, cap=5)))
    health = client.get("/api/health").json()
    assert health["recording"]["model"] == REC.model and health["recording"]["calls"] == len(REC.exchanges)
    h = start(client)
    with client.stream("POST", "/api/run", headers=h, json={"mode": "recorded", "pace": 0}) as r:
        events = [json.loads(line) for line in r.iter_lines() if line]
    assert (_order([{"type": e["type"], "data": e["data"]} for e in events]) or {}).get("summary") == \
        REC.provenance["outcome"]["run"]["order"]["summary"]
    if "false_alarm" in REC.provenance["outcome"]:
        doc = REC.provenance["outcome"]["run"]["under_review"][0]["document"]
        client.post("/api/review/clear", headers=h, json={"document_id": doc})
        # The browser may not know how the run got its answers (a reload); the server does.
        with client.stream("POST", "/api/replan", headers=h, json={"pace": 0}) as r:
            replan = [json.loads(line) for line in r.iter_lines() if line]
        assert not [e for e in replan if e["type"] == "error"]
        assert (_order(replan) or {}).get("summary") == \
            (REC.provenance["outcome"]["false_alarm"]["order"] or {}).get("summary")
