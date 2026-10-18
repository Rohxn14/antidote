# app/review.py
"""Under review: documents that count for nothing until a person decides.

Three checks run right after the Researcher has read every document, before
any agent concludes or decides anything:

1. the security scan (app/detector.py): hidden instructions aimed at AI;
2. hidden facts: a fact an agent recorded from text a person cannot see on the
   page (in a comment, or styled invisible), whatever its wording;
3. the conflict check (Cypher, below): a document says a supplier is the ONLY
   one holding a certification, while a trusted document says another supplier
   holds it too.

A flagged document goes under review (Source.review). The support engine then
counts it for nothing, so no agent and no order can rest on it, and the
suppliers its facts are about are suspended: the gate blocks any order for
them. A person decides what happens next:

- clear(): a false alarm. The document counts again and its suppliers are back.
- distrust it (repair.preview / repair.apply): its suppliers are blacklisted.

Suspending is automatic, blacklisting is not: the scan matches patterns and can
be wrong, and anyone who can put hidden text on a page about a supplier could
otherwise get that supplier blacklisted.
"""
from app import detector, memory, support
from app.agents.researcher import _text as comparable  # the quote check's own normalising
from app.db import ROOT
from app.schema import (ABOUT, BELIEF, EXTRACTION, JUSTIFICATION, PREMISE, QUARANTINED,
                        SOURCE, SUPPORTS, TRUSTED, VENDOR)

HIDDEN = "hidden instructions aimed at AI"
HIDDEN_FACT = "facts read in text a person can't see"
CONFLICT = "contradicts a trusted document"
REASON = {"conflict": CONFLICT, "hidden_fact": HIDDEN_FACT}  # any other rule: HIDDEN

# Every quote an agent recorded from each document we still read.
QUOTES = f"""
MATCH (s:{SOURCE})<-[:{PREMISE}]-(j:{JUSTIFICATION} {{kind: $extraction}})
WHERE s.trust <> $quarantined AND j.quote IS NOT NULL
RETURN s.id, s.uri, s.text, collect(j.quote)
ORDER BY s.id
"""

# An exclusive claim ("the only ISO 13485-certified supplier") read in a document we
# do not trust, against certification claims for OTHER suppliers read in trusted
# documents that are not under review themselves.
CONFLICTS = f"""
MATCH (x:{BELIEF} {{exclusive: true}})-[:{ABOUT}]->(v:{VENDOR})
MATCH (x)<-[:{SUPPORTS}]-(:{JUSTIFICATION} {{kind: $extraction}})-[:{PREMISE}]->(s:{SOURCE})
WHERE s.trust <> $trusted AND s.trust <> $quarantined
MATCH (y:{BELIEF})-[:{ABOUT}]->(w:{VENDOR})
WHERE y.standard = x.standard AND coalesce(y.exclusive, false) = false AND w <> v
MATCH (y)<-[:{SUPPORTS}]-(:{JUSTIFICATION} {{kind: $extraction}})-[:{PREMISE}]->(t:{SOURCE})
WHERE t.trust = $trusted AND t.review IS NULL
RETURN s.id, x.claim, x.standard, collect(DISTINCT w.name), collect(DISTINCT t.title)
ORDER BY s.id
"""

TITLE = f"MATCH (s:{SOURCE} {{id: $id}}) RETURN s.title"
UNDER_REVIEW = f"""
MATCH (s:{SOURCE}) WHERE s.review IS NOT NULL AND s.trust <> $quarantined
RETURN s.id ORDER BY s.id
"""

QUERIES = {"conflict check": CONFLICTS, "quotes per document": QUOTES,
           "under review": UNDER_REVIEW}


def _listing(items) -> str:
    items = sorted(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def conflicts(g) -> list[detector.Finding]:
    rows = g.ro_query(CONFLICTS, {"extraction": EXTRACTION, "trusted": TRUSTED,
                                  "quarantined": QUARANTINED}).result_set
    return [detector.Finding(sid, "conflict",
                             f'"{claim}" But {_listing(by)} lists {_listing(others)} '
                             f"as holding {standard} too.")
            for sid, claim, standard, others, by in rows]


def hidden_facts(g) -> list[detector.Finding]:
    """Facts an agent took from text a person cannot see: a quote that is on the page
    the agent read, but not on the page as a person sees it."""
    findings = []
    rows = g.ro_query(QUOTES, {"extraction": EXTRACTION, "quarantined": QUARANTINED}).result_set
    for source_id, uri, text, quotes in rows:
        if text is None and uri and (ROOT / uri).is_file():
            text = (ROOT / uri).read_text(encoding="utf-8")
        if not text:
            continue
        seen = comparable(detector.visible_html(text))
        findings += [detector.Finding(source_id, "hidden_fact", detector._clip(q))
                     for q in dict.fromkeys(quotes) if comparable(q) not in seen]
    return findings


def check(g) -> list[dict]:
    """Run the checks and put every flagged document under review.
    Returns one alert per document: {document_id, document_title, findings, suspended}."""
    grouped: dict[str, list[dict]] = {}
    for f in [*detector.scan_sources(g), *hidden_facts(g), *conflicts(g)]:
        grouped.setdefault(f.source_id, []).append({"rule": f.rule, "evidence": f.evidence})
    alerts = []
    for document_id, findings in grouped.items():
        reasons = [REASON.get(f["rule"], HIDDEN) for f in findings]
        reasons = list(dict.fromkeys(reasons))
        reason = reasons[0] if len(reasons) == 1 else ", ".join(reasons[:-1]) + " and " + reasons[-1]
        suspended = memory.set_review(g, document_id, reason, recompute=False)
        title = g.ro_query(TITLE, {"id": document_id}).result_set[0][0]
        alerts.append({"document_id": document_id, "document_title": title,
                       "reason": reason, "findings": findings, "suspended": sorted(suspended)})
    support.recompute(g)
    return alerts


def under_review(g) -> list[str]:
    return [r[0] for r in g.ro_query(UNDER_REVIEW, {"quarantined": QUARANTINED}).result_set]


def clear(g, document_id: str) -> list[str]:
    """A false alarm: the document counts again. Returns the suppliers reinstated."""
    return memory.clear_review(g, document_id)
