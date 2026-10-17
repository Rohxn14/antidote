# ui/render.py
"""Pure rendering helpers for the Streamlit app: DOT for the memory graph and
markdown for the "why?" tree. No database access here."""
import textwrap
from collections import defaultdict

GREEN, GREEN_FILL = "#15803d", "#dcfce7"
RED, RED_FILL = "#b91c1c", "#fee2e2"
AMBER, AMBER_FILL = "#b45309", "#fde68a"
SLATE = "#334155"
KIND_LETTER = {"extraction": "E", "inference": "I", "decision": "D"}


def _esc(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace('"', '\\"')


def _wrap(text: str, width: int = 30) -> str:
    return "\\n".join(textwrap.wrap(_esc(text), width)) or " "


def visible_ids(nodes: list[dict], edges, vendors: set | None) -> set:
    """Beliefs/decisions about the chosen vendors (plus general requirements),
    the justifications that support them, and those justifications' premises."""
    if not vendors:
        return {n["id"] for n in nodes}
    keep = {n["id"] for n in nodes if n["label"] in ("Belief", "Decision")
            and (not n["vendors"] or set(n["vendors"]) & vendors)}
    premises = defaultdict(list)
    for j, rel, x in edges:
        if rel == "PREMISE":
            premises[j].append(x)
    for j, rel, x in edges:
        if rel == "SUPPORTS" and x in keep:
            keep.add(j)
            keep.update(premises[j])
    return keep


def _node_attrs(n: dict, flips: set, selected: str | None) -> str:
    ok, label = n["ok"], n["label"]
    fill = GREEN_FILL if ok else RED_FILL
    if n["id"] in flips:
        fill = AMBER_FILL
    attrs = {"style": '"filled"', "fillcolor": f'"{fill}"', "color": f'"{SLATE}"'}
    if label == "Source":
        attrs["shape"] = "box"
        attrs["style"] = '"rounded,filled"'
        text = f"{_wrap(n['text'], 26)}\\n({n['trust']})"
        if n["trust"] == "quarantined":
            attrs.update(fillcolor='"#475569"', fontcolor='"white"')
            text = f"{_wrap(n['text'], 26)}\\nQUARANTINED"
        elif n["trust"] == "trusted":
            attrs.update(color=f'"{GREEN}"', penwidth="2")
        attrs["label"] = f'"{text}"'
    elif label == "Justification":
        attrs.update(shape="circle", fixedsize="true", width="0.3", fontsize="8",
                     fillcolor=f'"{"#86efac" if ok else "#fca5a5"}"',
                     label=f'"{KIND_LETTER.get(n["kind"], "?")}"',
                     tooltip=f'"{_esc(n["text"])}"')
    elif label == "Decision":
        attrs["shape"] = "box3d" if n["kind"] == "purchase_order" else "note"
        state = f"\\n[{n['state']}]" if n["state"] else ""
        attrs["label"] = f'"{_wrap(n["text"], 34)}{state}"'
    else:
        attrs["shape"] = "box"
        attrs["label"] = f'"{_wrap(n["text"])}"'
    if n["id"] == selected:
        attrs.update(color='"#2563eb"', penwidth="3")
    attrs["id"] = f'"{n["id"]}"'
    return ", ".join(f"{k}={v}" for k, v in attrs.items())


def graph_dot(nodes: list[dict], edges, keep: set, flips: set = frozenset(),
              selected: str | None = None) -> str:
    """Sources -> reasons -> beliefs -> reasons -> decisions, left to right.
    Green = supported, red = unsupported, amber = would lose support."""
    by_id = {n["id"]: n for n in nodes}
    lines = ["digraph G {",
             'rankdir=LR; bgcolor="transparent"; nodesep=0.12; ranksep=0.4;',
             'node [fontname="Helvetica", fontsize=10, fontcolor="#0f172a"];',
             "edge [arrowsize=0.6];"]
    for n in nodes:
        if n["id"] in keep:
            lines.append(f'"{n["id"]}" [{_node_attrs(n, flips, selected)}];')
    for j, rel, x in edges:
        if j not in keep or x not in keep:
            continue
        src, dst = (x, j) if rel == "PREMISE" else (j, x)  # evidence flows into reasons
        ok = by_id[x]["ok"] if rel == "PREMISE" else by_id[j]["ok"]
        lines.append(f'"{src}" -> "{dst}" [color="{GREEN if ok else RED}", '
                     f'style={"solid" if ok else "dashed"}];')
    lines.append("}")
    return "\n".join(lines)


def why_markdown(tree: dict, level: int = 0) -> str:
    """The support tree as a nested markdown list."""
    pad = "  " * level
    icon = "✅" if tree.get("ok") else "❌"
    if tree.get("label") == "Source":
        trust = tree.get("trust")
        icon = "⛔" if trust == "quarantined" else ("🟢" if trust == "trusted" else "🟡")
        return f"{pad}- {icon} **Source** · {_md(tree.get('text'))} · *{trust}*\n"
    out = f"{pad}- {icon} **{tree.get('label', '?')}** `{tree['id']}` · {_md(tree.get('text'))}\n"
    if tree.get("cut"):
        return out + f"{pad}  - ↩︎ *shown above (support loop)*\n"
    if not tree.get("justifications"):
        out += f"{pad}  - *no justification recorded*\n"
    for j in tree.get("justifications", []):
        mark = "holds" if j["holds"] else "**does not hold**"
        by = f" by {j['author']}" if j.get("author") else ""
        out += f"{pad}  - 🔗 *{j['kind']}*{by}, {mark}: {_md(j.get('reasoning'))}\n"
        if j.get("quote"):
            out += f"{pad}    - 💬 “{_md(j['quote'])}”\n"
        for p in j["premises"]:
            out += why_markdown(p, level + 2)
    return out


def _md(text: str | None) -> str:
    return (text or "").replace("$", "\\$").replace("*", "\\*")
