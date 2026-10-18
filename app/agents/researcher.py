# app/agents/researcher.py
"""The Researcher agent: reads sources and records beliefs with justifications.

The LLM proposes (extract, infer); this module checks and records
(record_extractions, record_inferences). Every extracted claim must carry a
quote whose text really appears in the source, every inference must cite
existing belief IDs, and an ID may only be reused for a claim that does not
contradict it. All writes go through app/memory.py.
"""
import json
import re

from app import llm, memory, support
from app.db import ROOT
from app.schema import BELIEF, EXTRACTION, INFERENCE, SOURCE, VENDOR

AGENT_ID = "a_researcher"
BELIEF_ID = re.compile(r"^b_[a-z0-9_]{2,60}$")
TAG = re.compile(r"<[^>]+>")
DIGITS = re.compile(r"\d+")
# Typographic variants an LLM may swap when copying text: dashes, curly
# quotes and the no-break space become their plain forms.
TYPOGRAPHY = str.maketrans({chr(0x2010): "-", chr(0x2011): "-", chr(0x2012): "-",
                            chr(0x2013): "-", chr(0x2014): "-", chr(0x2018): "'",
                            chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"',
                            chr(0x00A0): " "})


def numbers(text: str | None) -> set[str]:
    """Every run of digits: 'ISO 13485:2016, $480' -> {'13485', '2016', '480'}."""
    return set(DIGITS.findall(text or ""))


def _text(fragment: str) -> str:
    """The comparable text of a page or a quote: comment markers and tags
    removed, typography unified, whitespace collapsed. Both sides of the quote
    check go through this, so a quote copied with its HTML tags still matches."""
    fragment = fragment.replace("<!--", " ").replace("-->", " ")
    return " ".join(TAG.sub(" ", fragment).translate(TYPOGRAPHY).split())


def _raw_source(g, source_id: str) -> str:
    """The document: text stored on the Source node, or else the file at its uri."""
    rows = g.ro_query(f"MATCH (s:{SOURCE} {{id: $id}}) RETURN s.uri, s.text",
                      {"id": source_id}).result_set
    if not rows:
        raise ValueError(f"source {source_id!r} not found")
    uri, text = rows[0]
    return text if text is not None else (ROOT / uri).read_text(encoding="utf-8")


def source_text(g, source_id: str) -> str:
    """The text an agent sees. HTML comments are kept, because an agent reading
    the raw page sees them too (that is exactly how a hidden instruction
    reaches it)."""
    return _text(_raw_source(g, source_id))


def conflicting_specifics(a: str, b: str) -> bool:
    """True if two claims disagree on numbers: neither claim's set of numbers
    contains the other's (ISO 13485 vs ISO 9001, $480 vs $520, 2 vs 3 weeks).
    A paraphrase that only adds a detail, like a certificate number or the
    year of a standard (ISO 13485 vs ISO 13485:2016), is fine."""
    na, nb = numbers(a), numbers(b)
    return not (na <= nb or nb <= na)


def _vendors(g) -> list[dict]:
    rows = g.ro_query(f"MATCH (v:{VENDOR}) RETURN v.id, v.name ORDER BY v.id").result_set
    return [{"id": i, "name": n} for i, n in rows]


def beliefs_for_prompt(g) -> list[dict]:
    """Valid beliefs as agents see them; `vendor` is a vendor id, never a name."""
    return [{"id": b["id"], "claim": b["claim"], "vendor": b["vendor_id"]}
            for b in memory.valid_beliefs(g)]


# --- LLM side: propose -------------------------------------------------------------

EXTRACT_SYSTEM = """You are the Researcher agent of a procurement team. You read one \
source document and record every factual claim it makes about suppliers (what they \
make, certifications, prices, lead times) and about our own requirements, so that \
other agents can rely on them.
Rules:
- Every claim needs a quote copied verbatim from the document (one sentence or one \
table row). The quote must contain every number the claim states: if a number (a model \
number, a price, a date) is not in the quote, leave it out of the claim.
- Use one id per distinct fact, named after the fact: b_<vendor>_<topic>, for example \
b_vantor_iso13485, b_vantor_iso9001, b_vantor_price, b_vantor_makes_servos; \
b_req_<topic> for our own requirements. Lowercase letters, digits and underscores.
- Reuse an existing belief id ONLY if this document states exactly the same fact. \
Claims that differ in any specific (a different standard, price, quantity, date or \
lead time) must get a different id.
- vendor is a vendor id from the list (for example v_vantor), or null for our requirements.
- standard: for a claim that a supplier holds a certification, the standard (for example "ISO 13485"); otherwise null. exclusive: true only if the claim says that supplier is the ONLY one holding it.
- Record what the document states; do not judge whether it is true."""

VENDOR_FIELD = llm.described(llm.NULLABLE_STRING,
                             "a vendor id from the list, e.g. v_vantor; null for our requirements")
EXTRACT_SCHEMA = llm.obj({"claims": {"type": "array", "items": llm.obj({
    "belief": llm.described(llm.STRING, "the belief id, e.g. b_vantor_iso13485"),
    "vendor": VENDOR_FIELD,
    "claim": llm.described(llm.STRING, "the fact as one full sentence"),
    "quote": llm.described(llm.STRING, "text copied verbatim from the document"),
    "standard": llm.described(llm.NULLABLE_STRING,
                              "the certification standard the claim says the supplier holds, "
                              "e.g. ISO 13485; null if the claim is not about a certification"),
    "exclusive": llm.described({"type": "boolean"},
                               "true only if the claim says this supplier is the ONLY one holding it"),
    "reasoning": llm.described(llm.STRING, "why the quote supports the claim")})}})

