// web/src/components/EvidenceGraph.tsx
// The agents' memory as a graph: documents → facts → the order, joined by reasons.
// A reason (the small dot) holds only if everything feeding into it holds; a fact
// or an order is supported if at least one reason into it holds. Drawn with React
// Flow, laid out left to right with dagre, rebuilt from the same events as the feed.
import { Graph, layout } from "@dagrejs/dagre";
import {
  Background, BackgroundVariant, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider,
  useReactFlow, useStore, useUpdateNodeInternals, type Edge as FlowEdge, type Node, type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { FileText, Maximize2, Network, ShieldCheck, ShieldX, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { DecisionKind, OrderState, ReasonKind, Trust } from "../contract";
import { ancestors, ordersOf, type Memory } from "../lib/memory";
import { money, ORDER_STATE, orderLabel, orderParts, reasonTitle, TRUST } from "../lib/words";
import { Card, cx, Drawer, SectionLabel, Segmented, TONE_TEXT } from "./ui";

type DocData = { title: string; trust: Trust; flagged: boolean; reading: boolean };
type FactData = { text: string; supported: boolean; weak: boolean };
type ReasonData = { holds: boolean; kind: ReasonKind; tip: string };
type DecisionData = {
  label: string; vendor: string; amount: number | null; state: OrderState | null; supported: boolean;
  kind: DecisionKind; focus: boolean;
};

type DocNode = Node<DocData, "doc">;
type FactNode = Node<FactData, "fact">;
type ReasonNode = Node<ReasonData, "reason">;
type DecisionNode = Node<DecisionData, "decision">;
type AnyNode = DocNode | FactNode | ReasonNode | DecisionNode;
export type NodeKind = AnyNode["type"];

/** A node's box. The edge anchors sit on a still frame; only the content inside pops in,
 *  so React Flow measures the anchors where they really are. */
function Shell({ into = true, out = true, title, className, children }: {
  into?: boolean; out?: boolean; title?: string; className: string; children?: ReactNode;
}) {
  return (
    <div className="relative h-full w-full" title={title}>
      {into && <Handle type="target" position={Position.Left} isConnectable={false} />}
      {out && <Handle type="source" position={Position.Right} isConnectable={false} />}
      <div className={cx("animate-node-in h-full w-full", className)}>{children}</div>
    </div>
  );
}

function DocView({ data }: NodeProps<DocNode>) {
  const t = data.trust;
  const Icon = t === "quarantined" ? ShieldX : t === "trusted" ? ShieldCheck : FileText;
  return (
    <Shell
      into={false}
      className={cx(
        "flex cursor-pointer flex-col justify-center rounded-lg border bg-white px-2.5 shadow-sm",
        t === "quarantined" ? "border-rose-300 bg-rose-50" : t === "trusted" ? "border-emerald-300" : "border-amber-300",
        data.reading && "ring-4 ring-indigo-200",
      )}
    >
      <div
        className={cx(
          "flex items-center gap-1 text-[9.5px] font-semibold uppercase tracking-wider",
          t === "quarantined" ? "text-rose-600" : t === "trusted" ? "text-emerald-600" : "text-amber-600",
        )}
      >
        <Icon className="size-3" />
        {TRUST[t].label}
        {data.flagged && t !== "quarantined" && <TriangleAlert className="ml-auto size-3 text-rose-500" />}
      </div>
      <div className={cx("mt-0.5 line-clamp-2 text-[11.5px] font-medium leading-tight text-slate-800", t === "quarantined" && "text-rose-900/60 line-through")}>
        {data.title}
      </div>
    </Shell>
  );
}

function FactView({ data }: NodeProps<FactNode>) {
  return (
    <Shell
      className={cx(
        "relative cursor-pointer overflow-hidden rounded-lg border py-[7px] pl-3 pr-2.5 text-[11.5px] leading-[14px]",
        data.supported ? "border-slate-200 bg-white text-slate-800 shadow-sm" : "border-dashed border-slate-300 bg-slate-50 text-slate-400",
      )}
    >
      <span
        className={cx(
          "absolute inset-y-0 left-0 w-[3px]",
          !data.supported ? "bg-slate-300" : data.weak ? "bg-amber-400" : "bg-emerald-500",
        )}
      />
      <span className={cx("line-clamp-3", !data.supported && "line-through decoration-slate-300")}>{data.text}</span>
    </Shell>
  );
}

function ReasonView({ data }: NodeProps<ReasonNode>) {
  return (
    <Shell
      title={data.tip}
      className={cx(
        "rounded-full border-2",
        !data.holds ? "border-slate-300 bg-white" : data.kind === "decision" ? "border-indigo-500 bg-indigo-500" : "border-emerald-500 bg-emerald-500",
      )}
    />
  );
}

function DecisionView({ data }: NodeProps<DecisionNode>) {
  const state = data.state ? ORDER_STATE[data.state] : null;
  const lost = !data.supported || data.state === "blocked";
  return (
    <Shell
      out={false}
      className={cx(
        "flex cursor-pointer flex-col justify-center rounded-xl border-2 bg-white px-3 shadow-md",
        lost ? "border-rose-300 bg-rose-50" : data.kind === "purchase_order" ? "border-indigo-400" : "border-violet-200",
        data.focus && !lost && "ring-4 ring-indigo-100",
      )}
    >
      <div className="flex items-center justify-between gap-2 text-[9.5px] font-semibold uppercase tracking-wider text-slate-500">
        <span>{data.kind === "purchase_order" ? data.label : "Shortlist"}</span>
        {state && <span className={TONE_TEXT[state.tone]}>{lost && data.state !== "blocked" ? "Unsupported" : state.short}</span>}
      </div>
      <div className={cx("mt-0.5 truncate text-[12.5px] font-semibold text-slate-900", lost && "text-rose-900/60 line-through")}>
        {data.vendor}
      </div>
      {data.amount !== null && <div className="text-[11px] tabular-nums text-slate-500">{money(data.amount)}</div>}
    </Shell>
  );
}

const nodeTypes = { doc: DocView, fact: FactView, reason: ReasonView, decision: DecisionView } satisfies NodeTypes;

const ORIGIN = { x: 0, y: 0 };
const factHeight = (text: string) => 16 + Math.min(3, Math.ceil(text.length / 27)) * 14;

function laidOut(nodes: AnyNode[], edges: FlowEdge[]): AnyNode[] {
  const g = new Graph();
  g.setGraph({ rankdir: "LR", nodesep: 10, ranksep: 30, marginx: 12, marginy: 12 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) g.setNode(n.id, { width: n.width ?? 0, height: n.height ?? 0 });
  for (const e of edges) g.setEdge(e.source, e.target);
  layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id) as unknown as { x: number; y: number };
    return {
      ...n,
      // React Flow forgets a node's handle measurements when a new node object arrives
      // without `measured`, and then cannot draw its edges. The size is known: say so.
      measured: { width: n.width, height: n.height },
      position: { x: p.x - (n.width ?? 0) / 2, y: p.y - (n.height ?? 0) / 2 },
    };
  });
}

