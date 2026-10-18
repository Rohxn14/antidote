// web/src/components/CaseBar.tsx
// The purchase case at a glance: what it is about, where it stands, what to look at next.
import { AnimatePresence, motion } from "framer-motion";
import { Briefcase, CircleCheck, Lightbulb, TriangleAlert } from "lucide-react";
import type { Chip, Suggestion } from "../lib/story";
import { Badge, cx } from "./ui";

const HINT = {
  info: { Icon: Lightbulb, box: "bg-indigo-50/70 text-indigo-950 ring-indigo-100", icon: "text-indigo-500" },
  attention: { Icon: TriangleAlert, box: "bg-amber-50 text-amber-950 ring-amber-200", icon: "text-amber-500" },
  done: { Icon: CircleCheck, box: "bg-emerald-50 text-emerald-950 ring-emerald-200", icon: "text-emerald-500" },
};

export function CaseBar({ title, chips, suggestion }: { title: string; chips: Chip[]; suggestion: Suggestion }) {
  const hint = HINT[suggestion.tone];
  return (
    <div className="border-b border-slate-200/80 bg-white/80 backdrop-blur">
      <div className="mx-auto flex w-full max-w-[1680px] flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600">
            <Briefcase className="size-4" />
          </span>
          <div className="min-w-0">
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-slate-400">Purchase case</div>
            <div className="truncate text-[14px] font-semibold leading-5 text-slate-900">{title}</div>
          </div>
        </div>
        {chips.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            {chips.map((c) => <Badge key={c.text} tone={c.tone}>{c.text}</Badge>)}
          </div>
        )}
        <div className="flex min-w-[300px] flex-1 justify-end">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={suggestion.text}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              className={cx("flex max-w-[760px] items-start gap-2 rounded-lg px-3 py-1.5 text-[12.5px] leading-[18px] ring-1 ring-inset", hint.box)}
            >
              <hint.Icon className={cx("mt-px size-4 shrink-0", hint.icon)} />
              <span>{suggestion.text}</span>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
