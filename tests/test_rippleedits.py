# tests/test_rippleedits.py
"""The external test set: retracting each RippleEdits case's edit withdraws
exactly what the dataset's facts say loses all support (reference solver),
and nothing the dataset says must not change."""
from app import repair
from app.schema import BELIEF
from scripts import rippleedits


def test_every_case_is_repaired_exactly(g):
    cases = rippleedits.load_cases()
    structure = rippleedits.build(g, cases)
    must_stay = {rippleedits.fact_id(x["fact"]) for c in cases for x in c["must_not_change"]}
    for case in cases:
        sid = rippleedits.edit_source(case)
        p = repair.preview(g, sid)
        lost = {n["id"] for n in p.lost if n["label"] == BELIEF}
        assert lost == rippleedits.truth(structure, sid), f"case {case['case']}"
        assert not lost & must_stay, f"case {case['case']}"
        repair.discard(p)


def test_no_real_identities_in_the_committed_data():
    import re
    assert not re.search(r"\bQ\d+\b", rippleedits.CASES.read_text(encoding="utf-8"))
    facts = []
    for c in rippleedits.load_cases():
        facts += [c["edit"], *c["background"], *(x["fact"] for x in c["should_change"]),
                  *(x["fact"] for x in c["must_not_change"])]
    for subject, relation, obj in facts:  # placeholders only; relations are generic
        assert re.fullmatch(r"[EA]\d+", subject) and re.fullmatch(r"E\d+", obj)
        assert re.fullmatch(r"[A-Z_>]+", relation)
