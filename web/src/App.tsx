// Skeleton page (step 3): checks the server and that streams arrive incrementally.
// Replaced by the real interface in step 4.
import { useEffect, useState } from "react";
import type { AntidoteEvent, HealthResponse } from "./contract";

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [lines, setLines] = useState<string[]>([]);

  useEffect(() => {
    fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => setHealth(null));
  }, []);

  async function testStream() {
    setLines([]);
    const started = performance.now();
    const response = await fetch("/api/stream-test");
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n");
      buffer = parts.pop() ?? "";
      for (const part of parts.filter(Boolean)) {
        const event = JSON.parse(part) as AntidoteEvent;
        const seconds = ((performance.now() - started) / 1000).toFixed(1);
        setLines((l) => [...l, `${seconds}s  #${event.seq} ${event.type}`]);
      }
    }
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Antidote</h1>
      <p className="mt-2 text-slate-600">The new interface is on its way. This page checks the server.</p>
      <p className="mt-6">
        Memory (FalkorDB):{" "}
        <span className={health?.falkordb === "up" ? "font-medium text-emerald-700" : "font-medium text-rose-700"}>
          {health ? health.falkordb : "unreachable"}
        </span>
        {health?.memory?.used ? <span className="text-slate-500"> · {health.memory.used} used</span> : null}
      </p>
      <button
        onClick={testStream}
        className="mt-6 rounded-lg bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-700"
      >
        Test streaming
      </button>
      <pre className="mt-4 rounded-lg bg-white p-4 text-sm shadow-sm ring-1 ring-slate-200">{lines.join("\n")}</pre>
    </main>
  );
}
