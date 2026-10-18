// web/src/lib/words.ts
// Plain language for everything the API reports: the page never shows a raw code.
import type { DocumentKind, Evidence, OrderState, Outcome, ReasonKind, Trust } from "../contract";

export type Tone = "slate" | "green" | "amber" | "red" | "sky" | "indigo" | "violet";

export const TRUST: Record<Trust, { label: string; tone: Tone; hint: string }> = {
  trusted: { label: "Trusted", tone: "green", hint: "Counts as evidence on its own." },
  unverified: {
    label: "Unverified", tone: "amber",
    hint: "Usable, but weaker evidence: nothing independent confirms it.",
  },
  quarantined: {
    label: "Not trusted", tone: "red",
    hint: "You stopped trusting it: nothing it says counts any more.",
  },
};

export const EVIDENCE: Record<Evidence, { label: string; tone: Tone; hint: string }> = {
  robust: { label: "Robust", tone: "green", hint: "Still holds if any one trusted source is lost." },
  "single trusted origin": { label: "One trusted source", tone: "sky", hint: "Rests on a single trusted source." },
  "unverified only": { label: "Unverified sources only", tone: "amber", hint: "No trusted document backs it up." },
  unsupported: { label: "Unsupported", tone: "red", hint: "None of its reasons holds any more." },
};

export const ORDER_STATE: Record<OrderState, { label: string; short: string; tone: Tone }> = {
  draft: { label: "Draft", short: "Draft", tone: "slate" },
  pending_approval: { label: "Waiting for approval", short: "Pending", tone: "amber" },
  authorized: { label: "Approved", short: "Approved", tone: "sky" },
  executed: { label: "Order placed", short: "Placed", tone: "green" },
  blocked: { label: "Blocked", short: "Blocked", tone: "red" },
};

export const OUTCOME: Record<Outcome, string> = {
  auto: "safe to proceed automatically",
  needs_approval: "needs a person's approval",
  blocked: "blocked, no supported reason left",
  held: "on hold until a flagged document is dealt with",
};

export const DOC_KIND: Record<DocumentKind, string> = {
  request: "Purchase request",
  registry: "Supplier registry",
  vendor: "Supplier web page",
  other: "Document",
};

const RULES: Record<string, string> = {
  html_comment: "Hidden comment in the page's code",
  hidden_text: "Text styled to be invisible",
  fake_message_block: "Poses as a message from your team",
  fake_system_message: "Poses as a system message",
  task_hijack: "Tries to take over the agent's task",
  ignore_instructions: "Tells the AI to ignore its instructions",
  addressed_to_ai: "Speaks directly to AI assistants",
  steering: "Pushes one particular supplier",
  user_report: "Reported by a person",
};

export const ruleLabel = (rule: string) => RULES[rule] ?? rule.replaceAll("_", " ");

export function reasonTitle(kind: ReasonKind, author: string | null): string {
  const who = author ? `the ${author}` : "an agent";
  if (kind === "extraction") return `Read in a document by ${who}`;
  if (kind === "inference") return `Concluded by ${who}`;
  return `Decided by ${who}`;
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
export const money = (n: number) => usd.format(n);

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export interface OrderParts {
  label: string;
  quantity: string;
  item: string;
  vendor: string;
  unit: string;
  total: string;
}

/** "PO-1001: 100 servo actuators from Vantor Motion at $480 = $48,000" */
export function orderParts(summary: string): OrderParts | null {
  const m = /^(PO-\d+): (\d[\d,]*) (.+?) from (.+?) at (\$[\d,.]+) = (\$[\d,.]+)$/.exec(summary);
  return m ? { label: m[1], quantity: m[2], item: m[3], vendor: m[4], unit: m[5], total: m[6] } : null;
}

export const orderLabel = (summary: string, id: string) => orderParts(summary)?.label ?? id;

/** The approval check's notes (joined with "; " by the server), one sentence each. */
export function noteLines(note: string | null): string[] {
  return (note ?? "").split("; ").filter(Boolean).map((n) => {
    if (/^amount .* is at or above/.test(n)) return `A person must approve it: the ${n}.`;
    if (n.startsWith("no justification holds")) return "None of its reasons holds on the memory as it is now.";
    if (n === "not reversible") return "It can't be undone once placed, so a person must approve it.";
    const sentence = n.charAt(0).toUpperCase() + n.slice(1);
    return /[.!?]$/.test(sentence) ? sentence : `${sentence}.`;
  });
}

/** "Servo actuators for RehabArm v2 must come from…" -> "Servo actuators for RehabArm v2" */
export function caseTitle(request: string): string {
  const first = request.split("\n").map((l) => l.replace(/^\s*\d+[.)]\s*/, "").trim()).find(Boolean) ?? "";
  const m = /^(.+?)\s+(?:must|should|needs?|has to|have to)\b/i.exec(first);
  const title = (m ? m[1] : first).replace(/[.:]$/, "");
  if (!title) return "New purchase request";
  return title.length > 72 ? `${title.slice(0, 70)}…` : title;
}

export const listOf = (items: string[]) =>
  items.length <= 1 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
