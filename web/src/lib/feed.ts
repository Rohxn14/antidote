// web/src/lib/feed.ts
// One activity-feed line per event, in plain words. Reasons are not listed here:
// they appear in the graph, as the links between facts.
import type { Agent, AntidoteEvent } from "../contract";
import type { Memory } from "./memory";
import { OUTCOME, orderParts, plural } from "./words";

export type Who = "researcher" | "buyer" | "guard" | "you";

export type FeedTone =
  | "status" | "fact" | "refused" | "decision" | "gate" | "alert" | "error" | "done"
  | "action" | "blocked" | "good";

export interface FeedItem {
  id: number;
  at: number | null; // seconds since the run started
  who: Who;
  tone: FeedTone;
  title: string;
  body?: string;
  quote?: string;
  documentId?: string | null;
}

export type FeedEntry = Omit<FeedItem, "id" | "at">;

export const WHO: Record<Agent, Exclude<Who, "you">> = {
  researcher: "researcher", buyer: "buyer", security: "guard", approval: "guard", system: "guard",
};

export function describe(e: AntidoteEvent, m: Memory): FeedEntry | null {
  switch (e.type) {
    case "agent_status":
      return { who: WHO[e.data.agent], tone: "status", title: e.data.message, documentId: e.data.document_id };
    case "fact_recorded":
      return e.data.document_id
        ? {
            who: "researcher", tone: "fact", title: "Recorded a fact", body: e.data.text,
            quote: e.data.quote ?? undefined, documentId: e.data.document_id,
          }
        : { who: "researcher", tone: "fact", title: "Drew a conclusion", body: e.data.text };
    case "claim_refused":
      return {
        who: WHO[e.data.agent], tone: "refused", title: "A claim was refused by Antidote's checks",
        body: `${e.data.text} (${e.data.reason})`, documentId: e.data.document_id,
      };
    case "decision_recorded": {
      if (e.data.kind === "purchase_order") {
        const p = orderParts(e.data.summary);
        return {
          who: "buyer", tone: "decision", title: `Drafted ${p?.label ?? "a purchase order"}`,
          body: p ? `${p.quantity} ${p.item} from ${p.vendor} at ${p.unit} each, ${p.total} in total.` : e.data.summary,
        };
      }
      const vendor = e.data.vendor_id ? m.vendors[e.data.vendor_id] : null;
      return { who: "buyer", tone: "decision", title: "Shortlisted a supplier", body: vendor ?? e.data.summary };
    }
    case "gate_verdict":
      return {
        who: "guard", tone: e.data.outcome === "blocked" ? "blocked" : "gate",
        title: `Approval check: ${OUTCOME[e.data.outcome]}`, body: e.data.reasons.join("; "),
      };
    case "security_alert":
      return {
        who: "guard", tone: "alert", title: `Put under review: ${e.data.document_title}`,
        body: `Before the Buyer decides: ${e.data.reason}.${e.data.suspended.length ? ` ${e.data.suspended.join(", ")} suspended: nothing on this page counts and no order can go to it until you decide.` : ""}`,
        documentId: e.data.document_id,
      };
    case "error":
      return { who: "guard", tone: "error", title: "Something went wrong", body: e.data.message };
    case "run_complete": {
      const s = e.data.summary;
      const parts = [
        s.facts ? plural(s.facts, "fact") : null,
        plural(s.decisions, "decision"),
        s.alerts ? plural(s.alerts, "alert") : null,
        s.refused ? `${s.refused} refused` : null,
      ].filter(Boolean);
      return { who: "guard", tone: "done", title: "Finished", body: `${parts.join(" · ")}. All of it is stored in FalkorDB.` };
    }
    default:
      return null;
  }
}
