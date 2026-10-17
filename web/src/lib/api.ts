// web/src/lib/api.ts
// Typed calls to the Antidote API (api/server.py). Every call carries this
// visitor's private session token; the server maps it to the visitor's own graph,
// so the browser never names a graph. Streams are NDJSON: one event per line.
import type {
  Ack, AntidoteEvent, ApiError, DocumentResponse, HealthResponse, ImpactResponse,
  OrderActionResponse, QuarantineResponse, ReplanRequest, RunRequest, SessionResponse,
  StateResponse, WhyResponse,
} from "../contract";

const TOKEN_KEY = "antidote.session";

/** A refused or failed call, with the API's error code ("busy", "memory_unreachable", ...). */
export class ApiFailure extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, detail: string | null) {
    super(detail ?? code);
    this.status = status;
    this.code = code;
  }
}

function loadToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function saveToken(value: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, value);
  } catch {
    // Storage blocked: the session simply lasts as long as this page.
  }
}

let token = loadToken();

async function failure(response: Response): Promise<ApiFailure> {
  let body: Partial<ApiError> = {};
  try {
    body = (await response.json()) as ApiError;
  } catch {
    // Not JSON (a proxy error page, for instance).
  }
  return new ApiFailure(response.status, body.error ?? `http_${response.status}`, body.detail ?? null);
}

async function send(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<Response> {
  const headers: Record<string, string> = {};
  if (token) headers["X-Antidote-Session"] = token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api${path}`, {
    method,
    headers,
    signal,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await failure(response);
  return response;
}

async function json<T>(method: string, path: string, body?: unknown): Promise<T> {
  return (await (await send(method, path, body)).json()) as T;
}

type OnEvent = (event: AntidoteEvent) => void;

async function stream(path: string, body: unknown, onEvent: OnEvent, signal: AbortSignal): Promise<void> {
  const response = await send("POST", path, body, signal);
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    let end: number;
    while ((end = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, end).trim();
      buffer = buffer.slice(end + 1);
      if (line) onEvent(JSON.parse(line) as AntidoteEvent);
    }
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as AntidoteEvent);
}

export const api = {
  hasSession: () => token !== null,

  /** A fresh private memory. Sending the current token drops the old one. */
  async newSession(): Promise<void> {
    token = (await json<SessionResponse>("POST", "/session")).token;
    saveToken(token);
  },

  /** Health answers 503 with the same JSON body when FalkorDB is down. */
  async health(): Promise<HealthResponse> {
    const response = await fetch("/api/health");
    return (await response.json()) as HealthResponse;
  },

  state: () => json<StateResponse>("GET", "/state"),
  document: (id: string) => json<DocumentResponse>("GET", `/documents/${encodeURIComponent(id)}`),
  why: (id: string) => json<WhyResponse>("GET", `/why/${encodeURIComponent(id)}`),
  impact: (documentId: string) => json<ImpactResponse>("POST", "/impact", { document_id: documentId }),
  cancelImpact: () => json<Ack>("POST", "/impact/cancel"),
  quarantine: () => json<QuarantineResponse>("POST", "/quarantine"),
  order: (id: string, action: "approve" | "execute") =>
    json<OrderActionResponse>("POST", `/orders/${encodeURIComponent(id)}/${action}`),
  run: (body: RunRequest, onEvent: OnEvent, signal: AbortSignal) => stream("/run", body, onEvent, signal),
  replan: (body: ReplanRequest, onEvent: OnEvent, signal: AbortSignal) =>
    stream("/replan", body, onEvent, signal),
};
