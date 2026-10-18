// web/src/lib/memory.ts
// The browser's copy of the visitor's memory. It is loaded from GET /api/state and
// grows event by event while the agents work, so the graph and the activity feed
// come from the same events. FalkorDB stays the source of truth: after every run
// or action the app reloads the full state.
import type {
  Alert, AntidoteEvent, CaseSpec, Decision, Document, Edge, Fact, OrderState, Reason, RepairRecord,
  StateResponse, VendorStatus,
} from "../contract";

export interface Memory {
  revision: number;
  hasRun: boolean;
  documents: Record<string, Document>;
  facts: Record<string, Fact>;
  reasons: Record<string, Reason>;
  decisions: Record<string, Decision>;
  edges: Edge[];
  vendors: Record<string, string>;
  standing: Record<string, VendorStatus>; // suppliers suspended or blacklisted, by id
  alerts: Alert[];
  repairs: RepairRecord[];
  latest: string | null; // the fact or decision recorded most recently in this run
  builtCase: CaseSpec | null; // a case the visitor built, or null for the demo story
}

export const emptyMemory: Memory = {
  revision: 0, hasRun: false, documents: {}, facts: {}, reasons: {}, decisions: {}, edges: [],
  vendors: {}, standing: {}, alerts: [], repairs: [], latest: null, builtCase: null,
};

export type MemoryAction =
  | { type: "load"; state: StateResponse }       // everything, from GET /api/state
  | { type: "documents"; state: StateResponse }  // only the documents (a run just re-prepared them)
  | { type: "reset" }                            // a new run: keep the documents, drop the rest
  | { type: "event"; event: AntidoteEvent }
  // What an action's answer already says, shown at once; the reload that follows confirms it.
  | { type: "distrusted"; documents: string[]; withdrawn: string[] }
  | { type: "orderState"; id: string; state: OrderState };

const byId = <T extends { id: string }>(items: T[]): Record<string, T> =>
  Object.fromEntries(items.map((item) => [item.id, item]));

const vendorNames = (state: StateResponse) =>
  Object.fromEntries(state.vendors.map((v) => [v.id, v.name]));

const standingOf = (state: StateResponse) =>
  Object.fromEntries(state.vendors.flatMap((v) => (v.status ? [[v.id, v.status]] : [])));

export const edgeKey = (e: Edge) => `${e.from_id}>${e.to_id}`;

/** Orders from this amount wait until a trusted document confirms their checks (app/config.py). */
export const VERIFY_FROM = 5000;

export function memoryReducer(m: Memory, action: MemoryAction): Memory {
  switch (action.type) {
    case "load": {
      const s = action.state;
      return {
        revision: s.revision, hasRun: s.has_run, documents: byId(s.documents), facts: byId(s.facts),
        reasons: byId(s.reasons), decisions: byId(s.decisions), edges: s.edges,
        vendors: vendorNames(s), standing: standingOf(s), alerts: s.alerts, repairs: s.repairs,
        latest: null, builtCase: s.case,
      };
    }
    case "documents":
      return { ...m, documents: byId(action.state.documents), vendors: vendorNames(action.state), builtCase: action.state.case };
    case "reset":
      return { ...emptyMemory, documents: m.documents, vendors: m.vendors, builtCase: m.builtCase };
    case "event":
      return applyEvent(m, action.event);
    case "distrusted": {
      const gone = new Set([...action.documents, ...action.withdrawn]);
      const broken = new Set(m.edges.filter((e) => e.kind === "premise" && gone.has(e.from_id)).map((e) => e.to_id));
      const lose = <T extends { id: string; supported: boolean }>(items: Record<string, T>) =>
        Object.fromEntries(Object.entries(items).map(([id, x]) => [id, gone.has(id) ? { ...x, supported: false } : x]));
      return {
        ...m,
        documents: Object.fromEntries(Object.entries(m.documents).map(([id, d]) => [
          id, action.documents.includes(id) ? { ...d, trust: "quarantined" as const, supported: false } : d,
        ])),
        facts: lose(m.facts),
        decisions: lose(m.decisions),
        reasons: Object.fromEntries(Object.entries(m.reasons).map(([id, r]) => [id, broken.has(id) ? { ...r, holds: false } : r])),
      };
    }
    case "orderState": {
      const d = m.decisions[action.id];
      if (!d) return m;
      const supported = action.state === "blocked" ? false : d.supported;
      return { ...m, decisions: { ...m.decisions, [d.id]: { ...d, state: action.state, supported } } };
    }
  }
}

