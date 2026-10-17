// web/src/components/Header.tsx
import { RotateCcw } from "lucide-react";
import type { HealthResponse } from "../contract";
import { Button, cx } from "./ui";

export function Logo({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="antidote-logo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#14b8a6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#antidote-logo)" />
      <path d="M9 21.5 15 11l8 6" stroke="white" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
      <circle cx="9" cy="21.5" r="2.6" fill="white" />
      <circle cx="15" cy="11" r="2.6" fill="white" />
      <circle cx="23" cy="17" r="2.6" fill="white" />
    </svg>
  );
}

function MemoryPill({ health }: { health: HealthResponse | null }) {
  const up = health?.falkordb === "up";
  const used = health?.memory?.used;
  return (
    <div
      className="flex items-center gap-2 rounded-full bg-white/[0.06] px-3 py-1.5 text-[12px] text-slate-300 ring-1 ring-white/10"
      title={up ? `Every fact, reason and check lives in FalkorDB.${health?.sessions ? ` ${health.sessions} private session(s) open.` : ""}` : "FalkorDB is unreachable"}
    >
      <span className={cx("size-2 rounded-full", up ? "bg-emerald-400 shadow-[0_0_0_3px_rgba(52,211,153,0.18)]" : "bg-rose-400")} />
      <span className="font-medium text-white">FalkorDB</span>
      <span className="hidden sm:inline">{up ? `connected${used ? ` · ${used} in use` : ""}` : "unreachable"}</span>
    </div>
  );
}

export function Header({ health, onStartOver, restarting }: {
  health: HealthResponse | null; onStartOver: () => void; restarting: boolean;
}) {
  return (
    <header className="bg-ink text-white">
      <div className="mx-auto flex h-14 w-full max-w-[1680px] items-center gap-3 px-4">
        <Logo />
        <div className="flex items-baseline gap-3">
          <span className="text-[16px] font-semibold tracking-tight">Antidote</span>
          <span className="hidden text-[13px] text-slate-400 md:inline">Procurement agents with a memory you can audit</span>
        </div>
        <div className="ml-auto flex items-center gap-2.5">
          <MemoryPill health={health} />
          <Button
            variant="ghost"
            size="sm"
            icon={<RotateCcw />}
            loading={restarting}
            onClick={onStartOver}
            className="text-slate-200 hover:bg-white/10 hover:text-white"
            title="Throw this memory away and start a fresh one"
          >
            <span className="hidden sm:inline">Start over</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
