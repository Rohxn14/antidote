// web/src/components/OutageScreen.tsx
// Shown when FalkorDB is unreachable. Antidote fails closed: there is no copy of
// the memory anywhere else, so nothing can be read, recommended or approved.
import { DatabaseZap, LoaderCircle } from "lucide-react";
import { Logo } from "./Header";

export function OutageScreen({ detail }: { detail: string }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-ink px-4 py-10 text-white">
      <div className="w-full max-w-xl">
        <div className="flex items-center gap-3">
          <Logo />
          <span className="text-[16px] font-semibold tracking-tight">Antidote</span>
        </div>
        <div className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl sm:p-8">
          <div className="flex items-center gap-3.5">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-rose-500/15 text-rose-300 ring-1 ring-rose-400/30">
              <DatabaseZap className="size-5" />
            </span>
            <div>
              <h1 className="text-[19px] font-semibold tracking-tight">Antidote's memory is unreachable</h1>
              <p className="text-[13px] text-slate-400">FalkorDB isn't answering, so Antidote has stopped.</p>
            </div>
          </div>
          <p className="mt-5 text-[14px] leading-6 text-slate-300">
            Everything Antidote does happens inside FalkorDB: the agents' facts, the reasons behind them, what still
            holds, the preview of a repair and the approval check. There is no copy anywhere else and no fallback, so
            nothing can be read, recommended or approved until the memory is back.
          </p>
          <div className="mt-6 flex items-center gap-2 text-[13px] text-slate-400">
            <LoaderCircle className="size-4 animate-spin" />
            Checking again every few seconds. This page recovers on its own.
          </div>
          {detail && <p className="mt-3 font-mono text-[11.5px] text-slate-500">{detail}</p>}
        </div>
      </div>
    </div>
  );
}
