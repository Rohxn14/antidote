# scripts/seed_demo.py
"""Seed the demo graph, or play the whole story in the terminal.

    python -m scripts.seed_demo             # Act 1: ends with PO-1001 pending approval
    python -m scripts.seed_demo --story     # Act 1, then detection, preview, repair, gate
    python -m scripts.seed_demo --if-empty  # seed only if the graph has no data (start-up)
"""
import argparse
import sys

from app import demo, support
from app.agents.buyer import order_label
from app.db import get_graph


def act1(g) -> None:
    print("== Act 1: normal work")
    result = demo.seed(g)
    beliefs = sum(1 for k, v in support.status(g).items() if k.startswith("b_"))
    print(f"Researcher recorded {beliefs} beliefs from {len(demo.SOURCES)} sources; "
          f"rejected: {result['rejected'] or 'none'}")
    print(f"Buyer shortlisted: {', '.join(result['shortlisted'])}")
    v = result["verdict"]
    print(f"Buyer drafted {order_label(result['order'])}; gate: {v.outcome} "
          f"({'; '.join(v.reasons)}) -> {v.state}")


def rest_of_story(g) -> None:
    print("\n== Detection (rule-based; a human confirms)")
    for f in demo.detect(g):
        print(f"  {f.source_id}: {f.rule}: {f.evidence}")

    print(f"\n== Preview: quarantine {demo.POISONED} on a copy of the graph")
    p = demo.preview(g)
    print(f"  based on revision {p.base_revision}, copy: {p.graph_name}")
    for n in p.lost:
        print(f"  loses support: {n['id']}: {n['text']}")
    for s in p.survived:
        print(f"  survives:      {s['id']} via {s['kept_by']} (premises {s['premises']})")
    for o in p.orders_blocked:
        print(f"  gate will block: {order_label(o['id'])} ({o['state']})")

    print(f"\n== Repair approved by {demo.MANAGER} (memory only, not the purchase)")
    print(f"  applied and verified against the preview: {demo.approve_repair(g, p)}")

    print(f"\n== {demo.MANAGER} now approves {order_label(demo.FIRST_ORDER)}")
    v = demo.approve_order(g, demo.FIRST_ORDER)
    print(f"  gate: {v.outcome} ({'; '.join(v.reasons)}) -> {v.state}")

    print("\n== The Buyer re-decides on clean memory")
    result = demo.redecide(g)
    v = result["verdict"]
    print(f"  {order_label(result['order'])}: gate: {v.outcome} ({'; '.join(v.reasons)}) -> {v.state}")
    v = demo.approve_order(g, demo.SECOND_ORDER)
    print(f"  {demo.MANAGER} approves it -> {v.state}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--story", action="store_true", help="play the whole story")
    parser.add_argument("--if-empty", action="store_true", help="seed only if empty")
    parser.add_argument("--graph", help="graph name (default: FALKORDB_GRAPH or antidote)")
    args = parser.parse_args()

    g = get_graph(args.graph)
    if args.if_empty and demo.is_seeded(g):
        print(f"graph {g.name!r} already has data; nothing to do")
        return
    act1(g)
    if args.story:
        rest_of_story(g)


if __name__ == "__main__":
    main()
