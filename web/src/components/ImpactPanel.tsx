// web/src/components/ImpactPanel.tsx
// What would change if a document stopped being trusted, worked out on a copy of the
// memory (GRAPH.COPY) before anything real changes. Then the change, or not.
import { motion } from "framer-motion";
import { History, Radar, ShieldX } from "lucide-react";
import type { ImpactResponse, RepairRecord } from "../contract";
import type { Memory } from "../lib/memory";
import type { Pending } from "../useAntidote";
import { plural, listOf } from "../lib/words";
import { Button, Card, cx, SectionLabel } from "./ui";

function Stat({ n, label, tone }: { n: number; label: string; tone: "red" | "green" }) {
  return (
    <div className="px-2 py-3 text-center">
      <div className={cx("text-[22px] font-semibold tabular-nums leading-7", n === 0 ? "text-slate-300" : tone === "red" ? "text-rose-600" : "text-emerald-600")}>
        {n}
      </div>
      <div className="mt-0.5 text-[11px] leading-[14px] text-slate-500">{label}</div>
    </div>
  );
}

function List({ title, tone, items }: { title: string; tone: "red" | "green" | "amber"; items: string[] }) {
  if (!items.length) return null;
  const dot = tone === "red" ? "bg-rose-500" : tone === "green" ? "bg-emerald-500" : "bg-amber-500";
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-[0.07em] text-slate-400">{title}</div>
      <ul className="mt-1.5 space-y-1">
        {items.map((text, i) => (
          <li key={i} className="flex gap-2 text-[12.5px] leading-[18px] text-slate-700">
            <span className={cx("mt-[7px] size-1.5 shrink-0 rounded-full", dot)} />
            {text}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ImpactPanel({ impact, memory, pending, onConfirm, onCancel }: {
  impact: ImpactResponse;
  memory: Memory;
  pending: Pending | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const title = (id: string) => memory.documents[id]?.title ?? id;
  const lost = impact.lost.filter((x) => !impact.orders_blocked.some((o) => o.id === x.id));
  const lostFacts = lost.filter((x) => x.kind === "fact");
  // A document under review already counts for nothing: the preview let it count on the
  // copy first, so these are what rest only on it, gone for good once you confirm.
  const review = memory.alerts.find((a) => a.document_id === impact.document_id && a.resolution === "open");
  const suppliers = review?.suspended.length ? listOf(review.suspended) : null;

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
      <Card className="overflow-hidden border-amber-200 ring-1 ring-amber-100">
        <div className="bg-gradient-to-b from-amber-50 to-white px-4 pb-3 pt-4">
          <SectionLabel icon={<Radar />} className="text-amber-700">Preview · nothing has changed yet</SectionLabel>
          <h3 className="mt-1.5 text-[15px] font-semibold leading-5 text-slate-900">
            If you stop trusting {title(impact.document_id)}{suppliers ? ` and blacklist ${suppliers}` : ""}
          </h3>
          <p className="mt-1.5 text-[12px] leading-[18px] text-slate-600">
            {review
              ? "It is under review, so nothing on it counts right now. On a copy of the memory inside FalkorDB, Antidote let it count again, then stopped trusting it, to show what rests only on it. "
              : "Antidote copied the memory inside FalkorDB, stopped trusting the document on the copy, and recomputed what still holds. "}
            Your real memory is untouched until you confirm.
          </p>
        </div>
        <div className="grid grid-cols-3 divide-x divide-slate-100 border-y border-slate-100">
          <Stat n={lostFacts.length} label={review ? "facts rest only on it" : "facts lose their support"} tone="red" />
          <Stat n={impact.orders_blocked.length} label={impact.orders_blocked.length === 1 ? "order would be blocked" : "orders would be blocked"} tone="red" />
          <Stat n={impact.survived.length} label="kept by other evidence" tone="green" />
        </div>
        <div className="space-y-3.5 px-4 py-3.5">
          <List title={review ? "These rest only on it: gone for good" : "These lose their support"} tone="red" items={lost.map((x) => x.text)} />
          <List title="Orders that would be blocked" tone="red" items={impact.orders_blocked.map((x) => x.text)} />
          <List
            title="Still supported, by another document"
            tone="green"
            items={impact.survived.map((s) => `${s.text} (kept by ${s.premises.map(title).join(", ")})`)}
          />
          <List
            title="Already placed: a person needs to follow up"
            tone="amber"
            items={impact.executed_affected.map((x) => x.text)}
          />
          {impact.also_quarantined.length > 0 && (
            <p className="text-[12px] text-slate-600">
              Also stops trusting {impact.also_quarantined.map(title).join(", ")}: copies of the same original.
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2 border-t border-slate-100 px-4 py-3">
          <Button variant="danger" icon={<ShieldX />} loading={pending === "quarantine"} disabled={pending !== null} onClick={onConfirm}>
            {suppliers ? `Stop trusting it and blacklist ${suppliers}` : "Stop trusting this document"}
          </Button>
          <Button variant="ghost" loading={pending === "cancel"} disabled={pending !== null} onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </Card>
    </motion.div>
  );
}

/** The audit trail: every repair applied to this memory, and who approved it. */
export function RepairLog({ repairs, memory }: { repairs: RepairRecord[]; memory: Memory }) {
  if (!repairs.length) return null;
  return (
    <Card className="p-4">
      <SectionLabel icon={<History />}>Memory repairs</SectionLabel>
      <ul className="mt-2.5 space-y-2">
        {repairs.map((r) => {
          const facts = r.withdrawn.filter((id) => memory.facts[id]).length;
          return (
            <li key={r.id} className="rounded-xl bg-slate-50 px-3 py-2.5 text-[12.5px] leading-[18px] ring-1 ring-inset ring-slate-100">
              <div className="font-medium text-slate-800">Stopped trusting {r.documents.join(", ")}</div>
              <div className="text-slate-500">
                {plural(facts, "fact")} and {plural(r.withdrawn.length - facts, "decision")} withdrawn · approved by{" "}
                {r.approved_by} · memory revision {r.revision}
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
