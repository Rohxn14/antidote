// web/src/components/AlertCard.tsx
// Antidote's security scan found instructions hidden in a document.
import { Eye, Radar, ShieldAlert } from "lucide-react";
import type { Alert, Document } from "../contract";
import type { Pending } from "../useAntidote";
import { ruleLabel } from "../lib/words";
import { Badge, Button, Card, cx } from "./ui";

export function AlertCard({ alert, document, previewing, pending, busy, onShow, onPreview }: {
  alert: Alert;
  document: Document | undefined;
  previewing: boolean;
  pending: Pending | null;
  busy: boolean;
  onShow: () => void;
  onPreview: () => void;
}) {
  const distrusted = document?.trust === "quarantined";
  const steers = alert.findings.some((f) => f.rule === "steering");
  const shown = alert.findings.slice(0, 4);

  return (
    <Card className={cx("overflow-hidden", !distrusted && "border-rose-200 ring-1 ring-rose-100")}>
      <div className="flex gap-3 bg-gradient-to-b from-rose-50 to-white px-4 pb-3 pt-4">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-rose-600 text-white shadow-sm shadow-rose-600/30">
          <ShieldAlert className="size-[18px]" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold text-rose-900">Hidden instructions found</div>
          <div className="truncate text-[12.5px] text-rose-800/80">
            in <span className="font-medium">{alert.document_title}</span>
          </div>
        </div>
        {distrusted && <Badge tone="slate" className="self-start">No longer trusted</Badge>}
      </div>
      {distrusted ? (
        <>
          <p className="px-4 text-[12.5px] leading-5 text-slate-700">
            You stopped trusting this page. Everything that rested only on it was withdrawn from the agents' memory.
          </p>
          <div className="mt-3 flex border-t border-slate-100 px-4 py-3">
            <Button size="sm" icon={<Eye />} onClick={onShow}>See what the AI read</Button>
          </div>
        </>
      ) : (
        <AlertDetails alert={alert} steers={steers} shown={shown} previewing={previewing} pending={pending} busy={busy} onShow={onShow} onPreview={onPreview} />
      )}
    </Card>
  );
}

function AlertDetails({ alert, steers, shown, previewing, pending, busy, onShow, onPreview }: {
  alert: Alert; steers: boolean; shown: Alert["findings"]; previewing: boolean; pending: Pending | null;
  busy: boolean; onShow: () => void; onPreview: () => void;
}) {
  return (
    <>
      <p className="px-4 text-[12.5px] leading-5 text-slate-700">
        This page hides text that people can't see but AI agents read as ordinary text.{" "}
        {steers ? "It is written to steer the agents towards one supplier." : "It is written to change what the agents do."}
      </p>
      <ul className="mx-4 mt-2.5 space-y-1.5">
        {shown.map((f, i) => (
          <li key={i} className="rounded-lg bg-slate-50 px-2.5 py-1.5 ring-1 ring-inset ring-slate-100">
            <div className="text-[11.5px] font-medium text-slate-700">{ruleLabel(f.rule)}</div>
            <div className="line-clamp-2 font-mono text-[11px] leading-4 text-slate-500">{f.evidence}</div>
          </li>
        ))}
      </ul>
      {alert.findings.length > shown.length && (
        <p className="mx-4 mt-1.5 text-[11.5px] text-slate-500">and {alert.findings.length - shown.length} more warning signs</p>
      )}
      <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-100 px-4 py-3">
        <Button icon={<Eye />} onClick={onShow}>See what the AI read</Button>
        {!previewing && (
          <Button variant="dangerOutline" icon={<Radar />} loading={pending === "impact"} disabled={busy} onClick={onPreview}>
            What if we stop trusting it?
          </Button>
        )}
      </div>
    </>
  );
}
