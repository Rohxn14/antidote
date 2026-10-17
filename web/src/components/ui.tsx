// web/src/components/ui.tsx
// The few building blocks every panel uses: cards, badges, buttons, the slide-over
// drawer (panels, not pop-up dialogs) and a segmented switch.
import { AnimatePresence, motion } from "framer-motion";
import { LoaderCircle, X } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";
import type { Tone } from "../lib/words";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cx("rounded-2xl border border-slate-200/80 bg-white shadow-card", className)} {...rest}>
      {children}
    </div>
  );
}

const BADGE: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-rose-50 text-rose-700 ring-rose-200",
  sky: "bg-sky-50 text-sky-700 ring-sky-200",
  indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
};

export const TONE_TEXT: Record<Tone, string> = {
  slate: "text-slate-600", green: "text-emerald-700", amber: "text-amber-700", red: "text-rose-700",
  sky: "text-sky-700", indigo: "text-indigo-700", violet: "text-violet-700",
};

export function Badge({ tone = "slate", icon, title, className, children }: {
  tone?: Tone; icon?: ReactNode; title?: string; className?: string; children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset [&_svg]:size-3",
        BADGE[tone], className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

const VARIANT = {
  brand: "bg-indigo-600 text-white shadow-sm shadow-indigo-600/25 hover:bg-indigo-500",
  dark: "bg-ink text-white shadow-sm hover:bg-slate-800",
  secondary: "bg-white text-slate-800 shadow-xs ring-1 ring-inset ring-slate-200 hover:bg-slate-50",
  danger: "bg-rose-600 text-white shadow-sm shadow-rose-600/25 hover:bg-rose-500",
  dangerOutline: "bg-white text-rose-700 ring-1 ring-inset ring-rose-300 hover:bg-rose-50",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
};

const SIZE = {
  sm: "h-8 px-2.5 text-[12.5px]",
  md: "h-9 px-3.5 text-[13px]",
  lg: "h-11 px-5 text-[14px]",
};

export function Button({ variant = "secondary", size = "md", icon, loading, className, children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: keyof typeof VARIANT; size?: keyof typeof SIZE; icon?: ReactNode; loading?: boolean;
  }) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex select-none items-center justify-center gap-1.5 rounded-lg font-medium transition active:translate-y-px",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
        VARIANT[variant], SIZE[size], className,
      )}
    >
      {loading ? <LoaderCircle className="animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function SectionLabel({ icon, className, children }: { icon?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <div className={cx("flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.07em] text-slate-500 [&_svg]:size-3.5", className)}>
      {icon}
      {children}
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, className }: {
  value: T;
  options: { value: T; label: string; disabled?: boolean; title?: string }[];
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div className={cx("inline-flex rounded-lg bg-slate-100 p-0.5 text-[12px]", className)} role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={o.value === value}
          disabled={o.disabled}
          title={o.title}
          onClick={() => onChange(o.value)}
          className={cx(
            "rounded-md px-2.5 py-1 font-medium transition",
            o.value === value ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/70" : "text-slate-500 hover:text-slate-800",
            o.disabled && "cursor-not-allowed opacity-40 hover:text-slate-500",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function PulseDot({ className }: { className: string }) {
  return (
    <span className="relative flex size-2">
      <span className={cx("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", className)} />
      <span className={cx("relative inline-flex size-2 rounded-full", className)} />
    </span>
  );
}

/** A panel that slides in from the right. Escape or a click outside closes it. */
export function Drawer({ open, onClose, title, subtitle, icon, width = "min(640px, 100vw)", children }: {
  open: boolean; onClose: () => void; title: ReactNode; subtitle?: ReactNode; icon?: ReactNode;
  width?: string; children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="shade"
            className="fixed inset-0 z-40 bg-slate-950/25 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            key="panel"
            role="dialog"
            aria-modal="true"
            className="fixed inset-y-0 right-0 z-50 flex flex-col bg-white shadow-2xl"
            style={{ width }}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 34, stiffness: 340 }}
          >
            <header className="flex items-start gap-3 border-b border-slate-200 px-5 py-4">
              {icon}
              <div className="min-w-0 flex-1">
                <h2 className="text-[15px] font-semibold leading-6 text-slate-900">{title}</h2>
                {subtitle && <div className="mt-0.5 text-[13px] leading-5 text-slate-500">{subtitle}</div>}
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
              >
                <X className="size-4" />
              </button>
            </header>
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">{children}</div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-[13px] text-slate-500">
      <LoaderCircle className="size-4 animate-spin" />
      {label}
    </div>
  );
}
