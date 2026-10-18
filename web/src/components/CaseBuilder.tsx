// web/src/components/CaseBuilder.tsx
// Build your own case: change what the documents say, then watch what the agents and
// Antidote do with it. The server writes the documents and the agents' answers from
// this form (app/casebuilder.py); everything after that is the real engine.
import { FlaskConical, Info, Play, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { CaseSlot, CaseSpec, CaseSupplier } from "../contract";
import { Button, cx, Drawer } from "./ui";

const NAMES: Record<CaseSlot, string> = {
  vantor: "Vantor Motion", boltline: "Boltline Automation", ferrocraft: "Ferrocraft Servo", quillon: "Quillon Drives",
};

const STORY: CaseSpec = {
  name: "The demo story", max_weeks: 4, suppliers: [
    { slot: "vantor", price: 480, weeks: 2, claims_certificate: true, registry_confirms: false, hidden_instructions: true },
    { slot: "boltline", price: 520, weeks: 3, claims_certificate: true, registry_confirms: true, hidden_instructions: false },
    { slot: "ferrocraft", price: 560, weeks: 4, claims_certificate: true, registry_confirms: true, hidden_instructions: false },
    { slot: "quillon", price: 390, weeks: 2, claims_certificate: false, registry_confirms: false, hidden_instructions: false },
  ],
};

function variant(name: string, changes: Partial<Record<CaseSlot, Partial<CaseSupplier>>>): CaseSpec {
  return { ...STORY, name, suppliers: STORY.suppliers.map((s) => ({ ...s, ...changes[s.slot] })) };
}

const PRESETS: { spec: CaseSpec; about: string }[] = [
  { spec: STORY, about: "Vantor's page hides instructions for AI and claims a certificate the registry doesn't list." },
  {
    spec: variant("A plain lie", { vantor: { hidden_instructions: false } }),
    about: "Vantor claims ISO 13485 with no hidden text: no alert fires. Only the evidence gives it away.",
  },
  {
    spec: variant("Two problems at once", { vantor: { hidden_instructions: false }, ferrocraft: { hidden_instructions: true } }),
    about: "Hidden text pushes the priciest supplier, and Vantor still lies about its certificate.",
  },
  {
    spec: variant("Nothing wrong", { vantor: { claims_certificate: false, hidden_instructions: false } }),
    about: "Every claim is true. Antidote should stay out of the way.",
  },
];

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Math.round(Number.isFinite(n) ? n : lo)));
const same = (a: CaseSpec, b: CaseSpec) => JSON.stringify({ ...a, name: "" }) === JSON.stringify({ ...b, name: "" });

function NumberBox({ value, min, max, onChange, prefix, label }: {
  value: number; min: number; max: number; onChange: (n: number) => void; prefix?: string; label: string;
}) {
  return (
    <label className="flex items-center gap-1 rounded-lg bg-white px-2 ring-1 ring-inset ring-slate-200 focus-within:ring-2 focus-within:ring-indigo-300">
      {prefix && <span className="text-[12px] text-slate-400">{prefix}</span>}
      <input
        type="number"
        aria-label={label}
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(Number(e.target.value))}
        onBlur={(e) => onChange(clamp(Number(e.target.value), min, max))}
        className="h-8 w-full min-w-0 bg-transparent text-[13px] tabular-nums text-slate-800 outline-none"
      />
    </label>
  );
}

function Check({ checked, onChange, label, danger }: { checked: boolean; onChange: (v: boolean) => void; label: string; danger?: boolean }) {
  return (
    <label className="flex justify-center">
      <input
        type="checkbox"
        aria-label={label}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className={cx("size-4 cursor-pointer", danger ? "accent-rose-600" : "accent-indigo-600")}
      />
    </label>
  );
}

