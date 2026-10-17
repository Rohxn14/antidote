# api/contract.py
"""The contract between the API and the web app.

Every streamed event and every JSON response, as Pydantic models.
web/src/contract.ts mirrors this file model for model, field for field, and
tests/test_contract.py fails if the two drift apart.

Streams (POST /api/run, /api/replan, /api/capabilities) send NDJSON: one event
per line, each an envelope {type, seq, data}. `type` is stable, `seq` counts
up from 1 within a stream, and `data` is typed per event. The activity feed
and the graph are both updated from the same events; after a refresh the
client rebuilds everything from GET /api/state.
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

# --- Vocabulary -----------------------------------------------------------------------

Agent = Literal["researcher", "buyer", "security", "approval", "system"]
AgentState = Literal["working", "done", "waiting"]
ReasonKind = Literal["extraction", "inference", "decision"]
DecisionKind = Literal["shortlist", "purchase_order"]
OrderState = Literal["draft", "pending_approval", "authorized", "executed", "blocked"]
Outcome = Literal["blocked", "needs_approval", "auto"]
Trust = Literal["trusted", "unverified", "quarantined"]
Evidence = Literal["unsupported", "unverified only", "single trusted origin", "robust"]
DocumentKind = Literal["request", "registry", "vendor", "other"]
RunMode = Literal["replay", "live"]


# --- Event data -------------------------------------------------------------------------

class AgentStatusData(BaseModel):
    agent: Agent
    state: AgentState
    message: str                      # plain language, shown in the activity feed
    document_id: str | None = None    # the document being read, if any


class FactRecordedData(BaseModel):
    fact_id: str
    text: str
    vendor_id: str | None
    document_id: str | None           # the document it was read from (None for conclusions)
    quote: str | None
    supported: bool


class ClaimRefusedData(BaseModel):
    agent: Agent
    document_id: str | None
    text: str                         # what the agent tried to record
    reason: str                       # why the checks refused it, in plain language


class ReasonRecordedData(BaseModel):
    reason_id: str
    kind: ReasonKind
    supports: str                     # the fact or decision this reason supports
    premises: list[str]               # documents and facts it needs (ALL of them)
    author: Agent | None
    holds: bool


class DecisionRecordedData(BaseModel):
    decision_id: str
    kind: DecisionKind
    summary: str
    vendor_id: str | None
    amount: float | None
    state: OrderState | None


class GateVerdictData(BaseModel):
    decision_id: str
    outcome: Outcome
    state: OrderState
    reasons: list[str]


class Finding(BaseModel):
    rule: str                         # e.g. hidden_text, fake_message_block
    evidence: str


class SecurityAlertData(BaseModel):
    document_id: str
    document_title: str
    findings: list[Finding]


class ErrorData(BaseModel):
    message: str
    recoverable: bool = True


class RunSummary(BaseModel):
    facts: int
    refused: int
    decisions: int
    alerts: int


class RunCompleteData(BaseModel):
    revision: int
    summary: RunSummary


class Statement(BaseModel):
    cypher: str                       # the exact statement FalkorDB executed
    ms: float
    rows: int


class CapabilityResultData(BaseModel):
    capability: str                   # e.g. "Decide what is still believable"
    feature: str                      # the FalkorDB feature it relies on
    ok: bool
    ms: float
    result: str                       # what it produced, in plain language
    statements: list[Statement]
    error: str | None = None


# --- Event envelopes --------------------------------------------------------------------

class AgentStatusEvent(BaseModel):
    type: Literal["agent_status"] = "agent_status"
    seq: int
    data: AgentStatusData


class FactRecordedEvent(BaseModel):
    type: Literal["fact_recorded"] = "fact_recorded"
    seq: int
    data: FactRecordedData


class ClaimRefusedEvent(BaseModel):
    type: Literal["claim_refused"] = "claim_refused"
    seq: int
    data: ClaimRefusedData


class ReasonRecordedEvent(BaseModel):
    type: Literal["reason_recorded"] = "reason_recorded"
    seq: int
    data: ReasonRecordedData


class DecisionRecordedEvent(BaseModel):
    type: Literal["decision_recorded"] = "decision_recorded"
    seq: int
    data: DecisionRecordedData


class GateVerdictEvent(BaseModel):
    type: Literal["gate_verdict"] = "gate_verdict"
    seq: int
    data: GateVerdictData


class SecurityAlertEvent(BaseModel):
    type: Literal["security_alert"] = "security_alert"
    seq: int
    data: SecurityAlertData


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    seq: int
    data: ErrorData


class RunCompleteEvent(BaseModel):
    type: Literal["run_complete"] = "run_complete"
    seq: int
    data: RunCompleteData


class CapabilityResultEvent(BaseModel):
    type: Literal["capability_result"] = "capability_result"
    seq: int
    data: CapabilityResultData


Event = Annotated[Union[AgentStatusEvent, FactRecordedEvent, ClaimRefusedEvent,
                        ReasonRecordedEvent, DecisionRecordedEvent, GateVerdictEvent,
                        SecurityAlertEvent, ErrorEvent, RunCompleteEvent,
                        CapabilityResultEvent], Field(discriminator="type")]

EVENT_TYPES = ["agent_status", "fact_recorded", "claim_refused", "reason_recorded",
               "decision_recorded", "gate_verdict", "security_alert", "error",
               "run_complete", "capability_result"]


# --- Requests ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    mode: RunMode = "replay"
    request: str | None = None        # the buyer's instruction (editable in live mode only)
    pace: float = 1.0                 # 1 = normal (~30 s replay), 0 = instant (skip to result)


class ImpactRequest(BaseModel):
    document_id: str


class ReplanRequest(BaseModel):
    mode: RunMode = "replay"
    pace: float = 1.0


# --- Responses --------------------------------------------------------------------------

class ApiError(BaseModel):
    error: str                        # stable code, e.g. "memory_unreachable", "not_found"
    detail: str | None = None


class Ack(BaseModel):
    ok: bool


class SessionResponse(BaseModel):
    token: str                        # unguessable; mapped to a private graph on the server


class MemoryUse(BaseModel):
    used: str | None                  # e.g. "3.1M", if the server reports it
    graphs: int


class HealthResponse(BaseModel):
    falkordb: Literal["up", "down"]
    detail: str | None = None
    memory: MemoryUse | None = None
    live_ai: bool                     # Live AI switch available (key set and not disabled)
    model: str | None = None
    sessions: int
    session_cap: int


class RequestInfo(BaseModel):
    text: str
    editable: bool                    # true only when Live AI is available


class Document(BaseModel):
    id: str
    title: str
    kind: DocumentKind
    trust: Trust
    origin: str
    supported: bool
    vendor_id: str | None


class Fact(BaseModel):
    id: str
    text: str
    supported: bool
    evidence: Evidence | None
    weak_origin: str | None           # the trusted origin whose loss would drop it
    vendor_id: str | None


class Reason(BaseModel):
    id: str
    kind: ReasonKind
    holds: bool
    author: str | None
    quote: str | None


class Decision(BaseModel):
    id: str
    kind: DecisionKind
    summary: str
    amount: float | None
    state: OrderState | None
    supported: bool
    evidence: Evidence | None
    vendor_id: str | None
    note: str | None                  # the approval check's last reasons
    approved_by: str | None


class Edge(BaseModel):
    from_id: str                      # display direction: evidence flows into reasons,
    to_id: str                        # reasons flow into what they support
    kind: Literal["premise", "supports"]


class Alert(BaseModel):
    document_id: str
    document_title: str
    findings: list[Finding]


class RepairRecord(BaseModel):
    id: str
    approved_by: str
    revision: int
    documents: list[str]              # titles of the documents no longer trusted
    withdrawn: list[str]              # ids of facts and decisions withdrawn


class Vendor(BaseModel):
    id: str
    name: str


class StateResponse(BaseModel):
    revision: int
    has_run: bool
    request: RequestInfo
    vendors: list[Vendor]
    documents: list[Document]
    facts: list[Fact]
    reasons: list[Reason]
    decisions: list[Decision]
    edges: list[Edge]
    alerts: list[Alert]
    repairs: list[RepairRecord]


class Segment(BaseModel):
    text: str
    hidden: bool                      # invisible to a person, read by an agent
    kind: Literal["visible", "comment", "hidden_element"]


class DocumentResponse(BaseModel):
    id: str
    title: str
    kind: DocumentKind
    trust: Trust
    segments: list[Segment]           # "what the AI reads", hidden parts marked
    html: str | None                  # for a sandboxed iframe (never executed)


class ImpactItem(BaseModel):
    id: str
    kind: Literal["fact", "decision"]
    text: str


class Survivor(BaseModel):
    id: str
    text: str
    kept_by: str                      # the reason that still holds it up
    premises: list[str]               # what that reason rests on


class ImpactResponse(BaseModel):
    document_id: str
    also_quarantined: list[str]       # copies with the same origin
    lost: list[ImpactItem]            # would no longer be believed
    survived: list[Survivor]          # lose a reason, keep another
    orders_blocked: list[ImpactItem]  # open orders the approval check would block
    executed_affected: list[ImpactItem]  # already executed: needs a human
    base_revision: int


class QuarantineResponse(BaseModel):
    repair_id: str
    quarantined: list[str]
    withdrawn: list[str]


class OrderActionResponse(BaseModel):
    decision_id: str
    action: Literal["approve", "execute"]
    outcome: Outcome
    state: OrderState
    reasons: list[str]
    message: str                      # plain language for the UI


class WhyReason(BaseModel):
    id: str
    kind: ReasonKind
    holds: bool
    author: str | None
    reasoning: str | None
    quote: str | None
    premises: list["WhyNode"]


class WhyNode(BaseModel):
    id: str
    kind: Literal["document", "fact", "decision"]
    text: str
    supported: bool
    evidence: Evidence | None = None
    trust: Trust | None = None
    loop: bool = False                # already shown higher up (a support loop)
    reasons: list[WhyReason] = []


WhyReason.model_rebuild()


class WhyResponse(BaseModel):
    root: WhyNode


class CypherQuery(BaseModel):
    name: str
    cypher: str


class CypherSection(BaseModel):
    title: str
    intro: str
    queries: list[CypherQuery]


class CypherResponse(BaseModel):
    sections: list[CypherSection]


class BenchmarkRow(BaseModel):
    scenario: str
    method: str
    residual: int
    collateral: int
    stale: int | None                 # not applicable to the external test set
    ms: float | None


class BenchmarkResponse(BaseModel):
    rows: list[BenchmarkRow]
