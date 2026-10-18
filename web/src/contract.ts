// web/src/contract.ts
// The contract between the API and the web app: mirrors api/contract.py model for
// model, field for field (tests/test_contract.py fails if the two drift apart).
//
// Streams (POST /api/run, /api/replan, /api/capabilities) send NDJSON: one event per
// line, each an envelope {type, seq, data}. The activity feed and the graph are both
// updated from the same events; after a refresh, rebuild from GET /api/state.

// --- Vocabulary -----------------------------------------------------------------------

export type Agent = "researcher" | "buyer" | "security" | "approval" | "system";
export type AgentState = "working" | "done" | "waiting";
export type ReasonKind = "extraction" | "inference" | "decision";
export type DecisionKind = "shortlist" | "purchase_order";
export type OrderState = "draft" | "pending_approval" | "authorized" | "executed" | "blocked";
export type Outcome = "blocked" | "needs_approval" | "auto" | "held"; // held: rests on a flagged document
export type Trust = "trusted" | "unverified" | "quarantined";
export type Evidence = "unsupported" | "unverified only" | "single trusted origin" | "robust";
export type DocumentKind = "request" | "registry" | "vendor" | "other";
export type RunMode = "replay" | "live";

// --- Event data -------------------------------------------------------------------------

export interface AgentStatusData {
  agent: Agent;
  state: AgentState;
  message: string;
  document_id: string | null;
}

export interface FactRecordedData {
  fact_id: string;
  text: string;
  vendor_id: string | null;
  document_id: string | null;
  quote: string | null;
  supported: boolean;
}

export interface ClaimRefusedData {
  agent: Agent;
  document_id: string | null;
  text: string;
  reason: string;
}

export interface ReasonRecordedData {
  reason_id: string;
  kind: ReasonKind;
  supports: string;
  premises: string[];
  author: Agent | null;
  holds: boolean;
}

export interface DecisionRecordedData {
  decision_id: string;
  kind: DecisionKind;
  summary: string;
  vendor_id: string | null;
  amount: number | null;
  state: OrderState | null;
}

export interface GateVerdictData {
  decision_id: string;
  outcome: Outcome;
  state: OrderState;
  reasons: string[];
}

export interface Finding {
  rule: string;
  evidence: string;
}

export interface SecurityAlertData {
  document_id: string;
  document_title: string;
  findings: Finding[];
}

export interface ErrorData {
  message: string;
  recoverable: boolean;
}

export interface RunSummary {
  facts: number;
  refused: number;
  decisions: number;
  alerts: number;
}

export interface RunCompleteData {
  revision: number;
  summary: RunSummary;
}

export interface Statement {
  cypher: string;
  ms: number;
  rows: number;
}

export interface CapabilityResultData {
  capability: string;
  feature: string;
  ok: boolean;
  ms: number;
  result: string;
  statements: Statement[];
  error: string | null;
}

// --- Event envelopes --------------------------------------------------------------------