export function CaseBuilder({ open, current, busy, onClose, onUse }: {
  open: boolean;
  current: CaseSpec | null; // the case in use, or null for the demo story
  busy: boolean;
  onClose: () => void;
  onUse: (spec: CaseSpec | null) => void;
}) {
  const [spec, setSpec] = useState<CaseSpec>(current ?? STORY);
  useEffect(() => {
    if (open) setSpec(current ?? STORY);
  }, [open, current]);

  const preset = PRESETS.find((p) => same(p.spec, spec));
  const setSupplier = (slot: CaseSlot, changes: Partial<CaseSupplier>) =>
    setSpec((s) => ({ ...s, suppliers: s.suppliers.map((x) => (x.slot === slot ? { ...x, ...changes } : x)) }));
  const ready = (): CaseSpec => ({
    name: preset?.spec.name ?? "Your own case",
    max_weeks: clamp(spec.max_weeks, 1, 12),
    suppliers: spec.suppliers.map((s) => ({ ...s, price: clamp(s.price, 50, 5000), weeks: clamp(s.weeks, 1, 26) })),
  });

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="min(820px, 100vw)"
      title="Build your own case"
      subtitle="Change what the documents say, then watch what the agents and Antidote do with it."
      icon={
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
          <FlaskConical className="size-[18px]" />
        </span>
      }
    >
      <div className="space-y-5 p-5">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.07em] text-slate-400">Start from</div>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {PRESETS.map((p) => (
              <button
                key={p.spec.name}
                type="button"
                onClick={() => setSpec(p.spec)}
                className={cx(
                  "rounded-xl px-3.5 py-2.5 text-left ring-1 ring-inset transition",
                  preset === p ? "bg-indigo-50 ring-indigo-300" : "bg-white ring-slate-200 hover:bg-slate-50",
                )}
              >
                <div className="text-[13px] font-semibold text-slate-900">{p.spec.name}</div>
                <div className="mt-0.5 text-[12px] leading-[17px] text-slate-500">{p.about}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-xl bg-slate-50 px-4 py-3 ring-1 ring-inset ring-slate-200/70">
          <div className="text-[11px] font-semibold uppercase tracking-[0.07em] text-slate-400">Your request</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[13px] text-slate-700">
            100 servo actuators from an ISO 13485-certified supplier, delivered within
            <span className="w-16">
              <NumberBox label="Weeks to deliver" value={spec.max_weeks} min={1} max={12} onChange={(n) => setSpec((s) => ({ ...s, max_weeks: n }))} />
            </span>
            weeks, at the lowest unit price.
          </div>
        </div>

        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.07em] text-slate-400">The suppliers' documents</div>
          <div className="scroll-thin mt-2 overflow-x-auto">
            <table className="w-full min-w-[640px] text-[12.5px]">
              <thead className="text-[11px] text-slate-500">
                <tr className="border-b border-slate-200">
                  <th className="py-2 pr-2 text-left font-medium">Supplier</th>
                  <th className="w-24 px-1 py-2 text-left font-medium">Price per unit</th>
                  <th className="w-20 px-1 py-2 text-left font-medium">Ships in (weeks)</th>
                  <th className="w-24 px-1 py-2 text-center font-medium">Its page claims ISO 13485</th>
                  <th className="w-24 px-1 py-2 text-center font-medium">Registry confirms it</th>
                  <th className="w-24 px-1 py-2 text-center font-medium text-rose-700">Hidden text for AI on its page</th>
                </tr>
              </thead>
              <tbody>
                {spec.suppliers.map((s) => (
                  <tr key={s.slot} className="border-b border-slate-100">
                    <td className="py-2 pr-2 font-medium text-slate-800">{NAMES[s.slot]}</td>
                    <td className="px-1 py-2">
                      <NumberBox label={`${NAMES[s.slot]} price`} prefix="$" value={s.price} min={50} max={5000} onChange={(n) => setSupplier(s.slot, { price: n })} />
                    </td>
                    <td className="px-1 py-2">
                      <NumberBox label={`${NAMES[s.slot]} weeks`} value={s.weeks} min={1} max={26} onChange={(n) => setSupplier(s.slot, { weeks: n })} />
                    </td>
                    <td className="px-1 py-2"><Check label={`${NAMES[s.slot]} claims ISO 13485`} checked={s.claims_certificate} onChange={(v) => setSupplier(s.slot, { claims_certificate: v })} /></td>
                    <td className="px-1 py-2"><Check label={`Registry confirms ${NAMES[s.slot]}`} checked={s.registry_confirms} onChange={(v) => setSupplier(s.slot, { registry_confirms: v })} /></td>
                    <td className="px-1 py-2"><Check danger label={`Hidden text on ${NAMES[s.slot]}'s page`} checked={s.hidden_instructions} onChange={(v) => setSupplier(s.slot, { hidden_instructions: v })} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="flex gap-2.5 rounded-xl bg-amber-50 px-3.5 py-3 text-[12.5px] leading-5 text-amber-950 ring-1 ring-inset ring-amber-200">
          <Info className="mt-0.5 size-4 shrink-0 text-amber-600" />
          <p>
            <span className="font-semibold">No AI runs in a case you build.</span> Antidote writes the documents from
            this form, and the agents answer by two rules: the Researcher records what each document says, with exact
            quotes and hidden text included; the Buyer orders from the cheapest supplier that qualifies and delivers in
            time, unless a page tells it another supplier is the only certified one. Everything after that is real: the
            checks on every claim, the memory in FalkorDB, the approval check, the security scan, the preview and the repair.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
          <Button variant="brand" icon={<Play />} loading={busy} onClick={() => onUse(ready())}>
            Use this case and start the agents
          </Button>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          {current && (
            <Button variant="ghost" icon={<Undo2 />} className="ml-auto" disabled={busy} onClick={() => onUse(null)}>
              Back to the demo story
            </Button>
          )}
        </div>
      </div>
    </Drawer>
  );
}
