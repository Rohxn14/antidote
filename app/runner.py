# app/runner.py
"""Runs the agents step by step and reports what they do, as events.

The web app streams these events: its activity feed and its graph are built
from them. Two modes:

    replay  the Researcher's recorded answers (data/fixtures/) and a Buyer that
            follows the request's rules on what memory supports right now,
            paced so a person can follow along; needs no LLM key
    live    the real agents (an LLM through app/llm.py), on the request the
            user typed

Either way, every answer goes through the same checks (app/agents) and the same
write path (app/memory.py) as everywhere else. Events are plain dicts
{"type", "data"}; the API validates them against api/contract.py.
"""
import time

from app import casebuilder, demo, llm, memory, recording, review, support, views
from app.agents import buyer, researcher
from app.schema import (ABOUT, AGENT, AUTHORED, BELIEF, DECISION, HOLDS, JUSTIFICATION,
                        PREMISE, SOURCE, SUPPORTS, VENDOR)

REQUEST_ID = "s_policy"
DEFAULT_REQUEST = (
    "1. Servo actuators for RehabArm v2 must come from an ISO 13485-certified supplier.\n"
    "2. We need 100 servo actuators delivered within 4 weeks.\n"
    "3. Among qualifying suppliers, choose the lowest unit price.")
MAX_REQUEST = 2000

# Seconds to pause per step at pace 1 (about 30 s for a whole replay).
PAUSE = {"document": 0.9, "claim": 0.45, "conclusion": 0.6, "decision": 0.9, "scan": 0.8}
AGENTS = {"a_researcher": "researcher", "a_buyer": "buyer"}

REASONS_FOR = f"""
MATCH (j:{JUSTIFICATION})-[:{SUPPORTS}]->(n {{id: $id}})
OPTIONAL MATCH (a:{AGENT})-[:{AUTHORED}]->(j)
OPTIONAL MATCH (j)-[:{PREMISE}]->(p)
RETURN j.id, j.kind, coalesce(j.{HOLDS}, false), a.id, collect(p.id)
ORDER BY j.id
"""
VENDOR_OF = f"MATCH (n {{id: $id}})-[:{ABOUT}]->(v:{VENDOR}) RETURN v.id LIMIT 1"
DECISION_INFO = f"""
MATCH (d:{DECISION} {{id: $id}})
OPTIONAL MATCH (d)-[:{ABOUT}]->(v:{VENDOR})
RETURN d.kind, d.summary, d.amount, d.state, v.id
"""
TITLE = f"MATCH (s:{SOURCE} {{id: $id}}) RETURN s.title"


def event(event_type: str, /, **data) -> dict:
    return {"type": event_type, "data": data}


def status(agent: str, message: str, state: str = "working", document_id: str | None = None) -> dict:
    return event("agent_status", agent=agent, state=state, message=message,
                 document_id=document_id)


# The story's suppliers as the planner sees them (prices and delivery from their pages).
STORY_CASE = {"max_weeks": 4, "suppliers": [
    {"slot": "vantor", "price": 480, "weeks": 2}, {"slot": "boltline", "price": 520, "weeks": 3},
    {"slot": "ferrocraft", "price": 560, "weeks": 4}, {"slot": "quillon", "price": 390, "weeks": 2},
    {"slot": "nexapoint", "price": 545, "weeks": 3}, {"slot": "orvane", "price": 610, "weeks": 2},
    {"slot": "talisk", "price": 450, "weeks": 6}, {"slot": "brennick", "price": 505, "weeks": 3}]}