function applyEvent(m: Memory, e: AntidoteEvent): Memory {
  switch (e.type) {
    case "fact_recorded": {
      const d = e.data;
      const fact: Fact = {
        id: d.fact_id, text: d.text, supported: d.supported, evidence: null, weak_origin: null,
        vendor_id: d.vendor_id,
      };
      return { ...m, facts: { ...m.facts, [fact.id]: fact }, latest: fact.id };
    }
    case "reason_recorded": {
      const d = e.data;
      const reason: Reason = { id: d.reason_id, kind: d.kind, holds: d.holds, author: d.author, quote: null };
      const known = new Set(m.edges.map(edgeKey));
      const premises = d.premises.map((p): Edge => ({ from_id: p, to_id: d.reason_id, kind: "premise" }));
      const supports: Edge = { from_id: d.reason_id, to_id: d.supports, kind: "supports" };
      const added = [...premises, supports].filter((edge) => !known.has(edgeKey(edge)));
      return { ...m, reasons: { ...m.reasons, [reason.id]: reason }, edges: [...m.edges, ...added] };
    }
    case "decision_recorded": {
      const d = e.data;
      const decision: Decision = {
        id: d.decision_id, kind: d.kind, summary: d.summary, amount: d.amount, state: d.state,
        supported: true, evidence: null, vendor_id: d.vendor_id, note: null, approved_by: null,
        reasoning: null, held_by: [], needs_verification: [],
      };
      return { ...m, decisions: { ...m.decisions, [decision.id]: decision }, latest: decision.id };
    }
    case "gate_verdict": {
      const old = m.decisions[e.data.decision_id];
      if (!old) return m;
      const note = e.data.reasons.join("; ") || old.note;
      // The verification hold (gate.approve), shown at once: a large order whose checks
      // nothing trusted confirms. The next state reload brings the server's own list.
      const unconfirmed = (old.amount ?? 0) >= VERIFY_FROM
        ? basisOf(m, old.id).filter((b) => b.kind === "check" && b.supported && !b.documents.some((d) => d.trust === "trusted")).map((b) => b.text)
        : [];
      const needs_verification = old.needs_verification.length ? old.needs_verification : unconfirmed;
      return { ...m, decisions: { ...m.decisions, [old.id]: { ...old, state: e.data.state, note, needs_verification } } };
    }
    case "security_alert": {
      const doc = e.data.document_id;
      if (m.alerts.some((a) => a.document_id === doc)) return m;
      // Under review before anyone decides: the document counts for nothing and its
      // suppliers are suspended (the reload after the run brings the server's view).
      const suspended = Object.entries(m.vendors).filter(([, name]) => e.data.suspended.includes(name));
      const standing = { ...m.standing, ...Object.fromEntries(suspended.map(([id]) => [id, "suspended" as const])) };
      const documents = m.documents[doc] ? { ...m.documents, [doc]: { ...m.documents[doc], supported: false } } : m.documents;
      return { ...m, alerts: [...m.alerts, { ...e.data, resolution: "open" }], standing, documents };
    }
    case "run_complete":
      return { ...m, revision: e.data.revision, hasRun: true };
    default:
      return m;
  }
}

/** Purchase orders, oldest first (PO-1001, PO-1002, ...). */
export function ordersOf(m: Memory): Decision[] {
  return Object.values(m.decisions)
    .filter((d) => d.kind === "purchase_order")
    .sort((a, b) => a.id.localeCompare(b.id));
}

/** Everything a node rests on: its reasons, their premises, and so on down to the documents. */
export function ancestors(m: Memory, rootId: string): Set<string> {
  const into = new Map<string, string[]>();
  for (const e of m.edges) {
    const list = into.get(e.to_id);
    if (list) list.push(e.from_id);
    else into.set(e.to_id, [e.from_id]);
  }
  const seen = new Set([rootId]);
  const stack = [rootId];
  while (stack.length) {
    for (const p of into.get(stack.pop()!) ?? []) {
      if (!seen.has(p)) {
        seen.add(p);
        stack.push(p);
      }
    }
  }
  return seen;
}

export interface Basis {
  id: string;
  text: string;
  supported: boolean;
  // check: tests your request against a supplier's claim; claim: a supplier's own
  // statement; rule: comes from your request alone
  kind: "check" | "claim" | "rule";
  documents: Document[]; // the documents beneath it (your request left out unless it is a rule)
}

const KIND_ORDER = { check: 0, claim: 1, rule: 2 };

/** The facts a decision rests on directly, each with the documents beneath it. */
export function basisOf(m: Memory, decisionId: string): Basis[] {
  const reasons = new Set(m.edges.filter((e) => e.kind === "supports" && e.to_id === decisionId).map((e) => e.from_id));
  const premises = [...new Set(m.edges.filter((e) => e.kind === "premise" && reasons.has(e.to_id)).map((e) => e.from_id))];
  return premises
    .filter((id) => m.facts[id])
    .map((id): Basis => {
      const documents = [...ancestors(m, id)].map((x) => m.documents[x]).filter(Boolean);
      const fromRequest = documents.some((d) => d.kind === "request");
      const others = documents.filter((d) => d.kind !== "request");
      const kind = !others.length ? "rule" : fromRequest ? "check" : "claim";
      return { id, text: m.facts[id].text, supported: m.facts[id].supported, kind, documents: kind === "rule" ? documents : others };
    })
    .sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind]);
}

/** How many facts were read from each document. */
export function factsPerDocument(m: Memory): Record<string, number> {
  const readFrom = new Map<string, string[]>(); // reason -> documents it quotes
  for (const e of m.edges) {
    if (e.kind === "premise" && m.documents[e.from_id]) {
      readFrom.set(e.to_id, [...(readFrom.get(e.to_id) ?? []), e.from_id]);
    }
  }
  const facts: Record<string, Set<string>> = {};
  for (const e of m.edges) {
    if (e.kind !== "supports" || !m.facts[e.to_id]) continue;
    for (const doc of readFrom.get(e.from_id) ?? []) (facts[doc] ??= new Set()).add(e.to_id);
  }
  return Object.fromEntries(Object.entries(facts).map(([doc, ids]) => [doc, ids.size]));
}
