# scripts/benchmark.py
"""Benchmark: Antidote vs. delete-source-only vs. full rollback.

    python -m scripts.benchmark      # prints a markdown table, writes docs/benchmark.md

Each scenario is built once through app/memory.py, with a GRAPH.COPY snapshot
taken just before the first poisoned source is ingested. Each method then runs
on its own copy of the same finished graph:

  antidote     preview, then the approved apply: quarantine, recompute,
               verify against the preview, write the audit record
  delete_only  DETACH DELETE the poisoned sources; nothing is recomputed and
               orders keep the status they had (no propagation)
  rollback     restore the snapshot taken before the poisoned ingestion

Ground truth comes from the independent reference in tests/reference.py (the
least model of a Horn program), computed from the graph's structure with the
poisoned sources quarantined. It never uses the Cypher engine being measured.

Metrics, over beliefs and decisions:
  residual       active, but unsupported in the ground truth
  collateral     supported in the ground truth, but withdrawn or gone
  stale_auth     unsupported purchase orders that still pass the gate
  repair_ms      from confirmed quarantine to repaired state
"""
import random
import sys
import time
from datetime import date

from app import demo, gate, memory, repair, support
from app.agents import researcher
from app.db import ROOT, copy_graph, drop_graph, get_db
from app.schema import (AUTHORIZED, BELIEF, BUYER, DECIDED, DECISION, EXTRACTION,
                        INFERENCE, JUSTIFICATION, PENDING_APPROVAL, PREMISE,
                        PURCHASE_ORDER, QUARANTINED, RESEARCHER, SHORTLIST, SOURCE,
                        SUPPORTS, TRUSTED, UNVERIFIED, VALID)
from tests.reference import least_model

METHODS = ("antidote", "delete_only", "rollback")


# --- Scenarios ------------------------------------------------------------------------

def build_demo(g, snapshot) -> list[str]:
    """The procurement story from app/demo.py."""
    demo.reset(g)
    demo.register(g)
    for sid, *_ in demo.SOURCES:
        if sid == demo.POISONED:
            snapshot()
        demo.ingest(g, sid)
    researcher.record_inferences(g, demo.fixture("researcher_inference"))
    demo.buy(g)
    return [demo.POISONED]


