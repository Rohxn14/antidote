# api/server.py
"""The web API: a thin layer over Antidote's tested modules.

    uvicorn api.server:app --reload        # http://localhost:8000

Every /api/* endpoint needs FalkorDB. When it is unreachable they all answer
503 {"error": "memory_unreachable"}: the product fails closed and there is no
in-memory fallback. The web app itself is static files and loads without
FalkorDB, so it can show the outage screen; /api/health answers 503 with a
HealthResponse body that the web app reads.

Requests and responses follow api/contract.py. Streams are NDJSON: one
contract event per line.
"""
import logging
import os
import re
import threading
import time
from typing import Literal

import redis
from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter
from redis.backoff import NoBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.retry import Retry

from api import contract as c
from api.session_store import Session, SessionStore
from app import demo, evidence, gate, llm, memory, repair, runner, views
from app.agents.buyer import order_label
from app.casebuilder import CaseScript
from app.db import ROOT, connection_settings, drop_graph, get_db
from app.config import AUTO_MAX_AMOUNT
from app.schema import (ABOUT, AGENT, AUTHORED, DECISION, HOLDS, INFERENCE, JUSTIFICATION,
                        SUPPORTS, VALID, VENDOR)

log = logging.getLogger("antidote")
EVENTS = TypeAdapter(c.Event)
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
WEB = ROOT / "web" / "dist"
DATA = (ROOT / "data").resolve()
EMPTY_SUMMARY = {"facts": 0, "refused": 0, "decisions": 0, "alerts": 0}


# --- Failing closed ---------------------------------------------------------------------

class ApiFailure(Exception):
    def __init__(self, status: int, error: str, detail: str | None = None):
        self.status, self.error, self.detail = status, error, detail


def public_detail(e: Exception) -> str:
    """What visitors may see about a lost connection: the error type only.
    The full message names the database host, so it goes to the server log."""
    log.warning("FalkorDB unreachable: %s: %s", type(e).__name__, e)
    return f"{type(e).__name__}: the memory database cannot be reached"


class MemoryProbe:
    """Is FalkorDB reachable? A separate, fast-failing client (2 s, no retries),
    checked at most every `ttl` seconds."""

    def __init__(self, client=None, ttl: float = 2.0):
        self.client = client or redis.Redis(
            **connection_settings(),
            socket_connect_timeout=2, socket_timeout=2, retry=Retry(NoBackoff(), 0))
        self.ttl, self.checked, self.ok, self.detail = ttl, 0.0, False, None

    def up(self, force: bool = False) -> bool:
        if force or time.time() - self.checked > self.ttl:
            try:
                self.client.ping()
                self.ok, self.detail = True, None
            except Exception as e:  # any failure means: no memory
                self.ok, self.detail = False, public_detail(e)
            self.checked = time.time()
        return self.ok

    def used(self) -> str | None:
        try:
            return self.client.info("memory").get("used_memory_human")
        except Exception:  # some hosted servers do not allow INFO
            return None

    def used_bytes(self) -> int | None:
        try:
            return int(self.client.info("memory").get("used_memory"))
        except Exception:
            return None


def require_memory(request: Request) -> None:
    probe: MemoryProbe = request.app.state.memory
    if not probe.up():
        raise ApiFailure(503, "memory_unreachable", probe.detail)


def current(request: Request, x_antidote_session: str | None = Header(default=None)) -> Session:
    session = request.app.state.store.get(x_antidote_session)
    if session is None:
        raise ApiFailure(401, "session_expired", "start a new session")
    return session


def graph_of(session: Session):
    return get_db().select_graph(session.graph_name)


def live_ai() -> bool:
    """Live AI is optional: it needs a key, and ANTIDOTE_LIVE_AI=off disables it."""
    return llm.configured() and os.getenv("ANTIDOTE_LIVE_AI", "on").lower() != "off"


# --- Streams ------------------------------------------------------------------------------

