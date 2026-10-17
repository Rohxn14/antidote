// web/src/App.tsx
// The procurement copilot: give the agents a request, watch them work, decide.
//   1. Request and documents   2. Agents and evidence   3. Recommendation and action
import { Info, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ActivityFeed } from "./components/ActivityFeed";
import { AgentStrip } from "./components/AgentStrip";
import { AlertCard } from "./components/AlertCard";
import { DocumentDrawer } from "./components/DocumentDrawer";
import { DocumentList } from "./components/DocumentList";
import { GraphCard, type NodeKind } from "./components/EvidenceGraph";
import { Header } from "./components/Header";
import { ImpactPanel, RepairLog } from "./components/ImpactPanel";
import { Guarantees, OrderCard } from "./components/OrderCard";
import { OutageScreen } from "./components/OutageScreen";
import { RequestCard } from "./components/RequestCard";
import { StoryGuide } from "./components/StoryGuide";
import { cx } from "./components/ui";
import { WhyDrawer } from "./components/WhyDrawer";
import { storyOf } from "./lib/story";
import { useAntidote, type Notice } from "./useAntidote";

function Column({ n, title, subtitle, className, children }: {
  n: number; title: string; subtitle: string; className?: string; children: ReactNode;
}) {
  return (
    <section className={cx("flex flex-col gap-3", className)} aria-label={title}>
      <div className="flex items-center gap-2.5 px-1">
        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-ink text-[12px] font-semibold text-white">{n}</span>
        <div className="min-w-0">
          <h2 className="text-[14px] font-semibold leading-5 text-slate-900">{title}</h2>
          <p className="truncate text-[12px] leading-4 text-slate-500">{subtitle}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function NoticeBar({ notice, onClose }: { notice: Notice; onClose: () => void }) {
  const error = notice.tone === "error";
  return (
    <div className="mx-auto w-full max-w-[1680px] px-4 pt-3">
      <div
        role={error ? "alert" : "status"}
        className={cx(
          "flex items-center gap-2.5 rounded-xl px-3.5 py-2 text-[13px]",
          error ? "bg-rose-50 text-rose-800 ring-1 ring-rose-200" : "bg-sky-50 text-sky-800 ring-1 ring-sky-200",
        )}
      >
        {error ? <TriangleAlert className="size-4 shrink-0" /> : <Info className="size-4 shrink-0" />}
        <span className="flex-1">{notice.text}</span>
        <button type="button" onClick={onClose} aria-label="Dismiss" className="rounded p-1 hover:bg-black/5">
          <X className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const a = useAntidote();
  const m = a.memory;
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [whyId, setWhyId] = useState<string | null>(null);
  const [seenWhy, setSeenWhy] = useState(false);
  const impactRef = useRef<HTMLDivElement>(null);

  const latest = a.orders.length ? a.orders[a.orders.length - 1] : null;
  const openWhy = useCallback((id: string) => {
    setWhyId(id);
    if (id === latest?.id || id.startsWith("d_po_")) setSeenWhy(true);
  }, [latest?.id]);
  const openNode = useCallback((id: string, kind: NodeKind) => {
    if (kind === "doc") setDocumentId(id);
    else openWhy(id);
  }, [openWhy]);
  const closeDocument = useCallback(() => setDocumentId(null), []);
  const closeWhy = useCallback(() => setWhyId(null), []);

  useEffect(() => {
    if (!m.hasRun) setSeenWhy(false);
  }, [m.hasRun]);

  useEffect(() => {
    if (a.impact) impactRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [a.impact]);

  if (a.outage) return <OutageScreen detail={a.outage} />;

  const story = storyOf(m, { ready: a.ready, running: a.running, impact: a.impact, seenWhy });
  const reading = a.agents.researcher.state === "working" ? a.agents.researcher.documentId : null;
  const busy = a.pending !== null || a.running !== null;

  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh">
      <Header health={a.health} onStartOver={a.startOver} restarting={a.pending === "restart"} />
      <StoryGuide story={story} />
      {a.notice && <NoticeBar notice={a.notice} onClose={a.dismissNotice} />}

      <main className="mx-auto grid w-full max-w-[1680px] flex-1 gap-5 px-4 pb-5 pt-4 lg:min-h-0 lg:grid-cols-[minmax(290px,330px)_minmax(0,1fr)_minmax(330px,390px)]">
        <Column n={1} title="Request and documents" subtitle="What they're asked, and what they can read" className="scroll-thin lg:min-h-0 lg:overflow-y-auto lg:pb-2 [&>*]:shrink-0">
          <RequestCard
            text={a.requestText}
            onTextChange={a.setRequestText}
            liveAvailable={a.health?.live_ai ?? false}
            model={a.health?.model ?? null}
            running={a.running}
            hasRun={m.hasRun}
            onStart={a.start}
          />
          <DocumentList memory={m} readingId={reading} onOpen={setDocumentId} />
        </Column>

        <Column n={2} title="Agents and evidence" subtitle="What they did, and what every conclusion rests on" className="lg:min-h-0">
          <AgentStrip agents={a.agents} />
          <div className="flex min-h-[680px] flex-1 flex-col gap-3 lg:min-h-0">
            <GraphCard memory={m} running={a.running === "run"} readingId={reading} onOpen={openNode} className="min-h-[360px] flex-[1.8]" />
            <ActivityFeed
              feed={a.feed}
              documents={m.documents}
              running={a.running !== null}
              onOpenDocument={setDocumentId}
              className="min-h-[190px] flex-1"
            />
          </div>
        </Column>

        <Column n={3} title="Recommendation and action" subtitle="What they propose, and what you decide" className="scroll-thin lg:min-h-0 lg:overflow-y-auto lg:pb-2 [&>*]:shrink-0">
          <OrderCard
            orders={a.orders}
            vendors={m.vendors}
            lastAction={a.lastAction}
            pending={a.pending}
            running={a.running}
            onWhy={openWhy}
            onDecide={a.decide}
            onReplan={a.replan}
          />
          {m.alerts.map((alert) => (
            <div key={alert.document_id} className="space-y-3">
              <AlertCard
                alert={alert}
                document={m.documents[alert.document_id]}
                previewing={a.impact?.document_id === alert.document_id}
                pending={a.pending}
                busy={busy}
                onShow={() => setDocumentId(alert.document_id)}
                onPreview={() => a.previewImpact(alert.document_id)}
              />
              {a.impact?.document_id === alert.document_id && (
                <div ref={impactRef}>
                  <ImpactPanel impact={a.impact} memory={m} pending={a.pending} onConfirm={a.quarantine} onCancel={a.cancelImpact} />
                </div>
              )}
            </div>
          ))}
          {a.impact && !m.alerts.some((x) => x.document_id === a.impact?.document_id) && (
            <div ref={impactRef}>
              <ImpactPanel impact={a.impact} memory={m} pending={a.pending} onConfirm={a.quarantine} onCancel={a.cancelImpact} />
            </div>
          )}
          <RepairLog repairs={m.repairs} memory={m} />
          {m.alerts.length === 0 && <Guarantees />}
        </Column>
      </main>

      {/* The document panel comes last so it opens on top of a "Why?" panel. */}
      <WhyDrawer nodeId={whyId} revision={m.revision} onClose={closeWhy} onOpenDocument={setDocumentId} />
      <DocumentDrawer documentId={documentId} onClose={closeDocument} />
    </div>
  );
}
