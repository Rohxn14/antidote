// web/src/components/AlertCard.tsx
// A document Antidote put under review before the Buyer decided: hidden instructions
// aimed at AI, or a claim a trusted document contradicts. While it is under review it
// counts for nothing and its supplier is suspended; a person blacklists or clears it.
import { Ban, CheckCircle2, Eye, RefreshCw, ShieldAlert } from "lucide-react";
import type { Alert, Document } from "../contract";
import type { Pending } from "../useAntidote";
import { listOf, ruleLabel } from "../lib/words";
import { Badge, Button, Card, cx } from "./ui";

function headline(alert: Alert): string {
  const instructions = alert.findings.some((f) => f.rule !== "conflict" && f.rule !== "hidden_fact");
  const unseen = alert.findings.some((f) => f.rule === "hidden_fact");
  const conflict = alert.findings.some((f) => f.rule === "conflict");
  const hidden = instructions ? "Hidden instructions" : unseen ? "Facts hidden from people" : null;
  if (hidden && conflict) return `${hidden} and a contradicted claim`;
  if (hidden) return instructions ? "Hidden instructions found" : "Facts taken from text nobody can see";
  return "A claim trusted documents contradict";
}

export function AlertCard({ alert, document, previewing, pending, busy, onShow, onPreview, onClear, onReplan }: {
  alert: Alert;
  document: Document | undefined;
  previewing: boolean;
  pending: Pending | null;
  busy: boolean;
  onShow: () => void;
  onPreview: () => void;
  onClear: () => void;
  onReplan: () => void;
}) {
  const distrusted = alert.resolution === "distrusted" || document?.trust === "quarantined";
  const cleared = alert.resolution === "cleared" && !distrusted;
  const open = !distrusted && !cleared;
  const suppliers = alert.suspended.length ? listOf(alert.suspended) : null;

  return (
    <Card className={cx("overflow-hidden", open && "border-rose-200 ring-1 ring-rose-100")}>
      <div className={cx("flex gap-3 bg-gradient-to-b to-white px-4 pb-3 pt-4", open ? "from-rose-50" : "from-slate-50")}>
        <span className={cx("grid size-9 shrink-0 place-items-center rounded-xl text-white shadow-sm",
          open ? "bg-rose-600 shadow-rose-600/30" : "bg-slate-500 shadow-slate-500/30")}>
          <ShieldAlert className="size-[18px]" />
        </span>
        <div className="min-w-0 flex-1">
          <div className={cx("text-[14px] font-semibold", open ? "text-rose-900" : "text-slate-800")}>{headline(alert)}</div>
          <div className="truncate text-[12.5px] text-slate-600">
            in <span className="font-medium">{alert.document_title}</span>
          </div>
        </div>
        {open && <Badge tone="red" className="self-start">Under review</Badge>}
        {distrusted && <Badge tone="slate" className="self-start">{suppliers ? "Blacklisted" : "Distrusted"}</Badge>}
        {cleared && <Badge tone="green" className="self-start">False alarm</Badge>}
      </div>

      {open && (
        <p className="px-4 text-[12.5px] leading-5 text-slate-700">
          Antidote checked this page <span className="font-medium">before the Buyer decided</span>. While it is under
          review, nothing on it counts as evidence{suppliers ? <>, and <span className="font-medium">{suppliers}</span> is suspended: no order can go to it</> : null}.
          Blacklisting is your call: the check can be wrong, and anyone able to plant text on a page could otherwise get a supplier blacklisted.
        </p>
      )}
      {distrusted && (
        <p className="px-4 text-[12.5px] leading-5 text-slate-700">
          You stopped trusting this page{suppliers ? <> and <span className="font-medium">{suppliers}</span> is blacklisted</> : null}.
          Everything that rested only on it is gone from the agents' memory for good.
        </p>
      )}
      {cleared && (
        <p className="px-4 text-[12.5px] leading-5 text-slate-700">
          You marked this as a false alarm: the page counts as evidence again{suppliers ? <> and {suppliers} is no longer suspended</> : null}.
          Re-plan if you want the Buyer to consider it.
        </p>
      )}

      {open && (
        <ul className="mx-4 mt-2.5 space-y-1.5">
          {alert.findings.slice(0, 4).map((f, i) => (
            <li key={i} className="rounded-lg bg-slate-50 px-2.5 py-1.5 ring-1 ring-inset ring-slate-100">
              <div className="text-[11.5px] font-medium text-slate-700">{ruleLabel(f.rule)}</div>
              <div className={cx("text-[11px] leading-4 text-slate-500", f.rule === "conflict" ? "" : "line-clamp-2 font-mono")}>{f.evidence}</div>
            </li>
          ))}
          {alert.findings.length > 4 && (
            <li className="text-[11.5px] text-slate-500">and {alert.findings.length - 4} more warning signs</li>
          )}
        </ul>
      )}

      <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-100 px-4 py-3">
        <Button size={open ? undefined : "sm"} icon={<Eye />} onClick={onShow}>See what the AI read</Button>
        {open && !previewing && (
          <Button variant="dangerOutline" icon={<Ban />} loading={pending === "impact"} disabled={busy} onClick={onPreview}>
            {suppliers ? `Blacklist ${suppliers}…` : "Stop trusting it…"}
          </Button>
        )}
        {open && (
          <Button icon={<CheckCircle2 />} loading={pending === "clear"} disabled={busy} onClick={onClear}>
            It's a false alarm
          </Button>
        )}
        {cleared && (
          <Button size="sm" variant="brand" icon={<RefreshCw />} disabled={busy} onClick={onReplan}>
            Re-plan with it
          </Button>
        )}
      </div>
    </Card>
  );
}
