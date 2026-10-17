# ui/streamlit_app.py
"""Antidote demo UI. Run from the repo root:

    streamlit run ui/streamlit_app.py

Every action calls the same tested functions as the terminal story
(app/demo.py, app/repair.py, app/gate.py); this file only renders.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from mcp import Client  # noqa: E402

from app import demo, detector, gate, llm, memory, repair, sessions, support, views  # noqa: E402
from app.agents import buyer, tool_agent  # noqa: E402
from app.mcp_server import create_server  # noqa: E402
from app.agents.buyer import order_label  # noqa: E402
from app.config import AUTO_MAX_AMOUNT, MIN_INDEPENDENT_TRUSTED_ROOTS  # noqa: E402
from app.db import ROOT, drop_graph, get_db  # noqa: E402
from app.schema import (AUTHORIZED, BLOCKED, DRAFT, EXECUTED, PENDING_APPROVAL,  # noqa: E402
                        PURCHASE_ORDER, QUARANTINED)
from ui import render  # noqa: E402

st.set_page_config(page_title="Antidote", page_icon="🧪", layout="wide")
ss = st.session_state
VENDOR_NAMES = dict(demo.VENDORS)


# --- A private graph per visitor ---------------------------------------------------

@st.cache_resource(show_spinner="Seeding the demo memory in FalkorDB…")
def _template_ready() -> str:
    return sessions.seed_template().name


def session_graph():
    _template_ready()
    if ss.get("graph_name") not in get_db().list_graphs():
        ss.graph_name = sessions.new_session_graph().name
        ss.pop("preview", None)
        ss.pop("findings", None)
    return get_db().select_graph(ss.graph_name)


g = session_graph()


# --- Actions (each calls tested code, then reruns the page) -------------------------

def flash(kind: str, text: str) -> None:
    ss.setdefault("flash", []).append((kind, text))


def run(action, *args) -> None:
    try:
        action(*args)
    except Exception as e:  # show the problem instead of crashing the demo
        flash("error", f"{type(e).__name__}: {e}")
    st.rerun()


def md(text) -> str:
    return str(text or "").replace("$", "\\$")


def reasons(v) -> str:
    return "; ".join(v.reasons)


def act_scan() -> None:
    ss.findings = detector.scan_sources(g)
    sources = {f.source_id for f in ss.findings}
    flash("info", f"Detector found {len(ss.findings)} injection signs in "
                  f"{len(sources)} source(s). It only proposes; a human decides.")


def discard_preview() -> None:
    p = ss.pop("preview", None)
    if p:
        repair.discard(p)


def act_preview(source_id: str, reported: str | None = None) -> None:
    discard_preview()
    if reported:
        ss.setdefault("findings", []).append(detector.report(source_id, reported))
    ss.preview = repair.preview(g, source_id)


def act_apply() -> None:
    p = ss.preview
    try:
        repair_id = repair.apply(g, p, approved_by=demo.MANAGER)
    except repair.StalePreview as e:
        ss.preview = repair.preview(g, p.source_id)
        flash("warning", f"{e}. Showing a fresh preview: review it and approve again.")
        return
    ss.pop("preview")
    flash("success", f"Repair applied and verified against the preview ({repair_id}). "
                     "Memory changed; no purchase was approved.")


def act_order(order_id: str, action: str) -> None:
    if action == "approve":
        v = gate.approve(g, order_id, approver=demo.MANAGER)
    else:
        v = {"submit": gate.submit, "execute": gate.execute}[action](g, order_id)
    label = order_label(order_id)
    if v.state == BLOCKED:
        flash("error", f"🛑 The gate blocked {label}: {reasons(v)}. "
                       "A human approval cannot override missing support.")
    elif v.state == PENDING_APPROVAL:
        flash("warning", f"⏸ {label} waits for a human approval: {reasons(v)}.")
    else:
        flash("success", f"✅ {label} is now {v.state}." + (f" ({reasons(v)})" if v.reasons else ""))


def act_redecide() -> None:
    if ss.get("live") and llm.configured():
        result = buyer.record_plan(g, buyer.decide(g))
    else:
        result = demo.redecide(g)
    for note in result["rejected"]:
        flash("warning", f"Rejected: {note}")
    if result["order"]:
        v = result["verdict"]
        flash("info", f"The Buyer drafted {order_label(result['order'])} on clean memory. "
                      f"Gate: {v.outcome} ({reasons(v)}) → {v.state}.")


def reset_session() -> None:
    discard_preview()
    for name in get_db().list_graphs():
        if name.startswith(ss.graph_name):
            drop_graph(name)
    for key in ("graph_name", "findings", "flash"):
        ss.pop(key, None)


# --- Read the current state once per run ---------------------------------------------

nodes, edges = views.nodes(g), views.edges(g)
decisions = views.decisions(g)
orders = [d for d in decisions if d["kind"] == PURCHASE_ORDER]
by_decision = {d["id"]: d for d in decisions}
sources = views.sources(g)
by_source = {s["id"]: s for s in sources}
preview = ss.get("preview")


# --- Sidebar -------------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🧪 Antidote")
    st.caption("A graph-native recovery layer for multi-agent memory, built on FalkorDB.")
    st.caption(f"Your private copy of the demo memory: `{g.name}`")
    if st.button("↺ Reset my demo", width="stretch"):
        run(reset_session)
    st.divider()
    st.markdown("**Agents**")
    if llm.configured():
        ss.live = st.toggle(f"Buyer uses the live LLM ({llm.model_name()})", value=ss.get("live", False))
    else:
        st.caption("Replaying recorded agent outputs: the same structured JSON the "
                   "Researcher and Buyer produce, checked by the same code.")
    st.markdown("**Stakes policy** (demo values)")
    st.caption(f"An order proceeds automatically only if it is supported, reversible, under "
               f"${AUTO_MAX_AMOUNT:,}, and still supported after losing any "
               f"{MIN_INDEPENDENT_TRUSTED_ROOTS - 1} trusted origin. Otherwise a human approves; "
               "an unsupported order is always blocked.")


# --- Header --------------------------------------------------------------------------------

st.title("🧪 Antidote")
st.markdown("When a source turns out to be poisoned, Antidote recomputes **what the agents' "
            "shared memory may still believe**, previews the blast radius on a copy of the "
            "graph, and **blocks actions that lost their justification**, while keeping "
            "knowledge that is independently supported.")
for kind, text in ss.pop("flash", []):
    getattr(st, kind)(text)

counts = views.counts(g)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Graph revision", memory.revision(g))
for col, label in ((c2, "Belief"), (c3, "Decision")):
    ok, bad = counts.get((label, True), 0), counts.get((label, False), 0)
    col.metric(f"{label}s supported", f"{ok} / {ok + bad}")
c4.metric("Purchase orders", " · ".join(f"{order_label(o['id'])} {o['state']}" for o in orders) or "none")

left, right = st.columns([3, 2], gap="large")


# --- Left: the memory graph -----------------------------------------------------------

with left:
    st.markdown("#### Shared memory")
    chosen = st.multiselect("Vendors to show", list(VENDOR_NAMES), default=["v_vantor"],
                            format_func=VENDOR_NAMES.get,
                            help="Requirements and the evidence behind each shown "
                                 "conclusion are always included. Empty = everything.")
    keep = render.visible_ids(nodes, edges, set(chosen) or None)
    flips = {n["id"] for n in preview.lost} if preview else set()
    st.graphviz_chart(render.graph_dot(nodes, edges, keep, flips, ss.get("why_id")),
                      width="stretch")
    st.caption("🟩 supported · 🟥 not supported · 🟨 would lose support (preview) · "
               "circles are reasons (E extraction, I inference, D decision): "
               "all premises in → one conclusion out · green border = trusted source")


# --- Right: the story -------------------------------------------------------------------

with right:
    st.markdown("#### The story")
    po1, po2 = by_decision.get(demo.FIRST_ORDER), by_decision.get(demo.SECOND_ORDER)
    quarantined = by_source.get(demo.POISONED, {}).get("trust") == QUARANTINED
    push_po1 = {DRAFT: ("Submit PO-1001", "submit"), PENDING_APPROVAL: ("Approve PO-1001", "approve"),
                AUTHORIZED: ("Execute PO-1001", "execute")}.get(po1["state"] if po1 else None)
    steps = [
        ("**Normal work.** The Researcher read 6 sources; the Buyer shortlisted 3 vendors and "
         "drafted **PO-1001**: 100 servo actuators from Vantor Motion, \\$48,000. The gate holds "
         "it for a human: the amount is at or above \\$5,000.", True, None),
        ("**Detect.** Scan the sources for signs of prompt injection.",
         ss.get("findings") is not None or quarantined, ("Scan sources", act_scan)),
        ("**Preview.** Quarantine Vantor's page *on a copy of the graph* and see what changes.",
         preview is not None or quarantined,
         ("Preview quarantine", lambda: act_preview(demo.POISONED))),
        ("**Approve the repair** in the preview below. This changes memory only.", quarantined, None),
        ("**Push PO-1001 through** as the manager, and watch the gate re-check it.",
         bool(po1) and po1["state"] == BLOCKED,
         (push_po1[0], lambda: act_order(demo.FIRST_ORDER, push_po1[1])) if push_po1 else None),
        ("**Re-decide.** The Buyer decides again, reading only supported memory.",
         po2 is not None, ("Buyer re-decides", act_redecide)),
        ("**Approve PO-1002** (procurement approval).",
         bool(po2) and po2["state"] in (AUTHORIZED, EXECUTED),
         ("Approve PO-1002", lambda: act_order(demo.SECOND_ORDER, "approve"))
         if po2 and po2["state"] == PENDING_APPROVAL else None),
    ]
    current = next((i for i, (_, done, _) in enumerate(steps) if not done), None)
    for i, (text, done, action) in enumerate(steps):
        st.markdown(f"{'✅' if done else ('👉' if i == current else '⬜')} {text}")
        if i == current and action:
            if st.button(action[0], type="primary", key=f"step_{i}"):
                run(action[1])
    if current is None:
        st.success("Story complete. Explore the tabs below, or reset your demo in the sidebar.")

    if ss.get("findings"):
        with st.expander(f"Detector findings ({len(ss.findings)})", expanded=not quarantined):
            for f in ss.findings:
                st.markdown(f"- `{f.source_id}` · **{f.rule}** · {md(f.evidence)}")

    if preview:
        st.markdown(f"##### Preview: quarantine `{preview.source_id}`")
        st.caption(f"Computed on `{preview.graph_name}`, a copy of your graph at revision "
                   f"{preview.base_revision}. Nothing has changed yet.")
        st.markdown(f"**Loses all support ({len(preview.lost)})**")
        for n in preview.lost:
            st.markdown(f"- ❌ `{n['id']}` {md(n['text'])}")
        if preview.survived:
            st.markdown(f"**Loses a reason but survives ({len(preview.survived)})**")
            for s in preview.survived:
                st.markdown(f"- ✅ `{s['id']}` {md(s['text'])}: still held by `{s['kept_by']}` "
                            f"({s['kept_kind']} from {', '.join(s['premises'])})")
        for o in preview.orders_blocked:
            st.markdown(f"- 🛑 The gate will block **{order_label(o['id'])}** ({o['state']}).")
        for o in preview.executed_affected:
            st.warning(f"{order_label(o['id'])} was already executed. Memory can be repaired; "
                       "the real-world action needs a human.")
        a, b = st.columns(2)
        if a.button("Approve repair", type="primary", width="stretch",
                    help="Approves the memory change only. It approves no purchase."):
            run(act_apply)
        if b.button("Discard preview", width="stretch"):
            run(discard_preview)

    with st.expander("Repair another source, or report one by hand"):
        open_sources = [s["id"] for s in sources if s["trust"] != QUARANTINED]
        if open_sources:
            pick = st.selectbox("Source", open_sources,
                                format_func=lambda i: f"{by_source[i]['title']} ({by_source[i]['trust']})")
            why_report = st.text_input("Why are you reporting it?", placeholder="e.g. price looks outdated")
            if st.button("Report and preview quarantine"):
                run(act_preview, pick, why_report or "reported by a user")


# --- Tabs -------------------------------------------------------------------------------------

tab_why, tab_orders, tab_agents, tab_audit, tab_cypher, tab_bench, tab_about = st.tabs(
    ["Why?", "Orders & decisions", "Agents (MCP)", "Audit trail", "Cypher", "Benchmark", "About"])

with tab_why:
    explainable = [n for n in nodes if n["label"] in ("Belief", "Decision")]
    ids = [n["id"] for n in explainable]
    text = {n["id"]: f"{'✅' if n['ok'] else '❌'} {n['text']}" for n in explainable}
    default = ids.index(demo.FIRST_ORDER) if demo.FIRST_ORDER in ids else 0
    ss.why_id = st.selectbox("Explain", ids, index=default, format_func=text.get)
    st.caption("Every reason behind it, down to the sources. A reason holds only if ALL "
               "its premises are supported; a conclusion needs ANY one holding reason.")
    st.markdown(render.why_markdown(views.why(g, ss.why_id)))

with tab_orders:
    for o in orders:
        info, act1, act2 = st.columns([5, 1.4, 1.2])
        info.markdown(f"**{order_label(o['id'])}** {md(o['summary'])}  \n"
                      f"state `{o['state']}` · {'✅ supported' if o['valid'] else '❌ not supported'}"
                      + (f" · approved by {o['approved_by']}" if o["approved_by"] else "")
                      + (f"  \n*gate: {md(o['note'])}*" if o["note"] else ""))
        if o["state"] in (DRAFT, BLOCKED) and act1.button("Submit", key=f"sub_{o['id']}"):
            run(act_order, o["id"], "submit")
        if o["state"] == PENDING_APPROVAL and act1.button(
                "Approve purchase order", key=f"app_{o['id']}", type="primary",
                help="Procurement approval. Separate from approving a memory repair."):
            run(act_order, o["id"], "approve")
        if o["state"] == AUTHORIZED and act2.button("Execute", key=f"exe_{o['id']}"):
            run(act_order, o["id"], "execute")
    st.markdown("**Shortlist**")
    for d in decisions:
        if d["kind"] != PURCHASE_ORDER:
            st.markdown(f"- {'✅' if d['valid'] else '❌'} {md(d['summary'])}")

with tab_agents:
    st.markdown("Agents use the graph through **MCP tools** (`python -m app.mcp_server`). "
                "They can read supported memory, record reasons, check orders and preview "
                "a quarantine. There is **no tool to approve** a repair or a purchase: the "
                "tool surface keeps those with humans.")

    async def _list_tools():
        async with Client(create_server(lambda: g)) as client:
            return (await client.list_tools()).tools

    for t in asyncio.run(_list_tools()):
        ro = t.annotations and t.annotations.read_only_hint
        st.markdown(f"- `{t.name}` {'· read-only' if ro else '· writes through memory.py'}: "
                    f"{md((t.description or '').split(chr(10))[0])}")

    def show_transcript(tr: dict) -> None:
        st.caption(f"Model: {tr['model']}")
        for i, step in enumerate(tr["steps"], 1):
            with st.expander(f"{i}. {step['tool']}({', '.join(step['arguments'])})"):
                st.json({"arguments": step["arguments"], "result": step["result"]})
        if tr.get("final"):
            st.markdown(f"**Agent:** {md(tr['final'])}")

    recorded = ROOT / "data" / "fixtures" / "live" / "tool_agent.json"
    if llm.configured() and st.button("Run the Buyer as a tool-using agent on my graph"):
        with st.spinner("The agent is choosing tools…"):
            try:
                ss.agent_run = asyncio.run(tool_agent.run(create_server(lambda: g)))
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")
    if ss.get("agent_run"):
        st.markdown("**Your run**")
        show_transcript(ss.agent_run)
    elif recorded.exists():
        st.markdown("**A recorded run** (after the repair: the agent finds Vantor unsupported "
                    "and proposes a supported order)")
        show_transcript(json.loads(recorded.read_text(encoding="utf-8")))
    elif not llm.configured():
        st.caption("No LLM key configured and no recorded run yet.")

with tab_audit:
    found = views.repairs(g)
    if not found:
        st.caption("No repairs yet.")
    for r in found:
        st.markdown(f"**{r['id']}** · quarantined *{r['title']}* · approved by {r['approved_by']} "
                    f"· revision {r['revision']}  \nwithdrew: "
                    + ", ".join(f"`{c}`" for c in sorted(r["changed"])))
    st.markdown("**Sources**")
    st.dataframe([{"source": s["title"], "trust": s["trust"], "origin": s["origin"],
                   "valid": s["valid"]} for s in sources], width="stretch", hide_index=True)

with tab_cypher:
    st.caption("The queries the product depends on. Labels come from app/schema.py; "
               "values are always query parameters.")
    groups = {
        "Support engine (app/support.py): least fixed point, run in rounds": support.QUERIES,
        "Action gate (app/gate.py)": {"read decision": gate.READ_DECISION,
                                      "trusted origins": gate.TRUSTED_ORIGINS,
                                      "what-if: remember trust": gate.REMEMBER_TRUST,
                                      "what-if: scenario": gate.SET_SCENARIO},
        "Repair preview (app/repair.py), run on a GRAPH.COPY": {
            "snapshot conclusions": repair.SNAPSHOT_CONCLUSIONS,
            "snapshot justifications": repair.SNAPSHOT_JUSTIFICATIONS,
            "lost": repair.LOST, "survived": repair.SURVIVED},
        "Views (app/views.py)": views.QUERIES,
    }
    for title, queries in groups.items():
        with st.expander(title, expanded=title.startswith("Support")):
            for name, q in queries.items():
                st.markdown(f"`{name}`")
                st.code(q.strip(), language="cypher")
    st.markdown("**Try a read-only query on your graph**")
    q = st.text_area("Cypher", "MATCH (b:Belief) WHERE b.valid = false\nRETURN b.id, b.claim",
                     label_visibility="collapsed")
    if st.button("Run read-only"):
        try:
            rows = g.ro_query(q, timeout=3000).result_set[:200]
            st.dataframe(rows, width="stretch")
        except Exception as e:
            st.error(str(e))

with tab_bench:
    bench = ROOT / "docs" / "benchmark.md"
    st.markdown(bench.read_text(encoding="utf-8").split("\n", 1)[1] if bench.exists()
                else "Run `python -m scripts.benchmark`.")
    st.caption("Residual contamination: active but unsupported. Collateral withdrawal: "
               "supported but withdrawn or lost. Stale-action authorization: unsupported "
               "orders that still pass the gate. Ground truth comes from an independent "
               "reference solver, not from Antidote's engine.")

with tab_about:
    st.markdown("""
**How it works.** Agents record *why* they believe things: every belief or decision has one or
more **justifications**, each with premises (sources or other beliefs). The rule is AND inside
a justification, OR across justifications. FalkorDB computes the least fixed point of that rule
with Cypher queries, so a loop of beliefs that justify each other can never keep itself alive.

**Repair.** Quarantining a source is previewed on a copy of the graph (GRAPH.COPY), approved by
a human, applied, verified against the preview, and written to an audit trail.

**The gate.** Before any order is authorized or executed, the gate recomputes support on the
current graph. No valid justification means blocked, whoever approves it.

**Honest limitation.** Antidote guarantees beliefs are consistent with the support graph it
recorded. It cannot guarantee that an LLM recorded every real dependency, or that a trusted
source is factually correct. A missing dependency can leave contamination behind.

All data in this demo is synthetic; the vendors and the company are fictional.
""")
