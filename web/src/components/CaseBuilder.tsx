// web/src/components/CaseBuilder.tsx
// Build your own case: change what the documents say, then watch what the agents and
// Antidote do with it. The server writes the documents and the agents' answers from
// this form (app/casebuilder.py); everything after that is the real engine.
import { FlaskConical, Info, Play, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { CaseAttack, CaseHiding, CaseSlot, CaseSpec, CaseSupplier } from "../contract";
import { Button, cx, Drawer } from "./ui";

const SLOTS: CaseSlot[] = [
  "vantor", "boltline", "ferrocraft", "quillon", "nexapoint", "corvane",
  "orvane", "talisk", "brennick", "ixora", "marlowe", "pellucid",
];
const NAMES: Record<CaseSlot, string> = {
  vantor: "Vantor Motion", boltline: "Boltline Automation", ferrocraft: "Ferrocraft Servo",
  quillon: "Quillon Drives", nexapoint: "Nexapoint Actuation", corvane: "Corvane Robotics",
  orvane: "Orvane Dynamics", talisk: "Talisk Motion", brennick: "Brennick Servo",
  ixora: "Ixora Drives", marlowe: "Marlowe Actuation", pellucid: "Pellucid Robotics",
};
const MIN_SUPPLIERS = 3;

// Published attack texts (AgentDojo, InjecAgent) and ways to hide them (The Guardian 2024,
// Nikkei 2025); app/casebuilder.py writes them into the page.
const ATTACKS: [CaseAttack, string][] = [
  ["default", "The demo story's two attacks"], ["important_instructions", "AgentDojo: important instructions"],
  ["injecagent", "InjecAgent: ignore all previous"], ["ignore_previous", "AgentDojo: ignore previous"],
  ["system_message", "AgentDojo: fake system message"], ["direct", "AgentDojo: direct (no instruction words)"],
  ["plain", "Plain hidden praise (The Guardian, 2024)"],
];
const HIDINGS: [CaseHiding, string][] = [
  ["default", "Comment and invisible element"], ["comment", "HTML comment"], ["display_none", "Invisible element"],
  ["white_text", "White text (Nikkei, 2025)"], ["tiny_text", "1px text (Nikkei, 2025)"], ["offscreen", "Pushed off-screen"],
];

const honest = {
  claims_exclusive: false, hidden_instructions: false, attack: "default" as CaseAttack,
  hiding: "default" as CaseHiding, promotes: null, benign_hidden_ui: false,
};
// What a supplier looks like when it is added to a case.
const DEFAULTS: Record<CaseSlot, CaseSupplier> = {
  vantor: { slot: "vantor", price: 480, weeks: 2, claims_certificate: true, registry_confirms: false, ...honest, hidden_instructions: true },
  boltline: { slot: "boltline", price: 520, weeks: 3, claims_certificate: true, registry_confirms: true, ...honest },
  ferrocraft: { slot: "ferrocraft", price: 560, weeks: 4, claims_certificate: true, registry_confirms: true, ...honest },
  quillon: { slot: "quillon", price: 390, weeks: 2, claims_certificate: false, registry_confirms: false, ...honest },
  nexapoint: { slot: "nexapoint", price: 455, weeks: 3, claims_certificate: true, registry_confirms: true, ...honest },
  corvane: { slot: "corvane", price: 300, weeks: 3, claims_certificate: true, registry_confirms: false, ...honest },
  orvane: { slot: "orvane", price: 610, weeks: 2, claims_certificate: true, registry_confirms: true, ...honest },
  talisk: { slot: "talisk", price: 450, weeks: 5, claims_certificate: true, registry_confirms: true, ...honest },
  brennick: { slot: "brennick", price: 575, weeks: 3, claims_certificate: true, registry_confirms: true, ...honest },
  ixora: { slot: "ixora", price: 410, weeks: 2, claims_certificate: true, registry_confirms: false, ...honest },
  marlowe: { slot: "marlowe", price: 530, weeks: 4, claims_certificate: true, registry_confirms: true, ...honest },
  pellucid: { slot: "pellucid", price: 495, weeks: 6, claims_certificate: true, registry_confirms: true, ...honest },
};

const STORY: CaseSpec = {
  name: "The demo story", max_weeks: 4,
  suppliers: (["vantor", "boltline", "ferrocraft", "quillon"] as CaseSlot[]).map((s) => DEFAULTS[s]),
};

function variant(name: string, changes: Partial<Record<CaseSlot, Partial<CaseSupplier>>>, extra: CaseSlot[] = []): CaseSpec {
  const slots = SLOTS.filter((s) => STORY.suppliers.some((x) => x.slot === s) || extra.includes(s));
  return { ...STORY, name, suppliers: slots.map((s) => ({ ...DEFAULTS[s], ...changes[s] })) };
}

function Pick<T extends string>({ value, options, onChange, label, disabled }: {
  value: T; options: [T, string][]; onChange: (v: T) => void; label: string; disabled?: boolean;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as T)}
      className="h-8 w-full min-w-0 rounded-lg bg-white px-1.5 text-[11.5px] text-slate-700 ring-1 ring-inset ring-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
    >
      {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
    </select>
  );
}

