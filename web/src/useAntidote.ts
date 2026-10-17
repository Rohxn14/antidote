// web/src/useAntidote.ts
// Everything the page knows and can do. Streams grow the memory and the activity
// feed event by event; every run and every other action ends by reloading
// GET /api/state, so the screen always matches what FalkorDB holds.
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type {
  AntidoteEvent, HealthResponse, ImpactResponse, OrderActionResponse, RunMode, StateResponse,
} from "./contract";
import { api, ApiFailure } from "./lib/api";
import { describe, WHO, type FeedEntry, type FeedItem, type Who } from "./lib/feed";
import { emptyMemory, memoryReducer, ordersOf, type Memory } from "./lib/memory";
import { OUTCOME, orderLabel, plural } from "./lib/words";

export type AgentKey = Exclude<Who, "you">;

export interface AgentView {
  state: "idle" | "working" | "waiting" | "done";
  message: string;
  documentId: string | null;
}

export interface Notice {
  tone: "info" | "error";
  text: string;
}

export type Pending = "impact" | "cancel" | "quarantine" | "approve" | "execute" | "restart";

const IDLE: Record<AgentKey, AgentView> = {
  researcher: { state: "idle", message: "Ready to read the documents.", documentId: null },
  buyer: { state: "idle", message: "Ready to compare suppliers.", documentId: null },
  guard: { state: "idle", message: "Watching the memory.", documentId: null },
};

const UNREACHABLE = "The server can't be reached.";
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const expired = (e: unknown) => e instanceof ApiFailure && e.status === 401;

/** Agent cards for a session restored after a page refresh. */
function restoredAgents(s: StateResponse): Record<AgentKey, AgentView> {
  const orders = s.decisions.filter((d) => d.kind === "purchase_order");
  const waiting = orders.some((d) => d.state === "pending_approval" || d.state === "authorized");
  return {
    researcher: { state: "done", message: "Finished reading.", documentId: null },
    buyer: { state: waiting ? "waiting" : "done", message: waiting ? "Waiting for your decision." : "Done.", documentId: null },
    guard: { state: "done", message: `Scan finished: ${plural(s.alerts.length, "document")} flagged.`, documentId: null },
  };
}

