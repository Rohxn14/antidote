# scripts/import_rippleedits.py
"""Import the STRUCTURE of 15 RippleEdits cases as an external test set.

    python -m scripts.import_rippleedits PATH/TO/RippleEdits/data/benchmark

RippleEdits (Cohen, Biran, Yoran, Globerson, Geva, "Evaluating the Ripple
Effects of Knowledge Editing in Language Models", TACL 2024; MIT licence,
Copyright (c) 2023 Eden Biran) pairs a factual edit with facts that should
change because of it and facts that must not.

Its facts are Wikidata facts about real people, and its edits are deliberately
false, so this script keeps only the structure: every entity id and every name
becomes a placeholder (E1, E2, ... and aliases A1, A2, ...). Relation names are
kept. The output, data/rippleedits/cases.json, is what the benchmark and the
tests use; the dataset itself is not needed after import.

Selection (deterministic): from each subset file, in file order, the first 5
cases that have a logical-generalization test, a multi-hop test
(compositionality I or II) and a must-not-change test (relation specificity or
forgetfulness).
"""
import json
import sys
from pathlib import Path

from app.db import ROOT

OUT = ROOT / "data" / "rippleedits" / "cases.json"
SUBSETS = ("popular", "random", "recent")
PER_SUBSET = 5
NOTICE = ("Structure derived from RippleEdits (Cohen, Biran, Yoran, Globerson, Geva, TACL 2024), "
          "https://github.com/edenbiran/RippleEdits. MIT License, Copyright (c) 2023 Eden Biran. "
          "Permission is hereby granted, free of charge, to any person obtaining a copy of this "
          "software and associated documentation files, to deal in the Software without "
          "restriction, subject to including this copyright and permission notice. Entity ids, "
          "names and aliases are replaced with placeholders; only relations and the dependency "
          "structure are kept.")


class Anonymiser:
    def __init__(self):
        self.entities, self.aliases = {}, {}

    def entity(self, qid: str) -> str:
        return self.entities.setdefault(qid, f"E{len(self.entities) + 1}")

    def alias(self, subject: str, surface: str) -> str:
        return self.aliases.setdefault((subject, surface), f"A{len(self.aliases) + 1}")


def _ids(value) -> list[str]:
    return value if isinstance(value, list) else [value]


def eligible(case: dict) -> bool:
    return bool(case.get("Logical_Generalization")
                and (case.get("Compositionality_I") or case.get("Compositionality_II"))
                and (case.get("Relation_Specificity") or case.get("Forgetfulness")))


def convert(case: dict, anon: Anonymiser, number: int, subset: str) -> dict:
    e = case["edit"]
    S, R, T = anon.entity(e["subject_id"]), e["relation"], anon.entity(e["target_id"])
    edit = [S, R, T]
    change, keep, background = [], [], []

    def add(bucket, category, fact, premises=None):
        item = {"category": category, "fact": fact}
        if premises is not None:
            item["premises"] = premises
        if item not in bucket:
            bucket.append(item)

    for t in case.get("Logical_Generalization", []):
        for q in t["test_queries"]:
            for s in _ids(q["subject_id"]):
                for o in q["target_ids"]:
                    add(change, "Logical_Generalization",
                        [anon.entity(s), q["relation"], anon.entity(o)], [edit])
    for t in case.get("Compositionality_I", []):      # S -R-> T -R2-> X
        for cq in t.get("condition_queries", []):
            for x in cq["target_ids"]:
                hop = [T, cq["relation"], anon.entity(x)]
                if hop not in background:
                    background.append(hop)
                add(change, "Compositionality_I", [S, f"{R}>{cq['relation']}", anon.entity(x)],
                    [edit, hop])
    for t in case.get("Compositionality_II", []):     # Z -R0-> S -R-> T
        for cq in t.get("condition_queries", []):
            for z in _ids(cq["subject_id"]):
                hop = [anon.entity(z), cq["relation"], S]
                if hop not in background:
                    background.append(hop)
                add(change, "Compositionality_II", [anon.entity(z), f"{cq['relation']}>{R}", T],
                    [hop, edit])
    for t in case.get("Subject_Aliasing", []):        # the same fact under another name
        for q in t["test_queries"]:
            alias = anon.alias(S, q["prompt"])
            hop = [alias, "ALIAS_OF", S]
            if hop not in background:
                background.append(hop)
            add(change, "Subject_Aliasing", [alias, R, T], [edit, hop])
    for category in ("Relation_Specificity", "Forgetfulness"):
        for t in case.get(category, []):
            for q in t["test_queries"]:
                for s in _ids(q["subject_id"]):
                    for o in q["target_ids"]:
                        add(keep, category, [anon.entity(s), q["relation"], anon.entity(o)])
    return {"case": number, "subset": subset, "edit": edit, "should_change": change,
            "must_not_change": keep, "background": background}


def main() -> None:
    folder = Path(sys.argv[1])
    anon, cases = Anonymiser(), []
    for subset in SUBSETS:
        data = json.loads((folder / f"{subset}.json").read_text(encoding="utf-8"))
        picked = [c for c in data if eligible(c)][:PER_SUBSET]
        for case in picked:
            cases.append(convert(case, anon, len(cases) + 1, subset))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"notice": NOTICE, "selection": __doc__.split("Selection")[1].strip(),
                               "cases": cases}, indent=1) + "\n", encoding="utf-8")
    n_change = sum(len(c["should_change"]) for c in cases)
    n_keep = sum(len(c["must_not_change"]) for c in cases)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(cases)} cases, {n_change} facts that should "
          f"change, {n_keep} that must not, {len(anon.entities)} entities, {len(anon.aliases)} aliases")


if __name__ == "__main__":
    main()
