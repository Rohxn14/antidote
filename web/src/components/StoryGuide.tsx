// web/src/components/StoryGuide.tsx
// Where the visitor is in the story, and the one thing to do next.
import { AnimatePresence, motion } from "framer-motion";
import { Check, Sparkles } from "lucide-react";
import { STEPS, type Story } from "../lib/story";
import { cx } from "./ui";

export function StoryGuide({ story }: { story: Story }) {
  return (
    <div className="border-b border-slate-200/80 bg-white/75 backdrop-blur">
      <div className="mx-auto flex w-full max-w-[1680px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
        <ol className="flex flex-wrap items-center gap-1" aria-label="Steps">
          {STEPS.map((label, i) => {
            const complete = story.done || i < story.index;
            const now = !story.done && i === story.index;
            return (
              <li key={label} className="flex items-center gap-1">
                <span
                  className={cx(
                    "flex items-center gap-1.5 rounded-full py-1 pl-1 pr-2.5 text-[12px] font-medium transition",
                    now && "bg-indigo-50 text-indigo-800 ring-1 ring-indigo-200",
                    complete && "text-slate-600",
                    !now && !complete && "text-slate-400",
                  )}
                  aria-current={now ? "step" : undefined}
                >
                  <span
                    className={cx(
                      "grid size-5 place-items-center rounded-full text-[10.5px] font-semibold",
                      now && "bg-indigo-600 text-white",
                      complete && "bg-emerald-500 text-white",
                      !now && !complete && "bg-slate-100 text-slate-500",
                    )}
                  >
                    {complete ? <Check className="size-3" strokeWidth={3} /> : i + 1}
                  </span>
                  {label}
                </span>
                {i < STEPS.length - 1 && <span className="h-px w-3 bg-slate-200" />}
              </li>
            );
          })}
        </ol>
        <div className="flex min-w-[280px] flex-1 items-center gap-2 text-[13px] text-slate-700">
          <Sparkles className="size-4 shrink-0 text-indigo-500" />
          <AnimatePresence mode="wait" initial={false}>
            <motion.p
              key={story.hint}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
            >
              {story.hint}
            </motion.p>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
