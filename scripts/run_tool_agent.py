# scripts/run_tool_agent.py
"""Run the Buyer as a tool-using agent over Antidote's MCP tools, after the repair.

    python -m scripts.run_tool_agent

Needs LLM_API_KEY and LLM_MODEL (a Groq model that supports tool use). Seeds
its own graph (antidote_agent), quarantines the poisoned page as a human
would, then lets the LLM choose which MCP tools to call. The transcript is
printed and saved to data/fixtures/live/tool_agent.json for the UI.
"""
import asyncio
import json
import logging
import sys

from app import demo, llm, repair
from app.agents import tool_agent
from app.db import drop_graph, get_graph
from app.mcp_server import create_server

OUT = demo.ROOT / "data" / "fixtures" / "live" / "tool_agent.json"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # no per-request log lines
    if not llm.configured():
        sys.exit("Set LLM_API_KEY and LLM_MODEL first (see .env.example).")
    g = get_graph("antidote_agent")
    demo.seed(g)
    repair.apply(g, repair.preview(g, demo.POISONED), approved_by=demo.MANAGER)
    demo.approve_order(g, demo.FIRST_ORDER)  # the gate blocks it

    transcript = asyncio.run(tool_agent.run(create_server(lambda: g)))
    for step in transcript["steps"]:
        print(f"-> {step['tool']}({json.dumps(step['arguments'])})")
    print(f"\nFinal answer:\n{transcript['final']}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(transcript, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nsaved {OUT.relative_to(demo.ROOT)}")
    drop_graph(g.name)


if __name__ == "__main__":
    main()
