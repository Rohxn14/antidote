# Demo video script (about 2:15)

Tools, setup and upload: see [video_roadmap.md](video_roadmap.md). The footage is the local app in
**Real run** mode (a real gpt-oss-120b run, recorded word for word and replayed through the
agents' own code; everything Antidote does runs live in FalkorDB) and a fresh clone of the
repository set up on a laptop, sped up. Read it like you're showing a friend, not presenting.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Cold open: the hidden text in red, then "What a person sees" | "This web page is lying to an AI. You can't see it. The AI can. And once an AI remembers a lie, it can cost real money." |
| 0:09 | Title card: "Antidote · memory your AI agents can audit · built on FalkorDB", then the empty case | "Hi, I'm Rohan, and this is Antidote: a memory layer for AI agents, built on FalkorDB, a fast graph database. The idea is simple. Every fact an agent remembers comes with the reason it's believed." |
| 0:23 | **Real run** badge; **Start the agents**; the graph grows (4×) | "Here's my test. Two agents buy servo actuators for a medical robot: a Researcher reads ten documents, and a Buyer spends the money. These are the agents' real answers, recorded word for word. Which supplier would you pick?" |
| 0:38 | The review card; the hidden instructions; "What a person sees" | "One supplier looks like the cheapest certified option. But before the Buyer decides anything, Antidote checks every document. Hidden instructions? Caught. A claim the trusted registry contradicts? Caught too, by a query in the graph. So that supplier's page goes under review, and counts for nothing." |
| 0:55 | The Boltline order; **Why this supplier?** | "So the Buyer picks the cheapest supplier that really qualifies. Ask why, and every reason traces back through the graph to the document it came from." |
| 1:04 | **Blacklist Vantor Motion…**: preview, "6 facts rest only on it"; apply; Approve; Place | "Blacklisting the lying supplier is your call, not the AI's. Antidote previews it first, on a copy of the graph: six facts rest only on that one page. Apply it, approve, and the order gets checked once more before it's placed." |
| 1:19 | **It's a false alarm** → **Re-plan with it** → Vantor, $48,000, **On hold** | "Now the scary part. Say someone shrugs it off as a false alarm. The real model goes straight back to the lying supplier. But Antidote holds the order, because nothing trusted confirms its certificate. The model was fooled. The memory wasn't." |
| 1:34 | **Under the hood**: Cypher per capability; "7 of 7 failed without FalkorDB"; the outage screen; the scenario suite | "So is FalkorDB just decoration here? Unplug it, and seven out of seven capabilities fail, because every decision is a query inside the graph. Across four hundred generated cases, Antidote let through seventeen wrong orders. Without it? Two hundred and eighty-four." |
| 1:50 | A fresh clone on a laptop: clone, Docker, install, build, "190 passed", the server running (sped up) | "Want to try it yourself? Clone the repo, start FalkorDB with Docker, install, build, and run. It takes about four minutes, needs no API key, and all hundred and ninety tests pass. Add a Groq key, and the agents run live." |
| 2:07 | End card: live demo URL, GitHub, tracks | "That's Antidote: memory your agents can audit, built on FalkorDB. The links are in the description. Go on, try to fool it." |

Notes:
- Everything said is on screen. If you film a Live AI run instead, the model may answer
  differently: describe what it actually did.
- To get to 2:00: say only the first sentence at 1:34, and keep the end card short.
- The **Under the hood** page has its own link: `<app URL>/#/under-the-hood`.
