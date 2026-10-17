// web/src/components/AgentStrip.tsx
// The three workers: two AI agents, and Antidote watching their memory.
import { BookOpen, Check, Hourglass, ShieldCheck, ShoppingCart, type LucideIcon } from "lucide-react";
import type { AgentKey, AgentView } from "../useAntidote";
import { Card, cx, PulseDot } from "./ui";

const AGENTS: Record<AgentKey, { name: string; role: string; Icon: LucideIcon; tint: string }> = {
  researcher: { name: "Researcher", role: "Reads the documents", Icon: BookOpen, tint: "bg-indigo-100 text-indigo-700" },
  buyer: { name: "Buyer", role: "Drafts the order", Icon: ShoppingCart, tint: "bg-violet-100 text-violet-700" },
  guard: { name: "Antidote", role: "Guards the memory", Icon: ShieldCheck, tint: "bg-teal-100 text-teal-700" },
};

function Status({ state }: { state: AgentView["state"] }) {
  if (state === "working") return <PulseDot className="bg-indigo-500" />;
  if (state === "waiting") return <Hourglass className="size-3.5 text-amber-500" />;
  if (state === "done") return <Check className="size-3.5 text-emerald-500" strokeWidth={3} />;
  return <span className="size-2 rounded-full bg-slate-300" />;
}

export function AgentStrip({ agents }: { agents: Record<AgentKey, AgentView> }) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {(Object.keys(AGENTS) as AgentKey[]).map((key) => {
        const { name, role, Icon, tint } = AGENTS[key];
        const view = agents[key];
        return (
          <Card
            key={key}
            className={cx("relative overflow-hidden p-3 transition", view.state === "working" && "border-indigo-200 ring-2 ring-indigo-100")}
          >
            {view.state === "working" && <div className="shimmer pointer-events-none absolute inset-0" />}
            <div className="relative flex items-center gap-2.5">
              <span className={cx("grid size-8 shrink-0 place-items-center rounded-lg", tint)}>
                <Icon className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold leading-4 text-slate-900">{name}</div>
                <div className="truncate text-[11px] text-slate-500">{role}</div>
              </div>
              <Status state={view.state} />
            </div>
            <p className="relative mt-2 line-clamp-2 min-h-[34px] text-[12px] leading-[17px] text-slate-600">{view.message}</p>
          </Card>
        );
      })}
    </div>
  );
}
