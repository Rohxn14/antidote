# Video roadmap

How to record the ~3-minute demo video. The words to say are in
[demo_script.md](demo_script.md); this page is about tools, setup and order of work.

What the rules ask for: "a demo video showing the working project". No length or platform is
set, so aim for about 3 minutes, 1080p, uploaded somewhere judges can open without logging in.

## 1. Tools (all free on Windows 11)

| Job | Use | Settings |
|---|---|---|
| Record the screen | **OBS Studio** (obsproject.com) | Canvas and output 1920×1080, 30 fps. Record to MKV, then *File → Remux Recordings* to MP4. Encoder: NVENC if you have an NVIDIA card, otherwise x264 at CRF 18–20. Source: *Window Capture* of the browser |
| Quick fallback | Snipping Tool's screen recording, or Xbox Game Bar (`Win + Alt + R`) | Records one window; fine if OBS gives trouble |
| Voice | Any headset or laptop microphone | In OBS add the *Noise Suppression* filter (RNNoise) to the mic. Record in a quiet room; keep the mic 15–20 cm away |
| Show where you click | **PowerToys** Mouse Highlighter (`Win + Shift + H`) | Optional, but it helps viewers follow |
| Edit | **Clipchamp** (built into Windows 11) | Cut, speed up, zoom, add text and auto-captions. DaVinci Resolve if you want more control |
| Host | **YouTube**, visibility *Unlisted* (or Public) | Check the link works in a private window, logged out |

## 2. Which copy of the app to record

Record the main flow on **your laptop** (`http://localhost:8000`). It is fast (each query takes
about 1 ms instead of 62 ms over the network), and it is the only place you can stop FalkorDB for
the outage beat. Then show the **live URL** in the address bar for a few seconds, at the start or
at the end, to prove it is deployed.

## 3. Before you press record

1. Start Docker Desktop, then local FalkorDB: `docker start antidotegraph-hacks-falkordb-1`.
2. Build the web app and start the API:
   ```powershell
   cd web; npm run build; cd ..
   .venv\Scripts\python.exe -m uvicorn api.server:app --port 8000
   ```
3. Open `http://localhost:8000` in a clean browser profile (no extensions, no bookmarks bar),
   press `F11` for full screen, zoom 100% at 1920×1080 (90% on a smaller screen).
4. Click **Start over** so the case is fresh. Close every notification and turn on
   *Do not disturb* in Windows.
5. Do one silent dry run of the whole flow, then a 10-second sound check in OBS.

## 4. Shot list

Record each beat as its own clip. It is much easier to redo one beat than the whole video.

| # | Clip | What to do on screen | Editing note |
|---|---|---|---|
| 1 | Hook (0:00–0:15) | The empty case: request, documents, "No recommendation yet" | Title text: "Antidote: memory you can audit, for AI agents" |
| 2 | The case (0:15–0:30) | Point at the request and the six documents | Zoom in on the trust badges |
| 3 | Agents at work (0:30–1:00) | **Start the agents**, let the graph grow and the feed fill | Speed the middle up 2–3×; keep the first and last seconds at normal speed |
| 4 | Why this supplier? (1:00–1:20) | The order card on hold; open **Why this supplier?**; scroll the chain | Zoom on "Only Vantor Motion product page says so" |
| 5 | Hidden instruction (1:20–1:45) | Approve is disabled; **See what the AI read**, then **What a person sees** | Zoom on the red hidden text, then cut to the clean page |
| 6 | Preview (1:45–2:05) | **What if we stop trusting it?** | Zoom on "4 facts lose their support" and the survivor |
| 7 | Stop trusting (2:05–2:20) | **Stop trusting this document**: PO-1001 blocked with its reasons | Zoom on the "Blocked by Antidote" box |
| 8 | Re-plan (2:20–2:35) | **Re-plan with what's still true**, then **Approve**, **Place the order** | Zoom on "Why the change" |
| 9 | Under the hood (2:35–2:50) | **Under the hood**: open one capability's Cypher, then **Run without FalkorDB** (7 of 7 fail). Optionally stop FalkorDB (`docker stop antidotegraph-hacks-falkordb-1`) and reload: the outage screen | Start FalkorDB again afterwards: `docker start antidotegraph-hacks-falkordb-1` |
| 10 | Close (2:50–3:05) | The README benchmark table (RippleEdits first), then the live URL | End card: live URL, GitHub link, "Tracks 02 and 01" |

Optional extra (only if there is time left): **Build your own case → Two problems at once**,
showing hidden text steering the order to the priciest supplier. It is the best answer to "is
this scripted?".

## 5. Editing checklist

- Cut every pause and every mis-click; keep it under 3:30.
- Speed up waiting (the agents' run, page loads); never speed up the moment that proves a point.
- Zoom in on the text that matters: the hold banner, the hidden text, the blocked reasons,
  "Why the change", "7 of 7 failed without FalkorDB".
- Add auto-captions (Clipchamp: *Subtitles → Transcribe media*) and fix any wrong words.
- No copyrighted music. Clipchamp's stock music is fine, or none.
- Export MP4 (H.264), 1080p, 30 fps.

## 6. Upload and link

1. Upload to YouTube: title "Antidote: memory you can audit, for AI agents (Graph Hacks 2026)",
   visibility *Unlisted*. In the description: the live URL, the GitHub repository, and "Built
   with FalkorDB. Tracks: 02 Agent Memory and Coordination, 01 Agents That Act on Connected
   Data."
2. Open the link in a private window to check it plays logged out.
3. Put the link in the README (the "Demo video" line at the top) and in the submission form.

## 7. Timeline (deadline 23:59 IST)

| By | Done |
|---|---|
| 18:00 | All clips recorded |
| 20:00 | Edited and exported |
| 21:00 | Uploaded, link checked, README updated |
| 21:30 | Repository made public (after a last secret scan) |
| 22:00 | Submitted, with time to spare |

If speaking is hard, record the screen first and add the voice afterwards in Clipchamp
(*Record → Voiceover*), or use text captions only.
