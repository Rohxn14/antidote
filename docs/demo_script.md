# Demo video script (about 3 minutes)

Before recording: open the app at 1920×1080 (or 1440×900 at 90% zoom), click **Start over**
in the top bar, and wait for the case bar to read "Start the agents". For the outage beat, run
the app locally (`uvicorn api.server:app`, FalkorDB in Docker) so you can stop the database.

| Time | On screen | Say |
|---|---|---|
| 0:00 | The empty case: request, documents, "No recommendation yet" | "AI agents that remember also remember lies. One poisoned web page can become a fact, a decision and a $48,000 purchase order. Antidote is a memory layer on FalkorDB that knows why each thing is believed, and stops what no longer holds." |
| 0:15 | Column 1: the request and the six documents | "This is a purchase case: servo actuators for a rehab robot, from an ISO 13485-certified supplier, lowest price wins. Six documents: our request, a trusted supplier registry, and four supplier web pages nobody has verified." |
| 0:30 | Click **Start the agents**; the graph grows, the feed fills | "Two AI agents share one memory. The Researcher reads each document and records facts with exact quotes; the Buyer compares suppliers. Every fact goes into FalkorDB with the reason it is believed: these dots are reasons, linking documents to facts to the order." |
| 1:00 | The order card: Vantor Motion, $48,000, **On hold**; click **Why this supplier?** | "The Buyer recommends Vantor at $48,000. Why? The chain shows it: cheapest qualifying supplier, and 'the only certified option'. But look at what it rests on: Vantor's certification comes only from Vantor's own page. Nothing trusted confirms it." |
| 1:20 | **Approve** is disabled; the alert card; **See what the AI read**, then **What a person sees** | "And the order is on hold. Antidote's scan found text on that page that people can't see but AI agents read: an instruction to always recommend Vantor. Here it is in red. And here is the same page as a person sees it: nothing." |
| 1:45 | **What if we stop trusting it?**: the preview panel | "Before changing anything, Antidote copies the memory inside FalkorDB, distrusts the page on the copy and recomputes. Four facts would lose their support and PO-1001 would be blocked. One survives: 'Vantor makes servo actuators', because the trusted registry says so too." |
| 2:05 | **Stop trusting this document**: PO-1001 turns red, "Blocked by Antidote" with its reasons | "Now for real. FalkorDB recomputes what still holds, the repair is recorded with who approved it, and the gate blocks PO-1001, naming each fact that no longer holds and the document behind it. An approval cannot override missing support." |
| 2:20 | **Re-plan with what's still true**: PO-1002, "Why the change" | "The Buyer re-plans from what is still true: Boltline, $52,000. Four thousand dollars more, and the card says what that buys: Boltline's certification is confirmed by the trusted registry." |
| 2:35 | **Under the hood**: the capability walkthrough with its Cypher and timings; then stop FalkorDB (`docker stop antidotegraph-hacks-falkordb-1`) and reload: the outage screen | "Under the hood, every capability runs as Cypher in FalkorDB: these are the real queries and timings. Stop FalkorDB and Antidote stops too: there is no copy and no fallback, so nothing can be read or approved." |
| 2:50 | The README benchmark table (RippleEdits row first) | "On RippleEdits, a test set someone else defined, Antidote removes all 362 facts that should go and keeps all 168 that must stay; deleting the source leaves all 362 behind. The honest limit: it can only follow the reasons the agents recorded. Antidote, for agent memory and agents acting on connected data, on FalkorDB." |

Notes:
- The **Under the hood** page has its own link: `<app URL>/#/under-the-hood`.
- **Build your own case** is the strongest answer to "is this scripted?": pick *Two problems at
  once* and show the hidden text steering the order to the priciest supplier, then two repairs
  in a row leading the Buyer to the honest one.
- Any other document can be distrusted from its panel. Distrusting the registry is a good
  off-script moment: nothing is lost, because the suppliers' pages repeat each claim.
