// web/src/lib/story.ts
// The guide at the top of the page: which step of the story the visitor is on,
// and one sentence about what to do next. Worked out from the memory itself.
import type { ImpactResponse } from "../contract";
import { ordersOf, type Memory } from "./memory";
import { orderParts } from "./words";

export const STEPS = [
  "Run the agents",
  "Review the order",
  "Check the alert",
  "Stop trusting it",
  "Approve anyway?",
  "Re-plan",
];

export interface Story {
  index: number; // the current step
  done: boolean;
  hint: string;
}

interface Situation {
  ready: boolean;
  running: "run" | "replan" | null;
  impact: ImpactResponse | null;
  seenWhy: boolean;
}

export function storyOf(m: Memory, s: Situation): Story {
  const step = (index: number, hint: string, done = false): Story => ({ index, hint, done });
  if (!s.ready) return step(0, "Connecting to Antidote's memory…");
  if (s.running === "run") {
    return step(0, "The agents are reading the documents. Every fact they record appears in the graph, linked to where it came from.");
  }
  const orders = ordersOf(m);
  const first = orders[0];
  if (!m.hasRun || !first) {
    return step(0, "Press “Start the agents”. They read six documents and recommend a purchase order, about 30 seconds.");
  }
  const p = orderParts(first.summary);
  if (m.repairs.length === 0) {
    if (s.impact) {
      return step(3, "This is a preview on a copy of the memory: nothing has changed yet. Stop trusting the document to make it real.");
    }
    if (!s.seenWhy) {
      return step(1, `The Buyer recommends ${p?.vendor ?? "a supplier"} for ${p?.total ?? "this order"}. Open “Why this supplier?” to see the evidence behind it.`);
    }
    const alert = m.alerts[0];
    if (alert) {
      return step(2, `Antidote found hidden instructions in ${alert.document_title}. See what the AI read, then preview what changes if you stop trusting it.`);
    }
    return step(1, "Approve the order, or look at the evidence behind it first.");
  }
  if (s.running === "replan") return step(5, "The Buyer is re-planning with the facts that are still supported…");
  if (orders.length === 1) {
    if (first.state === "blocked") {
      return step(5, `${p?.label ?? "The order"} is blocked: no supported reason is left. Ask the Buyer to re-plan with what's still true.`);
    }
    if (!first.supported && first.state === "pending_approval") {
      return step(4, `${p?.label ?? "The order"} lost its support. Try “Approve anyway”: the approval check looks at the memory as it is now.`);
    }
    return step(5, "Ask the Buyer to re-plan with the evidence that's left.");
  }
  const latest = orders[orders.length - 1];
  const q = orderParts(latest.summary);
  if (latest.state === "executed") {
    return step(5, `Done. ${q?.label ?? "The order"} went to ${q?.vendor ?? "a supplier"}, and every reason behind it still holds.`, true);
  }
  if (latest.state === "authorized") return step(5, `${q?.label ?? "The order"} is approved. Place it when you're ready.`);
  return step(5, `The Buyer now recommends ${q?.vendor ?? "another supplier"} for ${q?.total ?? "this order"}, from facts that still hold. Approve it to finish.`);
}
