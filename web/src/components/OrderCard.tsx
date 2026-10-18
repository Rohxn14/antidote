// web/src/components/OrderCard.tsx
// The Buyer's recommendation, what it rests on, and the decisions a person makes about it.
// Approving and placing an order both re-check, in FalkorDB, that its reasons still hold;
// an order resting on a flagged document is held until someone deals with the alert.
import {
  Ban, Check, CircleCheck, CircleX, GitBranch, Lock, MessageSquareQuote, Package, Quote,
  RotateCcw, Send, ShieldAlert, ShieldCheck, ShieldX,
} from "lucide-react";
import type { ReactNode } from "react";
import type { Decision, Document, OrderActionResponse } from "../contract";
import { basisOf, type Basis, type Memory } from "../lib/memory";
import { listOf, money, noteLines, ORDER_STATE, orderParts } from "../lib/words";
import type { Pending } from "../useAntidote";
import { Badge, Button, Card, cx, SectionLabel } from "./ui";

function Row({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex gap-2.5">
      <span className="mt-0.5 shrink-0 text-slate-400 [&_svg]:size-4">{icon}</span>
      <div className="min-w-0">
        <dt className="text-[11px] font-medium uppercase tracking-[0.06em] text-slate-400">{label}</dt>
        <dd className="text-[12.5px] leading-[18px] text-slate-700">{children}</dd>
      </div>
    </div>
  );
}

const titles = (docs: Document[]) => listOf(docs.map((d) => d.title));

/** One fact the order rests on, and what stands behind it. */
function BasisLine({ item, onOpenDocument }: { item: Basis; onOpenDocument: (id: string) => void }) {
  const trusted = item.documents.filter((d) => d.trust === "trusted");
  const distrusted = item.documents.filter((d) => d.trust === "quarantined");
  let behind: ReactNode;
  let tone = "text-slate-500";
  if (item.kind === "rule") {
    behind = "Your rule, from your request";
  } else if (!item.supported && distrusted.length) {
    behind = <>Rested on {titles(distrusted)}, which you stopped trusting</>;
    tone = "text-rose-700";
  } else if (item.kind === "check" && trusted.length) {
    behind = <>Confirmed by {titles(trusted)} (trusted)</>;
    tone = "text-emerald-700";
  } else if (item.kind === "check") {
    behind = <>Only {titles(item.documents)} says so: nothing trusted confirms it</>;
    tone = "text-amber-700";
  } else {
    behind = <>The supplier's own statement, from {titles(item.documents)}</>;
  }
  const Icon = !item.supported ? CircleX : item.kind === "check" && !trusted.length ? ShieldAlert : CircleCheck;
  const iconTone = !item.supported ? "text-rose-500" : item.kind === "check" && !trusted.length ? "text-amber-500" : "text-emerald-500";
  return (
    <li className="flex gap-2.5">
      <Icon className={cx("mt-0.5 size-4 shrink-0", iconTone)} />
      <div className="min-w-0">
        <p className={cx("text-[12.5px] leading-[18px]", item.supported ? "text-slate-800" : "text-slate-400 line-through")}>{item.text}</p>
        <p className={cx("text-[11.5px] leading-4", tone)}>
          {behind}
          {item.documents.length > 0 && item.kind !== "rule" && (
            <button
              type="button"
              onClick={() => onOpenDocument(item.documents[0].id)}
              className="ml-1.5 font-medium text-indigo-600 hover:text-indigo-800 hover:underline"
            >
              open
            </button>
          )}
        </p>
      </div>
    </li>
  );
}

/** Why the Buyer moved from an earlier order to this one, from the facts themselves. */
function switchNote(m: Memory, earlier: Decision, current: Decision): string | null {
  if (earlier.amount === null || current.amount === null) return null;
  const was = orderParts(earlier.summary);
  const now = orderParts(current.summary);
  const diff = current.amount - earlier.amount;
  const cost = diff === 0 ? "costs the same as" : `costs ${money(Math.abs(diff))} ${diff > 0 ? "more" : "less"} than`;
  const nowCheck = basisOf(m, current.id).find((b) => b.kind === "check");
  const wasCheck = basisOf(m, earlier.id).find((b) => b.kind === "check");
  const trustedNow = nowCheck?.documents.filter((d) => d.trust === "trusted") ?? [];
  const parts = [`${now?.label ?? current.id} ${cost} ${was?.label ?? earlier.id}.`];
  if (trustedNow.length) parts.push(`${now?.vendor ?? "This supplier"}'s qualification is confirmed by ${titles(trustedNow)}, a trusted document.`);
  if (wasCheck && !wasCheck.supported) {
    const gone = wasCheck.documents.filter((d) => d.trust === "quarantined");
    parts.push(`${was?.vendor ?? "The earlier supplier"}'s rested only on ${titles(wasCheck.documents)}${gone.length ? ", which you stopped trusting" : ""}.`);
  }
  return parts.join(" ");
}

