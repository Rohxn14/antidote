// web/src/components/UnderTheHood.tsx
// The proof that FalkorDB is central: each capability runs through the real code on a
// scratch graph and shows the exact Cypher it executed, then the same code runs with
// FalkorDB unplugged. Also the graph model, the benchmark and every query by name.
import {
  CircleCheck, CircleX, Database, DatabaseZap, FlaskConical, LoaderCircle, Network, Play, Scale,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { BenchmarkRow, CapabilityResultData, CypherResponse } from "../contract";
import { api, ApiFailure } from "../lib/api";
import { Badge, Button, Card, cx, SectionLabel } from "./ui";

type Mode = "with" | "without";
type Results = Record<Mode, CapabilityResultData[]>;

const METHOD: Record<string, string> = { antidote: "Antidote", delete_only: "Delete source only", rollback: "Full rollback" };

function scenarioName(s: string): string {
  if (s.startsWith("RippleEdits")) return "RippleEdits, an external test set (15 cases)";
  if (s.startsWith("demo")) return "The demo story";
  const m = /^synthetic_(\d+)/.exec(s);
  return m ? `${m[1]} vendors, several sources poisoned` : s;
}

function Capability({ result, without }: { result: CapabilityResultData; without?: CapabilityResultData }) {
  return (
    <Card className="flex flex-col overflow-hidden">
      <div className="flex items-start gap-3 px-4 pt-4">
        {result.ok ? <CircleCheck className="mt-0.5 size-5 shrink-0 text-emerald-500" /> : <CircleX className="mt-0.5 size-5 shrink-0 text-rose-500" />}
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold text-slate-900">{result.capability}</div>
          <div className="text-[12px] text-slate-500">{result.feature}</div>
        </div>
        <div className="text-right text-[11.5px] tabular-nums text-slate-500">
          <div className="font-medium text-slate-700">{result.ms.toFixed(1)} ms</div>
          <div>{result.statements.length} Cypher statements</div>
        </div>
      </div>
      <p className={cx("mx-4 mt-2.5 rounded-lg px-3 py-2 text-[12.5px] leading-5", result.ok ? "bg-emerald-50 text-emerald-900" : "bg-rose-50 text-rose-900")}>
        {result.ok ? result.result : result.error}
      </p>
      {without && (
        <div className="mx-4 mt-2 flex items-start gap-2 rounded-lg bg-slate-900 px-3 py-2 text-[12px] leading-5 text-slate-200">
          <DatabaseZap className="mt-0.5 size-4 shrink-0 text-rose-300" />
          <span>
            <span className="font-semibold text-white">Without FalkorDB: </span>
            {without.ok ? without.result : `failed in ${without.ms.toFixed(0)} ms (${without.error})`}
          </span>
        </div>
      )}
      {result.statements.length > 0 && (
        <details className="group mx-4 mb-4 mt-3">
          <summary className="cursor-pointer select-none text-[12px] font-medium text-indigo-600 hover:text-indigo-800">
            Show the {result.statements.length} statements FalkorDB ran
          </summary>
          <ol className="mt-2 space-y-2">
            {result.statements.map((s, i) => (
              <li key={i} className="rounded-lg bg-slate-950 p-2.5">
                <div className="mb-1 flex justify-between text-[10.5px] tabular-nums text-slate-400">
                  <span>#{i + 1}</span>
                  <span>{s.ms.toFixed(1)} ms · {s.rows} rows</span>
                </div>
                <pre className="scroll-thin overflow-x-auto whitespace-pre font-mono text-[11px] leading-[16px] text-slate-200">{s.cypher.trim()}</pre>
              </li>
            ))}
          </ol>
        </details>
      )}
      {result.statements.length === 0 && <div className="mb-4" />}
    </Card>
  );
}

function GraphModel() {
  const box = "rounded-lg border bg-white px-3 py-2 text-[12.5px] font-medium shadow-sm";
  const dot = <span className="size-3 shrink-0 rounded-full bg-emerald-500 ring-4 ring-emerald-100" />;
  const arrow = <span className="h-px w-3 shrink-0 bg-slate-300" />;
  return (
    <Card className="p-5">
      <SectionLabel icon={<Network />}>The graph model</SectionLabel>
      <div className="mt-4 flex flex-wrap items-center gap-1.5">
        <span className={cx(box, "border-emerald-300")}>Document</span>{arrow}{dot}{arrow}
        <span className={cx(box, "border-slate-200")}>Fact</span>{arrow}{dot}{arrow}
        <span className={cx(box, "border-slate-200")}>Conclusion</span>{arrow}{dot}{arrow}
        <span className={cx(box, "border-indigo-400")}>Order</span>
      </div>
      <ul className="mt-4 space-y-2 text-[13px] leading-5 text-slate-700">
        <li><span className="font-semibold">Every link is a reason</span> (the dots): a node in FalkorDB that records who gave it, the exact quote, and how many premises it needs.</li>
        <li><span className="font-semibold">A reason holds only if all its premises hold</span>; a fact or an order is supported if <span className="font-semibold">at least one</span> of its reasons holds.</li>
        <li><span className="font-semibold">Support is recomputed inside FalkorDB</span> after every change: one reset, then the same Cypher query round after round until nothing changes. A loop of facts propping each other up cannot keep itself alive.</li>
        <li><span className="font-semibold">What-ifs run on a copy</span> made with <code className="rounded bg-slate-100 px-1 font-mono text-[12px]">GRAPH.COPY</code>: the impact preview, the approval check's robustness test and evidence strength never touch the real memory.</li>
      </ul>
    </Card>
  );
}

function Benchmark({ rows }: { rows: BenchmarkRow[] }) {
  const scenarios = [...new Set(rows.map((r) => r.scenario))].sort((a, b) => Number(b.startsWith("Ripple")) - Number(a.startsWith("Ripple")));
  return (
    <Card className="overflow-hidden">
      <div className="px-5 pt-5">
        <SectionLabel icon={<Scale />}>Benchmark: removing a poisoned source</SectionLabel>
        <p className="mt-2 text-[13px] leading-5 text-slate-600">
          Ground truth comes from an independent solver that shares no code with Antidote: exactly what loses all
          support once the source is gone. <span className="font-medium">Left behind</span> = facts and decisions still
          active with nothing supporting them. <span className="font-medium">Lost good</span> = still-supported knowledge
          thrown away. <span className="font-medium">Stale orders</span> = unsupported orders the approval check would
          still let through.
        </p>
      </div>
      <div className="scroll-thin mt-3 overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-[12.5px]">
          <thead className="border-y border-slate-100 bg-slate-50 text-[11px] uppercase tracking-[0.06em] text-slate-500">
            <tr>
              <th className="px-5 py-2 font-medium">Test</th>
              <th className="px-3 py-2 font-medium">Method</th>
              <th className="px-3 py-2 text-right font-medium">Left behind</th>
              <th className="px-3 py-2 text-right font-medium">Lost good</th>
              <th className="px-3 py-2 text-right font-medium">Stale orders</th>
              <th className="px-5 py-2 text-right font-medium">Time</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.map((scenario) =>
              rows.filter((r) => r.scenario === scenario).map((r, i) => {
                const ours = r.method === "antidote";
                return (
                  <tr key={`${scenario}-${r.method}`} className={cx("border-b border-slate-100", ours && "bg-emerald-50/40")}>
                    <td className="px-5 py-2 align-top text-slate-700">{i === 0 ? scenarioName(scenario) : ""}</td>
                    <td className={cx("whitespace-nowrap px-3 py-2", ours ? "font-semibold text-slate-900" : "text-slate-600")}>{METHOD[r.method] ?? r.method}</td>
                    <td className={cx("px-3 py-2 text-right tabular-nums", r.residual ? "text-rose-600" : "text-emerald-700", ours && "font-semibold")}>{r.residual}</td>
                    <td className={cx("px-3 py-2 text-right tabular-nums", r.collateral ? "text-rose-600" : "text-emerald-700", ours && "font-semibold")}>{r.collateral}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-slate-600">{r.stale ?? "n/a"}</td>
                    <td className="whitespace-nowrap px-5 py-2 text-right tabular-nums text-slate-500">{r.ms === null ? "" : `${r.ms.toFixed(0)} ms`}</td>
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </div>
      <p className="px-5 py-3 text-[12px] leading-[18px] text-slate-500">
        Delete source only is what a plain memory store does: the record goes, everything built on it stays. Full
        rollback restores a snapshot from before the poison: clean, but everything learned since is lost. RippleEdits
        has no timeline, so it has no rollback row.
      </p>
    </Card>
  );
}

function CypherReference({ data }: { data: CypherResponse }) {
  const total = data.sections.reduce((n, s) => n + s.queries.length, 0);
  return (
    <Card className="p-5">
      <SectionLabel icon={<Database />}>Every query Antidote depends on ({total})</SectionLabel>
      <div className="mt-3 space-y-4">
        {data.sections.map((s) => (
          <div key={s.title}>
            <div className="text-[13.5px] font-semibold text-slate-900">{s.title}</div>
            <p className="text-[12.5px] leading-5 text-slate-500">{s.intro}</p>
            <div className="mt-2 space-y-1.5">
              {s.queries.map((q) => (
                <details key={q.name} className="rounded-lg ring-1 ring-inset ring-slate-200">
                  <summary className="cursor-pointer select-none px-3 py-1.5 font-mono text-[12px] text-slate-700 hover:bg-slate-50">{q.name}</summary>
                  <pre className="scroll-thin overflow-x-auto rounded-b-lg bg-slate-950 p-3 font-mono text-[11px] leading-[16px] text-slate-200">{q.cypher.trim()}</pre>
                </details>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

export function UnderTheHood() {
  const [results, setResults] = useState<Results>({ with: [], without: [] });
  const [running, setRunning] = useState<Mode | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [cypher, setCypher] = useState<CypherResponse | null>(null);
  const [bench, setBench] = useState<BenchmarkRow[] | null>(null);
  const started = useRef(false);

  const run = useCallback(async (mode: Mode) => {
    setRunning(mode);
    setMessage(null);
    setResults((r) => ({ ...r, [mode]: [] }));
    try {
      await api.capabilities(mode === "without", (e) => {
        if (e.type === "capability_result") setResults((r) => ({ ...r, [mode]: [...r[mode], e.data] }));
        if (e.type === "error") setMessage(e.data.message);
      }, new AbortController().signal);
    } catch (e) {
      setMessage(e instanceof ApiFailure && e.status === 429
        ? "The walkthrough ran a moment ago (it builds a whole scratch graph). Try again in a few seconds."
        : e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(null);
    }
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void run("with");
    api.cypher().then(setCypher).catch(() => undefined);
    api.benchmark().then((b) => setBench(b.rows)).catch(() => undefined);
  }, [run]);

  const withByName = results.with;
  const withoutByName = Object.fromEntries(results.without.map((r) => [r.capability, r]));
  const failedWithout = results.without.filter((r) => !r.ok).length;

  return (
    <main className="mx-auto w-full max-w-[1280px] space-y-5 px-4 pb-10 pt-6">
      <Card className="overflow-hidden">
        <div className="bg-gradient-to-br from-indigo-50 via-white to-teal-50 px-6 py-6">
          <SectionLabel icon={<FlaskConical />}>Under the hood</SectionLabel>
          <h1 className="mt-2 text-[24px] font-semibold tracking-tight text-slate-900">Every decision Antidote makes is a query in FalkorDB</h1>
          <p className="mt-2 max-w-3xl text-[14px] leading-6 text-slate-600">
            Below, each capability runs through the real code on a fresh scratch graph, and you see the exact Cypher it
            executed and how long it took. Then run the same code with FalkorDB unplugged: nothing works, because there
            is no copy of the memory anywhere else and no fallback.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button variant="brand" icon={<Play />} loading={running === "with"} disabled={running !== null} onClick={() => run("with")}>
              Run with FalkorDB
            </Button>
            <Button variant="dangerOutline" icon={<DatabaseZap />} loading={running === "without"} disabled={running !== null} onClick={() => run("without")}>
              Run without FalkorDB
            </Button>
            {running && (
              <span className="flex items-center gap-1.5 text-[12.5px] text-slate-500">
                <LoaderCircle className="size-3.5 animate-spin" />
                {running === "with" ? "Running against FalkorDB…" : "Running with no database behind the graph…"}
              </span>
            )}
            {results.without.length > 0 && !running && (
              <Badge tone="red">{failedWithout} of {results.without.length} failed without FalkorDB</Badge>
            )}
          </div>
          {message && <p className="mt-3 text-[12.5px] text-amber-800">{message}</p>}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {withByName.map((r) => <Capability key={r.capability} result={r} without={withoutByName[r.capability]} />)}
        {running === "with" && withByName.length < 7 && (
          <Card className="grid min-h-[140px] place-items-center text-[13px] text-slate-400">
            <span className="flex items-center gap-2"><LoaderCircle className="size-4 animate-spin" /> Next capability…</span>
          </Card>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
        <GraphModel />
        {bench && <Benchmark rows={bench} />}
      </div>
      {cypher && <CypherReference data={cypher} />}
    </main>
  );
}