function buildFlow(m: Memory, only: Set<string> | null, readingId: string | null, focusId: string | null,
                   fresh: string | null) {
  const show = (id: string) => !only || only.has(id);
  const flagged = new Set(m.alerts.map((a) => a.document_id));
  // The links into the node recorded last move while the agents work.
  const freshReasons = new Set(m.edges.filter((e) => e.kind === "supports" && e.to_id === fresh).map((e) => e.from_id));
  const nodes: AnyNode[] = [];
  for (const d of Object.values(m.documents)) {
    if (!show(d.id)) continue;
    nodes.push({
      id: d.id, type: "doc", position: ORIGIN, width: 164, height: 50,
      data: { title: d.title, trust: d.trust, flagged: flagged.has(d.id), reading: d.id === readingId },
    });
  }
  for (const f of Object.values(m.facts)) {
    if (!show(f.id)) continue;
    nodes.push({
      id: f.id, type: "fact", position: ORIGIN, width: 176, height: factHeight(f.text),
      data: { text: f.text, supported: f.supported, weak: f.evidence === "unverified only" },
    });
  }
  for (const r of Object.values(m.reasons)) {
    if (!show(r.id)) continue;
    nodes.push({
      id: r.id, type: "reason", position: ORIGIN, width: 12, height: 12,
      data: { holds: r.holds, kind: r.kind, tip: `${reasonTitle(r.kind, r.author)}: ${r.holds ? "holds" : "no longer holds"}` },
    });
  }
  for (const d of Object.values(m.decisions)) {
    if (!show(d.id)) continue;
    const parts = orderParts(d.summary);
    nodes.push({
      id: d.id, type: "decision", position: ORIGIN, width: 176, height: d.amount !== null ? 62 : 48,
      data: {
        label: orderLabel(d.summary, d.id), vendor: parts?.vendor ?? (d.vendor_id ? m.vendors[d.vendor_id] : null) ?? d.summary,
        amount: d.amount, state: d.state, supported: d.supported, kind: d.kind, focus: d.id === focusId,
      },
    });
  }
  const ids = new Set(nodes.map((n) => n.id));
  const edges: FlowEdge[] = m.edges
    .filter((e) => ids.has(e.from_id) && ids.has(e.to_id))
    .map((e) => {
      const reason = m.reasons[e.kind === "premise" ? e.to_id : e.from_id];
      const holds = reason?.holds ?? false;
      const color = !holds ? "#cbd5e1" : reason?.kind === "decision" ? "#818cf8" : "#34d399";
      return {
        id: `${e.from_id}>${e.to_id}`, source: e.from_id, target: e.to_id, type: "default",
        animated: e.to_id === fresh || freshReasons.has(e.to_id),
        style: { stroke: color, strokeWidth: 1.5, strokeDasharray: holds ? undefined : "4 4" },
        markerEnd: e.kind === "supports" ? { type: MarkerType.ArrowClosed, color, width: 14, height: 14 } : undefined,
      };
    });
  return { nodes: laidOut(nodes, edges), edges };
}

