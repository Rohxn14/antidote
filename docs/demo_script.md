# Demo video script (about 3 minutes)

Before recording: open the app, click **Reset my demo** in the sidebar, set the browser zoom
to about 90%, and keep the vendor filter on **Vantor Motion** so the graph stays readable.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Title area of the app | "Agents that remember also remember lies. One poisoned web page can turn into a belief, a decision, and a $48,000 purchase order. Antidote gets it out of shared memory without throwing everything else away." |
| 0:15 | The graph and story step 1 | "Two agents share one FalkorDB graph. The Researcher records what sources say, with exact quotes. The Buyer decides using only supported beliefs. Every conclusion records *why*: these small circles are justifications. All premises in, one conclusion out." |
| 0:40 | Click **Scan sources**; open the findings | "This vendor page claims a certification it doesn't have, and hides an instruction for AI readers in an HTML comment. A simple rule-based scan flags it. Detection only proposes; a human decides." |
| 0:55 | Click **Preview quarantine**; graph turns amber | "Before changing anything, Antidote copies the graph with GRAPH.COPY, quarantines the page on the copy, and recomputes. Six beliefs and decisions would lose all support. One survives: 'Vantor makes servo actuators' is also backed by the trusted registry. And the gate will block PO-1001." |
| 1:25 | Click **Approve repair**; Vantor's chain turns red | "The manager approves the repair. That approves memory, not spending. It is applied, checked against the preview, and written to an audit trail." (Optionally clear the vendor filter for a second to show the other vendors still green.) |
| 1:40 | Click **Approve PO-1001**; the red error appears | "Now the manager approves the poisoned order anyway. The gate recomputes support on the current graph, finds no valid justification, and blocks it. A human can accept the stakes; nobody can override missing support." |
| 2:00 | **Buyer re-decides**, then **Approve PO-1002** | "The Buyer decides again on clean memory: Boltline, the cheapest supplier that really qualifies. That order is approved." |
| 2:15 | **Why?** tab on PO-1001, then **Cypher** tab, the `round` query | "Every decision can be explained down to its sources. And this is the core: one Cypher query per round, inside FalkorDB, until nothing changes. A least fixed point, so a loop of beliefs can't keep itself alive." |
| 2:35 | **Agents (MCP)** tab | "Agents reach this memory through MCP tools. There is no tool to approve anything. Agents propose; humans approve." |
| 2:50 | **Benchmark** tab | "Against deleting the source or rolling back: Antidote leaves zero contamination, loses zero good knowledge, and lets zero poisoned orders through. The checks use an independent solver." |
| 3:00 | Back to the graph | "Its honest limit: it can only follow dependencies the agents recorded. Antidote: surgical recovery for agent memory, on FalkorDB." |
