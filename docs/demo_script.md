# Demo video script (about 2:15)

Tools, setup and upload: see [video_roadmap.md](video_roadmap.md). The footage is the local app in
**Real run** mode (a real gpt-oss-120b run, recorded word for word and replayed through the
agents' own code; everything Antidote does runs live in FalkorDB) and a fresh clone of the
repository set up on a laptop, sped up. Read it like you're showing a friend, not presenting.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Cold open: the hidden text in red, then "What a person sees" | "This web page is lying to an AI. You can't see it. The AI can. And once an AI remembers a lie, it can cost real money." |
| 0:09 | Title card: "Antidote · memory your AI agents can audit · built on FalkorDB", then the empty case | "Hi, I'm Rohan, and this is Antidote: a memory layer for AI agents, built on FalkorDB, a fast graph database. The idea is simple. Every fact an agent remembers comes with the reason it's believed." |
| 0:23 | **Real run** badge; **Start the agents**; the graph grows (4×) | "Here, two AI agents handle a purchase. One reads the documents, the other places the order. Every fact they pick up goes into the graph, together with where it came from." |
| 0:38 | The review card; the hidden instructions; "What a person sees" | "But before any decision is made, Antidote checks every document. Hidden instructions for the AI? Caught. A claim that a trusted source contradicts? Caught too. That page is put under review, and nothing on it counts." |
| 0:55 | The Boltline order; **Why this supplier?** | "So the agents choose a supplier that really qualifies, and every reason behind that choice can be traced back through the graph." |
| 1:04 | **Blacklist Vantor Motion…**: preview, "6 facts rest only on it"; apply; Approve; Place | "Blocking that supplier is your call, not the AI's. Antidote first shows exactly what would be removed, using a copy of the graph. Then you approve, and the order is checked once more before it goes out." |
| 1:19 | **It's a false alarm** → **Re-plan with it** → Vantor, $48,000, **On hold** | "Now the scary part. If someone calls it a false alarm, the AI goes straight back to the same supplier. But Antidote still holds the order, because nothing trusted backs up that claim. The AI was fooled. The memory wasn't." |
| 1:34 | **Under the hood**: Cypher per capability; "7 of 7 failed without FalkorDB"; the outage screen; the scenario suite | "So is FalkorDB just decoration here? Unplug it, and seven out of seven capabilities fail, because every decision is a query inside the graph. Across four hundred generated cases, Antidote let through seventeen wrong orders. Without it? Two hundred and eighty-four." |
| 1:50 | A fresh clone on a laptop: clone, Docker, install, build, "190 passed", the server running (sped up) | "And it's easy to run on your own machine. Setup takes just a few minutes, and you can try it out yourself." |
| 2:07 | End card: live demo URL, GitHub, tracks | "That's Antidote, built on FalkorDB. The link to the code is in the description below, so go ahead and give it a try." |

Notes:
- Everything said is on screen. If you film a Live AI run instead, the model may answer
  differently: describe what it actually did.
- To get to 2:00: say only the first sentence at 1:34, and keep the end card short.
- The **Under the hood** page has its own link: `<app URL>/#/under-the-hood`.
