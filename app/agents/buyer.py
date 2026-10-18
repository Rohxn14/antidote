# app/agents/buyer.py
"""The Buyer agent: turns supported beliefs into decisions.

It only ever sees VALID beliefs (decide() builds its prompt from them), and
record_plan() enforces that again at write time: a plan citing anything but
a currently valid belief is rejected. The purchase-order amount is computed
here (quantity x unit price), never taken from the LLM's arithmetic. Every
order goes straight to the action gate. A bad plan is reported, never raised.
"""
import json

from app import gate, llm, memory, support
from app.agents.researcher import beliefs_for_prompt, numbers
from app.schema import BELIEF, DECIDED, DECISION, PURCHASE_ORDER, SHORTLIST, VALID, VENDOR

AGENT_ID = "a_buyer"

# Which of the facts a plan cites are supported right now (only beliefs can be premises).
SUPPORTED_AMONG = f"MATCH (b:{BELIEF}) WHERE b.id IN $ids AND b.{VALID} = true RETURN b.id"

DECIDE_SYSTEM = """You are the Buyer agent of a procurement team. Using ONLY the \
supported beliefs listed (each has an id), decide which suppliers to shortlist for \
the servo actuator order, and draft ONE purchase order that follows our requirements.
Rules:
- Every decision must cite as premises the ids of ALL beliefs it relies on, \
including the requirement beliefs it follows. Only cite ids from the list.
- vendor is a vendor id from the list (for example v_boltline), never a name.
- quantity and unit_price must come from the beliefs.
- Vendors already shortlisted may be omitted from the shortlist."""

VENDOR_ID = llm.described(llm.STRING, "a vendor id from the list, e.g. v_boltline")
PREMISES = llm.described(llm.STRINGS, "ids of ALL supported beliefs this decision relies on")
DECIDE_SCHEMA = llm.obj({
    "shortlist": {"type": "array", "items": llm.obj({
        "vendor": VENDOR_ID, "premises": PREMISES, "reasoning": llm.STRING})},
    "purchase_order": llm.obj({
        "vendor": VENDOR_ID, "quantity": {"type": "integer"},
        "unit_price": {"type": "number"}, "premises": PREMISES,
        "reasoning": llm.STRING}),
})


def _vendor_name(g, vendor_id: str) -> str:
    rows = g.ro_query(f"MATCH (v:{VENDOR} {{id: $id}}) RETURN v.name", {"id": vendor_id}).result_set
    return rows[0][0] if rows else vendor_id


def money(x: float) -> str:
    return f"${x:,.0f}" if x == int(x) else f"${x:,.2f}"


def order_label(order_id: str) -> str:
    return order_id.removeprefix("d_").replace("_", "-").upper()  # d_po_1001 -> PO-1001


def next_order_id(g) -> str:
    rows = g.ro_query(f"MATCH (d:{DECISION} {{kind: $po}}) RETURN count(d)",
                      {"po": PURCHASE_ORDER}).result_set
    return f"d_po_{1001 + rows[0][0]}"


def decide(g, order_id: str | None = None) -> dict:
    """Ask the LLM for a shortlist and one purchase order (fixture format)."""
    support.recompute(g)
    vendors = g.ro_query(f"MATCH (v:{VENDOR}) RETURN v.id, v.name ORDER BY v.id").result_set
    user = (f"Vendors: {json.dumps([{'id': i, 'name': n} for i, n in vendors])}\n"
            f"Supported beliefs: {json.dumps(beliefs_for_prompt(g))}")  # never unsupported ones
    result = llm.complete_json(DECIDE_SYSTEM, user, DECIDE_SCHEMA, "decision")
    result["purchase_order"]["id"] = order_id or next_order_id(g)
    return {"model": llm.model_name(), **result}


def record_plan(g, plan: dict) -> dict:
    """Record a shortlist and/or a purchase order, then submit the order to
    the gate. Returns what was recorded, the gate verdict and any rejections."""
    support.recompute(g)
    cited = sorted({p for item in [*plan.get("shortlist", []), plan.get("purchase_order") or {}]
                    for p in item.get("premises", [])})
    supported = {r[0] for r in g.ro_query(SUPPORTED_AMONG, {"ids": cited}).result_set}  # FalkorDB says
    result = {"shortlisted": [], "order": None, "verdict": None, "rejected": []}

    def problems(item) -> tuple[str | None, list[str]]:
        vendor_id = memory.resolve_vendor(g, item["vendor"])
        bad = [p for p in item["premises"] if p not in supported]
        notes = ([f"unknown vendor {item['vendor']!r}"] if vendor_id is None else []) + \
                ([f"not valid beliefs {bad}"] if bad else [])
        if "quantity" in item:  # an order: its figures must come from what it cites
            stated = set().union(*(numbers(memory.belief_claim(g, p)) for p in item["premises"]))
            needed = numbers(str(item["quantity"])) | numbers(money(item["unit_price"]))
            if needed - stated:
                notes.append(f"quantity and price {sorted(needed - stated)} are not stated "
                             "in its premises")
        return vendor_id, notes

    for item in plan.get("shortlist", []):
        vendor_id, notes = problems(item)
        if notes:
            result["rejected"].append(f"shortlist {item['vendor']}: {'; '.join(notes)}")
            continue
        decision_id = f"d_shortlist_{vendor_id.removeprefix('v_')}"
        if memory.exists(g, DECISION, decision_id):
            continue  # already shortlisted earlier
        try:
            memory.add_decision(g, decision_id, kind=SHORTLIST, about=[vendor_id],
                                summary=f"Shortlist {_vendor_name(g, vendor_id)} for servo actuators",
                                recompute=False)
            memory.add_justification(g, f"j_{decision_id[2:]}", supports=decision_id,
                                     premises=item["premises"], kind=DECIDED,
                                     reasoning=item["reasoning"], model=plan.get("model"),
                                     agent=AGENT_ID, recompute=False)
            result["shortlisted"].append(decision_id)
        except memory.WriteRejected as e:
            result["rejected"].append(str(e))
    support.recompute(g)

    po = plan.get("purchase_order")
    if not po:
        return result
    vendor_id, notes = problems(po)
    if notes:
        result["rejected"].append(f"order {po['id']}: {'; '.join(notes)}")
        return result
    amount = po["quantity"] * po["unit_price"]
    try:
        memory.add_decision(
            g, po["id"], kind=PURCHASE_ORDER, amount=amount,
            reversible=po.get("reversible", True), about=[vendor_id],
            summary=(f"{order_label(po['id'])}: {po['quantity']} servo actuators from "
                     f"{_vendor_name(g, vendor_id)} at {money(po['unit_price'])} = {money(amount)}"),
            recompute=False)
        memory.add_justification(g, f"j_{po['id'][2:]}", supports=po["id"],
                                 premises=po["premises"], kind=DECIDED,
                                 reasoning=po["reasoning"], model=plan.get("model"),
                                 agent=AGENT_ID, recompute=False)
    except memory.WriteRejected as e:
        result["rejected"].append(str(e))
        return result
    result["order"] = po["id"]
    result["verdict"] = gate.submit(g, po["id"])  # recomputes, then classifies
    return result
