# Demo video script (2 minutes)

Tools, setup and upload: see [video_roadmap.md](video_roadmap.md). The footage is the local app in
**Real run** mode: the agents' answers are a real gpt-oss-120b run (Groq, 18 Oct 2026), recorded
word for word and replayed through the agents' own code; everything Antidote does runs live in
FalkorDB. About 270 words: read it slightly faster than conversation.

| Time | On screen | Say |
|---|---|---|
| 0:00 | The empty case; title "Antidote: memory your AI agents can audit" | "AI agents that share memory also share its mistakes. One poisoned supplier page can turn into a fact, a decision, and a forty-eight-thousand-dollar purchase order." |
| 0:10 | The **Real run** badge, then **Start the agents**; the graph grows (4× speed) | "Antidote is a memory layer for AI agents, built on FalkorDB. These answers are a real run of gpt-oss-120b, recorded word for word. The Researcher reads ten documents, and every fact goes into the graph with its quote and the reason it's believed." |
| 0:28 | The alert card; **See what the AI read**: hidden text in red; **What a person sees**: nothing | "Before the Buyer decides, Antidote checks every document. Vantor's page hides instructions written for AI. A person sees nothing; the model even recorded the hidden claim. And FalkorDB finds that claim contradicts the trusted registry. So the page goes under review: it counts for nothing, and Vantor is suspended." |
| 0:48 | The Boltline order, $52,000; **Why this supplier?** | "So the Buyer orders from Boltline, and every link back to a trusted document is a path in the graph." |
| 0:58 | **Blacklist Vantor Motion…**: the preview, "6 facts rest only on it"; apply; **Approve**; **Place the order** | "Blacklisting is a person's call. Antidote previews it on a copy of the graph: six facts rest only on that page and go for good. Then I approve, and the order is checked again before it's placed." |
| 1:16 | **It's a false alarm** → **Re-plan with it** → PO-1002, Vantor, $48,000, **On hold**; Approve disabled | "And if someone calls it a false alarm? The real model goes straight back to Vantor. Antidote holds the order: nothing trusted confirms Vantor's certificate. The model was fooled; the memory wasn't." |
| 1:32 | **Under the hood**: each capability's Cypher; **Run without FalkorDB** → "7 of 7 failed"; the outage screen; the scenario suite table | "Every decision is a Cypher query inside FalkorDB. Unplug the database and seven of seven capabilities fail. Across four hundred generated cases, Antidote approved seventeen wrong orders; without it, two hundred and eighty-four, a hundred and forty-five of them to suppliers that manipulated the agents." |
| 1:50 | The README on GitHub; end card: live URL, GitHub, tracks | "Its honest limit: it can only reason over what the agents recorded. Antidote: memory your agents can audit, on FalkorDB." |

Notes:
- Everything said here is on screen. If you film a Live AI run instead, the model may answer
  differently: describe what it actually did.
- The **Under the hood** page has its own link: `<app URL>/#/under-the-hood`.
- Good extras if a judge asks "is this scripted?": **Build your own case → An open lie** (no hidden
  text; the conflict check alone catches it) and **A lie nothing contradicts** (where the checks
  stop and the verification hold takes over).
