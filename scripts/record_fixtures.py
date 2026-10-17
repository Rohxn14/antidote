# scripts/record_fixtures.py
"""Run the real LLM agents through the demo story and save their outputs.

    python -m scripts.record_fixtures

Needs LLM_API_KEY and LLM_MODEL (see .env.example). Uses its own graph
(antidote_record), so the demo graph is untouched. Makes 9 LLM calls:
6 extractions, 1 inference, 1 decision, and 1 decision after the repair.
Outputs go to data/fixtures/live/; replay them with DEMO_FIXTURES=live.
"""
import json
import sys

from app import demo, llm, memory, repair
from app.agents import buyer, researcher
from app.db import drop_graph, get_graph

OUT = demo.ROOT / "data" / "fixtures" / "live"


def save(name: str, data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                                      encoding="utf-8")
    print(f"  saved {name}.json")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not llm.configured():
        sys.exit("Set LLM_API_KEY and LLM_MODEL first (see .env.example).")
    print(f"Recording with model {llm.model_name()}")
    g = get_graph("antidote_record")
    demo.reset(g)
    demo.register(g)

    for sid, uri, title, trust, origin in demo.SOURCES:
        memory.add_source(g, sid, uri=uri, title=title, trust=trust, origin=origin)
        extraction = researcher.extract(g, sid)
        save(f"researcher_{sid}", extraction)
        for note in researcher.record_extractions(g, extraction):
            print(f"    rejected: {note}")

    inference = researcher.infer(g)
    save("researcher_inference", inference)
    for note in researcher.record_inferences(g, inference):
        print(f"    rejected: {note}")

    plan = buyer.decide(g, demo.FIRST_ORDER)
    save("buyer_initial", plan)
    result = buyer.record_plan(g, plan)
    print(f"  first order: {result['order']} -> {result['verdict'] and result['verdict'].state}; "
          f"rejected: {result['rejected'] or 'none'}")

    repair.apply(g, repair.preview(g, demo.POISONED), approved_by="recorder")
    plan = buyer.decide(g, demo.SECOND_ORDER)
    save("buyer_after_repair", plan)
    result = buyer.record_plan(g, plan)
    print(f"  second order: {result['order']} -> {result['verdict'] and result['verdict'].state}; "
          f"rejected: {result['rejected'] or 'none'}")
    drop_graph(g.name)


if __name__ == "__main__":
    main()
