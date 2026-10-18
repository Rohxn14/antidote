# scripts/record_run.py
"""Record a real model run of the demo story, verbatim, for replay.

    python -m scripts.record_run        # needs LLM_API_KEY and LLM_MODEL in .env

Runs the real agents through exactly the steps the web app runs (app/runner.py): the
Researcher reads every document, Antidote checks them before anyone decides, the
Researcher concludes and the Buyer decides. Then the two follow-ups a visitor can take
that ask the model again:

    false_alarm   clear the document under review; the Buyer re-plans
    distrust      distrust the page of the supplier the Buyer chose; the order is
                  blocked; the Buyer re-plans (on a copy of the graph after the run)

Every model call is saved verbatim (prompts sent, reply as returned, model reported,
token usage) to data/recordings/<model>_<date>_attempt<N>/exchanges.jsonl, with
provenance.json next to it. Every attempt, kept or failed, is logged in
data/recordings/attempts.log. Nothing in a recording is edited afterwards.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import app.db  # noqa: F401  (loads .env)
from app import gate, llm, recording, repair, review, runner
from app.agents import buyer, researcher
from app.db import copy_graph, drop_graph, get_graph

IST = timezone(timedelta(hours=5, minutes=30))
LOG = recording.DIR / "attempts.log"
PATHS = {
    "run": "the agents read all 10 documents, Antidote checks them, the Researcher concludes "
           "and the Buyer decides",
    "false_alarm": "the document under review is cleared as a false alarm and the Buyer re-plans",
    "distrust": "the page of the supplier the Buyer chose is distrusted, its order is blocked, "
                "and the Buyer re-plans",
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=recording.DIR.parent.parent).stdout.strip()


def order_of(g, events) -> dict | None:
    orders = [e["data"] for e in events if e["type"] == "decision_recorded" and e["data"]["kind"] == "purchase_order"]
    if not orders:
        return None
    o = orders[-1]
    return {"id": o["decision_id"], "summary": o["summary"], "vendor": o["vendor_id"], "state": o["state"]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pause", type=float, default=8.0, help="seconds between calls (provider rate limits)")
    args = ap.parse_args()
    if not llm.configured():
        sys.exit("Set LLM_API_KEY and LLM_MODEL first (see .env.example).")
    recording.DIR.mkdir(parents=True, exist_ok=True)
    attempt = sum(1 for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip()) + 1 if LOG.exists() else 1
    started = datetime.now(IST)
    commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))  # the code that runs
    model = llm.model_name()
    name = f"{model.split('/')[-1]}_{started:%Y-%m-%d}_attempt{attempt}"
    print(f"Attempt {attempt}: recording {model} -> data/recordings/{name}")

    exchanges, path = [], ["run"]

    def keep(ex: llm.Exchange) -> None:
        exchanges.append({
            "index": len(exchanges) + 1, "path": path[0], "name": ex.name,
            "key": recording.key(ex.name, ex.system, ex.user),
            "system_sha256": sha(ex.system), "user_sha256": sha(ex.user),
            "model": ex.model, "fallback": ex.fallback, "usage": ex.usage, "seconds": round(ex.seconds, 2),
            "system": ex.system, "user": ex.user, "content": ex.content})
        print(f"  call {len(exchanges)} [{path[0]}] {ex.name}: {ex.seconds:.1f}s"
              f"{' (plain JSON fallback)' if ex.fallback else ''}", flush=True)
        time.sleep(args.pause)

    client = llm.Live(on_exchange=keep)
    script = runner.StoryScript("live", client=client)
    g = get_graph("antidote_record_run")
    outcome, status = {}, "failed"
    try:
        runner.prepare(g, script)
        events = list(runner.run(g, "live", 0, script))
        outcome["run"] = {
            "under_review": [{"document": e["data"]["document_id"], "reason": e["data"]["reason"],
                              "suspended": e["data"]["suspended"]} for e in events if e["type"] == "security_alert"],
            "refused": [f"{e['data']['agent']}: {e['data']['reason']}" for e in events if e["type"] == "claim_refused"],
            "order": order_of(g, events)}
        first = outcome["run"]["order"]
        print("  run:", json.dumps(outcome["run"])[:600])

        copy = copy_graph(g, "antidote_record_run_distrust")
        try:
            path[0] = "false_alarm"
            for item in outcome["run"]["under_review"]:
                review.clear(g, item["document"])
            replan = list(runner.replan(g, "live", 0, script))
            o = order_of(g, replan)
            if o and o["state"] == "pending_approval":
                o["approve"] = gate.approve(g, o["id"], approver="recorder",
                                            under_review=review.under_review(g)).outcome
            outcome["false_alarm"] = {"order": o,
                                      "refused": [e["data"]["reason"] for e in replan if e["type"] == "claim_refused"]}
            print("  false alarm:", json.dumps(outcome["false_alarm"])[:400])

            path[0] = "distrust"
            if first:
                page = f"s_{first['vendor'].removeprefix('v_')}_page"
                p = repair.preview(copy, page)
                repair.apply(copy, p, approved_by="recorder")
                blocked = [x["id"] for x in p.orders_blocked if gate.recheck(copy, x["id"]).state == "blocked"]
                replan = list(runner.replan(copy, "live", 0, script))
                o = order_of(copy, replan)
                if o and o["state"] == "pending_approval":
                    o["approve"] = gate.approve(copy, o["id"], approver="recorder",
                                                under_review=review.under_review(copy)).outcome
                outcome["distrust"] = {"distrusted": p.sources, "blocked": blocked, "order": o,
                                       "refused": [e["data"]["reason"] for e in replan if e["type"] == "claim_refused"]}
                print("  distrust:", json.dumps(outcome["distrust"])[:400])
        finally:
            drop_graph(copy.name)
        status = "complete"
    except Exception as e:  # a failed attempt is logged, never hidden
        outcome["error"] = f"{type(e).__name__}: {e}"
        print("  FAILED:", outcome["error"])
    finally:
        drop_graph(g.name)

    folder = recording.DIR / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / recording.EXCHANGES).write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in exchanges), encoding="utf-8")
    tokens = sum((e["usage"] or {}).get("total_tokens", 0) for e in exchanges)
    provenance = {
        "model": model, "models_reported": sorted({e["model"] for e in exchanges if e["model"]}),
        "provider": "Groq (OpenAI-compatible chat completions API)",
        "base_url": llm.GROQ_OPENAI_URL, "recorded_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(IST).isoformat(timespec="seconds"),
        "code_commit": commit, "uncommitted_changes": dirty,
        "prompts_sha256": {"extraction": sha(researcher.EXTRACT_SYSTEM), "inference": sha(researcher.INFER_SYSTEM),
                           "decision": sha(buyer.DECIDE_SYSTEM)},
        "temperature": llm.TEMPERATURE,
        "response_format": "strict JSON schema; plain JSON mode only if the provider refuses the schema",
        "fallback_calls": sum(1 for e in exchanges if e["fallback"]),
        "calls": len(exchanges), "total_tokens": tokens,
        "attempt": attempt, "attempts_log": "data/recordings/attempts.log", "status": status,
        "paths": PATHS, "outcome": outcome,
        "exchanges_sha256": recording.sha256_file(folder / recording.EXCHANGES),
        "note": "Replies are saved exactly as the provider returned them; nothing is edited afterwards.",
    }
    (folder / recording.PROVENANCE).write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{started.isoformat(timespec='seconds')}  attempt {attempt}  {model}  {status}  "
                f"{len(exchanges)} calls  {tokens} tokens  -> {name}\n")
    print(f"{status}: {len(exchanges)} calls, {tokens} tokens -> data/recordings/{name}")


if __name__ == "__main__":
    main()