def _line(seq: int, ev: dict) -> str:
    """One contract event as one NDJSON line (validated on the way out)."""
    return EVENTS.validate_python({"type": ev["type"], "seq": seq, "data": ev["data"]}
                                  ).model_dump_json() + "\n"


def _stream(lines) -> StreamingResponse:
    return StreamingResponse(lines, media_type="application/x-ndjson", headers=STREAM_HEADERS)


def _plain(e: Exception) -> str:
    if isinstance(e, (RedisConnectionError, RedisTimeoutError)):
        return "Antidote's memory (FalkorDB) is unreachable."
    return f"{type(e).__name__}: {e}"


def _session_stream(session: Session, events, on_complete=None) -> StreamingResponse:
    def produce():
        seq = 0
        session.busy = True
        try:
            for ev in events():
                if ev["type"] == "security_alert":
                    session.alerts.append(ev["data"])
                if ev["type"] == "run_complete" and on_complete:
                    on_complete()
                seq += 1
                yield _line(seq, ev)
        except Exception as e:  # reported to the client as an `error` event
            seq += 1
            yield _line(seq, {"type": "error", "data": {"message": _plain(e), "recoverable": True}})
        finally:
            session.busy = False
    return _stream(produce())


# --- State ---------------------------------------------------------------------------------

REASONS = f"""
MATCH (j:{JUSTIFICATION})
OPTIONAL MATCH (a:{AGENT})-[:{AUTHORED}]->(j)
RETURN j.id, j.kind, coalesce(j.{HOLDS}, false), a.id, j.quote
ORDER BY j.id
"""
DECISIONS = f"""
MATCH (d:{DECISION})
OPTIONAL MATCH (d)-[:{ABOUT}]->(v:{VENDOR})
OPTIONAL MATCH (j:{JUSTIFICATION})-[:{SUPPORTS}]->(d)
RETURN d.id, d.kind, d.summary, d.amount, d.state, coalesce(d.{VALID}, false), v.id,
       d.note, d.approved_by, collect(j.reasoning)
ORDER BY d.id
"""
OPEN_ORDER_STATES = ("draft", "pending_approval", "authorized")


def under_review(session: Session) -> list[str]:
    """Documents the security scan flagged: orders resting on them wait for a person."""
    return [a["document_id"] for a in session.alerts]


def unverified(g, decision_id: str, amount, strength: dict) -> list[str]:
    """What the verification hold (gate.approve) will wait for, from the cached evidence
    levels: the order's conclusions that hold only because unverified documents say so."""
    if amount is None or amount < AUTO_MAX_AMOUNT:
        return []
    rows = g.ro_query(gate.CONCLUSIONS_OF, {"id": decision_id, "inference": INFERENCE}).result_set
    return [claim for i, claim in rows if (strength.get(i) or {}).get("level") == "unverified only"]


def script_for(session: Session, mode: str, request_text: str | None = None):
    """Where this session's documents and agents' answers come from."""
    if session.case:
        return CaseScript(session.case)
    text = (request_text or "").strip()[:runner.MAX_REQUEST]
    return runner.StoryScript(mode, text or runner.DEFAULT_REQUEST)
VENDORS = f"MATCH (v:{VENDOR}) RETURN v.id, v.name ORDER BY v.name"
DOC_KIND = {runner.REQUEST_ID: "request", "s_registry": "registry"}


def _doc_kind(source_id: str) -> str:
    return DOC_KIND.get(source_id, "vendor" if source_id.endswith("_page") else "other")


def _doc_vendor(source_id: str) -> str | None:
    match = re.fullmatch(r"s_(\w+?)_page", source_id)
    return f"v_{match.group(1)}" if match else None


def _strength(g, session: Session) -> dict:
    """Evidence strength, cached per revision (it runs what-ifs on a graph copy)."""
    revision = memory.revision(g)
    if not session.evidence or session.evidence[0] != revision:
        session.evidence = (revision, evidence.strength(g))
    return session.evidence[1]


