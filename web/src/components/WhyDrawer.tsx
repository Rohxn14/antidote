// web/src/components/WhyDrawer.tsx
// Why is this believed? The chain of reasons from an order or a fact down to the
// documents, read live from the graph (GET /api/why).
import { CircleDot, FileText, GitBranch, Package } from "lucide-react";
import { useEffect, useState } from "react";
import type { WhyNode, WhyReason } from "../contract";
import { api } from "../lib/api";
import { EVIDENCE, reasonTitle, TRUST } from "../lib/words";
import { Badge, cx, Drawer, Loading } from "./ui";

function NodeBox({ node, root, onOpenDocument }: {
  node: WhyNode; root?: boolean; onOpenDocument: (id: string) => void;
}) {
  const doc = node.kind === "document";
  const Icon = doc ? FileText : node.kind === "decision" ? Package : CircleDot;
  return (
    <div
      className={cx(
        "flex items-start gap-2.5 rounded-xl border px-3 py-2",
        node.supported ? "border-slate-200 bg-white" : "border-dashed border-slate-300 bg-slate-50",
        root && "border-indigo-200 bg-indigo-50/40 shadow-sm",
      )}
    >
      <Icon className={cx("mt-0.5 size-4 shrink-0", doc ? "text-slate-400" : node.supported ? "text-emerald-500" : "text-slate-300")} />
      <div className="min-w-0 flex-1">
        {doc ? (
          <button
            type="button"
            onClick={() => onOpenDocument(node.id)}
            className="text-left text-[13px] font-medium text-indigo-700 hover:text-indigo-900 hover:underline"
          >
            {node.text}
          </button>
        ) : (
          <div className={cx("text-[13px] leading-5", root ? "font-semibold" : "font-medium", node.supported ? "text-slate-900" : "text-slate-400 line-through")}>
            {node.text}
          </div>
        )}
        <div className="mt-1 flex flex-wrap gap-1.5">
          {doc && node.trust && <Badge tone={TRUST[node.trust].tone} title={TRUST[node.trust].hint}>{TRUST[node.trust].label}</Badge>}
          {!doc && <Badge tone={node.supported ? "green" : "red"}>{node.supported ? "Supported" : "Not supported"}</Badge>}
          {!doc && node.evidence && (
            <Badge tone={EVIDENCE[node.evidence].tone} title={EVIDENCE[node.evidence].hint}>{EVIDENCE[node.evidence].label}</Badge>
          )}
          {node.loop && <Badge tone="slate">already shown above</Badge>}
        </div>
      </div>
    </div>
  );
}

function ReasonBlock({ reason, onOpenDocument }: { reason: WhyReason; onOpenDocument: (id: string) => void }) {
  return (
    <div className="relative py-2">
      <span
        className={cx(
          "absolute -left-[21px] top-[14px] size-2.5 rounded-full ring-[3px] ring-white",
          reason.holds ? "bg-emerald-500" : "bg-slate-300",
        )}
      />
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[12px] font-semibold text-slate-700">{reasonTitle(reason.kind, reason.author)}</span>
        <Badge tone={reason.holds ? "green" : "slate"}>{reason.holds ? "holds" : "doesn't hold"}</Badge>
        {reason.premises.length > 1 && <span className="text-[11px] text-slate-500">needs all {reason.premises.length} below</span>}
      </div>
      {reason.reasoning && <p className="mt-0.5 text-[12.5px] leading-5 text-slate-600">{reason.reasoning}</p>}
      {reason.quote && (
        <blockquote className="mt-1.5 rounded-lg bg-slate-50 px-2.5 py-1.5 text-[12px] italic leading-5 text-slate-600 ring-1 ring-inset ring-slate-100">
          “{reason.quote}”
        </blockquote>
      )}
      <div className="mt-2 space-y-2">
        {reason.premises.map((p) => <Tree key={p.id} node={p} onOpenDocument={onOpenDocument} />)}
      </div>
    </div>
  );
}

function Tree({ node, root, onOpenDocument }: { node: WhyNode; root?: boolean; onOpenDocument: (id: string) => void }) {
  return (
    <div>
      <NodeBox node={node} root={root} onOpenDocument={onOpenDocument} />
      {node.reasons.length > 0 && !node.loop && (
        <div className="ml-[15px] border-l-2 border-slate-100 pl-4">
          {node.reasons.length > 1 && (
            <div className="pt-2 text-[11px] font-medium text-slate-500">Any one of these {node.reasons.length} reasons is enough</div>
          )}
          {node.reasons.map((r) => <ReasonBlock key={r.id} reason={r} onOpenDocument={onOpenDocument} />)}
        </div>
      )}
    </div>
  );
}

export function WhyDrawer({ nodeId, revision, onClose, onOpenDocument }: {
  nodeId: string | null; revision: number; onClose: () => void; onOpenDocument: (id: string) => void;
}) {
  const [root, setRoot] = useState<WhyNode | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!nodeId) return;
    let live = true;
    setError(null);
    api.why(nodeId)
      .then((r) => live && setRoot(r.root))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [nodeId, revision]);

  const shown = root && root.id === nodeId ? root : null;
  const title = shown?.kind === "decision" ? "Why this supplier?" : shown?.kind === "document" ? "This document" : "Why is this believed?";

  return (
    <Drawer
      open={nodeId !== null}
      onClose={onClose}
      title={title}
      subtitle={shown?.text}
      icon={
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
          <GitBranch className="size-[18px]" />
        </span>
      }
    >
      {error && <p className="m-5 rounded-xl bg-rose-50 p-4 text-[13px] text-rose-800">{error}</p>}
      {!shown && !error && <Loading label="Reading the reasons from FalkorDB…" />}
      {shown && (
        <div className="space-y-4 p-5">
          <div className="rounded-xl bg-slate-50 px-3.5 py-3 text-[12.5px] leading-5 text-slate-600 ring-1 ring-inset ring-slate-100">
            Read it from the top down: each item is believed because of the reasons under it. A reason holds only if
            everything it rests on holds; one reason that holds is enough. Antidote recomputes this inside FalkorDB
            after every change.
          </div>
          <Tree node={shown} root onOpenDocument={onOpenDocument} />
        </div>
      )}
    </Drawer>
  );
}