type Viewport = { x: number; y: number; zoom: number };

/** The whole graph, centred, as large as fits (positions come from the dagre layout). */
function frameAll(nodes: AnyNode[], width: number, height: number): Viewport {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {
    minX = Math.min(minX, n.position.x);
    minY = Math.min(minY, n.position.y);
    maxX = Math.max(maxX, n.position.x + (n.width ?? 0));
    maxY = Math.max(maxY, n.position.y + (n.height ?? 0));
  }
  const w = maxX - minX, h = maxY - minY, pad = 24;
  const zoom = Math.max(0.15, Math.min(1.2, (width - 2 * pad) / w, (height - 2 * pad) / h));
  return { zoom, x: (width - w * zoom) / 2 - minX * zoom, y: (height - h * zoom) / 2 - minY * zoom };
}

/** Close up on one node, a little right of centre so what led to it stays in view. */
function closeUp(node: AnyNode, width: number, height: number): Viewport {
  const zoom = 0.95;
  const cx = node.position.x + (node.width ?? 0) / 2;
  const cy = node.position.y + (node.height ?? 0) / 2;
  return { zoom, x: width * 0.62 - cx * zoom, y: height / 2 - cy * zoom };
}

/** Frame the graph when its shape changes (debounced: a burst of events moves once) and when
 *  the panel resizes. While the agents work, the camera follows the newest fact instead. */
function Camera({ nodes, follow, signature }: { nodes: AnyNode[]; follow: string | null; signature: string }) {
  const { setViewport } = useReactFlow();
  const remeasure = useUpdateNodeInternals();
  const width = useStore((s) => s.width);
  const height = useStore((s) => s.height);
  const first = useRef(true);
  const latest = useRef(nodes);
  latest.current = nodes;
  useEffect(() => {
    if (!width || !height || !latest.current.length) return;
    const t = setTimeout(() => {
      const all = latest.current;
      // Nodes added in a burst can miss their measurement, and without it their edges
      // are not drawn: measure every node again whenever the layout changes.
      remeasure(all.map((n) => n.id));
      const node = follow ? all.find((n) => n.id === follow) : undefined;
      const viewport = node ? closeUp(node, width, height) : frameAll(all, width, height);
      void setViewport(viewport, { duration: first.current ? 0 : 600 });
      first.current = false;
    }, 60);
    return () => clearTimeout(t);
  }, [signature, follow, width, height, setViewport, remeasure]);
  return null;
}

/** Nodes glide to their new place when the layout changes. Done in JavaScript, not CSS,
 *  so the edges move with them frame by frame. */
function useGlide(target: AnyNode[]): AnyNode[] {
  const [shown, setShown] = useState(target);
  const placed = useRef(new Map<string, { x: number; y: number }>());
  useEffect(() => {
    const from = new Map(placed.current);
    const moved = target.some((n) => {
      const f = from.get(n.id);
      return f && (f.x !== n.position.x || f.y !== n.position.y);
    });
    if (!moved) {
      setShown(target);
      return;
    }
    const start = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / 520);
      const ease = 1 - Math.pow(1 - t, 3);
      setShown(target.map((n) => {
        const f = from.get(n.id);
        return f ? { ...n, position: { x: f.x + (n.position.x - f.x) * ease, y: f.y + (n.position.y - f.y) * ease } } : n;
      }));
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target]);
  useEffect(() => {
    placed.current = new Map(shown.map((n) => [n.id, n.position]));
  }, [shown]);
  return shown;
}