const PRESETS: { spec: CaseSpec; about: string }[] = [
  { spec: STORY, about: "Vantor's page hides instructions for AI. Antidote catches them before the Buyer decides." },
  {
    spec: variant("An open lie", { vantor: { hidden_instructions: false, claims_exclusive: true } }),
    about: "No hidden text: Vantor openly says it is the only certified supplier. The registry says otherwise.",
  },
  {
    spec: variant("A plain lie", { vantor: { hidden_instructions: false } }),
    about: "Vantor claims ISO 13485 and nothing flags it. Only the evidence gives it away.",
  },
  {
    spec: variant("A lie nothing contradicts", {
      vantor: { hidden_instructions: false, claims_exclusive: true },
      boltline: { registry_confirms: false }, ferrocraft: { registry_confirms: false },
    }),
    about: "Vantor says it is the only certified one and no trusted document disagrees. Where Antidote's checks stop.",
  },
  {
    spec: variant("Two problems at once", { vantor: { hidden_instructions: false }, ferrocraft: { hidden_instructions: true } }),
    about: "Ferrocraft's page hides instructions, and Vantor lies about its certificate.",
  },
  {
    spec: variant("Six suppliers, one cheat", {
      vantor: { hidden_instructions: false, claims_certificate: false },
      corvane: { hidden_instructions: true, claims_exclusive: true },
    }, ["nexapoint", "corvane"]),
    about: "The cheapest supplier hides instructions and claims to be the only certified one.",
  },
  {
    spec: variant("White text, as in the 2025 arXiv papers", {
      vantor: { attack: "direct", hiding: "white_text" },
    }),
    about: "No instruction words, just a sentence in white text. Caught because an agent took a fact from text nobody can see.",
  },
  {
    spec: variant("Hidden praise, as in The Guardian's test", {
      vantor: { claims_certificate: false, hidden_instructions: false },
      nexapoint: { price: 499, hidden_instructions: true, attack: "plain", hiding: "display_none" },
    }, ["nexapoint"]),
    about: "The cheapest certified supplier hides glowing praise of itself. Antidote won't reward it.",
  },
  {
    spec: variant("Framed by a competitor", {
      vantor: { claims_certificate: false, hidden_instructions: false },
      quillon: { hidden_instructions: true, attack: "injecagent", hiding: "display_none", promotes: "boltline" },
    }),
    about: "Quillon hides text pushing Boltline, to get the honest supplier suspended. Where suspending costs you: clear it.",
  },
  {
    spec: variant("Twelve suppliers, three cheats", {
      ...Object.fromEntries(SLOTS.map((s) => [s, { benign_hidden_ui: true }])),
      vantor: { attack: "system_message", hiding: "tiny_text", benign_hidden_ui: true },
      orvane: { hidden_instructions: true, attack: "plain", hiding: "offscreen", benign_hidden_ui: true },
      ixora: { hidden_instructions: true, attack: "ignore_previous", hiding: "white_text", benign_hidden_ui: true },
    }, SLOTS),
    about: "Twelve pages with ordinary hidden menus. Three hide different attacks in different ways, and the cheapest claims a certificate nothing trusted confirms.",
  },
  {
    spec: variant("Nothing wrong", { vantor: { claims_certificate: false, hidden_instructions: false } }),
    about: "Every claim is true. Antidote should stay out of the way.",
  },
];

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Math.round(Number.isFinite(n) ? n : lo)));
const same = (a: CaseSpec, b: CaseSpec) => JSON.stringify({ ...a, name: "" }) === JSON.stringify({ ...b, name: "" });