def build_state(g, session: Session) -> c.StateResponse:
    strength = _strength(g, session)
    level = lambda i: (strength.get(i) or {}).get("level")  # noqa: E731
    facts = [c.Fact(id=n["id"], text=n["text"] or n["id"], supported=bool(n["ok"]),
                    evidence=level(n["id"]),
                    weak_origin=(strength.get(n["id"]) or {}).get("weak_origin"),
                    vendor_id=(n["vendors"] or [None])[0])
             for n in views.nodes(g) if n["label"] == "Belief"]
    edges = [c.Edge(from_id=x, to_id=j, kind="premise") if rel == "PREMISE"
             else c.Edge(from_id=j, to_id=x, kind="supports")
             for j, rel, x in views.edges(g)]
    return c.StateResponse(
        revision=memory.revision(g),
        has_run=session.has_run,
        request=c.RequestInfo(text=session.request, editable=live_ai()),
        vendors=[c.Vendor(id=i, name=n) for i, n in g.ro_query(VENDORS).result_set],
        documents=[c.Document(id=s["id"], title=s["title"], kind=_doc_kind(s["id"]),
                              trust=s["trust"], origin=s["origin"], supported=bool(s["valid"]),
                              vendor_id=_doc_vendor(s["id"])) for s in views.sources(g)],
        facts=facts,
        reasons=[c.Reason(id=i, kind=k, holds=bool(h), author=runner.AGENTS.get(a), quote=q)
                 for i, k, h, a, q in g.ro_query(REASONS).result_set],
        decisions=[c.Decision(id=i, kind=k, summary=s, amount=amt, state=st, supported=bool(ok),
                              evidence=level(i), vendor_id=v, note=note, approved_by=by,
                              reasoning=next((r for r in why if r), None),
                              held_by=[h["id"] for h in gate.held_by(g, i, under_review(session))]
                              if st in OPEN_ORDER_STATES else [],
                              needs_verification=unverified(g, i, amt, strength) if st in OPEN_ORDER_STATES else [])
                   for i, k, s, amt, st, ok, v, note, by, why in g.ro_query(DECISIONS).result_set],
        edges=edges,
        alerts=[c.Alert(**a) for a in session.alerts],
        repairs=[c.RepairRecord(id=r["id"], approved_by=r["approved_by"], revision=r["revision"],
                                documents=r["titles"], withdrawn=r["changed"])
                 for r in views.repairs(g)],
        case=c.CaseSpec(**session.case) if session.case else None)


# --- Documents ---------------------------------------------------------------------------

HIDDEN_PART = re.compile(
    r"<!--(.*?)-->|<(\w+)[^>]*?style\s*=\s*\"[^\"]*(?:display\s*:\s*none|visibility\s*:\s*hidden"
    r"|font-size\s*:\s*0|opacity\s*:\s*0)[^\"]*\"[^>]*>(.*?)</\2>", re.DOTALL | re.IGNORECASE)