class StoryScript:
    """Where a run's documents and the agents' answers come from, for the demo story.
    A built case (app/casebuilder.CaseScript) has the same shape.

        replay    scripted: hand-written answers in the LLM's format for the Researcher
                  (data/fixtures/), and a Buyer that applies the request's rules
        recorded  a real model run (app/recording.py): the agents' own code runs, and
                  each prompt gets the reply the model really gave to that prompt
        live      the real model, called now (needs a key; off on the deployed site)
    """

    def __init__(self, mode: str = "replay", request_text: str = DEFAULT_REQUEST, client=None):
        self.mode = mode
        if client is None and mode == "live":
            client = llm.LIVE
        if client is None and mode == "recorded":
            client = recording.default()
            if client is None:
                raise recording.NotRecorded("No recorded model run is available.")
        self.client = client  # None: scripted answers
        if mode == "recorded":
            request_text = DEFAULT_REQUEST  # the recording's prompts contain this request
        self.request_text = request_text[:MAX_REQUEST] or DEFAULT_REQUEST

    def sources(self) -> list[tuple]:
        """(id, uri, title, trust, origin, text): text None means the file at uri."""
        return [(sid, uri, "Your request" if sid == REQUEST_ID else title, trust, origin,
                 self.request_text if sid == REQUEST_ID else None)
                for sid, uri, title, trust, origin in demo.SOURCES]

    def extraction(self, g, source_id: str) -> dict:
        if self.client:
            return researcher.extract(g, source_id, self.client)
        return demo.fixture(f"researcher_{source_id}")

    def inference(self, g) -> dict:
        return researcher.infer(g, self.client) if self.client else demo.fixture("researcher_inference")

    def vendors(self) -> list[tuple]:
        return demo.VENDORS

    # Scripted, the Buyer applies the request's rules to what memory supports right now
    # (the same planner as a built case): which documents are under review or distrusted
    # changes its answer, so one fixed written answer could not.
    def plan(self, g) -> dict:
        if self.client:
            return buyer.decide(g, demo.FIRST_ORDER, self.client)
        return casebuilder.CaseScript(STORY_CASE).plan(g)

    def replan(self, g) -> dict:
        if self.client:
            return buyer.decide(g, client=self.client)
        return casebuilder.CaseScript(STORY_CASE).replan(g)


def prepare(g, script=DEFAULT_REQUEST) -> None:
    """A fresh memory for one run: the agents, the vendors and the documents
    (the user's request among them, trusted), but no facts yet. `script` is a
    StoryScript or a CaseScript (a plain string: the story with that request)."""
    if isinstance(script, str):
        script = StoryScript(request_text=script)
    demo.reset(g)
    for agent_id, name, role in demo.AGENTS:
        memory.add_agent(g, agent_id, name=name, role=role)
    for vendor_id, name in script.vendors():
        memory.add_vendor(g, vendor_id, name=name)
    for sid, uri, title, trust, origin, text in script.sources():
        memory.add_source(g, sid, uri=uri, title=title, trust=trust, origin=origin, text=text,
                          recompute=False)
    support.recompute(g)


class _Run:
    """One run's bookkeeping: reasons already reported, and the totals."""

    def __init__(self, g, pace: float):
        self.g, self.pace = g, pace
        self.reported: set[str] = set()
        self.counts = {"facts": 0, "refused": 0, "decisions": 0, "alerts": 0}

    def pause(self, step: str) -> None:
        if self.pace > 0:
            time.sleep(PAUSE[step] * self.pace)

    def vendor_of(self, node_id: str) -> str | None:
        rows = self.g.ro_query(VENDOR_OF, {"id": node_id}).result_set
        return rows[0][0] if rows else None

    def new_reasons(self, node_id: str):
        """Report every reason supporting `node_id` that has not been reported yet."""
        for jid, kind, holds, author, premises in self.g.ro_query(
                REASONS_FOR, {"id": node_id}).result_set:
            if jid in self.reported:
                continue
            self.reported.add(jid)
            yield event("reason_recorded", reason_id=jid, kind=kind, supports=node_id,
                        premises=premises, author=AGENTS.get(author), holds=holds)

    def fact(self, fact_id: str, document_id: str | None, quote: str | None):
        node = views.node(self.g, fact_id)
        self.counts["facts"] += 1
        return event("fact_recorded", fact_id=fact_id, text=node["text"],
                     vendor_id=self.vendor_of(fact_id), document_id=document_id,
                     quote=quote, supported=bool(node["ok"]))

    def refused(self, agent: str, document_id: str | None, text: str, note: str):
        self.counts["refused"] += 1
        return event("claim_refused", agent=agent, document_id=document_id, text=text,
                     reason=note.split(": ", 1)[-1])


def _claim(r: _Run, document_id: str, claim: dict, model: str | None):
    """One claim the Researcher read in a document: checked, then recorded."""
    fact_id = claim.get("belief", "")
    is_new = not memory.exists(r.g, BELIEF, fact_id)
    refused = researcher.record_extractions(r.g, {"source_id": document_id, "model": model,
                                                  "claims": [claim]})
    if refused:
        yield r.refused("researcher", document_id, claim.get("claim", ""), refused[0])
        return
    if is_new:
        yield r.fact(fact_id, document_id, claim.get("quote"))
    yield from r.new_reasons(fact_id)


