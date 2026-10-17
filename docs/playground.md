# Hands-on guide: use it, test it, attack it

## 1. Start it

```bash
docker compose up -d                  # FalkorDB on :6379, FalkorDB Browser on :3000
.venv\Scripts\activate                # macOS/Linux: source .venv/bin/activate
streamlit run ui/streamlit_app.py     # http://localhost:8501
```

The sidebar has two modes. **Guided demo** plays the procurement story. **Playground** is a
second private graph where you design your own world. **Reset everything** in the sidebar
gives you fresh copies of both.

## 2. The guided demo (2 minutes)

On the right, click the button on each 👉 step: **Scan sources → Preview quarantine →
Approve repair** (in the preview box) **→ Approve PO-1001 → Buyer re-decides → Approve
PO-1002**. Watch the graph go green → amber (preview) → red. In the tabs:

- **Why?** shows the reasons behind any belief or decision, down to the source quotes, with
  evidence strength, plus a table of every conclusion's evidence.
- **Orders & decisions** lets you submit, approve and execute orders through the gate.
- **Agents (MCP)** lists the tools agents get (none of them approves anything) and shows a
  recorded run of a real LLM choosing tools.
- **Audit trail** lists every repair: who approved it, what it quarantined, what it withdrew.
- **Cypher** shows every query the product runs, plus a read-only console on your graph.

## 3. The Playground: design your own world

Switch the sidebar to **Playground**, open **Design your own world**, pick an example or
start from *Your own world*, edit the JSON and click **Load into my playground**.

```json
{
  "title": "My world",
  "description": "What it is about",
  "sources": [
    {"id": "s_registry", "title": "Registry", "trust": "trusted", "origin": "registry"},
    {"id": "s_blog", "title": "A blog", "trust": "unverified", "origin": "blog.example",
     "text": "Optional: the document itself, so quoted claims can be checked."}
  ],
  "beliefs": [
    {"id": "b_cert", "claim": "Acme is certified", "because": [["s_registry"], ["s_blog"]]},
    {"id": "b_cheap", "claim": "Acme is cheapest", "because": [{"premises": ["s_blog"], "quote": "..."}]}
  ],
  "decisions": [
    {"id": "d_po_1", "kind": "purchase_order", "summary": "Buy from Acme", "amount": 900,
     "reversible": true, "because": [["b_cert", "b_cheap"]]}
  ]
}
```

- **`because` is the whole idea.** It lists reasons. Each reason is a list of ids that are
  **all** needed (AND); **any** one reason is enough (OR). `[["s_registry"], ["s_blog"]]` means
  "the registry, or the blog". `[["b_cert", "b_cheap"]]` means "both".
- `trust` is `trusted`, `unverified` or `quarantined`. `origin` is the claim's lineage: copies
  and mirrors of one document share an origin.
- Ids start with `s_`, `b_` or `d_`. Premises are sources or beliefs; decisions are never premises.
- A reason with a `quote`, citing one source that has `text`, goes through the Researcher's
  real checks: the quote must be in the text, and the claim may not state numbers the quote
  doesn't. Refused claims are listed and never get support.
- Orders start as drafts: submit them in the **Orders & decisions** tab.

Every source has **Preview quarantine** or **Lift quarantine** next to it. Mistakes in the
JSON are reported before anything is written, so your previous world stays intact.

## 4. Manual test plan

| # | World | Do this | You should see | What it proves |
|---|---|---|---|---|
| 1 | 1. AND / OR | Preview quarantining `s_blog` | `b_certified` survives through the registry; `b_cheap`, `b_good_deal`, `d_po_acme` lose support | OR across reasons, AND inside one |
| 2 | 1. AND / OR | Approve the repair, then **Lift quarantine** | Everything comes back | Status moves both ways; nothing is deleted |
| 3 | 2. Loops | Preview and approve quarantining `s_rumour` | `b_a` and `b_b` fall although each still has a reason citing the other; `b_c`, `b_d` were never supported | Loops cannot hold themselves up |
| 4 | 3. Gate | Submit `d_po_auto` | Authorized automatically | Two independent trusted origins, small, reversible |
| 5 | 3. Gate | Submit `d_po_copies` | Waits for a human: "depends on a single trusted origin: registry" | Copies of one claim count once |
| 6 | 3. Gate | Submit `d_po_vendor` | Waits: "not supported by trusted sources alone" | A vendor's own word never auto-approves |
| 7 | 3. Gate | Submit `d_po_big`, `d_po_final` | Waits: amount over \$5,000 / not reversible | The stakes policy |
| 8 | 3. Gate | Submit `d_po_vendor`, quarantine `s_vendor`, then **Approve purchase order** | **Blocked** | A human approval cannot override missing support |
| 9 | 3. Gate | Preview quarantining `s_registry` | The mirror is included; `b_cert` survives through the audit | Quarantine by origin; surgical repair |
| 10 | 4. Agent checks | Load it | Two claims refused: a laundered certification and a fake quote | What agents write is checked |
| 11 | any | Preview a quarantine, then submit an order, then **Approve repair** | "graph changed since the preview": a fresh preview to review | Stale previews are never applied |
| 12 | any | Look at the outlines and the **Why?** table | Dashed = unverified only, double = robust | Evidence strength |
| 13 | any | **Cypher** tab: `MATCH (j:Justification) WHERE j.holds = false RETURN j.id` | The reasons that currently fail | The state lives in the graph |

## 5. Attack it yourself

- **Launder a lie through a trusted source.** Give the registry some `text`, then claim
  something its text doesn't say, quoting a real line. The numbers check refuses it if the
  numbers differ. Pure wording lies ("not certified" → "certified") are not caught: that is a
  real limit, and why humans approve anything at stake.
- **Flood it with fake sources.** Add three unverified pages with different origins all
  saying the same lie. The belief is supported, but its evidence stays **unverified only** and
  no order built on it is ever approved automatically.
- **Mirror the poison.** Copy a poisoned source under a new id with the same `origin`.
  Quarantining one takes both.
- **Make the agents vouch for each other.** Beliefs citing each other in a loop add no
  support; only a real source can switch them on.
- **Corrupt a trusted source.** Antidote believes it: it cannot know truth. When you find out,
  quarantine it and watch everything that depended on it recompute, previewed first.

## 6. Beyond the UI

- **Terminal:** `python -m scripts.seed_demo --story` (the story), `python -m pytest` (118
  tests), `python -m scripts.benchmark` (the comparison table).
- **FalkorDB Browser** at http://localhost:3000: open the graph named in the sidebar (your
  playground graph ends in `_play`) and watch it change as you click.
- **MCP:** `python -m app.mcp_server`, then connect any MCP host. Try `supported_beliefs`
  (each belief carries its evidence strength) or `propose_purchase_order` with a price no
  belief states: it is refused.
- **Real agents on your own poison:** edit `data/vendors/vantor.html` (plant a different lie
  or a sneakier injection), run `python -m scripts.record_fixtures` with your Groq key, then
  replay with `DEMO_FIXTURES=live python -m scripts.seed_demo --story`. See what the LLM
  extracts and what the checks let through.