BLOCK_END = re.compile(r"</(?:p|h\d|li|tr|div|section|header|footer|title|table)>|<br\s*/?>",
                       re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")


def _lines(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def _visible(fragment: str) -> str:
    return _lines(TAG.sub(" ", BLOCK_END.sub("\n", fragment)))


def segments(raw: str, is_html: bool) -> list[c.Segment]:
    """The document as an agent reads it, with the parts a person can't see marked."""
    if not is_html:
        return [c.Segment(text=raw.strip(), hidden=False, kind="visible")]
    out, pos = [], 0
    for m in HIDDEN_PART.finditer(raw):
        before = _visible(raw[pos:m.start()])
        if before:
            out.append(c.Segment(text=before, hidden=False, kind="visible"))
        if m.group(1) is not None:
            out.append(c.Segment(text=_lines(m.group(1)), hidden=True, kind="comment"))
        else:
            out.append(c.Segment(text=_visible(m.group(3)), hidden=True, kind="hidden_element"))
        pos = m.end()
    tail = _visible(raw[pos:])
    if tail:
        out.append(c.Segment(text=tail, hidden=False, kind="visible"))
    return out


# --- Messages ------------------------------------------------------------------------------

def order_message(v: gate.Verdict, action: str, held: list[dict] = ()) -> str:
    label = order_label(v.decision_id)
    if v.outcome == gate.HELD and held:
        titles = " and ".join(h["title"] for h in held)
        return (f"{label} is on hold: it rests on {titles}, which the security scan flagged "
                f"for hidden instructions. Deal with the alert first: if you stop trusting the "
                f"document, the Buyer can re-plan without it.")
    if v.outcome == gate.HELD:
        return (f"{label} is on hold until a trusted document confirms what it rests on. "
                f"{' '.join(r[0].upper() + r[1:] + '.' for r in v.reasons)} If you don't believe "
                f"the supplier's own page, stop trusting it and the Buyer will re-plan.")
    if v.state == "blocked":
        return (f"Blocked: {label} has no supported reason left. An approval cannot "
                "override missing support.")
    if v.state == "pending_approval":
        return f"{label} needs a person's approval: {'; '.join(v.reasons)}."
    if v.state == "authorized":
        return f"{label} is approved and ready to place."
    return f"{label} has been placed."


# --- Routes ---------------------------------------------------------------------------------

router = APIRouter(prefix="/api")


@router.post("/session", response_model=c.SessionResponse)
def new_session(request: Request, x_antidote_session: str | None = Header(default=None)):
    """A fresh private memory. Sending the current token starts over."""
    store: SessionStore = request.app.state.store
    if x_antidote_session and store.get(x_antidote_session):
        store.drop(x_antidote_session)
    token = store.create(lambda g: runner.prepare(g, runner.DEFAULT_REQUEST),
                         runner.DEFAULT_REQUEST)
    return c.SessionResponse(token=token)


@router.get("/state", response_model=c.StateResponse)
def state(session: Session = Depends(current)):
    return build_state(graph_of(session), session)


@router.get("/documents/{document_id}", response_model=c.DocumentResponse)
def document(document_id: str, session: Session = Depends(current)):
    g = graph_of(session)
    rows = g.ro_query("MATCH (s:Source {id: $id}) RETURN s.title, s.trust, s.uri, s.text",
                      {"id": document_id}).result_set
    if not rows:
        raise ApiFailure(404, "not_found", f"no document {document_id!r}")
    title, trust, uri, text = rows[0]
    html = None
    if text is None and uri:
        path = (ROOT / uri).resolve()
        if path.is_relative_to(DATA) and path.is_file():
            text = path.read_text(encoding="utf-8")
            html = text if path.suffix == ".html" else None
    elif text and text.lstrip().lower().startswith("<!doctype html"):
        html = text  # a page written by the case builder
    return c.DocumentResponse(id=document_id, title=title, kind=_doc_kind(document_id),
                              trust=trust, segments=segments(text or "", html is not None),
                              html=html)


@router.post("/run")
def run(body: c.RunRequest, session: Session = Depends(current)):
    if session.busy:
        raise ApiFailure(409, "busy", "the agents are already working")
    if body.mode == "live" and session.case:
        raise ApiFailure(400, "case_without_ai", "A case you build runs without AI: use the recorded agents")
    if body.mode == "live" and not live_ai():
        raise ApiFailure(400, "live_ai_unavailable", "Live AI is switched off on this server")
    script = script_for(session, body.mode, body.request if body.mode == "live" else None)
    g = graph_of(session)

    def events():
        if session.preview is not None:
            repair.discard(session.preview)
        session.preview, session.alerts, session.has_run = None, [], False
        session.request = script.request_text
        runner.prepare(g, script)
        yield from runner.run(g, body.mode, body.pace, script)

    return _session_stream(session, events, on_complete=lambda: setattr(session, "has_run", True))


@router.post("/replan")
def replan(body: c.ReplanRequest, session: Session = Depends(current)):
    if session.busy:
        raise ApiFailure(409, "busy", "the agents are already working")
    if body.mode == "live" and not live_ai():
        raise ApiFailure(400, "live_ai_unavailable", "Live AI is switched off on this server")
    g = graph_of(session)
    script = script_for(session, body.mode, session.request)
    return _session_stream(session, lambda: runner.replan(g, body.mode, body.pace, script))


@router.post("/case", response_model=c.Ack)
def set_case(body: c.CaseRequest, session: Session = Depends(current)):
    """Switch this session to a case the visitor built, or back to the demo story
    (case = null). The memory starts afresh with the case's documents."""
    if session.busy:
        raise ApiFailure(409, "busy", "the agents are already working")
    if session.preview is not None:
        repair.discard(session.preview)
    session.case = body.case.model_dump() if body.case else None
    script = script_for(session, "replay")
    session.preview, session.alerts, session.has_run = None, [], False
    session.request = script.request_text
    runner.prepare(graph_of(session), script)
    return c.Ack(ok=True)


@router.post("/impact", response_model=c.ImpactResponse)
def impact(body: c.ImpactRequest, session: Session = Depends(current)):
    if session.busy:
        raise ApiFailure(409, "busy", "wait until the agents finish")
    g = graph_of(session)
    if session.preview is not None:
        repair.discard(session.preview)
        session.preview = None
    try:
        p = repair.preview(g, body.document_id)
    except ValueError as e:
        raise ApiFailure(400, "cannot_preview", str(e))
    session.preview = p
    item = lambda n: c.ImpactItem(id=n["id"], text=n["text"],  # noqa: E731
                                  kind="fact" if n["label"] == "Belief" else "decision")
    return c.ImpactResponse(
        document_id=body.document_id, also_quarantined=p.sources[1:],
        lost=[item(n) for n in p.lost],
        survived=[c.Survivor(id=s["id"], text=s["text"], kept_by=s["kept_by"],
                             premises=s["premises"]) for s in p.survived],
        orders_blocked=[item(n) for n in p.orders_blocked],
        executed_affected=[item(n) for n in p.executed_affected],
        base_revision=p.base_revision)


@router.post("/impact/cancel", response_model=c.Ack)
def cancel_impact(session: Session = Depends(current)):
    if session.preview is not None:
        repair.discard(session.preview)
        session.preview = None
    return c.Ack(ok=True)


@router.post("/quarantine", response_model=c.QuarantineResponse)
def quarantine(session: Session = Depends(current)):
    p = session.preview
    if p is None:
        raise ApiFailure(409, "no_preview", "preview the impact first")
    g = graph_of(session)
    try:
        repair_id = repair.apply(g, p, approved_by=demo.MANAGER)
    except repair.StalePreview as e:
        raise ApiFailure(409, "stale_preview", str(e))
    finally:
        session.preview = None
    # The preview listed the open orders that lose their support: block them now, with
    # the reason, rather than waiting for someone to try to approve or place them.
    blocked = [o["id"] for o in p.orders_blocked if gate.recheck(g, o["id"]).state == "blocked"]
    return c.QuarantineResponse(repair_id=repair_id, quarantined=p.sources,
                                withdrawn=[n["id"] for n in p.lost], orders_blocked=blocked)


@router.post("/orders/{order_id}/{action}", response_model=c.OrderActionResponse)
def order_action(order_id: str, action: Literal["approve", "execute"],
                 session: Session = Depends(current)):
    g = graph_of(session)
    review = under_review(session)
    try:
        v = (gate.approve(g, order_id, approver=demo.MANAGER, under_review=review)
             if action == "approve" else gate.execute(g, order_id, under_review=review))
    except gate.GateError as e:
        raise ApiFailure(409, "wrong_state", str(e))
    held = gate.held_by(g, order_id, review) if v.outcome == gate.HELD else []
    return c.OrderActionResponse(decision_id=order_id, action=action, outcome=v.outcome,
                                 state=v.state, reasons=v.reasons,
                                 message=order_message(v, action, held))


WHY_KIND = {"Source": "document", "Belief": "fact", "Decision": "decision"}


def _why_node(t: dict, strength: dict) -> c.WhyNode:
    return c.WhyNode(
        id=t["id"], kind=WHY_KIND.get(t.get("label"), "fact"), text=t.get("text") or t["id"],
        supported=bool(t.get("ok")), evidence=(strength.get(t["id"]) or {}).get("level"),
        trust=t.get("trust") if t.get("label") == "Source" else None, loop=bool(t.get("cut")),
        reasons=[c.WhyReason(id=j["id"], kind=j["kind"], holds=bool(j["holds"]),
                             author=j.get("author"), reasoning=j.get("reasoning"),
                             quote=j.get("quote"),
                             premises=[_why_node(p, strength) for p in j["premises"]])
                 for j in t.get("justifications", [])])


@router.get("/why/{node_id}", response_model=c.WhyResponse)
def why(node_id: str, session: Session = Depends(current)):
    g = graph_of(session)
    tree = views.why(g, node_id)
    if not tree.get("label"):
        raise ApiFailure(404, "not_found", f"nothing called {node_id!r}")
    return c.WhyResponse(root=_why_node(tree, _strength(g, session)))


@router.get("/cypher", response_model=c.CypherResponse)
def cypher():
    from scripts.export_cypher import SECTIONS
    return c.CypherResponse(sections=[
        c.CypherSection(title=title, intro=intro,
                        queries=[c.CypherQuery(name=n, cypher=q.strip()) for n, q in queries.items()])
        for title, intro, queries in SECTIONS])


@router.get("/benchmark", response_model=c.BenchmarkResponse)
def benchmark():
    rows = []
    for line in (ROOT / "docs" / "benchmark.md").read_text(encoding="utf-8").splitlines():
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[3].isdigit():    # scenario, graph, method, residual, ...
            rows.append(c.BenchmarkRow(scenario=cells[0], method=cells[2], residual=int(cells[3]),
                                       collateral=int(cells[4]), stale=int(cells[5]),
                                       ms=float(cells[6])))
        elif len(cells) == 6 and cells[3].isdigit():  # test set, method, exact, residual, ...
            rows.append(c.BenchmarkRow(scenario=cells[0], method=cells[1], residual=int(cells[3]),
                                       collateral=int(cells[4]), stale=None, ms=float(cells[5])))
    return c.BenchmarkResponse(rows=rows)


class Walkthrough:
    """The capability walkthrough seeds a scratch graph, so it is rationed: one at a
    time, a pause between runs, and leftovers of an interrupted run are deleted
    before the next one starts (none can be in use then)."""

    SCRATCH = "antidote_centrality_"

    def __init__(self, gap_s: float = 10.0, stale_s: float = 180.0):
        self.gap_s, self.stale_s = gap_s, stale_s
        self.lock = threading.Lock()
        self.running_since: float | None = None
        self.last_start = 0.0

    def start(self) -> None:
        with self.lock:
            now = time.time()
            if self.running_since is not None and now - self.running_since < self.stale_s:
                raise ApiFailure(429, "busy", "The walkthrough is already running. Try again in a few seconds.")
            if now - self.last_start < self.gap_s:
                raise ApiFailure(429, "too_soon", "The walkthrough just ran. Try again in a few seconds.")
            self.running_since = self.last_start = now
        for name in get_db().list_graphs():
            if name.startswith(self.SCRATCH):
                drop_graph(name)

    def finish(self) -> None:
        with self.lock:
            self.running_since = None


@router.post("/capabilities")
def capabilities(request: Request, without: bool = False):
    """The capability walkthrough: each capability through the real code, with the
    Cypher FalkorDB executed. `without=true` runs it with no server behind the graph."""
    try:
        from app import centrality
    except ModuleNotFoundError:
        raise ApiFailure(501, "not_ready", "app/centrality.py has not been written yet")
    # Only the real run is rationed: without FalkorDB nothing is written anywhere.
    walkthrough: Walkthrough | None = None if without else request.app.state.walkthrough
    if walkthrough:
        walkthrough.start()

    def produce():
        seq = 0
        try:
            for result in centrality.run(with_falkordb=not without):
                seq += 1
                yield _line(seq, {"type": "capability_result", "data": result})
            seq += 1
            yield _line(seq, {"type": "run_complete",
                              "data": {"revision": 0, "summary": EMPTY_SUMMARY}})
        except Exception as e:
            seq += 1
            yield _line(seq, {"type": "error", "data": {"message": _plain(e), "recoverable": True}})
        finally:
            if walkthrough:
                walkthrough.finish()
    return _stream(produce())


@router.get("/stream-test")
def stream_test():
    """Eight events 0.4 s apart: used to check that hosting does not buffer streams."""
    def produce():
        for i in range(1, 9):
            yield _line(i, runner.status("system", f"tick {i} of 8"))
            time.sleep(0.4)
        yield _line(9, {"type": "run_complete", "data": {"revision": 0, "summary": EMPTY_SUMMARY}})
    return _stream(produce())


PLACEHOLDER = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Antidote</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 16px;
color:#0f172a;background:#f8fafc}code,pre{background:#e2e8f0;padding:2px 6px;border-radius:6px}
pre{padding:12px;white-space:pre-wrap}</style></head><body>
<h1>Antidote</h1><p>The new interface is being built. This page checks the server.</p>
<p>Memory (FalkorDB): <code id="health">checking…</code></p>
<p><button id="go">Test streaming</button></p><pre id="out"></pre>
<script>
fetch('/api/health').then(r=>r.json()).then(h=>{document.getElementById('health').textContent=
 h.falkordb+(h.memory&&h.memory.used?' ('+h.memory.used+' used)':'')}).catch(e=>{
 document.getElementById('health').textContent='unreachable'});
document.getElementById('go').onclick=async()=>{const out=document.getElementById('out');
 out.textContent='';const t0=performance.now();const r=await fetch('/api/stream-test');
 const reader=r.body.getReader();const dec=new TextDecoder();
 for(;;){const {done,value}=await reader.read();if(done)break;
  out.textContent+=((performance.now()-t0)/1000).toFixed(1)+'s  '+dec.decode(value);}};
</script></body></html>"""


def create_app(store: SessionStore | None = None, memory_probe: MemoryProbe | None = None,
               walkthrough: Walkthrough | None = None) -> FastAPI:
    app = FastAPI(title="Antidote API", version="1.0",
                  description="Graph-native recovery for multi-agent memory, on FalkorDB.")
    app.state.memory = memory_probe or MemoryProbe()
    app.state.store = store or SessionStore(memory_used=app.state.memory.used_bytes)
    app.state.walkthrough = walkthrough or Walkthrough()

    @app.exception_handler(ApiFailure)
    def _failure(request: Request, e: ApiFailure):
        return JSONResponse(status_code=e.status, content=c.ApiError(
            error=e.error, detail=e.detail).model_dump())

    @app.exception_handler(RedisConnectionError)
    @app.exception_handler(RedisTimeoutError)
    def _memory_lost(request: Request, e: Exception):
        return JSONResponse(status_code=503, content=c.ApiError(
            error="memory_unreachable", detail=public_detail(e)).model_dump())

    @app.get("/api/health", response_model=c.HealthResponse)
    def health(request: Request):
        probe: MemoryProbe = request.app.state.memory
        store: SessionStore = request.app.state.store
        up = probe.up(force=True)
        body = c.HealthResponse(
            falkordb="up" if up else "down", detail=probe.detail,
            memory=c.MemoryUse(used=probe.used(), graphs=len(get_db().list_graphs())) if up else None,
            live_ai=live_ai(), model=llm.model_name() if live_ai() else None,
            sessions=store.count(), session_cap=store.cap)
        return body if up else JSONResponse(status_code=503, content=body.model_dump())

    app.include_router(router, dependencies=[Depends(require_memory)])

    if (WEB / "index.html").exists():
        app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    else:
        @app.get("/", response_class=HTMLResponse)
        def placeholder():
            return PLACEHOLDER
    return app


app = create_app()