export const EVENT_TYPES = [
  "agent_status", "fact_recorded", "claim_refused", "reason_recorded",
  "decision_recorded", "gate_verdict", "security_alert", "error",
  "run_complete", "capability_result",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

interface Envelope<T extends EventType, D> {
  type: T;
  seq: number;
  data: D;
}

export type AgentStatusEvent = Envelope<"agent_status", AgentStatusData>;
export type FactRecordedEvent = Envelope<"fact_recorded", FactRecordedData>;
export type ClaimRefusedEvent = Envelope<"claim_refused", ClaimRefusedData>;
export type ReasonRecordedEvent = Envelope<"reason_recorded", ReasonRecordedData>;
export type DecisionRecordedEvent = Envelope<"decision_recorded", DecisionRecordedData>;
export type GateVerdictEvent = Envelope<"gate_verdict", GateVerdictData>;
export type SecurityAlertEvent = Envelope<"security_alert", SecurityAlertData>;
export type ErrorEvent = Envelope<"error", ErrorData>;
export type RunCompleteEvent = Envelope<"run_complete", RunCompleteData>;
export type CapabilityResultEvent = Envelope<"capability_result", CapabilityResultData>;

export type AntidoteEvent =
  | AgentStatusEvent | FactRecordedEvent | ClaimRefusedEvent | ReasonRecordedEvent
  | DecisionRecordedEvent | GateVerdictEvent | SecurityAlertEvent | ErrorEvent
  | RunCompleteEvent | CapabilityResultEvent;

// --- Requests ---------------------------------------------------------------------------

export interface RunRequest {
  mode: RunMode;
  request: string | null;
  pace: number;
}

export interface ImpactRequest {
  document_id: string;
}

export interface ReplanRequest {
  mode: RunMode;
  pace: number;
}

// --- Responses --------------------------------------------------------------------------

export interface ApiError {
  error: string;
  detail: string | null;
}

export interface Ack {
  ok: boolean;
}

export interface SessionResponse {
  token: string;
}

export interface MemoryUse {
  used: string | null;
  graphs: number;
}

export interface HealthResponse {
  falkordb: "up" | "down";
  detail: string | null;
  memory: MemoryUse | null;
  live_ai: boolean;
  model: string | null;
  sessions: number;
  session_cap: number;
}

export interface RequestInfo {
  text: string;
  editable: boolean;
}

export interface Document {
  id: string;
  title: string;
  kind: DocumentKind;
  trust: Trust;
  origin: string;
  supported: boolean;
  vendor_id: string | null;
}

export interface Fact {
  id: string;
  text: string;
  supported: boolean;
  evidence: Evidence | null;
  weak_origin: string | null;
  vendor_id: string | null;
}

export interface Reason {
  id: string;
  kind: ReasonKind;
  holds: boolean;
  author: string | null;
  quote: string | null;
}

export interface Decision {
  id: string;
  kind: DecisionKind;
  summary: string;
  amount: number | null;
  state: OrderState | null;
  supported: boolean;
  evidence: Evidence | null;
  vendor_id: string | null;
  note: string | null;
  approved_by: string | null;
  reasoning: string | null;
  held_by: string[];
}

export interface Edge {
  from_id: string;
  to_id: string;
  kind: "premise" | "supports";
}

export interface Alert {
  document_id: string;
  document_title: string;
  findings: Finding[];
}

export interface RepairRecord {
  id: string;
  approved_by: string;
  revision: number;
  documents: string[];
  withdrawn: string[];
}

export interface Vendor {
  id: string;
  name: string;
}

export interface StateResponse {
  revision: number;
  has_run: boolean;
  request: RequestInfo;
  vendors: Vendor[];
  documents: Document[];
  facts: Fact[];
  reasons: Reason[];
  decisions: Decision[];
  edges: Edge[];
  alerts: Alert[];
  repairs: RepairRecord[];
}

export interface Segment {
  text: string;
  hidden: boolean;
  kind: "visible" | "comment" | "hidden_element";
}

export interface DocumentResponse {
  id: string;
  title: string;
  kind: DocumentKind;
  trust: Trust;
  segments: Segment[];
  html: string | null;
}

export interface ImpactItem {
  id: string;
  kind: "fact" | "decision";
  text: string;
}

export interface Survivor {
  id: string;
  text: string;
  kept_by: string;
  premises: string[];
}

export interface ImpactResponse {
  document_id: string;
  also_quarantined: string[];
  lost: ImpactItem[];
  survived: Survivor[];
  orders_blocked: ImpactItem[];
  executed_affected: ImpactItem[];
  base_revision: number;
}

export interface QuarantineResponse {
  repair_id: string;
  quarantined: string[];
  withdrawn: string[];
  orders_blocked: string[];
}

export interface OrderActionResponse {
  decision_id: string;
  action: "approve" | "execute";
  outcome: Outcome;
  state: OrderState;
  reasons: string[];
  message: string;
}

export interface WhyReason {
  id: string;
  kind: ReasonKind;
  holds: boolean;
  author: string | null;
  reasoning: string | null;
  quote: string | null;
  premises: WhyNode[];
}

export interface WhyNode {
  id: string;
  kind: "document" | "fact" | "decision";
  text: string;
  supported: boolean;
  evidence: Evidence | null;
  trust: Trust | null;
  loop: boolean;
  reasons: WhyReason[];
}

export interface WhyResponse {
  root: WhyNode;
}

export interface CypherQuery {
  name: string;
  cypher: string;
}

export interface CypherSection {
  title: string;
  intro: string;
  queries: CypherQuery[];
}

export interface CypherResponse {
  sections: CypherSection[];
}

export interface BenchmarkRow {
  scenario: string;
  method: string;
  residual: number;
  collateral: number;
  stale: number | null;
  ms: number | null;
}

export interface BenchmarkResponse {
  rows: BenchmarkRow[];
}
