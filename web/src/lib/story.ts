// web/src/lib/story.ts
// The case bar: what this purchase case looks like right now, and the one thing worth
// doing next. Worked out from the memory itself, never from a script.
import type { Decision, ImpactResponse } from "../contract";
import { ordersOf, type Memory } from "./memory";
import { ORDER_STATE, orderParts, plural, type Tone } from "./words";

export interface Suggestion {
  tone: "info" | "attention" | "done";
  text: string;
}

export interface Chip {
  tone: Tone;
  text: string;
}

interface Situation {
  ready: boolean;
  running: "run" | "replan" | null;
  impact: ImpactResponse | null;
}

const label = (d: Decision) => orderParts(d.summary)?.label ?? d.id;

export function chipsOf(m: Memory, running: Situation["running"]): Chip[] {
  const chips: Chip[] = [];
  if (running) chips.push({ tone: "indigo", text: running === "run" ? "Agents working" : "Re-planning" });
  const open = m.alerts.filter((a) => m.documents[a.document_id]?.trust !== "quarantined");
  if (open.length) chips.push({ tone: "red", text: plural(open.length, "security alert") });
  const distrusted = Object.values(m.documents).filter((d) => d.trust === "quarantined").length;
  if (distrusted) chips.push({ tone: "slate", text: `${plural(distrusted, "document")} distrusted` });
  const orders = ordersOf(m);
  const latest = orders[orders.length - 1];
  if (latest?.state) {
    const held = latest.held_by.length > 0;
    const state = ORDER_STATE[latest.state];
    chips.push({ tone: held ? "amber" : state.tone, text: `${label(latest)} · ${held ? "On hold" : state.label}` });
  }
  return chips;
}

export function suggestionOf(m: Memory, s: Situation): Suggestion {
  const info = (text: string): Suggestion => ({ tone: "info", text });
  const attention = (text: string): Suggestion => ({ tone: "attention", text });
  if (!s.ready) return info("Connecting to Antidote's memory…");
  if (s.running === "run") {
    return info("The agents are reading the documents. Every fact they record appears in the graph, linked to where it came from.");
  }
  if (s.running === "replan") return info("The Buyer is re-planning with the facts that still hold…");
  const orders = ordersOf(m);
  const latest = orders[orders.length - 1];
  if (!m.hasRun || !latest) {
    return info("Start the agents: they read the documents on the left and recommend a supplier for this request.");
  }
  if (s.impact) {
    return attention("This is a preview on a copy of the memory: nothing has changed yet. Stop trusting the document to apply it, or cancel.");
  }
  const p = orderParts(latest.summary);
  if (latest.held_by.length) {
    const doc = m.documents[latest.held_by[0]]?.title ?? "a flagged document";
    return attention(`${label(latest)} is on hold: it rests on ${doc}, which contains hidden instructions. Look at what the AI read, then decide whether to keep trusting it.`);
  }
  if (latest.state === "blocked") {
    return attention(`${label(latest)} was blocked: facts it rested on no longer hold. Ask the Buyer to re-plan with what's still true.`);
  }
  if (latest.state === "pending_approval") {
    return attention(`${label(latest)} recommends ${p?.vendor ?? "a supplier"} for ${p?.total ?? "this order"}. Check what it rests on, then approve it if you agree.`);
  }
  if (latest.state === "authorized") return attention(`${label(latest)} is approved. Place it when you're ready.`);
  if (latest.state === "executed") {
    return { tone: "done", text: `${label(latest)} was placed with ${p?.vendor ?? "the supplier"}. Every fact behind it still holds.` };
  }
  return info("Review the recommendation on the right.");
}