function Outcome({ response }: { response: OrderActionResponse }) {
  return (
    <div className="mx-4 mb-3 flex gap-2.5 rounded-xl bg-emerald-50 px-3 py-2.5 text-[12.5px] leading-5 text-emerald-900 ring-1 ring-emerald-200">
      <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-600" />
      <p>{response.message}</p>
    </div>
  );
}

function Empty({ running }: { running: boolean }) {
  return (
    <Card className="p-4">
      <SectionLabel icon={<Package />}>Recommended order</SectionLabel>
      {running ? (
        <div className="mt-4 space-y-2.5">
          <div className="shimmer h-5 w-2/3 rounded-md bg-slate-100" />
          <div className="shimmer h-4 w-1/2 rounded-md bg-slate-100" />
          <div className="shimmer h-16 rounded-xl bg-slate-100" />
          <p className="pt-1 text-[12px] text-slate-500">The Buyer will recommend an order once the facts are in.</p>
        </div>
      ) : (
        <div className="mt-3 rounded-xl border border-dashed border-slate-200 px-4 py-6 text-center">
          <p className="text-[13px] font-medium text-slate-600">No recommendation yet</p>
          <p className="mx-auto mt-1 max-w-[290px] text-[12px] leading-[18px] text-slate-500">
            Orders over $5,000 need a person's approval, and Antidote stops any order whose reasons no longer hold.
          </p>
        </div>
      )}
    </Card>
  );
}

