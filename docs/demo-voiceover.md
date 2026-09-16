# KeepAlive — demo video script, draft 2

Built on the storyboard in Rana's master plan (section 8, Sep 16), merged with
draft 1: the 911 line, the live latency pill, the unedited live run.

- **Length:** 2:30 on paper. Team target ~3:00, never over 4:00 (the submission
  limit is 5:00). The slack is for the live run — real latency and pauses run long.
- **The live run is one unedited take** with a visible clock and an
  "Unedited live run" tag. Among the top submissions checked on Sep 15, KiaOra
  simulates its calls with buttons and MockMate plays back a scripted
  candidate, so showing the real thing is our edge.
- **Narration is sparse.** The caller and the app carry the story; the narrator
  only opens, explains the architecture, and closes. The narrator's voice is not
  the app's voice.
- **Zoom in.** Record at 1080p and punch in on the 3D body, the HUD and the pill:
  small UI on a big dark screen is unreadable (KiaOra's and Siberia's problem).
- `[brackets]` = not decided yet.

---

## 0:00–0:15 · Hook

**On screen:** black, white text: *"Your hands are busy saving a life. Why does
emergency software require your hands?"* → cut to a simulated collapse in a
kitchen `[needs filming: who, where]`.

**VO** (optional, 16 words, ~7 s):
> Every year, over 350,000 Americans have a cardiac arrest outside a hospital.
> Most don't survive.

## 0:15–1:25 · Live run — one take, no narration

| ~time | Rescuer (live) | KeepAlive | On screen |
|---|---|---|---|
| 0:15 | "Help! He collapsed, he's not breathing!" | — | live transcript |
| 0:18 | | `cpr_01_confirm` — "Call 911 now and put it on speaker! Roll the patient flat on their back. Kneel beside their chest." | **● PROTOCOL LOCKED: AHA-BLS**, red **Call 911** button, latency pill "Protocol: ~20 ms" |
| 0:26 | | `cpr_03_position` — hand placement | 3D body: sternum crosshair, interlocked hands |
| 0:35 | | `cpr_04_start_beat` — metronome starts | **the money shot:** 3D hands pumping at 110 BPM, orbit 360° |
| 0:46 | "He's gasping, is he breathing again?" | `cpr_02_agonal` **cuts in** mid-line | callout `critical → cuts in`; the cut line replays after |
| 0:55 | | `cpr_07_aed` — send someone for an AED `[if the line is approved]` | |
| 1:10 | "I heard a bone pop — did I break his rib?!" | answer over the ducked beat, metronome never stops `[pre-recorded qa_rib_pop or live agent — pending Rana]` | latency pill shows both numbers |

If the run overruns, trim pauses between lines; don't drop the 3D shot or the
agonal cut-in — those are the two moments nobody else has.

## 1:25–1:35 · Architecture — 8 seconds

**On screen:** Speech → AssemblyAI Voice Agent API → deterministic protocol engine
→ audio cache + 3D cockpit. A lock icon: **LLM ≠ medical decision**. The latency
pill: `Protocol: ~20 ms · Live agent: ~1.0 s`.

**VO** (18 words, ~8 s):
> Assembly A.I. provides the ears, but it never makes the medical decision. Every
> critical step comes from a locked protocol.

## 1:35–1:55 · Second emergency, or the hybrid in close-up

`[Bleeding only if the cardiac flow is complete by Sep 24.]`

**Option A — bleeding** (Rana's storyboard): rescuer shouts "Right thigh!" → the
3D body highlights the femoral artery and draws the tourniquet line 2–3 inches
above the wound.

**Option B — no bleeding:** close-up on the rescue timeline and the latency pill.

**VO for option B** (27 words, ~11 s):
> Protocol lines play in milliseconds. Questions nobody scripted go to
> Assembly A.I.'s Voice Agent API, which answers in about a second. And the
> metronome never stops.

## 1:55–2:15 · Paramedics arrive

| Rescuer (live) | KeepAlive | On screen |
|---|---|---|
| "Paramedics are here!" | `cpr_06_paramedics` — "Stop compressions and step back…" | timers freeze, compression count |
| | the agent, in its own voice: grounding — "Take a slow breath with me…" | AI-generated EMS handoff card |

The agent speaking only here — after the crisis — is deliberate: during the
rescue every word is the locked protocol voice.

## 2:15–2:30 · Close

**On screen:** logo; *"KeepAlive — When seconds count, your hands should save a
life, not hold a phone."*; live link; GitHub (MIT); team names; AssemblyAI ×
lablab.ai.

**VO:** the tagline, read once (15 words, ~6 s).

---

## Budget

| Segment | Length | VO words |
|---|---|---|
| Hook | 0:15 | 16 (optional) |
| Live run | 1:10 | 0 |
| Architecture | 0:10 | 19 |
| Bleeding / hybrid | 0:20 | 0 / 27 |
| Paramedics | 0:20 | 0 |
| Close | 0:15 | 15 |
| **Total** | **2:30** | **49–76** |

## Rendered narration

Voice: Eric (`cjVigY5qzO86Huf0OWal`), ElevenLabs Multilingual v2, -14 LUFS.
Files in `video/voiceover/`; re-render with
`python3 tools/render_directives.py voiceover --voice-id cjVigY5qzO86Huf0OWal`
(text lives in `VOICEOVER` in the renderer). Add `--only <id>` to redo one line
without changing the takes of the others.

"AssemblyAI" is written **"Assembly A.I."** in the narration text: with the dots
the model stresses "A.I." instead of running the name together (approved Sep 17).

| File | Segment | Length |
|---|---|---|
| `vo_01_hook.wav` | Hook — the question on the black screen | 4.2 s |
| `vo_02_stat.wav` | Hook — the statistic | 6.0 s |
| `vo_03_architecture.wav` | Architecture | 6.4 s |
| `vo_04_hybrid.wav` | Hybrid close-up (option B) | 9.8 s |
| `vo_05_close.wav` | Close — the tagline | 4.4 s |

## Production checklist

- [ ] Actor for the rescuer: English, live, loud enough for the laptop mic
- [ ] Collapse shot for the hook: location, person, 3–5 seconds
- [ ] Rehearse on the demo laptop with the mic gate on (it hears its own speakers)
- [ ] Screen recording at 1080p, UI zoom 125%+, then punch in during editing
- [ ] Two full takes of the live run; keep the better one uncut
- [ ] Narrator voice ≠ app voice; no background music under the metronome
- [ ] End card: working live link + public repo

## Open items

1. ~~Stats~~ — verified Sep 13 (AHA): 356,000+ out-of-hospital cardiac arrests a
   year in the US, ~10% survive to discharge; 2025 AHA BLS: 100–120/min, at least
   2 in (5 cm), not more than 2.4 in (6 cm).
2. **Who answers the rib question** during the crisis: pre-recorded `qa_rib_pop`
   (instant, same voice) or the live agent — depends on the "agent doesn't talk
   over the protocol" rule, pending Rana.
3. **Bleeding in or out** — decide by Sep 24.
4. **`cpr_07_aed`** — proposed, waiting on Rana.
5. **`cpr_04_start_beat` wording** — "Push down two inches" → AHA says *at least*
   2 inches. Waiting on Rana.
6. **Who plays the rescuer**, and where the collapse shot is filmed.
