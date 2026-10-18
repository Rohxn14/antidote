# Demo video script (about 2:15)

Tools, setup and upload: see [video_roadmap.md](video_roadmap.md). The footage is the local app in
**Real run** mode (a real gpt-oss-120b run, recorded word for word and replayed through the
agents' own code; everything Antidote does runs live in FalkorDB) and a fresh clone of the
repository set up on a laptop, sped up. Read it like you're showing a friend, not presenting.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Cold open: the hidden text in red, then "What a person sees" | "This web page is lying to an AI. You can't see the lie, but the AI can. Let's watch what happens when two AI agents read it, and what stops them." |
| 0:09 | Title, then the empty case | "Meet the agents: a Researcher that reads supplier pages, and a Buyer that spends real money, here on a hundred servo actuators for a medical robot. They share one memory, and that's the danger. One bad page can turn into a fact, then a decision, then a forty-eight-thousand-dollar order." |
| 0:23 | **Real run** badge; **Start the agents**; the graph grows (4×) | "What you're watching is a real run of gpt-oss-120b, recorded word for word. Every fact lands in FalkorDB with its quote and the reason it's believed. So, which supplier would you pick? Vantor looks like the cheapest certified one." |
| 0:38 | The review card; the hidden instructions; "What a person sees" | "But before the Buyer decides anything, Antidote checks every document. Hidden instructions? Caught. A claim the trusted registry contradicts? Caught too, by a query in the graph. So Vantor's page goes under review, and it counts for nothing." |
| 0:55 | The Boltline order; **Why this supplier?** | "The Buyer picks Boltline instead. Ask why, and every reason traces back through the graph to the document it came from, with the certificate confirmed by the trusted registry." |
| 1:04 | **Blacklist Vantor Motion…**: preview, "6 facts rest only on it"; apply; Approve; Place | "Blacklisting Vantor is your call. Antidote previews it first, on a copy of the graph: six facts rest only on that page. Apply it, approve, and the order is checked one more time before it's placed." |
| 1:19 | **It's a false alarm** → **Re-plan with it** → Vantor, $48,000, **On hold** | "Now the scary part. Say someone waves it off as a false alarm. The real model goes straight back to Vantor. But Antidote holds the order, because nothing trusted confirms that certificate. The model was fooled. The memory wasn't." |
| 1:34 | **Under the hood**: Cypher per capability; "7 of 7 failed without FalkorDB"; the outage screen; the scenario suite | "Is the graph just decoration? Unplug FalkorDB, and seven out of seven capabilities fail, because every decision here is a query inside the graph. And across four hundred generated cases, Antidote let through seventeen wrong orders. Without it: two hundred and eighty-four." |
| 1:50 | A fresh clone on a laptop: clone, Docker, install, build, "190 passed", the server running (sped up) | "Want to try it yourself? Clone the repo, start FalkorDB with Docker, install, build, and run. No API key needed, and all hundred and ninety tests pass. Add a Groq key, and the agents run live." |
| 2:07 | End card: live demo URL, GitHub, tracks | "Antidote: memory your agents can audit, built on FalkorDB. The live demo and the code are in the description. Go on, try to fool it." |

Notes:
- Everything said is on screen. If you film a Live AI run instead, the model may answer
  differently: describe what it actually did.
- To get to 2:00: say only the first sentence at 1:34, and keep the end card short.
- The **Under the hood** page has its own link: `<app URL>/#/under-the-hood`.