/** What Antidote promises, shown until the first alert needs the space. */
export function Guarantees() {
  const items = [
    {
      Icon: Quote, title: "Every fact keeps its source",
      text: "The agents must quote the document they read. Each fact is stored with the reason it is believed.",
    },
    {
      Icon: ShieldCheck, title: "Orders are checked against today's memory",
      text: "Approving or placing an order re-runs the check inside FalkorDB. If its reasons no longer hold, it is blocked.",
    },
    {
      Icon: ShieldX, title: "Distrust a source, and what it built goes",
      text: "Preview the impact on a copy first. Facts that other documents also back survive.",
    },
  ];
  return (
    <Card className="p-4">
      <SectionLabel icon={<ShieldCheck />}>What Antidote guarantees</SectionLabel>
      <ul className="mt-3 space-y-3">
        {items.map(({ Icon, title, text }) => (
          <li key={title} className="flex gap-3">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-teal-50 text-teal-700 ring-1 ring-inset ring-teal-100">
              <Icon className="size-4" />
            </span>
            <div>
              <div className="text-[13px] font-semibold leading-5 text-slate-900">{title}</div>
              <p className="text-[12px] leading-[18px] text-slate-500">{text}</p>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function OrderCard({ orders, memory, lastAction, pending, running, onWhy, onDecide, onReplan, onOpenDocument }: {
  orders: Decision[];
  memory: Memory;
  lastAction: OrderActionResponse | null;
  pending: Pending | null;
  running: "run" | "replan" | null;
  onWhy: (id: string) => void;
  onDecide: (id: string, action: "approve" | "execute") => void;
  onReplan: () => void;
  onOpenDocument: (id: string) => void;
}) {
  const order = orders.length ? orders[orders.length - 1] : null;
  if (!order) return <Empty running={running === "run"} />;

  const parts = orderParts(order.summary);
  const held = order.held_by.map((id) => memory.documents[id]).filter(Boolean);
  const state = order.state ? ORDER_STATE[order.state] : null;
  const blocked = order.state === "blocked";
  const lost = !order.supported || blocked;
  const earlier = orders.slice(0, -1).reverse();
  const basis = basisOf(memory, order.id);
  const why = earlier.length ? switchNote(memory, earlier[0], order) : null;
  const outcome = lastAction?.decision_id === order.id && lastAction.outcome !== "held" && lastAction.state !== "blocked" ? lastAction : null;
  const vendor = parts?.vendor ?? (order.vendor_id ? memory.vendors[order.vendor_id] : null) ?? order.summary;
  const busy = pending !== null || running !== null;
  const approvalNotes = noteLines(order.note).filter(() => !blocked);

  return (
    <Card className={cx("overflow-hidden", lost && "border-rose-200", held.length > 0 && !lost && "border-amber-200")}>
      <div className={cx("px-4 pb-4 pt-4", lost ? "bg-gradient-to-b from-rose-50 to-white" : held.length ? "bg-gradient-to-b from-amber-50 to-white" : "bg-gradient-to-b from-indigo-50/80 to-white")}>
        <div className="flex items-center justify-between gap-2">
          <SectionLabel icon={<Package />}>{earlier.length ? "New recommendation" : "Recommended order"}</SectionLabel>
          {held.length > 0 && !lost ? <Badge tone="amber">On hold</Badge> : state && <Badge tone={state.tone}>{state.label}</Badge>}
        </div>
        <div className="mt-3 flex items-end justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.07em] text-slate-400">{parts?.label ?? order.id}</div>
            <div className={cx("truncate text-[21px] font-semibold tracking-tight text-slate-900", lost && "text-rose-900/60 line-through decoration-rose-300")}>
              {vendor}
            </div>
            {parts && <div className="text-[12.5px] text-slate-600">{parts.quantity} {parts.item} · {parts.unit} each</div>}
          </div>
          <div className="shrink-0 text-right">
            <div className="text-[11px] text-slate-400">Total</div>
            <div className="text-[22px] font-semibold tabular-nums tracking-tight text-slate-900">
              {order.amount !== null ? money(order.amount) : parts?.total}
            </div>
          </div>
        </div>
      </div>

      {held.length > 0 && !lost && (
        <div className="mx-4 mb-3 flex gap-2.5 rounded-xl bg-amber-50 px-3 py-2.5 text-[12.5px] leading-5 text-amber-950 ring-1 ring-amber-200">
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-600" />
          <p>
            <span className="font-semibold">On hold.</span> It rests on {titles(held)}, which contains hidden
            instructions. Approval waits until you deal with the alert: stop trusting the page, and the Buyer can
            re-plan without it.
          </p>
        </div>
      )}

      {blocked && (
        <div className="mx-4 mb-3 rounded-xl bg-rose-50 px-3 py-2.5 text-[12.5px] leading-5 text-rose-950 ring-1 ring-rose-200">
          <div className="flex items-center gap-2 font-semibold text-rose-800">
            <Ban className="size-4" /> Blocked by Antidote
          </div>
          <ul className="mt-1.5 space-y-1">
            {noteLines(order.note).map((line, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-rose-400" />
                {line}
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-rose-900/75">An approval can't override missing support.</p>
        </div>
      )}

      {why && (
        <div className="mx-4 mb-3 rounded-xl bg-indigo-50/70 px-3 py-2.5 text-[12.5px] leading-5 text-indigo-950 ring-1 ring-indigo-100">
          <span className="font-semibold">Why the change: </span>{why}
        </div>
      )}

      {order.reasoning && (
        <div className="mx-4 mb-3 flex gap-2.5">
          <MessageSquareQuote className="mt-0.5 size-4 shrink-0 text-violet-500" />
          <div>
            <div className="text-[11px] font-medium uppercase tracking-[0.06em] text-slate-400">The Buyer's reasoning</div>
            <p className="text-[12.5px] italic leading-[18px] text-slate-700">“{order.reasoning}”</p>
          </div>
        </div>
      )}

      <div className="border-t border-slate-100 px-4 py-3">
        <div className="text-[11px] font-medium uppercase tracking-[0.06em] text-slate-400">What it rests on</div>
        <ul className="mt-2 space-y-2.5">
          {basis.map((item) => <BasisLine key={item.id} item={item} onOpenDocument={onOpenDocument} />)}
        </ul>
      </div>

      {approvalNotes.length > 0 && !held.length && (
        <dl className="border-t border-slate-100 px-4 py-3">
          <Row icon={<Lock />} label="Approval">{approvalNotes.join(" ")}</Row>
        </dl>
      )}

      {outcome && <Outcome response={outcome} />}

      <div className="flex flex-wrap gap-2 border-t border-slate-100 px-4 py-3">
        <Button icon={<GitBranch />} onClick={() => onWhy(order.id)}>Why this supplier?</Button>
        {order.state === "pending_approval" && !lost && (
          <Button
            variant="brand"
            icon={<Check />}
            loading={pending === "approve"}
            disabled={busy || held.length > 0}
            title={held.length ? "On hold: deal with the security alert first" : undefined}
            onClick={() => onDecide(order.id, "approve")}
          >
            Approve
          </Button>
        )}
        {order.state === "authorized" && !lost && (
          <Button
            variant="brand"
            icon={<Send />}
            loading={pending === "execute"}
            disabled={busy || held.length > 0}
            onClick={() => onDecide(order.id, "execute")}
          >
            Place the order
          </Button>
        )}
        {lost && (
          <Button variant="brand" icon={<RotateCcw />} loading={running === "replan"} disabled={busy} onClick={onReplan}>
            Re-plan with what's still true
          </Button>
        )}
      </div>

      {earlier.length > 0 && (
        <div className="border-t border-slate-100 bg-slate-50/70 px-4 py-2.5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.07em] text-slate-400">Earlier</div>
          {earlier.map((o) => {
            const p = orderParts(o.summary);
            const s = o.state ? ORDER_STATE[o.state] : null;
            return (
              <button
                key={o.id}
                type="button"
                onClick={() => onWhy(o.id)}
                className="mt-1.5 flex w-full items-center gap-2 rounded-lg text-left text-[12.5px] hover:text-slate-900"
              >
                <span className="font-medium text-slate-700">{p?.label ?? o.id}</span>
                <span className="truncate text-slate-500 line-through decoration-slate-300">
                  {p ? `${p.vendor} · ${p.total}` : o.summary}
                </span>
                {s && <Badge tone={s.tone} className="ml-auto">{s.label}</Badge>}
              </button>
            );
          })}
        </div>
      )}
    </Card>
  );
}