export function useAntidote() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [outage, setOutage] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [memory, dispatch] = useReducer(memoryReducer, emptyMemory);
  const [requestText, setRequestText] = useState("");
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [agents, setAgents] = useState(IDLE);
  const [running, setRunning] = useState<"run" | "replan" | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [impact, setImpact] = useState<ImpactResponse | null>(null);
  const [lastAction, setLastAction] = useState<OrderActionResponse | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const memoryRef = useRef<Memory>(memory);
  const current = useRef<{ controller: AbortController; started: number } | null>(null);
  const nextId = useRef(0);
  const lastMode = useRef<RunMode>("replay");
  const booted = useRef(false);

  useEffect(() => {
    memoryRef.current = memory;
  }, [memory]);

  const push = useCallback((entry: FeedEntry) => {
    const run = current.current;
    const at = run ? (performance.now() - run.started) / 1000 : null;
    setFeed((items) => [...items, { ...entry, id: ++nextId.current, at }]);
  }, []);

  const refresh = useCallback(async (): Promise<StateResponse> => {
    const s = await api.state();
    dispatch({ type: "load", state: s });
    setRequestText((text) => (s.request.editable && text ? text : s.request.text));
    return s;
  }, []);

  const clearRun = useCallback(() => {
    setFeed([]);
    setAgents(IDLE);
    setImpact(null);
    setLastAction(null);
    setNotice(null);
  }, []);

  /** Every failure ends here: an expired session restarts, a lost database shows the outage screen. */
  const fail = useCallback(async (e: unknown) => {
    if (expired(e)) {
      try {
        await api.newSession();
        clearRun();
        await refresh();
        setNotice({ tone: "info", text: "Your session had expired, so you're starting with a fresh memory." });
      } catch (again) {
        setNotice({ tone: "error", text: again instanceof Error ? again.message : String(again) });
      }
      return;
    }
    if ((e instanceof ApiFailure && e.status === 503) || e instanceof TypeError) {
      const h = await api.health().catch(() => null);
      setHealth(h);
      if (h?.falkordb !== "up") {
        setOutage(h?.detail ?? UNREACHABLE);
        return;
      }
    }
    setNotice({ tone: "error", text: e instanceof Error ? e.message : String(e) });
  }, [clearRun, refresh]);

  const settle = useCallback(async () => {
    try {
      await refresh();
    } catch (e) {
      await fail(e);
    }
  }, [fail, refresh]);

  /** Load the session's memory, starting a new session if there is none (or it expired). */
  const connect = useCallback(async (): Promise<StateResponse> => {
    if (!api.hasSession()) await api.newSession();
    try {
      return await refresh();
    } catch (e) {
      if (!expired(e)) throw e;
      await api.newSession();
      return refresh();
    }
  }, [refresh]);

  // --- Streams: the agents at work ---------------------------------------------------------

  type Go = (onEvent: (e: AntidoteEvent) => void, signal: AbortSignal) => Promise<void>;

  const stream = useCallback(async (kind: "run" | "replan", go: Go, intro?: FeedEntry) => {
    current.current?.controller.abort();
    const mine = { controller: new AbortController(), started: performance.now() };
    current.current = mine;
    setRunning(kind);
    setNotice(null);
    if (intro) push(intro);
    let documentsStale = kind === "run";

    const onEvent = (e: AntidoteEvent) => {
      if (current.current !== mine) return; // a newer run took over
      dispatch({ type: "event", event: e });
      if (documentsStale) {
        // The run starts from a freshly prepared memory: reload the documents' trust.
        documentsStale = false;
        api.state()
          .then((s) => current.current === mine && dispatch({ type: "documents", state: s }))
          .catch(() => undefined);
      }
      if (e.type === "agent_status") {
        const key = WHO[e.data.agent];
        setAgents((a) => ({ ...a, [key]: { state: e.data.state, message: e.data.message, documentId: e.data.document_id } }));
      }
      if (e.type === "gate_verdict") {
        setAgents((a) => ({ ...a, guard: { state: "done", message: `Approval check: ${OUTCOME[e.data.outcome]}.`, documentId: null } }));
      }
      if (e.type === "error") setNotice({ tone: "error", text: e.data.message });
      const entry = describe(e, memoryRef.current);
      if (entry) push(entry);
    };

    try {
      for (let attempt = 0; ; attempt++) {
        try {
          await go(onEvent, mine.controller.signal);
          break;
        } catch (e) {
          // "Skip to result" restarts a run; the previous one needs a moment to let go.
          if (e instanceof ApiFailure && e.code === "busy" && attempt < 30) {
            await wait(250);
            continue;
          }
          throw e;
        }
      }
    } catch (e) {
      if (!mine.controller.signal.aborted) await fail(e);
    } finally {
      if (current.current === mine) {
        current.current = null;
        setRunning(null);
        await settle();
      }
    }
  }, [fail, push, settle]);

  const start = useCallback((mode: RunMode, pace: number) => {
    lastMode.current = mode;
    clearRun();
    dispatch({ type: "reset" });
    const intro: FeedEntry | undefined = pace === 0
      ? { who: "guard", tone: "status", title: "Skipped ahead: replaying the agents' recorded work at full speed." }
      : undefined;
    return stream("run", (onEvent, signal) =>
      api.run({ mode, request: mode === "live" ? requestText : null, pace }, onEvent, signal), intro);
  }, [clearRun, requestText, stream]);

  const replan = useCallback(() => {
    setLastAction(null);
    setImpact(null);
    return stream("replan", (onEvent, signal) => api.replan({ mode: lastMode.current, pace: 1 }, onEvent, signal));
  }, [stream]);

  // --- Actions: each ends by reloading the state ----------------------------------------------

  /** One action: call the API, react to the answer, then reload the state before the
   *  button stops spinning, so the screen never shows a half-updated memory. */
  const act = useCallback(async <T,>(kind: Pending, call: () => Promise<T>, then: (value: T) => void,
                                       after?: () => void) => {
    setPending(kind);
    setNotice(null);
    try {
      then(await call());
    } catch (e) {
      await fail(e);
    } finally {
      await settle();
      after?.();
      setPending(null);
    }
  }, [fail, settle]);

  const title = (id: string) => memoryRef.current.documents[id]?.title ?? id;
  const setAgent = (key: AgentKey, state: AgentView["state"], message: string) =>
    setAgents((a) => ({ ...a, [key]: { state, message, documentId: null } }));

  const previewImpact = useCallback((documentId: string) => act("impact", () => api.impact(documentId), (r) => {
    setImpact(r);
    const facts = r.lost.filter((x) => x.kind === "fact").length;
    push({
      who: "you", tone: "action", title: `You asked what changes if you stop trusting ${title(documentId)}`,
      body: `Simulated on a copy of the memory: ${plural(facts, "fact")} and ${plural(r.orders_blocked.length, "order")} would lose their support. Nothing has changed yet.`,
    });
  }), [act, push]);

  const cancelImpact = useCallback(() => act("cancel", api.cancelImpact, () => setImpact(null)), [act]);

  const quarantine = useCallback(() => act("quarantine", api.quarantine, (r) => {
    dispatch({ type: "distrusted", documents: r.quarantined, withdrawn: r.withdrawn });
    const facts = r.withdrawn.filter((id) => memoryRef.current.facts[id]).length;
    const decisions = r.withdrawn.length - facts;
    const titles = r.quarantined.map(title).join(", ");
    push({
      who: "you", tone: "blocked", title: `You stopped trusting ${titles}`,
      body: `${plural(facts, "fact")} and ${plural(decisions, "decision")} lost their support. FalkorDB recomputed what still holds and recorded the repair.`,
    });
    setAgent("guard", "done", `Withdrew ${plural(r.withdrawn.length, "fact or decision", "facts and decisions")} that rested on ${titles}.`);
  }, () => setImpact(null)), [act, push]);

  const decide = useCallback((orderId: string, action: "approve" | "execute") =>
    act(action, () => api.order(orderId, action), (r) => {
      setLastAction(r);
      dispatch({ type: "orderState", id: orderId, state: r.state });
      const d = memoryRef.current.decisions[orderId];
      const label = d ? orderLabel(d.summary, orderId) : orderId;
      if (r.state === "blocked") {
        push({ who: "guard", tone: "blocked", title: `The approval check blocked ${label}`, body: r.message });
        setAgent("guard", "done", `Blocked ${label}: none of its reasons holds any more.`);
        setAgent("buyer", "waiting", `${label} was blocked. Ask me to re-plan.`);
        return;
      }
      push({ who: "you", tone: "good", title: action === "approve" ? `You approved ${label}` : `You placed ${label}`, body: r.message });
      setAgent("guard", "done", `Checked ${label} again before ${action === "approve" ? "approval" : "placing it"}: every reason holds.`);
      setAgent("buyer", r.state === "executed" ? "done" : "waiting", r.state === "executed" ? `${label} has been placed.` : `${label} is approved, ready to place.`);
    }), [act, push]);

  const startOver = useCallback(() => {
    current.current?.controller.abort();
    current.current = null;
    setRunning(null);
    return act("restart", api.newSession, () => {
      clearRun();
      dispatch({ type: "reset" });
    });
  }, [act, clearRun]);

  // --- Connecting, and noticing when the memory goes away --------------------------------------

  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    void (async () => {
      const h = await api.health().catch(() => null);
      setHealth(h);
      if (h?.falkordb !== "up") {
        setOutage(h?.detail ?? UNREACHABLE);
        return;
      }
      try {
        const s = await connect();
        if (s.has_run) {
          setAgents(restoredAgents(s));
          push({ who: "guard", tone: "status", title: "Welcome back: your session was restored from Antidote's memory." });
        }
        setReady(true);
      } catch (e) {
        await fail(e);
      }
    })();
  }, [connect, fail, push]);

  useEffect(() => {
    if (!outage) return;
    const timer = setInterval(async () => {
      const h = await api.health().catch(() => null);
      if (h?.falkordb !== "up") return;
      setHealth(h);
      setOutage(null);
      try {
        await connect();
        setReady(true);
      } catch (e) {
        await fail(e);
      }
    }, 4000);
    return () => clearInterval(timer);
  }, [outage, connect, fail]);

  useEffect(() => {
    const timer = setInterval(() => {
      api.health()
        .then((h) => {
          setHealth(h);
          if (h.falkordb !== "up") setOutage(h.detail ?? UNREACHABLE);
        })
        .catch(() => setOutage(UNREACHABLE));
    }, 30000);
    return () => clearInterval(timer);
  }, []);

  return {
    health, outage, ready, memory, feed, agents, running, pending, impact, lastAction, notice,
    requestText, setRequestText,
    orders: ordersOf(memory),
    dismissNotice: () => setNotice(null),
    start, replan, previewImpact, cancelImpact, quarantine, decide, startOver,
  };
}

export type Antidote = ReturnType<typeof useAntidote>;