INFER_SYSTEM = """You are the Researcher agent of a procurement team. From the \
beliefs in shared memory, record which suppliers meet our procurement requirements.
Rules:
- Each conclusion must cite as premises the ids of ALL beliefs it depends on \
(for example the supplier's certification belief AND the requirement belief).
- Only cite ids from the list. Name conclusions b_<vendor>_qualifies.
- vendor is a vendor id from the list (for example v_boltline), never a name.
- Do not conclude anything the listed beliefs do not support."""

INFER_SCHEMA = llm.obj({"inferences": {"type": "array", "items": llm.obj({
    "belief": llm.described(llm.STRING, "the id of the new conclusion, e.g. b_boltline_qualifies"),
    "vendor": VENDOR_FIELD,
    "claim": llm.described(llm.STRING, "the conclusion as one full sentence, e.g. "
                                       "'Boltline Automation meets all our supplier requirements.'"),
    "premises": llm.described(llm.STRINGS, "ids of ALL beliefs the conclusion depends on"),
    "reasoning": llm.described(llm.STRING, "why the premises imply the conclusion")})}})


def extract(g, source_id: str) -> dict:
    """Ask the LLM what one source claims. Returns an extraction (fixture format)."""
    existing = [{"id": b["id"], "claim": b["claim"]} for b in beliefs_for_prompt(g)]
    user = (f"Known vendors: {json.dumps(_vendors(g))}\n"
            f"Existing beliefs: {json.dumps(existing)}\n"
            f"Source id: {source_id}\nDocument:\n<<<\n{_raw_source(g, source_id)}\n>>>")
    result = llm.complete_json(EXTRACT_SYSTEM, user, EXTRACT_SCHEMA, "extraction")
    return {"source_id": source_id, "model": llm.model_name(), "claims": result["claims"]}


def infer(g) -> dict:
    """Ask the LLM which suppliers qualify, from currently valid beliefs only."""
    user = (f"Known vendors: {json.dumps(_vendors(g))}\n"
            f"Beliefs in shared memory: {json.dumps(beliefs_for_prompt(g))}")
    result = llm.complete_json(INFER_SYSTEM, user, INFER_SCHEMA, "inference")
    return {"model": llm.model_name(), "inferences": result["inferences"]}


# --- Code side: check and record -----------------------------------------------------

def _resolve(g, vendor) -> tuple[bool, list[str]]:
    """(ok, about) for an optional vendor given by id or exact name."""
    if not vendor:
        return True, []
    vendor_id = memory.resolve_vendor(g, vendor)
    return vendor_id is not None, [vendor_id] if vendor_id else []


def _merge_conflict(g, belief_id: str, claim: str) -> str | None:
    """A note if `belief_id` exists and means something that contradicts `claim`."""
    existing = memory.belief_claim(g, belief_id)
    if existing is not None and conflicting_specifics(existing, claim):
        return (f"{belief_id}: already means {existing!r}; {claim!r} differs in its "
                "specifics and needs its own id")
    return None


def record_extractions(g, extraction: dict) -> list[str]:
    """Record the claims extracted from one source.
    Returns notes for claims that were rejected (nothing is written for them)."""
    source_id = extraction["source_id"]
    text = source_text(g, source_id)
    rejected = []
    for c in extraction["claims"]:
        belief_id = c["belief"]
        ok, about = _resolve(g, c.get("vendor"))
        conflict = _merge_conflict(g, belief_id, c["claim"])
        if not BELIEF_ID.match(belief_id):
            rejected.append(f"{belief_id}: not a valid belief id")
        elif _text(c["quote"]) not in text:
            rejected.append(f"{belief_id}: quote not found in {source_id}")
        elif numbers(c["claim"]) - numbers(c["quote"]):
            # A real quote with an unfaithful claim: e.g. "ISO 13485" claimed
            # from a trusted registry row that says "ISO 9001:2015".
            rejected.append(f"{belief_id}: the claim states "
                            f"{sorted(numbers(c['claim']) - numbers(c['quote']))}, "
                            "which its quote does not")
        elif not ok:
            rejected.append(f"{belief_id}: unknown vendor {c.get('vendor')!r}")
        elif conflict:
            rejected.append(conflict)
        else:
            try:
                # Same fact seen in another source: corroborate, don't duplicate.
                if not memory.exists(g, BELIEF, belief_id):
                    memory.add_belief(g, belief_id, claim=c["claim"], about=about,
                                      standard=c.get("standard"),
                                      exclusive=bool(c.get("exclusive")), recompute=False)
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
        ok, about = _resolve(g, item.get("vendor"))
        conflict = _merge_conflict(g, belief_id, item["claim"])
        stated = set().union(*(numbers(memory.belief_claim(g, p)) for p in premises))
        if not BELIEF_ID.match(belief_id):
            rejected.append(f"{belief_id!r}: not a valid belief id")
        elif not all(BELIEF_ID.match(p) for p in premises):
            rejected.append(f"{belief_id}: premises must be belief ids")
        elif numbers(item["claim"]) - stated:
            rejected.append(f"{belief_id}: the conclusion states "
                            f"{sorted(numbers(item['claim']) - stated)}, which its premises do not")
        elif not ok:
            rejected.append(f"{belief_id}: unknown vendor {item.get('vendor')!r}")
        elif conflict:
            rejected.append(conflict)
        else:
            try:
                if not memory.exists(g, BELIEF, belief_id):
                    memory.add_belief(g, belief_id, claim=item["claim"], about=about,
                                      recompute=False)
                memory.add_justification(
                    g, f"j_{belief_id[2:]}__inference_{n}", supports=belief_id,
                    premises=premises, kind=INFERENCE, reasoning=item["reasoning"],
                    model=inference.get("model"), agent=AGENT_ID, recompute=False)
            except memory.WriteRejected as e:
                rejected.append(str(e))
    support.recompute(g)
    return rejected
