# scripts/rippleedits.py
"""RippleEdits as an external test set (structure only: data/rippleedits/cases.json).

The graph: one trusted knowledge-base source stating every background fact and
every fact the dataset says must not change; one unverified source per case
stating its (counterfactual) edit; and every fact the dataset says follows from
the edit, justified by the edit plus the knowledge-base hop it needs.

For each case, we retract the edit (quarantine its source) and compare with the
ground truth: what loses all support, computed from the dataset's own facts by
the independent reference solver (tests/reference.py), never by Antidote's
engine. Where an edit restates a fact the knowledge base already holds, the
truth is that nothing falls; RippleEdits' labels describe inserting an edit, so
they over-count for a retraction there, and the report says so.
"""
import json
import time

from app import demo, memory, repair, support
from app.db import ROOT, copy_graph, drop_graph
from app.schema import BELIEF, INFERENCE, QUARANTINED, SOURCE, TRUSTED, UNVERIFIED
from tests.reference import least_model

CASES = ROOT / "data" / "rippleedits" / "cases.json"
KB = "s_kb"


def load_cases() -> list[dict]:
    return json.loads(CASES.read_text(encoding="utf-8"))["cases"]


def fact_id(fact) -> str:
    s, relation, o = fact
    return f"b_{s}_{relation.replace('>', '_then_')}_{o}".lower()


def edit_source(case: dict) -> str:
    return f"s_edit_{case['case']}"


def build(g, cases: list[dict]) -> dict:
    """Load every case into one graph. Returns {jid: (target, premises)} and the
    source trust map, i.e. the structure the reference solver needs."""
    demo.reset(g)
    trust, justifications, made = {}, {}, set()
    w = {"recompute": False}

    def belief(fact) -> str:
        fid = fact_id(fact)
        if fid not in made:
            memory.add_belief(g, fid, claim=" ".join(fact), **w)
            made.add(fid)
        return fid

    def justify(jid, target, premises):
        memory.add_justification(g, jid, supports=target, premises=premises, kind=INFERENCE,
                                 reasoning="RippleEdits structure", **w)
        justifications[jid] = (target, premises)

    memory.add_source(g, KB, uri="rippleedits://kb", title="Knowledge base (before the edits)",
                      trust=TRUSTED, origin="kb", **w)
    trust[KB] = TRUSTED
    kb_facts = []
    for c in cases:
        for fact in c["background"] + [x["fact"] for x in c["must_not_change"]]:
            if fact not in kb_facts:
                kb_facts.append(fact)
    for n, fact in enumerate(kb_facts):
        justify(f"j_kb_{n}", belief(fact), [KB])
    for c in cases:
        sid = edit_source(c)
        memory.add_source(g, sid, uri=f"rippleedits://edit/{c['case']}", trust=UNVERIFIED,
                          title=f"Edit {c['case']}", origin=f"edit-{c['case']}", **w)
        trust[sid] = UNVERIFIED
        justify(f"j_edit_{c['case']}", belief(c["edit"]), [sid])
        for n, item in enumerate(c["should_change"]):
            justify(f"j_c{c['case']}_{n}", belief(item["fact"]),
                    [belief(p) for p in item["premises"]])
    support.recompute(g)
    return {"trust": trust, "justifications": justifications, "beliefs": made}


def truth(structure: dict, retracted: str) -> set[str]:
    """Beliefs that lose all support when `retracted` is quarantined (reference solver)."""
    trust = dict(structure["trust"])
    before, _ = least_model(trust, structure["beliefs"], structure["justifications"])
    trust[retracted] = QUARANTINED
    after, _ = least_model(trust, structure["beliefs"], structure["justifications"])
    return {b for b in structure["beliefs"] if before[b] and not after[b]}


def evaluate(g) -> dict:
    """Retract each case's edit in turn with Antidote and with delete-only."""
    cases = load_cases()
    structure = build(g, cases)
    result = {"cases": len(cases), "should_fall": 0, "dataset_labels": 0, "redundant_edits": 0,
              "must_not_change": sum(len(c["must_not_change"]) for c in cases),
              "antidote": {"exact": 0, "residual": 0, "collateral": 0, "repair_ms": 0.0},
              "delete_only": {"exact": 0, "residual": 0, "collateral": 0, "repair_ms": 0.0}}
    for c in cases:
        sid = edit_source(c)
        expected = truth(structure, sid)
        labels = {fact_id(c["edit"])} | {fact_id(x["fact"]) for x in c["should_change"]}
        result["should_fall"] += len(expected)
        result["dataset_labels"] += len(labels)
        result["redundant_edits"] += not expected

        # Antidote: preview, apply (timed), compare, then lift the quarantine.
        p = repair.preview(g, sid)
        started = time.perf_counter()
        repair.apply(g, p, approved_by="benchmark")
        result["antidote"]["repair_ms"] += (time.perf_counter() - started) * 1000
        status = support.status(g)
        fell = {b for b in structure["beliefs"] if not status[b]}
        _score(result["antidote"], fell, expected)
        memory.set_trust(g, sid, UNVERIFIED)

        # Delete-only, on a copy: remove the source, recompute nothing.
        copy = copy_graph(g, f"{g.name}_delete_{c['case']}")
        started = time.perf_counter()
        copy.query(f"MATCH (s:{SOURCE} {{id: $id}}) DETACH DELETE s", {"id": sid})
        result["delete_only"]["repair_ms"] += (time.perf_counter() - started) * 1000
        flags = dict(copy.ro_query(f"MATCH (b:{BELIEF}) RETURN b.id, coalesce(b.valid, false)").result_set)
        _score(result["delete_only"], {b for b in structure["beliefs"] if not flags[b]}, expected)
        drop_graph(copy.name)
    return result


def _score(row: dict, fell: set[str], expected: set[str]) -> None:
    row["exact"] += fell == expected
    row["residual"] += len(expected - fell)
    row["collateral"] += len(fell - expected)


if __name__ == "__main__":
    from app.db import get_graph
    graph = get_graph("bench_rippleedits")
    print(json.dumps(evaluate(graph), indent=2))
    drop_graph(graph.name)