def _conclusion(r: _Run, item: dict, model: str | None):
    """One conclusion the Researcher drew from facts already in memory."""
    fact_id = item.get("belief", "")
    is_new = not memory.exists(r.g, BELIEF, fact_id)
    refused = researcher.record_inferences(r.g, {"model": model, "inferences": [item]})
    if refused:
        yield r.refused("researcher", None, item.get("claim", ""), refused[0])
        return
    if is_new:
        yield r.fact(fact_id, None, None)
    yield from r.new_reasons(fact_id)


def _plan(r: _Run, plan: dict):
    """The Buyer's shortlist and order: recorded, then the order meets the approval check."""
    result = buyer.record_plan(r.g, plan)
    for note in result["rejected"]:
        yield r.refused("buyer", None, "part of the Buyer's plan", note)
    for decision_id in result["shortlisted"] + ([result["order"]] if result["order"] else []):
        kind, summary, amount, state, vendor_id = r.g.ro_query(
            DECISION_INFO, {"id": decision_id}).result_set[0]
        r.counts["decisions"] += 1
        yield event("decision_recorded", decision_id=decision_id, kind=kind, summary=summary,
                    vendor_id=vendor_id, amount=amount, state=state)
        yield from r.new_reasons(decision_id)
    verdict = result["verdict"]
    if verdict:
        yield event("gate_verdict", decision_id=verdict.decision_id, outcome=verdict.outcome,
                    state=verdict.state, reasons=verdict.reasons)


def _review(r: _Run):
    """Before anyone concludes or decides: the security scan and the conflict check.
    A flagged document goes under review and counts for nothing; its suppliers are
    suspended until a person clears or distrusts it (app/review.py)."""
    yield status("security", "Checking every document: hidden instructions aimed at AI, "
                             "and claims that trusted documents contradict")
    r.pause("scan")
    alerts = review.check(r.g)
    for alert in alerts:
        r.counts["alerts"] += 1
        yield event("security_alert", **alert)
    yield status("security", f"Check finished: {len(alerts)} document(s) under review",
                 state="done")


def _after_plan(plan: dict):
    if plan.get("purchase_order"):
        yield status("buyer", "Waiting for your decision", state="waiting")
    else:
        yield status("buyer", "No supplier qualifies and delivers in time on what is supported", state="done")


def run(g, mode: str = "replay", pace: float = 1.0, script=None):
    """The whole job, from reading the documents to an order awaiting approval."""
    script = script or StoryScript(mode)
    r = _Run(g, pace)
    yield status("system", "The agents start from a fresh memory for this request")
    for sid, _uri, title, _trust, _origin, _text in script.sources():
        label = "your request" if sid == REQUEST_ID else title
        yield status("researcher", f"Reading {label}", document_id=sid)
        r.pause("document")
        extraction = script.extraction(g, sid)
        for claim in extraction["claims"]:
            yield from _claim(r, sid, claim, extraction.get("model"))
            r.pause("claim")
    yield from _review(r)
    yield status("researcher", "Working out which suppliers meet your requirements")
    inference = script.inference(g)
    for item in inference["inferences"]:
        yield from _conclusion(r, item, inference.get("model"))
        r.pause("conclusion")
    yield status("researcher", "Finished reading", state="done")
    yield status("buyer", "Comparing the suppliers that qualify")
    r.pause("decision")
    plan = script.plan(g)
    yield from _plan(r, plan)
    yield from _after_plan(plan)
    yield event("run_complete", revision=memory.revision(g), summary=r.counts)


def replan(g, mode: str = "replay", pace: float = 1.0, script=None):
    """The Buyer decides again, from the facts that are still supported."""
    script = script or StoryScript(mode)
    r = _Run(g, pace)
    yield status("buyer", "Re-planning with the facts that are still supported")
    r.pause("decision")
    plan = script.replan(g)
    yield from _plan(r, plan)
    yield from _after_plan(plan)
    yield event("run_complete", revision=memory.revision(g), summary=r.counts)
