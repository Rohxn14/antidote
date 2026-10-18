// web/src/components/ScenarioSuite.tsx
// The scenario suite's results (scripts/scenario_suite.py): many suppliers, many kinds of
// attack and failure, each run through the real pipeline and judged against the truth.
import { FlaskConical } from "lucide-react";
import summary from "../scenario_summary.json";
import { Card, cx, SectionLabel } from "./ui";

const tone = (result: string) =>
  result.startsWith("right") || result.startsWith("stopped") ? "text-emerald-700"
    : result.startsWith("held") ? "text-amber-700" : "text-rose-600";

const ORDER = (k: string) =>
  (k.startsWith("right") ? 0 : k.startsWith("stopped") ? 1 : k.startsWith("held") ? 2 : 3);

export function ScenarioSuite() {
  const results = [...new Set([...Object.keys(summary.antidote), ...Object.keys(summary.baseline)])]
    .sort((a, b) => ORDER(a) - ORDER(b) || a.localeCompare(b));
  const count = (side: Record<string, number>, k: string) => side[k] ?? 0;
  return (
    <Card className="overflow-hidden">
      <div className="px-5 pt-5">
        <SectionLabel icon={<FlaskConical />}>Scenario suite: many suppliers, many kinds of attack</SectionLabel>
        <p className="mt-2 text-[13px] leading-5 text-slate-600">
          Each case runs through the real pipeline, then a reviewer who <span className="font-medium">approves everything
          without looking</span> presses Approve, so this is what Antidote stops on its own. The right order is the cheapest
          supplier that truly qualifies (really certified, really on time) and did not try to manipulate the agents.
          <span className="font-medium"> Without Antidote</span> is the same agents reading the same documents with no checks.
          The attack texts are AgentDojo's and InjecAgent's published templates; the hiding techniques come from real
          incidents (The Guardian, 2024: hidden text on a product page; Nikkei, 2025: white text and tiny fonts in research
          papers). The suppliers and documents are generated, so this measures Antidote's checks across many cases, not a
          real model or real suppliers.
        </p>
      </div>

      <div className="mt-4 px-5 text-[11px] font-semibold uppercase tracking-[0.07em] text-slate-400">
        {summary.random_cases} random cases, {summary.suppliers[0]} to {summary.suppliers[1]} suppliers each
      </div>
      <div className="scroll-thin mt-2 overflow-x-auto">
        <table className="w-full min-w-[480px] text-left text-[12.5px]">
          <thead className="border-y border-slate-100 bg-slate-50 text-[11px] uppercase tracking-[0.06em] text-slate-500">
            <tr>
              <th className="px-5 py-2 font-medium">Result</th>
              <th className="px-3 py-2 text-right font-medium">With Antidote</th>
              <th className="px-5 py-2 text-right font-medium">Without Antidote</th>
            </tr>
          </thead>
          <tbody>
            {results.map((k) => (
              <tr key={k} className="border-b border-slate-100">
                <td className={cx("px-5 py-1.5", tone(k))}>{k}</td>
                <td className="px-3 py-1.5 text-right font-semibold tabular-nums text-slate-900">{count(summary.antidote, k)}</td>
                <td className="px-5 py-1.5 text-right tabular-nums text-slate-600">{count(summary.baseline, k)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-5 px-5 text-[11px] font-semibold uppercase tracking-[0.07em] text-slate-400">
        {summary.named.length} named scenarios, including ones built to make Antidote fail
      </div>
      <div className="scroll-thin mt-2 overflow-x-auto">
        <table className="w-full min-w-[820px] text-left text-[12.5px]">
          <thead className="border-y border-slate-100 bg-slate-50 text-[11px] uppercase tracking-[0.06em] text-slate-500">
            <tr>
              <th className="px-5 py-2 font-medium">Scenario</th>
              <th className="px-3 py-2 font-medium">Right order</th>
              <th className="px-3 py-2 font-medium">With Antidote</th>
              <th className="px-3 py-2 font-medium">Caught by</th>
              <th className="px-5 py-2 font-medium">Without Antidote</th>
            </tr>
          </thead>
          <tbody>
            {summary.named.map((r) => (
              <tr key={r.name} className="border-b border-slate-100 align-top">
                <td className="px-5 py-2">
                  <div className="font-medium text-slate-800">{r.name}</div>
                  <div className="text-[11.5px] leading-4 text-slate-500">{r.about} ({r.suppliers} suppliers)</div>
                </td>
                <td className="px-3 py-2 text-slate-700">{r.right}</td>
                <td className="px-3 py-2">
                  <div className="text-slate-800">{r.antidote}</div>
                  <div className={cx("text-[11.5px]", tone(r.antidote_result))}>{r.antidote_result}</div>
                </td>
                <td className="px-3 py-2 text-[11.5px] text-slate-600">{r.caught.join(", ") || "-"}</td>
                <td className="px-5 py-2">
                  <div className="text-slate-800">{r.baseline}</div>
                  <div className={cx("text-[11.5px]", tone(r.baseline_result))}>{r.baseline_result}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-5 py-3 text-[11.5px] leading-[17px] text-slate-500">
        Run it yourself: <code className="font-mono">python -m scripts.scenario_suite</code> (seed {summary.seed}). Full
        results in docs/scenario_suite.md.
      </p>
    </Card>
  );
}