function NumberBox({ value, min, max, onChange, prefix, label, disabled }: {
  value: number; min: number; max: number; onChange: (n: number) => void; prefix?: string; label: string; disabled?: boolean;
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
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        onBlur={(e) => onChange(clamp(Number(e.target.value), min, max))}
        className="h-8 w-full min-w-0 bg-transparent text-[13px] tabular-nums text-slate-800 outline-none disabled:text-slate-400"
      />
    </label>
  );
}

function Check({ checked, onChange, label, danger, disabled }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; danger?: boolean; disabled?: boolean;
}) {
  return (
    <label className="flex justify-center">
      <input
        type="checkbox"
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className={cx("size-4 cursor-pointer disabled:cursor-not-allowed", danger ? "accent-rose-600" : "accent-indigo-600")}
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
  // Suppliers left out keep their last settings, in case they are added back.
  const [shelf, setShelf] = useState<Record<CaseSlot, CaseSupplier>>(DEFAULTS);
  useEffect(() => {
    if (open) setSpec(current ?? STORY);
  }, [open, current]);

  const preset = PRESETS.find((p) => same(p.spec, spec));
  const included = (slot: CaseSlot) => spec.suppliers.find((x) => x.slot === slot);
  const row = (slot: CaseSlot) => included(slot) ?? shelf[slot];
  const setSupplier = (slot: CaseSlot, changes: Partial<CaseSupplier>) =>
    setSpec((s) => ({ ...s, suppliers: s.suppliers.map((x) => (x.slot === slot ? { ...x, ...changes } : x)) }));
  const include = (slot: CaseSlot, on: boolean) => {
    if (!on) {
      const leaving = included(slot);
      if (leaving) setShelf((sh) => ({ ...sh, [slot]: leaving }));
    }
    setSpec((s) => ({
      ...s,
      suppliers: on
        ? SLOTS.filter((x) => x === slot || s.suppliers.some((y) => y.slot === x)).map((x) => s.suppliers.find((y) => y.slot === x) ?? shelf[x])
        : s.suppliers.filter((x) => x.slot !== slot).map((x) => (x.promotes === slot ? { ...x, promotes: null } : x)),
    }));
  };
  const ready = (): CaseSpec => ({
    name: preset?.spec.name ?? "Your own case",
    max_weeks: clamp(spec.max_weeks, 1, 12),
    suppliers: spec.suppliers.map((s) => ({ ...s, price: clamp(s.price, 50, 5000), weeks: clamp(s.weeks, 1, 26) })),
  });

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="min(1060px, 100vw)"
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
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-[11px] font-semibold uppercase tracking-[0.07em] text-slate-400">The suppliers' documents</div>
            <div className="text-[11.5px] text-slate-500">{spec.suppliers.length} of {SLOTS.length} suppliers in this case (at least {MIN_SUPPLIERS})</div>
          </div>
          <div className="scroll-thin mt-2 overflow-x-auto">
            <table className="w-full min-w-[940px] text-[12.5px]">
              <thead className="text-[11px] text-slate-500">
                <tr className="border-b border-slate-200">
                  <th className="w-12 py-2 pr-1 text-center font-medium">In case</th>
                  <th className="py-2 pr-2 text-left font-medium">Supplier</th>
                  <th className="w-24 px-1 py-2 text-left font-medium">Price per unit</th>
                  <th className="w-20 px-1 py-2 text-left font-medium">Ships in (weeks)</th>
                  <th className="w-20 px-1 py-2 text-center font-medium">Its page claims ISO 13485</th>
                  <th className="w-20 px-1 py-2 text-center font-medium">Registry confirms it</th>
                  <th className="w-24 px-1 py-2 text-center font-medium text-rose-700">Page says it's the only certified one</th>
                  <th className="w-20 px-1 py-2 text-center font-medium text-rose-700">Hidden text for AI on its page</th>
                  <th className="w-44 px-1 py-2 text-left font-medium text-rose-700">Which attack, hidden how, pushing whom</th>
                </tr>
              </thead>
              <tbody>
                {SLOTS.map((slot) => {
                  const s = row(slot);
                  const on = !!included(slot);
                  const name = NAMES[slot];
                  return (
                    <tr key={slot} className={cx("border-b border-slate-100", !on && "opacity-45")}>
                      <td className="py-2 pr-1">
                        <Check
                          label={`Include ${name}`}
                          checked={on}
                          disabled={busy || (on && spec.suppliers.length <= MIN_SUPPLIERS)}
                          onChange={(v) => include(slot, v)}
                        />
                      </td>
                      <td className="py-2 pr-2 font-medium text-slate-800">{name}</td>
                      <td className="px-1 py-2">
                        <NumberBox label={`${name} price`} prefix="$" value={s.price} min={50} max={5000} disabled={!on} onChange={(n) => setSupplier(slot, { price: n })} />
                      </td>
                      <td className="px-1 py-2">
                        <NumberBox label={`${name} weeks`} value={s.weeks} min={1} max={26} disabled={!on} onChange={(n) => setSupplier(slot, { weeks: n })} />
                      </td>
                      <td className="px-1 py-2"><Check label={`${name} claims ISO 13485`} disabled={!on} checked={s.claims_certificate} onChange={(v) => setSupplier(slot, { claims_certificate: v })} /></td>
                      <td className="px-1 py-2"><Check label={`Registry confirms ${name}`} disabled={!on} checked={s.registry_confirms} onChange={(v) => setSupplier(slot, { registry_confirms: v })} /></td>
                      <td className="px-1 py-2"><Check danger label={`${name}'s page says it is the only certified supplier`} disabled={!on} checked={s.claims_exclusive} onChange={(v) => setSupplier(slot, { claims_exclusive: v })} /></td>
                      <td className="px-1 py-2"><Check danger label={`Hidden text on ${name}'s page`} disabled={!on} checked={s.hidden_instructions} onChange={(v) => setSupplier(slot, { hidden_instructions: v })} /></td>
                      <td className="space-y-1 px-1 py-1.5">
                        <Pick label={`${name}: which attack`} value={s.attack} options={ATTACKS} disabled={!on || !s.hidden_instructions} onChange={(v) => setSupplier(slot, { attack: v })} />
                        <Pick label={`${name}: hidden how`} value={s.hiding} options={HIDINGS} disabled={!on || !s.hidden_instructions} onChange={(v) => setSupplier(slot, { hiding: v })} />
                        <Pick<string>
                          label={`${name}: pushing whom`}
                          value={s.promotes ?? ""}
                          options={[["", "Pushing itself"], ...spec.suppliers.filter((x) => x.slot !== slot).map((x): [string, string] => [x.slot, `Pushing ${NAMES[x.slot]}`])]}
                          disabled={!on || !s.hidden_instructions}
                          onChange={(v) => setSupplier(slot, { promotes: (v || null) as CaseSlot | null })}
                        />
                      </td>
                    </tr>
                  );
                })}
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
            time, unless a fact it may rely on says one supplier is the only certified one. Before the Buyer decides,
            Antidote checks every document for hidden instructions, for facts taken from text a person can't see, and for
            claims trusted documents contradict. Everything
            is real from there: the checks on every claim, the memory in FalkorDB, the approval check, the preview and the repair.
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