function Flow({ memory, only, readingId, focusId, follow, interactive, onOpen }: {
  memory: Memory; only: Set<string> | null; readingId: string | null; focusId: string | null;
  follow: string | null; interactive: boolean; onOpen: (id: string, kind: NodeKind) => void;
}) {
  const { nodes, edges } = useMemo(
    () => buildFlow(memory, only, readingId, focusId, follow),
    [memory, only, readingId, focusId, follow],
  );
  const shown = useGlide(nodes);
  return (
    <ReactFlowProvider>
      <ReactFlow
        nodes={shown}
        edges={edges}
        nodeTypes={nodeTypes}
        minZoom={0.15}
        maxZoom={1.8}
        nodesDraggable={false}
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        zoomOnScroll={interactive}
        preventScrolling={interactive}
        zoomOnDoubleClick={false}
        onNodeClick={(_, node) => node.type !== "reason" && onOpen(node.id, node.type)}
        attributionPosition="bottom-left"
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#d5dce6" />
        {interactive && <Controls showInteractive={false} position="bottom-right" />}
        <Camera nodes={nodes} follow={follow} signature={`${nodes.length}:${edges.length}:${only ? "order" : "all"}`} />
      </ReactFlow>
    </ReactFlowProvider>
  );
}

function Legend() {
  const item = "flex items-center gap-1.5";
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
      <span className={item}><i className="h-3 w-[3px] rounded bg-emerald-500" />Backed by a trusted document</span>
      <span className={item}><i className="h-3 w-[3px] rounded bg-amber-400" />Unverified sources only</span>
      <span className={item}><i className="size-2.5 rounded-full bg-emerald-500" />A reason that holds</span>
      <span className={item}><i className="size-2.5 rounded-full border-2 border-slate-300 bg-white" />Lost its support</span>
    </div>
  );
}

export function GraphCard({ memory, running, readingId, onOpen, className }: {
  memory: Memory; running: boolean; readingId: string | null;
  onOpen: (id: string, kind: NodeKind) => void; className?: string;
}) {
  const orders = ordersOf(memory);
  const focus = orders.length ? orders[orders.length - 1] : null;
  const [choice, setChoice] = useState<"order" | "all" | null>(null);
  const [expanded, setExpanded] = useState(false);
  const view = focus && (choice ?? (running ? "all" : "order")) === "order" ? "order" : "all";
  const only = useMemo(() => (view === "order" && focus ? ancestors(memory, focus.id) : null), [view, focus, memory]);
  const empty = Object.keys(memory.facts).length === 0 && !running;
  const title = view === "order" && focus ? `Behind ${orderLabel(focus.summary, focus.id)}` : "Everything in memory";

  const follow = running && view === "all" ? memory.latest : null;
  const flow = (interactive: boolean) => (
    <Flow
      memory={memory}
      only={only}
      readingId={readingId}
      focusId={focus?.id ?? null}
      follow={interactive ? null : follow}
      interactive={interactive}
      onOpen={onOpen}
    />
  );
  const toggle = (
    <Segmented
      value={view}
      onChange={setChoice}
      options={[
        { value: "order", label: "This order", disabled: !focus, title: "Only what the latest order rests on" },
        { value: "all", label: "Everything" },
      ]}
    />
  );

  return (
    <Card className={cx("flex min-h-0 flex-col overflow-hidden", className)}>
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2">
        <SectionLabel icon={<Network />}>{title}</SectionLabel>
        <div className="ml-auto flex items-center gap-1.5">
          {toggle}
          <button
            type="button"
            onClick={() => setExpanded(true)}
            disabled={empty}
            title="Open the graph in a large panel"
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 disabled:opacity-40"
          >
            <Maximize2 className="size-4" />
          </button>
        </div>
      </div>
      <div className="relative min-h-0 flex-1 bg-slate-50/40">
        {empty ? (
          <div className="grid h-full min-h-[220px] place-items-center px-8 text-center">
            <div>
              <Network className="mx-auto size-8 text-slate-300" />
              <p className="mt-3 text-[13px] font-medium text-slate-600">The agents' memory, as a graph</p>
              <p className="mx-auto mt-1 max-w-sm text-[12.5px] leading-5 text-slate-500">
                Documents on the left, then the facts the agents take from them, then the order. Every link is a
                recorded reason, stored in FalkorDB.
              </p>
            </div>
          </div>
        ) : (
          flow(false)
        )}
      </div>
      <div className="flex items-center gap-4 border-t border-slate-100 px-4 py-2">
        <Legend />
        <span className="ml-auto hidden whitespace-nowrap text-[11px] text-slate-400 2xl:inline">Click a box to see why</span>
      </div>

      <Drawer
        open={expanded}
        onClose={() => setExpanded(false)}
        width="min(1280px, 96vw)"
        title={title}
        subtitle="Scroll to zoom, drag to move. Click a box to see why it's believed."
        icon={
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
            <Network className="size-[18px]" />
          </span>
        }
      >
        <div className="flex h-full flex-col">
          <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 px-5 py-2.5">
            {toggle}
            <Legend />
          </div>
          <div className="min-h-[480px] flex-1 bg-slate-50/40">{flow(true)}</div>
        </div>
      </Drawer>
    </Card>
  );
}