def build_synthetic(g, snapshot, *, vendors: int, categories: int, poisoned: int,
                    seed: int) -> list[str]:
    """A seeded procurement world: a trusted policy and registry, one page per
    vendor, poisoned pages that fake a certification and undercut prices."""
    rng = random.Random(seed)
    demo.reset(g)
    memory.add_agent(g, "a_researcher", name="Researcher", role=RESEARCHER)
    memory.add_agent(g, "a_buyer", name="Buyer", role=BUYER)
    w = {"recompute": False}

    def source(sid, trust, origin):
        memory.add_source(g, sid, uri=f"synthetic://{sid}", title=sid, trust=trust,
                          origin=origin, **w)

    def extract(belief_id, claim, sid, about=()):
        if not memory.exists(g, BELIEF, belief_id):
            memory.add_belief(g, belief_id, claim=claim, about=about, **w)
        memory.add_justification(g, f"j_{belief_id[2:]}__{sid}", supports=belief_id,
                                 premises=[sid], kind=EXTRACTION, reasoning="synthetic",
                                 quote=claim, agent="a_researcher", **w)

    def conclude(node_id, premises, kind, agent):
        memory.add_justification(g, f"j_{node_id[2:]}", supports=node_id, premises=premises,
                                 kind=kind, reasoning="synthetic", agent=agent, **w)

    cats = [f"c{i}" for i in range(categories)]
    source("s_policy", TRUSTED, "policy")
    source("s_registry", TRUSTED, "registry")
    extract("b_req_cert", "Suppliers must hold the certification.", "s_policy")
    for c in cats:
        extract(f"b_req_qty_{c}", f"We need 100 units of {c}.", "s_policy")

    plan = []
    for i in range(vendors):
        vid = f"v{i:03d}"
        memory.add_vendor(g, vid, name=f"Vendor {i:03d}")
        plan.append({"id": vid, "cats": rng.sample(cats, rng.randint(1, min(3, len(cats)))),
                     "certified": rng.random() < 0.5, "registered": rng.random() < 0.7,
                     "price": rng.randint(400, 600), "poisoned": False})
    for v in rng.sample(plan, poisoned):
        v.update(poisoned=True, certified=False, price=rng.randint(300, 399))

    # The registry is trusted: registered products and real certifications.
    for v in plan:
        if v["registered"]:
            for c in v["cats"]:
                extract(f"b_{v['id']}_makes_{c}", f"{v['id']} makes {c}.", "s_registry", [v["id"]])
        if v["certified"]:
            extract(f"b_{v['id']}_cert", f"{v['id']} is certified.", "s_registry", [v["id"]])

    # Vendor pages in random order; snapshot just before the first poisoned one.
    poisoned_sources, snapped = [], False
    for v in rng.sample(plan, len(plan)):
        sid = f"s_{v['id']}_page"
        if v["poisoned"] and not snapped:
            snapshot()
            snapped = True
        source(sid, UNVERIFIED, f"{v['id']}.example")
        if v["poisoned"]:
            poisoned_sources.append(sid)
        for c in v["cats"]:
            extract(f"b_{v['id']}_makes_{c}", f"{v['id']} makes {c}.", sid, [v["id"]])
            extract(f"b_{v['id']}_offer_{c}", f"{v['id']} sells {c} at ${v['price']}.", sid, [v["id"]])
        if v["certified"] or v["poisoned"]:
            extract(f"b_{v['id']}_cert", f"{v['id']} is certified.", sid, [v["id"]])

    # Researcher inferences (two hops), then the Buyer's decisions.
    candidates = {c: [] for c in cats}
    for v in plan:
        if not (v["certified"] or v["poisoned"]):
            continue
        qualifies = f"b_{v['id']}_qualifies"
        memory.add_belief(g, qualifies, claim=f"{v['id']} qualifies.", about=[v["id"]], **w)
        conclude(qualifies, [f"b_{v['id']}_cert", "b_req_cert"], INFERENCE, "a_researcher")
        for c in v["cats"]:
            cand = f"b_{v['id']}_candidate_{c}"
            memory.add_belief(g, cand, claim=f"{v['id']} is a candidate for {c}.", about=[v["id"]], **w)
            conclude(cand, [qualifies, f"b_{v['id']}_makes_{c}", f"b_{v['id']}_offer_{c}"],
                     INFERENCE, "a_researcher")
            candidates[c].append(v)
    orders = []
    for c in cats:
        for v in candidates[c]:
            d = f"d_short_{v['id']}_{c}"
            memory.add_decision(g, d, kind=SHORTLIST, summary=f"Shortlist {v['id']} for {c}",
                                about=[v["id"]], **w)
            conclude(d, [f"b_{v['id']}_candidate_{c}"], DECIDED, "a_buyer")
        if candidates[c]:
            best = min(candidates[c], key=lambda v: v["price"])
            po = f"d_po_{c}"
            memory.add_decision(g, po, kind=PURCHASE_ORDER, summary=f"PO for {c} from {best['id']}",
                                amount=100 * best["price"], about=[best["id"]], **w)
            conclude(po, [f"b_{best['id']}_candidate_{c}", f"b_req_qty_{c}"], DECIDED, "a_buyer")
            orders.append(po)
    support.recompute(g)
    for po in orders:
        gate.submit(g, po)
    return poisoned_sources


# --- Ground truth (independent of the Cypher engine) ----------------------------------

def ground_truth(g, poisoned: list[str]) -> dict[str, bool]:
    trust = {sid: QUARANTINED if sid in poisoned else t for sid, t in
             g.ro_query(f"MATCH (s:{SOURCE}) RETURN s.id, s.trust").result_set}
    conclusions = {row[0] for row in g.ro_query(
        f"MATCH (n) WHERE n:{BELIEF} OR n:{DECISION} RETURN n.id").result_set}
    justifications = {jid: (target, premises) for jid, target, premises in g.ro_query(
        f"""MATCH (j:{JUSTIFICATION})-[:{SUPPORTS}]->(t)
            MATCH (j)-[:{PREMISE}]->(p)
            RETURN j.id, t.id, collect(p.id)""").result_set}
    valid, _ = least_model(trust, conclusions, justifications)
    return {n: valid[n] for n in conclusions}


def active_flags(g) -> dict[str, bool]:
    """What each method's memory treats as active: the stored flags, as-is."""
    return {i: v for i, v in g.ro_query(
        f"MATCH (n) WHERE n:{BELIEF} OR n:{DECISION} RETURN n.id, coalesce(n.{VALID}, false)"
    ).result_set}


