// web/src/App.tsx
// The procurement copilot: give the agents a request, watch them work, decide.
//   1. Request and documents   2. Agents and evidence   3. Recommendation and action
import { Info, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ActivityFeed } from "./components/ActivityFeed";
import { AgentStrip } from "./components/AgentStrip";
import { AlertCard } from "./components/AlertCard";
import { CaseBar } from "./components/CaseBar";
import { CaseBuilder } from "./components/CaseBuilder";
import { DocumentDrawer } from "./components/DocumentDrawer";
import { DocumentList } from "./components/DocumentList";
import { GraphCard, type NodeKind } from "./components/EvidenceGraph";
import { Header, type Page } from "./components/Header";
import { UnderTheHood } from "./components/UnderTheHood";
import { ImpactPanel, RepairLog } from "./components/ImpactPanel";
import { Guarantees, OrderCard } from "./components/OrderCard";
import { OutageScreen } from "./components/OutageScreen";
import { RequestCard } from "./components/RequestCard";
import { cx } from "./components/ui";
import { WhyDrawer } from "./components/WhyDrawer";
import { chipsOf, suggestionOf } from "./lib/story";
import { caseTitle } from "./lib/words";
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

/** Which page is showing: the case, or #/under-the-hood (a link people can share). */
function usePage(): [Page, (page: Page) => void] {
  const read = (): Page => (window.location.hash === "#/under-the-hood" ? "hood" : "case");
  const [page, setPage] = useState<Page>(read);
  useEffect(() => {
    const onHash = () => setPage(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = useCallback((p: Page) => {
    window.location.hash = p === "hood" ? "#/under-the-hood" : "#/";
    window.scrollTo({ top: 0 });
  }, []);
  return [page, go];
}

export default function App() {
  const a = useAntidote();
  const m = a.memory;
  const [page, setPage] = usePage();
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [whyId, setWhyId] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const impactRef = useRef<HTMLDivElement>(null);
  const orderRef = useRef<HTMLDivElement>(null);

  const openNode = useCallback((id: string, kind: NodeKind) => {
    if (kind === "doc") setDocumentId(id);
    else setWhyId(id);
  }, []);
  const closeDocument = useCallback(() => setDocumentId(null), []);
  const closeWhy = useCallback(() => setWhyId(null), []);
  const { previewImpact } = a;
  const previewFromDocument = useCallback((id: string) => {
    setDocumentId(null);
    void previewImpact(id);
  }, [previewImpact]);

  useEffect(() => {
    if (a.impact) impactRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [a.impact]);

  // A new recommendation, or a change in its state (held, blocked, placed): show its top.
  const latest = a.orders.length ? a.orders[a.orders.length - 1] : null;
  const orderMark = latest ? `${latest.id}:${latest.state}:${latest.held_by.length}` : "";
  useEffect(() => {
    if (orderMark) orderRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [orderMark]);

  if (a.outage) return <OutageScreen detail={a.outage} />;

  const reading = a.agents.researcher.state === "working" ? a.agents.researcher.documentId : null;
  const busy = a.pending !== null || a.running !== null;
  const situation = { ready: a.ready, running: a.running, impact: a.impact };
  const impactFor = a.impact?.document_id ?? null;
  const impactPanel = a.impact && (
    <div ref={impactRef}>
      <ImpactPanel impact={a.impact} memory={m} pending={a.pending} onConfirm={a.quarantine} onCancel={a.cancelImpact} />
    </div>
  );

  const header = (
    <Header
      health={a.health}
      syncing={a.pending !== null}
      onStartOver={a.startOver}
      restarting={a.pending === "restart"}
      page={page}
      onNavigate={setPage}
    />
  );

  if (page === "hood") {
    return (
      <div className="min-h-dvh">
        {header}
        <UnderTheHood />
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh">
      {header}
      <CaseBar title={m.builtCase ? `${m.builtCase.name} (built by you)` : caseTitle(a.requestText)} chips={chipsOf(m, a.running)} suggestion={suggestionOf(m, situation)} />
      {a.notice && <NoticeBar notice={a.notice} onClose={a.dismissNotice} />}

      <main className="mx-auto grid w-full max-w-[1680px] flex-1 gap-5 px-4 pb-5 pt-4 lg:min-h-0 lg:grid-cols-[minmax(290px,330px)_minmax(0,1fr)_minmax(340px,400px)]">
        <Column n={1} title="Request and documents" subtitle="What they're asked, and what they can read" className="scroll-thin lg:min-h-0 lg:overflow-y-auto lg:pb-2 [&>*]:shrink-0">
          <RequestCard
            text={a.requestText}
            onTextChange={a.setRequestText}
            liveAvailable={a.health?.live_ai ?? false}
            model={a.health?.model ?? null}
            running={a.running}
            hasRun={m.hasRun}
            onStart={a.start}
            builtCase={m.builtCase}
            onBuild={() => setBuilding(true)}
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
          <div ref={orderRef} className="scroll-mt-2">
            <OrderCard
              orders={a.orders}
              memory={m}
              lastAction={a.lastAction}
              pending={a.pending}
              running={a.running}
              onWhy={setWhyId}
              onDecide={a.decide}
              onReplan={a.replan}
              onOpenDocument={setDocumentId}
            />
          </div>
          {impactFor && !m.alerts.some((x) => x.document_id === impactFor) && impactPanel}
          {m.alerts.map((alert) => (
            <div key={alert.document_id} className="space-y-3">
              <AlertCard
                alert={alert}
                document={m.documents[alert.document_id]}
                previewing={impactFor === alert.document_id}
                pending={a.pending}
                busy={busy}
                onShow={() => setDocumentId(alert.document_id)}
                onPreview={() => a.previewImpact(alert.document_id)}
              />
              {impactFor === alert.document_id && impactPanel}
            </div>
          ))}
          <RepairLog repairs={m.repairs} memory={m} />
          {m.alerts.length === 0 && !a.impact && <Guarantees />}
        </Column>
      </main>

      <CaseBuilder
        open={building}
        current={m.builtCase}
        busy={a.pending === "case" || a.running !== null}
        onClose={() => setBuilding(false)}
        onUse={(spec) => {
          setBuilding(false);
          void a.openCase(spec);
        }}
      />
      {/* The document panel comes last so it opens on top of a "Why?" panel. */}
      <WhyDrawer nodeId={whyId} revision={m.revision} onClose={closeWhy} onOpenDocument={setDocumentId} />
      <DocumentDrawer
        documentId={documentId}
        onClose={closeDocument}
        onPreview={m.hasRun && !busy && !a.impact ? previewFromDocument : null}
      />
    </div>
  );
}
