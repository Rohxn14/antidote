// web/src/components/RequestCard.tsx
// The buyer's instruction, and the button that sends the agents to work.
import { ClipboardList, FastForward, FlaskConical, LoaderCircle, Play, RotateCcw } from "lucide-react";
import { useState } from "react";
import type { CaseSpec, RunMode } from "../contract";
import { Badge, Button, Card, Segmented, SectionLabel } from "./ui";

export function RequestCard({ text, onTextChange, liveAvailable, model, running, hasRun, onStart, builtCase, onBuild }: {
  text: string;
  onTextChange: (text: string) => void;
  liveAvailable: boolean;
  model: string | null;
  running: "run" | "replan" | null;
  hasRun: boolean;
  onStart: (mode: RunMode, pace: number) => void;
  builtCase: CaseSpec | null;
  onBuild: () => void;
}) {
  const [mode, setMode] = useState<RunMode>("replay");
  const live = mode === "live" && liveAvailable && !builtCase;
  const lines = text.split("\n").map((l) => l.replace(/^\s*\d+[.)]\s*/, "").trim()).filter(Boolean);

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel icon={<ClipboardList />}>Your request</SectionLabel>
        {builtCase ? <Badge tone="indigo">Built by you</Badge> : <span className="text-[11px] text-slate-500">Kestrel · purchasing</span>}
      </div>

      {live ? (
        <textarea
          value={text}
          onChange={(e) => onTextChange(e.target.value)}
          maxLength={2000}
          rows={6}
          disabled={!!running}
          className="mt-3 w-full resize-none rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2.5 text-[13px] leading-5 text-slate-800 outline-none transition focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100"
        />
      ) : (
        <ol className="mt-3 space-y-2">
          {lines.map((line, i) => (
            <li key={i} className="flex gap-2.5 text-[13px] leading-5 text-slate-700">
              <span className="mt-px grid size-5 shrink-0 place-items-center rounded-md bg-slate-100 text-[11px] font-semibold text-slate-600">
                {i + 1}
              </span>
              {line}
            </li>
          ))}
        </ol>
      )}

      <Segmented
        className="mt-4 w-full [&>button]:flex-1"
        value={live ? "live" : "replay"}
        onChange={setMode}
        options={[
          { value: "replay", label: "Recorded agents", title: "Replays the agents' recorded answers: no AI key needed" },
          {
            value: "live", label: "Live AI", disabled: !liveAvailable || !!running || !!builtCase,
            title: builtCase ? "A case you build runs without AI" : liveAvailable ? `Calls ${model ?? "the model"} for real` : "Live AI is switched off on this server",
          },
        ]}
      />

      {running ? (
        <div className="mt-3 flex h-11 items-center gap-2 rounded-lg bg-indigo-50 pl-3 pr-1.5 ring-1 ring-inset ring-indigo-100">
          <LoaderCircle className="size-4 shrink-0 animate-spin text-indigo-600" />
          <span className="flex-1 truncate text-[13px] font-medium text-indigo-800">
            {running === "run" ? "Agents at work…" : "Re-planning…"}
          </span>
          {running === "run" && !live && (
            <Button size="sm" icon={<FastForward />} onClick={() => onStart("replay", 0)} title="Replay the rest at full speed">
              Skip to result
            </Button>
          )}
        </div>
      ) : (
        <Button
          variant="brand"
          size="lg"
          className="mt-3 w-full"
          icon={hasRun ? <RotateCcw /> : <Play />}
          onClick={() => onStart(live ? "live" : "replay", 1)}
        >
          {hasRun ? "Run the agents again" : "Start the agents"}
        </Button>
      )}
      {!running && (
        <Button className="mt-2 w-full" icon={<FlaskConical />} onClick={onBuild}>
          {builtCase ? "Change this case" : "Build your own case"}
        </Button>
      )}

      <p className="mt-2.5 text-[11.5px] leading-[17px] text-slate-500">
        {builtCase
          ? "Your case: the documents come from your form and the agents answer by simple rules (no AI). Every check, write and decision after that is real."
          : live
            ? `Calls ${model ?? "the model"} for real: slower, and the answers vary. Antidote checks every one.`
            : "Replays the agents' recorded answers in about 30 seconds. Every fact, reason and check runs live in FalkorDB."}
      </p>
    </Card>
  );
}
