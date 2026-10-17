// web/src/components/ActivityFeed.tsx
// What the agents did, line by line, as it happens.
import { motion } from "framer-motion";
import { Activity, BookOpen, FileText, ShieldCheck, ShoppingCart, User, type LucideIcon } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Document } from "../contract";
import type { FeedItem, FeedTone, Who } from "../lib/feed";
import { Card, cx, SectionLabel } from "./ui";

const AVATAR: Record<Who, { Icon: LucideIcon; tint: string; name: string }> = {
  researcher: { Icon: BookOpen, tint: "bg-indigo-100 text-indigo-700", name: "Researcher" },
  buyer: { Icon: ShoppingCart, tint: "bg-violet-100 text-violet-700", name: "Buyer" },
  guard: { Icon: ShieldCheck, tint: "bg-teal-100 text-teal-700", name: "Antidote" },
  you: { Icon: User, tint: "bg-ink text-white", name: "You" },
};

const TONE: Record<Exclude<FeedTone, "status">, { box: string; title: string }> = {
  fact: { box: "", title: "text-slate-900" },
  refused: { box: "bg-amber-50/80", title: "text-amber-800" },
  decision: { box: "bg-violet-50/70", title: "text-violet-800" },
  gate: { box: "bg-sky-50/80", title: "text-sky-800" },
  alert: { box: "bg-rose-50 ring-1 ring-inset ring-rose-100", title: "text-rose-700" },
  error: { box: "bg-rose-50 ring-1 ring-inset ring-rose-100", title: "text-rose-700" },
  done: { box: "bg-emerald-50/80", title: "text-emerald-800" },
  action: { box: "bg-slate-50 ring-1 ring-inset ring-slate-200/70", title: "text-slate-900" },
  blocked: { box: "bg-rose-50 ring-1 ring-inset ring-rose-100", title: "text-rose-700" },
  good: { box: "bg-emerald-50/80", title: "text-emerald-800" },
};

function Avatar({ who, small }: { who: Who; small?: boolean }) {
  const { Icon, tint, name } = AVATAR[who];
  return (
    <span title={name} className={cx("grid shrink-0 place-items-center rounded-full", tint, small ? "size-5" : "size-7")}>
      <Icon className={small ? "size-3" : "size-3.5"} />
    </span>
  );
}

const time = (at: number | null) => (at === null ? "" : `${at.toFixed(1)}s`);

function Row({ item, documents, onOpenDocument }: {
  item: FeedItem; documents: Record<string, Document>; onOpenDocument: (id: string) => void;
}) {
  if (item.tone === "status") {
    return (
      <div className="flex items-center gap-2 px-1.5 py-1 text-[12px] text-slate-500">
        <Avatar who={item.who} small />
        <span className="min-w-0 flex-1 truncate">{item.title}</span>
        <span className="text-[10.5px] tabular-nums text-slate-400">{time(item.at)}</span>
      </div>
    );
  }
  const tone = TONE[item.tone];
  const linked = item.tone === "fact" || item.tone === "alert" || item.tone === "refused";
  const doc = linked && item.documentId ? documents[item.documentId] : undefined;
  return (
    <div className={cx("flex gap-2.5 rounded-xl px-2.5 py-2", tone.box)}>
      <Avatar who={item.who} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className={cx("text-[12.5px] font-semibold", tone.title)}>{item.title}</span>
          <span className="ml-auto text-[10.5px] tabular-nums text-slate-400">{time(item.at)}</span>
        </div>
        {item.body && <p className="mt-0.5 text-[12.5px] leading-[18px] text-slate-700">{item.body}</p>}
        {item.quote && (
          <p className="mt-1 border-l-2 border-slate-200 pl-2 text-[12px] italic leading-[17px] text-slate-500">“{item.quote}”</p>
        )}
        {doc && (
          <button
            type="button"
            onClick={() => onOpenDocument(doc.id)}
            className="mt-1 inline-flex items-center gap-1 text-[11.5px] font-medium text-indigo-600 hover:text-indigo-800 hover:underline"
          >
            <FileText className="size-3" />
            {doc.title}
          </button>
        )}
      </div>
    </div>
  );
}

export function ActivityFeed({ feed, documents, running, onOpenDocument, className }: {
  feed: FeedItem[];
  documents: Record<string, Document>;
  running: boolean;
  onOpenDocument: (id: string) => void;
  className?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const follow = useRef(true);

  useEffect(() => {
    const el = box.current;
    if (el && follow.current) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [feed.length]);

  return (
    <Card className={cx("flex min-h-0 flex-col overflow-hidden", className)}>
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
        <SectionLabel icon={<Activity />}>Activity</SectionLabel>
        <span className="text-[11px] tabular-nums text-slate-400">
          {running ? "live" : feed.length ? `${feed.length} events` : ""}
        </span>
      </div>
      <div
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
        }}
        className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2.5 py-2"
      >
        {feed.length === 0 ? (
          <div className="grid h-full min-h-[120px] place-items-center px-6 text-center text-[12.5px] leading-5 text-slate-400">
            What the agents read, conclude and decide will appear here, step by step.
          </div>
        ) : (
          <ol className="space-y-1">
            {feed.map((item) => (
              <motion.li
                key={item.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, ease: "easeOut" }}
              >
                <Row item={item} documents={documents} onOpenDocument={onOpenDocument} />
              </motion.li>
            ))}
          </ol>
        )}
      </div>
    </Card>
  );
}
