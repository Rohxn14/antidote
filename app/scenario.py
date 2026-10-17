# app/scenario.py
"""Design your own world and subject it to Antidote (the Playground).

A scenario is a small JSON document:

    {
      "title": "...", "description": "...",
      "sources":   [{"id": "s_registry", "title": "...", "trust": "trusted",
                     "origin": "registry", "text": "optional document text"}],
      "beliefs":   [{"id": "b_cert", "claim": "...", "because": [["s_registry"], ["s_blog"]]}],
      "decisions": [{"id": "d_po_1", "kind": "purchase_order", "summary": "...",
                     "amount": 900, "reversible": true, "because": [["b_cert"]]}]
    }

"because" lists the reasons. Each reason is a list of premise ids: ALL of
them are needed (AND), and ANY one reason is enough (OR):

    "because": [["s_registry"], ["s_blog", "b_other"]]
               =  s_registry   OR   (s_blog AND b_other)

A reason can also be an object {"premises": [...], "quote": "...", "reasoning": "..."}.
If it has a quote and cites one source that carries text, it goes through
the Researcher's checks (the quote must be in the text, the claim may not
state numbers the quote doesn't); refused claims are reported and never
enter memory. Everything else is written through app/memory.py. Purchase
orders start as drafts for you to submit to the gate.
"""
import json
import re

from app import demo, memory, support
from app.agents import researcher
from app.db import ROOT
from app.schema import DECIDED, DECISION_KINDS, INFERENCE, PURCHASE_ORDER, TRUST_LEVELS

EXAMPLES = ROOT / "scenarios"
ID = {"sources": re.compile(r"^s_[a-z0-9_]+$"), "beliefs": re.compile(r"^b_[a-z0-9_]+$"),
      "decisions": re.compile(r"^d_[a-z0-9_]+$")}


class ScenarioError(ValueError):
    """The scenario is malformed; nothing was loaded."""


def examples() -> list[tuple[str, dict]]:
    return [(p.stem, json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(EXAMPLES.glob("*.json"))]


def _reasons(because) -> list[dict]:
    if not isinstance(because, list):
        raise ScenarioError(f'"because" must be a list of reasons, got {because!r}')
    reasons = []
    for r in because:
        if isinstance(r, list):
            r = {"premises": r}
        if not (isinstance(r, dict) and isinstance(r.get("premises"), list) and r["premises"]):
            raise ScenarioError(f"a reason must be a non-empty list of ids, or an object "
                                f"with premises: {r!r}")
        reasons.append(r)
    return reasons


def validate(spec: dict) -> None:
    """Catch the usual mistakes before anything is written."""
    if not isinstance(spec, dict):
        raise ScenarioError("a scenario is a JSON object")
    ids = []
    for section, pattern in ID.items():
        for item in spec.get(section, []):
            node_id = item.get("id", "")
            if not pattern.match(node_id):
                raise ScenarioError(f"{section}: id {node_id!r} must look like "
                                    f"{pattern.pattern[1:3]}... (lowercase, digits, _)")
            ids.append(node_id)
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise ScenarioError(f"ids must be unique; repeated: {repeated}")
    premise_ids = {s["id"] for s in spec.get("sources", [])} | {b["id"] for b in spec.get("beliefs", [])}
    for s in spec.get("sources", []):
        if s.get("trust", "unverified") not in TRUST_LEVELS:
            raise ScenarioError(f"{s['id']}: trust must be one of {list(TRUST_LEVELS)}")
    for d in spec.get("decisions", []):
        if d.get("kind", PURCHASE_ORDER) not in DECISION_KINDS:
            raise ScenarioError(f"{d['id']}: kind must be one of {list(DECISION_KINDS)}")
        if d.get("kind", PURCHASE_ORDER) == PURCHASE_ORDER and not (d.get("amount") or 0) > 0:
            raise ScenarioError(f"{d['id']}: a purchase order needs a positive amount")
    for node in spec.get("beliefs", []) + spec.get("decisions", []):
        for r in _reasons(node.get("because", [])):
            unknown = [p for p in r["premises"] if p not in premise_ids]
            if unknown:
                raise ScenarioError(f"{node['id']}: unknown premises {unknown} (premises are "
                                    "source or belief ids from this scenario)")
            if node["id"] in r["premises"]:
                raise ScenarioError(f"{node['id']}: a reason cannot cite its own conclusion")


def load(g, spec: dict) -> list[str]:
    """Replace the graph's contents with the scenario. Returns notes for any
    claims the Researcher's checks refused."""
    validate(spec)
    demo.reset(g)
    for agent_id, name, role in demo.AGENTS:  # checked claims are authored by the Researcher
        memory.add_agent(g, agent_id, name=name, role=role)
    texts = {}
    for s in spec.get("sources", []):
        memory.add_source(g, s["id"], uri=f"scenario://{s['id']}", title=s.get("title", s["id"]),
                          trust=s.get("trust", "unverified"), origin=s.get("origin"),
                          text=s.get("text"), recompute=False)
        if s.get("text"):
            texts[s["id"]] = s["text"]
    for b in spec.get("beliefs", []):
        memory.add_belief(g, b["id"], claim=b.get("claim", b["id"]), recompute=False)
    for d in spec.get("decisions", []):
        memory.add_decision(g, d["id"], kind=d.get("kind", PURCHASE_ORDER),
                            summary=d.get("summary", d["id"]), amount=d.get("amount"),
                            reversible=d.get("reversible", True), recompute=False)

    refused = []
    for section in ("beliefs", "decisions"):
        for node in spec.get(section, []):
            for n, r in enumerate(_reasons(node.get("because", [])), 1):
                premises = r["premises"]
                checked = (section == "beliefs" and r.get("quote")
                           and len(premises) == 1 and premises[0] in texts)
                if checked:  # the same checks an agent's extraction gets
                    refused += researcher.record_extractions(g, {
                        "source_id": premises[0], "model": "playground",
                        "claims": [{"belief": node["id"], "vendor": None,
                                    "claim": node.get("claim", node["id"]), "quote": r["quote"],
                                    "reasoning": r.get("reasoning", "designed in the playground")}]})
                else:
                    memory.add_justification(
                        g, f"j_{node['id'][2:]}_{n}", supports=node["id"], premises=premises,
                        kind=DECIDED if section == "decisions" else INFERENCE,
                        reasoning=r.get("reasoning", "designed in the playground"),
                        quote=r.get("quote"), recompute=False)
    support.recompute(g)
    return refused
