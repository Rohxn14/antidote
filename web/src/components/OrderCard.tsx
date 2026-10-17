// web/src/components/OrderCard.tsx
// The Buyer's recommendation and the decisions a person makes about it. Approving
// and placing an order both re-check, in FalkorDB, that its reasons still hold.
import {
  Ban, Check, CircleCheck, CircleX, GitBranch, Lock, Package, Quote, RotateCcw, Scale, Send, ShieldCheck, ShieldX,
} from "lucide-react";
import type { ReactNode } from "react";
import type { Decision, OrderActionResponse } from "../contract";
import type { Pending } from "../useAntidote";
import { approvalNote, EVIDENCE, money, ORDER_STATE, orderParts } from "../lib/words";
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

function Outcome({ response }: { response: OrderActionResponse }) {
  const blocked = response.state === "blocked";
  return (
    <div
      className={cx(
        "mx-4 mb-3 flex gap-2.5 rounded-xl px-3 py-2.5 text-[12.5px] leading-5",
        blocked ? "bg-rose-50 text-rose-900 ring-1 ring-rose-200" : "bg-emerald-50 text-emerald-900 ring-1 ring-emerald-200",
      )}
    >
      {blocked ? <Ban className="mt-0.5 size-4 shrink-0 text-rose-600" /> : <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-600" />}
      <p>
        <span className="font-semibold">{blocked ? "Antidote blocked this order. " : ""}</span>
        {response.message}
        {blocked && " The approval check looks at the memory as it is now, not as it was when the order was drafted."}
      </p>
    </div>
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
            Orders over $5,000 need a person's approval, and Antidote blocks any order whose reasons no longer hold.
          </p>
        </div>
      )}
    </Card>
  );
}

export function OrderCard({ orders, vendors, lastAction, pending, running, onWhy, onDecide, onReplan }: {
  orders: Decision[];
  vendors: Record<string, string>;
  lastAction: OrderActionResponse | null;
  pending: Pending | null;
  running: "run" | "replan" | null;
  onWhy: (id: string) => void;
  onDecide: (id: string, action: "approve" | "execute") => void;
  onReplan: () => void;
}) {
  const order = orders.length ? orders[orders.length - 1] : null;
  if (!order) return <Empty running={running === "run"} />;

  const parts = orderParts(order.summary);
  const state = order.state ? ORDER_STATE[order.state] : null;
  const lost = !order.supported;
  const evidence = order.evidence ? EVIDENCE[order.evidence] : null;
  const outcome = lastAction?.decision_id === order.id ? lastAction : null;
  const earlier = orders.slice(0, -1).reverse();
  const vendor = parts?.vendor ?? (order.vendor_id ? vendors[order.vendor_id] : null) ?? order.summary;
  const busy = pending !== null || running !== null;

  return (
    <Card className={cx("overflow-hidden", lost && "border-rose-200")}>
      <div className={cx("px-4 pb-4 pt-4", lost ? "bg-gradient-to-b from-rose-50 to-white" : "bg-gradient-to-b from-indigo-50/80 to-white")}>
        <div className="flex items-center justify-between gap-2">
          <SectionLabel icon={<Package />}>{earlier.length ? "New recommendation" : "Recommended order"}</SectionLabel>
          {state && <Badge tone={state.tone}>{state.label}</Badge>}
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

      <dl className="space-y-2.5 border-t border-slate-100 px-4 py-3">
        <Row icon={lost ? <CircleX className="text-rose-500" /> : <CircleCheck className="text-emerald-500" />} label="Support">
          {lost ? (
            <span className="font-medium text-rose-700">Lost: none of its reasons holds any more.</span>
          ) : (
            "Every reason behind it holds in the memory right now."
          )}
        </Row>
        {evidence && (
          <Row icon={<Scale />} label="Evidence">
            <span className="font-medium">{evidence.label}.</span> <span className="text-slate-500">{evidence.hint}</span>
          </Row>
        )}
        {order.note && <Row icon={<Lock />} label="Approval">{approvalNote(order.note)}</Row>}
      </dl>

      {outcome && <Outcome response={outcome} />}

      <div className="flex flex-wrap gap-2 border-t border-slate-100 px-4 py-3">
        <Button icon={<GitBranch />} onClick={() => onWhy(order.id)}>Why this supplier?</Button>
        {order.state === "pending_approval" && !lost && (
          <Button variant="brand" icon={<Check />} loading={pending === "approve"} disabled={busy} onClick={() => onDecide(order.id, "approve")}>
            Approve
          </Button>
        )}
        {order.state === "pending_approval" && lost && (
          <Button variant="dangerOutline" icon={<Check />} loading={pending === "approve"} disabled={busy} onClick={() => onDecide(order.id, "approve")}>
            Approve anyway
          </Button>
        )}
        {order.state === "authorized" && (
          <Button variant="brand" icon={<Send />} loading={pending === "execute"} disabled={busy} onClick={() => onDecide(order.id, "execute")}>
            Place the order
          </Button>
        )}
        {order.state === "blocked" && (
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