def open_orders(g) -> list[str]:
    return [r[0] for r in g.ro_query(
        f"MATCH (d:{DECISION} {{kind: $po}}) WHERE d.state = $pending RETURN d.id",
        {"po": PURCHASE_ORDER, "pending": PENDING_APPROVAL}).result_set]


# --- Methods ------------------------------------------------------------------------------

def run_antidote(work, poisoned):
    # One human confirmation per source: the preview happens before it and is
    # not timed; the apply (quarantine, recompute, verify, audit) is.
    elapsed = 0.0
    for sid in poisoned:
        p = repair.preview(work, sid)
        started = time.perf_counter()
        repair.apply(work, p, approved_by="benchmark")
        elapsed += time.perf_counter() - started
    passed = [o for o in open_orders(work)
              if gate.approve(work, o, approver="benchmark").state == AUTHORIZED]
    return active_flags(work), passed, elapsed


def run_delete_only(work, poisoned):
    started = time.perf_counter()
    work.query(f"MATCH (s:{SOURCE}) WHERE s.id IN $ids DETACH DELETE s", {"ids": poisoned})
    elapsed = time.perf_counter() - started
    flags = active_flags(work)
    # No propagation: an order passes if its recorded status says it is supported.
    passed = [o for o in open_orders(work) if flags.get(o)]
    return flags, passed, elapsed


def run_rollback(work, snapshot_name):
    db = get_db()
    started = time.perf_counter()
    name = work.name
    work.delete()
    restored = copy_graph(db.select_graph(snapshot_name), name)
    elapsed = time.perf_counter() - started
    flags = active_flags(restored)
    passed = [o for o in open_orders(restored) if flags.get(o)]
    return flags, passed, elapsed


def run_scenario(label: str, build, **kwargs) -> list[dict]:
    db = get_db()
    base = db.select_graph(f"bench_{label}")
    snapshot_name = f"bench_{label}_snapshot"

    def snapshot():
        support.recompute(base)
        drop_graph(snapshot_name)
        copy_graph(base, snapshot_name)

    poisoned = build(base, snapshot, **kwargs)
    truth = ground_truth(base, poisoned)
    size = base.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
    edges = base.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]

    rows = []
    for method in METHODS:
        work_name = f"bench_{label}_{method}"
        drop_graph(work_name)
        work = copy_graph(base, work_name)
        if method == "antidote":
            flags, passed, elapsed = run_antidote(work, poisoned)
        elif method == "delete_only":
            flags, passed, elapsed = run_delete_only(work, poisoned)
        else:
            flags, passed, elapsed = run_rollback(work, snapshot_name)
        rows.append({
            "scenario": label, "nodes": size, "edges": edges, "poisoned": len(poisoned),
            "should_withdraw": sum(1 for t in truth.values() if not t),
            "method": method,
            "residual": sum(1 for n, t in truth.items() if not t and flags.get(n, False)),
            "collateral": sum(1 for n, t in truth.items() if t and not flags.get(n, False)),
            "stale_auth": sum(1 for o in passed if not truth.get(o, False)),
            "repair_ms": elapsed * 1000,
        })
        drop_graph(work_name)
    for name in (base.name, snapshot_name):
        drop_graph(name)
    return rows


def table(rows: list[dict]) -> str:
    lines = ["| Scenario | Graph (nodes / edges) | Method | Residual contamination | "
             "Collateral withdrawal | Stale-action authorization | Repair time (ms) |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['scenario']} ({r['poisoned']} poisoned, {r['should_withdraw']} should go) "
                     f"| {r['nodes']} / {r['edges']} | {r['method']} | {r['residual']} | "
                     f"{r['collateral']} | {r['stale_auth']} | {r['repair_ms']:.0f} |")
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    rows += run_scenario("demo", build_demo)
    rows += run_scenario("synthetic_20", build_synthetic, vendors=20, categories=4,
                         poisoned=2, seed=1)
    rows += run_scenario("synthetic_100", build_synthetic, vendors=100, categories=8,
                         poisoned=5, seed=2)
    result = table(rows)
    print(result)
    (ROOT / "docs" / "benchmark.md").write_text(
        f"# Benchmark results\n\nGenerated by `python -m scripts.benchmark` on {date.today()} "
        "against local FalkorDB (Docker). Repair time depends on the machine and on network "
        "latency to the database.\n\n" + result + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
