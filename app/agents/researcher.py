# app/agents/researcher.py
"""The Researcher agent: reads sources and records beliefs with justifications.

The LLM proposes (extract, infer); this module checks and records
(record_extractions, record_inferences). Every extracted claim must carry an
exact quote that really appears in the source, and every inference must cite
existing belief IDs. All writes go through app/memory.py.
"""
import json
import re

from app import llm, memory, support
from app.db import ROOT
from app.schema import BELIEF, EXTRACTION, INFERENCE, SOURCE, VENDOR

AGENT_ID = "a_researcher"
BELIEF_ID = re.compile(r"^b_[a-z0-9_]{2,60}$")
TAG = re.compile(r"<[^>]+>")


def _normalise(text: str) -> str:
    return " ".join(text.split())


def _raw_source(g, source_id: str) -> str:
    rows = g.ro_query(f"MATCH (s:{SOURCE} {{id: $id}}) RETURN s.uri", {"id": source_id}).result_set
    if not rows:
        raise ValueError(f"source {source_id!r} not found")
    return (ROOT / rows[0][0]).read_text(encoding="utf-8")


def source_text(g, source_id: str) -> str:
    """The text an agent sees: the document with tags removed. HTML comments
    are kept, because an agent reading the raw page sees them too (that is
    exactly how a hidden instruction reaches it)."""
    raw = _raw_source(g, source_id).replace("<!--", " ").replace("-->", " ")
    return _normalise(TAG.sub(" ", raw))


def _vendors(g) -> list[dict]:
    rows = g.ro_query(f"MATCH (v:{VENDOR}) RETURN v.id, v.name ORDER BY v.id").result_set
    return [{"id": i, "name": n} for i, n in rows]


# --- LLM side: propose -------------------------------------------------------------

EXTRACT_SYSTEM = """You are the Researcher agent of a procurement team. You read one \
source document and record the factual claims it makes about suppliers and about \
our requirements, so that other agents can rely on them.
Rules:
- Every claim needs an exact quote copied verbatim from the document text \
(one sentence or one table row, without HTML tags).
- If an existing belief already states the same claim, reuse its id. Otherwise \
create an id like b_<vendor>_<topic> (lowercase letters, digits, underscores), \
or b_req_<topic> for our own requirements.
- vendor must be one of the given vendor ids, or null for general requirements.
- Record what the document states; do not judge whether it is true."""

EXTRACT_SCHEMA = llm.obj({"claims": {"type": "array", "items": llm.obj({
    "belief": llm.STRING, "vendor": llm.NULLABLE_STRING, "claim": llm.STRING,
    "quote": llm.STRING, "reasoning": llm.STRING})}})

INFER_SYSTEM = """You are the Researcher agent of a procurement team. From the \
beliefs in shared memory, record which suppliers meet our procurement requirements.
Rules:
- Each conclusion must cite as premises the ids of ALL beliefs it depends on \
(for example the supplier's certification belief AND the requirement belief).
- Only cite ids from the list. Name conclusions b_<vendor>_qualifies.
- Do not conclude anything the listed beliefs do not support."""

INFER_SCHEMA = llm.obj({"inferences": {"type": "array", "items": llm.obj({
    "belief": llm.STRING, "vendor": llm.NULLABLE_STRING, "claim": llm.STRING,
    "premises": llm.STRINGS, "reasoning": llm.STRING})}})


def extract(g, source_id: str) -> dict:
    """Ask the LLM what one source claims. Returns an extraction (fixture format)."""
    existing = [{"id": b["id"], "claim": b["claim"]} for b in memory.valid_beliefs(g)]
    user = (f"Known vendors: {json.dumps(_vendors(g))}\n"
            f"Existing beliefs: {json.dumps(existing)}\n"
            f"Source id: {source_id}\nDocument:\n<<<\n{_raw_source(g, source_id)}\n>>>")
    result = llm.complete_json(EXTRACT_SYSTEM, user, EXTRACT_SCHEMA, "extraction")
    return {"source_id": source_id, "model": llm.model_name(), "claims": result["claims"]}


def infer(g) -> dict:
    """Ask the LLM which suppliers qualify, from currently valid beliefs only."""
    beliefs = memory.valid_beliefs(g)
    user = f"Beliefs in shared memory: {json.dumps(beliefs)}"
    result = llm.complete_json(INFER_SYSTEM, user, INFER_SCHEMA, "inference")
    return {"model": llm.model_name(), "inferences": result["inferences"]}


# --- Code side: check and record -----------------------------------------------------

def record_extractions(g, extraction: dict) -> list[str]:
    """Record the claims extracted from one source.
    Returns notes for claims that were rejected (nothing is written for them)."""
    source_id = extraction["source_id"]
    text = source_text(g, source_id)
    rejected = []
    for c in extraction["claims"]:
        belief_id = c["belief"]
        if not BELIEF_ID.match(belief_id):
            rejected.append(f"{belief_id}: not a valid belief id")
            continue
        if _normalise(c["quote"]) not in text:
            rejected.append(f"{belief_id}: quote not found in {source_id}")
            continue
        try:
            # Same claim seen in another source: corroborate, don't duplicate.
            if not memory.exists(g, BELIEF, belief_id):
                memory.add_belief(g, belief_id, claim=c["claim"],
                                  about=[c["vendor"]] if c.get("vendor") else [],
                                  recompute=False)
            memory.add_justification(
                g, f"j_{belief_id[2:]}__{source_id}", supports=belief_id,
                premises=[source_id], kind=EXTRACTION, reasoning=c["reasoning"],
                quote=c["quote"], model=extraction.get("model"), agent=AGENT_ID,
                recompute=False)
        except memory.WriteRejected as e:
            rejected.append(str(e))
    support.recompute(g)
    return rejected


def record_inferences(g, inference: dict) -> list[str]:
    """Record conclusions drawn from existing beliefs (premises must be beliefs)."""
    rejected = []
    for n, item in enumerate(inference["inferences"]):
        belief_id = item["belief"]
        premises = item["premises"]
        if not BELIEF_ID.match(belief_id) or not all(BELIEF_ID.match(p) for p in premises):
            rejected.append(f"{belief_id}: inferences may only cite belief ids")
            continue
        try:
            if not memory.exists(g, BELIEF, belief_id):
                memory.add_belief(g, belief_id, claim=item["claim"],
                                  about=[item["vendor"]] if item.get("vendor") else [],
                                  recompute=False)
            memory.add_justification(
                g, f"j_{belief_id[2:]}__inference_{n}", supports=belief_id,
                premises=premises, kind=INFERENCE, reasoning=item["reasoning"],
                model=inference.get("model"), agent=AGENT_ID, recompute=False)
        except memory.WriteRejected as e:
            rejected.append(str(e))
    support.recompute(g)
    return rejected
