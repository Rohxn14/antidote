// web/src/components/DocumentList.tsx
// The documents the agents can read, with how far each one is trusted.
import { BookOpen, ChevronRight, ClipboardList, FileText, Files, ShieldAlert } from "lucide-react";
import type { Document, DocumentKind } from "../contract";
import { factsPerDocument, type Memory } from "../lib/memory";
import { plural, TRUST } from "../lib/words";
import { Badge, Card, cx, SectionLabel } from "./ui";

const ORDER: Record<DocumentKind, number> = { request: 0, registry: 1, vendor: 2, other: 3 };

function DocIcon({ doc }: { doc: Document }) {
  const Icon = doc.kind === "request" ? ClipboardList : doc.kind === "registry" ? BookOpen : FileText;
  const tint = doc.trust === "quarantined"
    ? "bg-rose-100 text-rose-600"
    : doc.trust === "trusted" ? "bg-emerald-50 text-emerald-600" : "bg-amber-50 text-amber-600";
  return (
    <span className={cx("mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg", tint)}>
      <Icon className="size-4" />
    </span>
  );
}

export function DocumentList({ memory, readingId, onOpen }: {
  memory: Memory; readingId: string | null; onOpen: (id: string) => void;
}) {
  const docs = Object.values(memory.documents).sort(
    (a, b) => ORDER[a.kind] - ORDER[b.kind] || a.title.localeCompare(b.title),
  );
  const facts = factsPerDocument(memory);
  const review = Object.fromEntries(memory.alerts.map((a) => [a.document_id, a]));

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-4">
        <SectionLabel icon={<Files />}>Documents the agents can read</SectionLabel>
        <span className="text-[11px] tabular-nums text-slate-400">{docs.length}</span>
      </div>
      <ul className="mt-2 divide-y divide-slate-100">
        {docs.map((d) => {
          const trust = TRUST[d.trust];
          const reading = readingId === d.id;
          return (
            <li key={d.id}>
              <button
                type="button"
                onClick={() => onOpen(d.id)}
                className={cx(
                  "group relative flex w-full items-start gap-3 overflow-hidden px-4 py-2.5 text-left transition hover:bg-slate-50",
                  d.trust === "quarantined" && "bg-rose-50/50",
                )}
              >
                {reading && <span className="shimmer pointer-events-none absolute inset-0" />}
                <DocIcon doc={d} />
                <div className="min-w-0 flex-1">
                  <div
                    className={cx(
                      "truncate text-[13px] font-medium text-slate-800",
                      d.trust === "quarantined" && "text-rose-900/70 line-through decoration-rose-300",
                    )}
                  >
                    {d.title}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <Badge tone={trust.tone} title={trust.hint}>{trust.label}</Badge>
                    {review[d.id]?.resolution === "open" && d.trust !== "quarantined" && (
                      <Badge tone="red" icon={<ShieldAlert />} title={review[d.id].reason}>Under review</Badge>
                    )}
                    {d.vendor_id && memory.standing[d.vendor_id] && (
                      <Badge tone={memory.standing[d.vendor_id] === "blacklisted" ? "slate" : "amber"}>
                        {memory.standing[d.vendor_id] === "blacklisted" ? "Supplier blacklisted" : "Supplier suspended"}
                      </Badge>
                    )}
                    {reading ? (
                      <span className="text-[11px] font-medium text-indigo-600">Reading…</span>
                    ) : facts[d.id] ? (
                      <span className="text-[11px] text-slate-500">{plural(facts[d.id], "fact")}</span>
                    ) : null}
                  </div>
                </div>
                <ChevronRight className="mt-2 size-4 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500" />
              </button>
            </li>
          );
        })}
      </ul>
      <p className="border-t border-slate-100 bg-slate-50/70 px-4 py-2.5 text-[11.5px] leading-[17px] text-slate-500">
        <span className="font-medium text-emerald-700">Trusted</span> documents count as evidence on their own;{" "}
        <span className="font-medium text-amber-700">unverified</span> ones are usable but weaker. Open one to see
        exactly what the agents read.
      </p>
    </Card>
  );
}
