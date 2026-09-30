# KeepAlive — audio layer

KeepAlive is a hackathon project (AssemblyAI Voice Agent Hackathon, lablab.ai) that
talks a bystander through CPR. The phone lies on the floor on speaker: it plays a
110 BPM compression metronome and spoken protocol directives, while AssemblyAI
streaming STT listens for questions ("I heard a rib pop") and for agonal gasping.

This folder is the audio layer only. The main application lives in
`ranazain9/keepalive`; everything here landed there as pull requests #1–#8, so keep
this repository self-contained.

Demo format (team, Sep 12): shown on a laptop as a web-based dashboard — a concept
demo of how it works, not a shipped phone app. Laptop speakers + laptop mic are the
real target; phone-specific work (iOS quirks, floor test) is secondary.

Team (Sep 13): Rana (lead — pipelines, FastAPI backend, dashboard), Rida Zafar
(joined Sep 13), and me. Decided Sep 13 by Rana: backend first, dashboard after —
Rana and Rida build it together. The dashboard includes a 3D human body showing
correct CPR hand placement — it syncs to `cpr_03_position` via the controller's
`clipstart` event (`detail.id`). The dashboard therefore lands late, and the demo
video can only be screen-recorded at the very end: everything else for the video
(voiceover text, recorded narration) must be ready before that.

Hackathon: lablab.ai AssemblyAI Voice Agent Hackathon, team page "keep-alive".
Runs Sep 1–30, 2026. Prizes: 5 equal winners, each $1,000 cash + $1,000 API
credits (no ranking between them). Submissions must be original and MIT-compliant,
so the code ends up MIT-licensed. Payout can take up to 90 days.
**Submission deadline: Sep 30, 6:00 PM EEST (= 17:00 CEST).** Final counts on the
live page at the deadline: 4,120 participants, 1,311 teams, 404 submissions,
138 drafts. The public page never listed a submission format or judging criteria.
The team WhatsApp group has 24 h disappearing messages — decisions go in this file.

Team plan (Sep 12): Rana builds the pipelines → pushes to git → FastAPI backend →
dashboard last. My assignment: the script and the voice now; the demo video
voiceover once the dashboard exists.

Clarified Sep 13: the demo runs the real application, live — no scripted data.
Pre-recorded protocol lines are confirmed as needed (zero latency). The demo
voiceover narrates how the system works, built around a caller saying
"my father collapsed and he's not breathing".

Agreed architecture (Sep 13, team confirmed) — the demo pitch:
"deterministic where safety matters, generative where flexibility matters".
- CPR protocol steps: pre-recorded clips, zero latency, fixed medical wording
- Conversation, questions, post-event debrief and paramedic handoff: originally the
  AssemblyAI Voice Agent API (Sep 16) — **superseded Sep 18**, see "the real
  architecture" below
- Dashboard HUD latency pill. The controller reports trigger→sound per line as
  `clipstart` `detail.latencyMs`
- 911 (decided Sep 16, AHA/ERC: call first, then compress): line 1 says "Call 911 now and
  put it on speaker!…"; a persistent red "Call 911 (Speakerphone)" button on the
  dashboard; the agent repeats the 911 instruction if asked about an ambulance
- The dashboard shows which live event triggered each line, so judges can see it's real
- The `qa_*` clips double as instant fallbacks if a live answer is slow

My scope:
1. Pre-rendered voice directives (ElevenLabs → normalised WAV + manifest) — assigned
2. The 2:30 demo video voiceover — assigned; draft due Sep 25, and the dashboard lands last
3. Browser audio controller — built on my own initiative, offered to the team, not requested

## Audio spec (Rana, Sep 10) — agree any change with her first

- Clips: 48 kHz / 16-bit mono WAV, -14 LUFS integrated, True Peak -1.0 dBTP
- Ducking: metronome drops **-4 dB** over 40 ms when a line starts, returns over 150 ms.
  -14 dB → -8 dB on Sep 14 (Rana's OK), -8 → -4 on Sep 16 after listening on a phone:
  the rescuer has to keep compressing *while* the voice talks, so the beat must stay
  clearly audible. **Approved and locked by Rana, Sep 17.**
- Metronome click: 3 kHz, -3 dBFS peak, 5 ms decay (Sep 16). At 1.5 kHz it sat inside the
  speech band and was masked; 3 kHz cuts through a phone speaker at a lower level
- A limiter (DynamicsCompressor, threshold -3 dB, ratio 20) sits between the buses and the
  speaker: a -3 dBFS click plus a -1 dBTP voice would otherwise clip
- ~~The STT stream is gated while a directive is audible~~ → **since Sep 17 (Rana) the mic
  stays open** (`micGate: 'off'`): Chrome's echo cancellation removes 32 dB and the backend
  drops transcripts that match the line being spoken, so the rescuer can interrupt anytime
- **Voice locked Sep 16: "Sarah — Mature, Reassuring, Confident"**, `EXAVITQu4vr4xnSDxMaL`.
  Runner-up Eric (`cjVigY5qzO86Huf0OWal`) — used for the demo video narration, so the
  narrator doesn't sound like the app. Re-render: `render --voice-id EXAVITQu4vr4xnSDxMaL`
- TTS for pre-rendered lines: ElevenLabs `eleven_flash_v2_5`. Live answers go through
  `/speak` in the same voice (Sep 18 onward), so there is one voice everywhere

## Layout

- `tools/render_directives.py` — renderer. Modes: `voices`, `audition`, `render`, `placeholder`
- `web/audio-controller.js` — the controller, one ES module, no dependencies, no build step
- `web/index.html` — test bench: scenarios, level scope, queue and event log
- `web/audio/` — rendered clips + `manifest.json` (generated)
- `web/audition.html` — voice audition page: plays the candidates through the controller, metronome underneath
- `web/audition/` — audition renders + manifest (gitignored)
- `web/leak-test.html` — measures how much of the app's voice leaks into the mic
- `server/speak_server.py` — reference `POST /speak` (FastAPI): agent text → `safety_gate`
  → ElevenLabs in the clips' voice (read from `web/audio/manifest.json`) → PCM16 24 kHz
  stream. Also serves `web/`. Binds to 127.0.0.1 only — the key must not be reachable from
  the network. A reference for the team backend, not the backend itself
- `server/speak_router.py` — the same `/speak` as a FastAPI router with the `SARAH` voice
  constants: what gets included in `server/main.py` (`server/INTEGRATION.md`).
  `speak_server.py` is now just the bench server around it
- `server/safety_gate.py` + tests — the deterministic text gate from
  `docs/agent-spec.md` section 4; `test_speak_router.py` checks the router offline and that
  `SARAH` matches the manifest (29 tests)
- `video/voiceover/` — demo video narration, voice Eric (`voiceover` mode)
- `tools/build_video_draft.py` — the video draft kit, from before the dashboard existed:
  renders the caller placeholder (ElevenLabs "Liam") and the agent's grounding line, mixes
  the 2:24 soundtrack with the controller's behaviour, draws 1920x1080 cards (TO RECORD
  placeholders where dashboard footage goes), a slideshow MP4 and `EDIT_PLAN.md`, all in
  `video/assets/`. Big outputs are gitignored — re-run the script
- `docs/video-shot-list.md` — what the dashboard must show in the video, for Rana and Rida
- `tools/line_audit.py` — takes a screen recording (or a transcript), transcribes it and
  says which clips still match the engine word for word, which drifted, and which spoken
  lines have no clip. Prints the `render --only` command
- `tools/storyboard_art.py` — the nine storyboard drawings as SVG, shared by the sheet and
  the animatic, so a shot that changes on set changes in one place
- `tools/build_animatic.py` — the storyboard as a 90 s video with the real soundtrack:
  the clips at their real moments, a 110 BPM metronome from 0:35 to 1:10, the closing
  narration. The film's timing, for the shoot and the edit
- `tools/capture_site_tour.py` — records the live cockpit at 1920x1080 (Playwright,
  silent) for the explainer half of the film: the three themes by visible label, then a
  scroll to the QR at the bottom of the page
- `tools/build_demo_cut.py` — the finished cut: the phone takes, the site tour and the two
  narrations into `video/assets/keepalive_demo.mp4` with burnt-in subtitles
- `tools/md_to_pdf.py` — any doc → A4 PDF for WhatsApp (`md_to_pdf.py in.md out.pdf`)
- `.env` — `ELEVENLABS_API_KEY=...`, read by the renderer (gitignored, never commit)

## Commands

```bash
python3 tools/render_directives.py placeholder             # macOS say, no API key
python3 tools/render_directives.py audition --voices A B C # needs ELEVENLABS_API_KEY
python3 tools/render_directives.py render --voice-id A
python3 -m http.server 8765 -d web                         # bench at localhost:8765
python3 server/speak_server.py                             # bench + /speak at localhost:8766
python3 -m pytest -q server                                # safety gate tests
python3 tools/build_demo_cut.py                            # → video/assets/keepalive_demo.mp4
```

Measured Sep 17 through the bench's "Live answer" panel: click → Sarah audible in
294–361 ms (ElevenLabs answers in 207–276 ms); a critical clip cuts a live answer.
Sep 17, later: the speak server keeps one pooled connection to ElevenLabs warm
(`requests.Session` + a request every 45 s, one retry on a dropped connection).
ElevenLabs response, median of 8: 244 ms → **141 ms**. `--port` runs a second copy.

## Clip ids and priorities

| id | priority |
|---|---|
| cpr_01_confirm | normal |
| cpr_02_agonal | critical |
| cpr_03_position | normal |
| cpr_04_start_beat | normal |
| cpr_05_recoil | normal |
| cpr_06_paramedics | normal |
| cpr_07_aed | normal — AED retrieval also appears in the engine's own step 1 |
| qa_rib_pop | response |
| qa_bed_surface | response |
| qa_vomit | response |
| qa_tired | response — added Sep 17 ("I'm tired" is a whitelisted answer) |
| qa_fallback | response |

- critical: cuts whatever is playing, plays next
- response: waits for the line currently playing, then jumps ahead of queued protocol lines
- normal: FIFO

Clip text lives in `DIRECTIVES` in the renderer; the manifest is generated from it.
These 12 are the originals; the 46 engine lines merged in on Sep 21 are keyed by the
backend's own ids (see "the whole engine is rendered in Sarah's voice" below).

## Controller decisions

- Metronome = one-shot click sources scheduled on the audio clock 3 s ahead (topped up
  every 250 ms). Beat n is at `startAt + n * period`, so no drift, and a stalled or
  throttled main thread doesn't break the beat. Don't switch to `loop = true` over the
  whole buffer: in Chromium 152 it plays once and goes silent (verified offline)
- A normal line cut by a critical one is requeued at the front of the normals
- A response or critical line that gets cut is dropped (stale)
- The same clip id is never stacked (STT may flag gasping several times in a row)
- 250 ms gap between back-to-back lines, metronome stays ducked through it
- Mic gate reopens 250 ms after the voice ends (output latency + room echo)
- `navigator.audioSession.type = 'playback'` on unlock, or iOS silent mode mutes everything
- Streamed replies: `openStream()` at the start, `push()` per chunk, `end()` when the
  stream completes / `flush()` if interrupted. They queue as `response`; a critical clip
  cuts them and their late chunks are ignored; they leave the mic open
  (`streamGate: false`) so barge-in still hears the caller
- `micToPcm16(micStream, { onFrame })` → base64 PCM16 frames, zeros while our clip is
  audible, frames never stop. **16 kHz for the AssemblyAI streaming socket**
  (`sampleRate: 16000`); the `/speak` output path stays 24 kHz
- `clipstart` carries `latencyMs` (trigger → audible) and, for streamed replies,
  `turnLatencyMs` (caller stopped talking → agent audible) for the HUD pill
- `userSpeaking(true/false)`: the line that's playing steps back -12 dB instead of talking
  over the caller, and queued lines wait until they stop. A **critical** alert never
  yields (`yieldPriorities`) — agonal-breathing must be heard over a panicking rescuer
- **Mic leak measured Sep 17** (web/leak-test.html; MacBook built-in speakers + mic, Chrome
  152, demo volume, quiet room): noise -55.2 · app voice with echo cancellation -48.6 ·
  without -16.4 · rescuer's shout -9.9 dBFS (p95). Echo cancellation removes 32 dB; the
  shout is 38.7 dB above the leak; the leak is 6.6 dB above room noise. Conclusion:
  `micGate: 'off'` is viable **together with** the backend text filter — the filter exists
  and the controller default is `'off'` since Sep 17
- `micGate` option, resolved Sep 17: `'mute'` sends silence while our voice plays, which is
  safe but deaf — nobody can interrupt a 6-8 s protocol line. `'attenuate'` (-18 dB) lets a
  shout through; `'off'` relies on echo cancellation plus the backend dropping transcripts
  that match the line being spoken at that moment. `'off'` is the default

## Team progress

**Sep 17, Agent #1 status (WhatsApp group):**
- Intent routing ~1.48 ms (p99 3.04 ms) — the router alone, not end-to-end
- "10 life-threatening crises": cardiac arrest, arterial bleed, choking, overdose,
  anaphylaxis, seizure, stroke, … marked complete. At this point our audio covered CPR
  only (11 clips); the other protocols needed their own lines — resolved Sep 21
- Agonal-gasping override, neck-tourniquet guard (direct pressure / packing instead),
  MARCH triage, limb + bystander detection (RIGHT_THIGH, LEFT_ARM…)
- Multilingual: en, es, ur/hi listed — **Sep 17: the demo is English only**. Our English
  lines are enough
- STT: **AssemblyAI Universal-3.5 Pro**, medical vocabulary boosted
- The 911 CAD feature was first described as live. Raised that a hackathon build can't
  integrate with real dispatch, and asked for it to be labelled simulated — agreed Sep 18,
  and the UI label shipped in PR #8
- 45/45 tests passing

**Sep 17, locked decisions (answers to the spec review):**
- The conversational agent never gives medical instructions; its replies are muted during
  an active protocol. It calls tools (`lock_protocol`, `request_probe`), understands
  questions, and speaks after EMS arrive
- Common crisis questions (ribs, tired, vomit…) → pre-recorded `qa_*` clips, same voice
- Scope: cardiac arrest is the polished flagship; arterial bleeding, anaphylaxis and
  overdose are shown as "plug-and-play extensible clinical engines"
- 3 kHz click and -4 dB duck: approved and locked
- Mic open during playback + backend echo filter (string similarity against the line
  being spoken): implemented
- 24 kHz PCM16 supported; the "100% offline" claim dropped
- The latency indicator shows routing time (1.2–2.5 ms). Suggested showing it next to the
  audio time (`clipstart` `latencyMs`, ~20 ms) so it isn't read as end-to-end
- `/speak` code and the gate rules requested for `server/main.py`

**Sep 18 — the real architecture (three agents):**
- **Not the Voice Agent API.** Agent #1 runs on **AssemblyAI Universal-3.5 Pro streaming**
  (`wss://streaming.assemblyai.com/v3/ws`) with local triage (inverted keyword index +
  regex, MARCH, agonal detector), 1.44 ms average. The README and the architecture card
  were corrected to match. **Mic frames for that socket are 16 kHz**, not 24 kHz: pass
  `sampleRate: 16000` to `micToPcm16` (our `/speak` output stays 24 kHz)
- **Agent #2 "Safety Coach"** is our audio layer + an SVG anatomical manikin (not the 3D
  body from the master plan): sternum displacement and a ripple locked to each beat, plus
  an AHA 2-minute fatigue timer that prompts a rescuer swap
- **Agent #3 "Clinical Companion"**: Groq LPU (qwen) at 180–290 ms + our `/speak`, with
  the section-4 gate and the deterministic micro-Q&A as offline fallback
- **911 dispatch is simulated by default** (ECHO packet, Medic-4, 4 min ETA, live
  reverse-geocoded GPS, real nearby AED data); optional live relays (RAPIDSOS, Twilio,
  ntfy) behind `.env`. The video needs a "simulated dispatch" label, and the live relays
  must stay off during the demo
- **Exact engine wording** for steps 1–3 received; AED is *not* in step 1. Our clips are
  re-rendered to match word for word, because the echo filter compares texts
- Latency pill: "routing 1.5 ms · voice 20 ms" — as suggested
- `report_event rescuer_exhausted` → `qa_tired`, with the companion as fallback

**Sep 21, the live app** — https://keepalive-dpt7.onrender.com (Render), repo
`ranazain9/keepalive` **public with an MIT LICENSE**, README says "simulated CAD
dispatch". A React cockpit (`client/src`) replaced `client_test.html`: three themes, a
Three.js scene after all (`client/public/models/*.glb`), a 2.2" depth gauge, a 110 BPM
ring, an EMS handoff modal, and a "70s Video Take Helper" that replays my shot list
through `simulateVoice()` — REST, not the mic, so the film take must use the real mic path.
- **Both clients spoke through `window.speechSynthesis`** (`client/src/hooks/useRescueState.js`,
  `EMSHandoverModal.jsx`): the browser's built-in voice, different on every machine. Our
  clips were not wired in — this was the main gap for the video, closed by PR #1
- Their metronome is `setInterval` + a per-click oscillator. **Measured on the live page
  with both WebGL canvases rendering: 110.09 BPM, worst single-beat error 2.9 ms** — good
  enough; no reason to push our scheduler on timing grounds alone
- Mic path is correct: downsample to 16 kHz PCM16, plus a word-overlap echo filter
- The HUD label read `LATITUDE: 0.8MS` where latency was meant
  (`client/src/components/TopTelemetryBar.jsx:55`) and would have been on screen in the
  video — fixed in PR #8, now `TRIAGE ROUTING:`
- From my README review: `py -3.13` in the quickstart (Windows only), `.env.example`
  missing `GROQ_API_KEY`/`CAD_PROVIDER`, "100% Offline Capable" for Agent #1, and the UI
  itself never saying the dispatch is simulated — the last one fixed in PR #8
- Spoken vs on-screen text differ in step 3: `instruction` says "at least 2 inches",
  `spoken_voice_text` says "two inches". The clips follow `spoken_voice_text` because the
  echo filter compares against it

**Sep 21, the whole engine is rendered in Sarah's voice.** `tools/sync_engine_lines.py`
parses `protocols.py` (`audio_cue_id` + `spoken_voice_text`) and `micro_qa_engine.py`
into `tools/engine_lines.py`, which `render_directives.py` merges into `DIRECTIVES`.
**46 engine lines + our original 12 = 58 clips**, all -14 LUFS / -1.3 dBTP, keyed by the
backend's own ids, so it can ask for a clip by the name it already uses: 21 protocol
directives (adult/child/infant CPR, choking ×3, bleed, anaphylaxis, overdose) and
26 micro-Q&A answers. Number-heavy lines verified by transcribing them back.
Re-run the sync after any line is edited upstream: it prints exactly what drifted.

**Sep 22 — the first two PRs** (push access granted Sep 20):
- **#1 `feat/human-voice-clips`** — 58 clips (3.0 MB Opus) in `client/public/audio`,
  `client/src/audio/clipVoice.js` (lookup by the backend's own `asset_id`, else exact text),
  the hook tries a clip first, browser speech stays as the fallback, `main.py` mounts
  `/audio`. Verified against their server: steps 1–3 and the paramedic line play from clips
- **#2 `feat/live-answers-same-voice`** (stacked on #1) — `/speak` + the safety gate inside
  the backend, so Groq's unscripted answers are voiced as Sarah. Order: clip → /speak →
  browser. No key → router not mounted → 404 → client stops asking → previous behaviour.
  Measured in their backend: upstream 125 ms, first sound 139 ms
- Two real bugs found by testing: the client always sent `protocol_state: 'active'`, so the
  gate cut the paramedic line as `too_long`; and a PCM chunk at an odd byte offset made
  `Int16Array` throw and abandoned the stream mid-answer. Both fixed in #2
- Their `unittest discover -s server/tests` stays 60/60; our 29 pytest tests live in
  `server/tests_voice`
- **`net::ERR_ABORTED` on a streamed `/speak` response is a devtools artefact**, not a
  failure — a direct call that demonstrably played audio is logged the same way
- **ntfy.sh fires by default**: `NTFY_TOPIC` has a hardcoded value in `config.py`, so a
  real push goes out even with `CAD_PROVIDER=MOCK`. Flagged in #2 — kept off while filming
- Sep 21: browser `speechSynthesis` was the default because no paid ElevenLabs tier was
  available. I offered a dedicated TTS-only key from my own account, to live only in
  Render's env vars and be rotated after Sep 30

**Sep 26–28 — the live app moved to https://keepalive-fmdh.onrender.com** (the old
`keepalive-dpt7` service died with 503s). Five more PRs, all merged: #3 the EMS briefing in
our voice + the `briefing` gate state; #4 the iOS mic (AudioContext after the await, the
half-open failure path, and the error nobody rendered); #5 one shared AudioContext — Safari
allows only a handful per page and the cockpit made four; #6 a mic context that matches the
stream's sample rate, plus naming the failing call; #7 clipVoice taking the shared context
itself, so the handover briefing speaks in Sarah's voice on a reloaded page too.
**Merging does not deploy reliably** — check the bundle hash at `/assets/index-*.js` after
every merge. The shoot is a three-person scene filmed on a phone: storyboard, camera plan
and animatic in `video/assets/`.

**Sep 30 — PR #8 "Say only what we can stand behind"**, merged and live: `SIMULATED
911 CAD:` in the UI, `NEMSIS v3.5-style record · demo data · not a certified ePCR`,
`SCENE SECURED` removed, and the `LATITUDE` label replaced with `TRIAGE ROUTING:`.
Verified in the deployed bundle, not just in the merge.

## Final state (Sep 30 — submitted)

- Submitted and accepted before the deadline. Live app: https://keepalive-fmdh.onrender.com
- All 8 PRs merged and confirmed present in the deployed bundle
- 58 clips in one voice; browser `speechSynthesis` is the fallback, not the default
- This repository published as https://github.com/Lawzz1/keepalive-voice-layer (MIT),
  linked from the main project as the individual contribution
- **Open: rotate the ElevenLabs key.** The same key is in Render's env vars and in the
  local `.env`. Judging does not need it — without it `/speak` returns 404 and the client
  falls back to clips, which are served as static files

## Superseded: Voice Agent API notes (Sep 16–18)

Kept because the wire format is worth having written down if the project ever moves to
the Voice Agent API. Agent #1 runs on Universal-3.5 Pro streaming instead (Sep 18).

- Mic in: `input.audio` with `audio` = base64 PCM16 mono **24 kHz** (not 16 kHz)
- Agent voice out: `reply.audio` chunks, `data` = base64 PCM16; `reply.started` / `reply.done`
  (`status`: completed | interrupted); captions via `transcript.agent.delta` (`start_ms`, `end_ms`)
- Turns: `input.speech.started` / `input.speech.stopped`, partials `transcript.user.delta`
- Tools: `tool.call` (`call_id`, `name`, `arguments`) → `tool.result`; context via `conversation.message`
- No client-side "cancel reply" event is documented: to cut the agent for a critical line,
  stop its playback locally. The agent replies to every user turn by default — it must
  not talk over the deterministic engine (tool-first prompt, or mute agent replies
  while a protocol line is active)
- No ElevenLabs/custom voice option found in the docs, which is why `docs/agent-spec.md`
  proposes a `say(text)` tool instead: the agent never speaks itself, the backend gates the
  text and voices it as Sarah, and the browser plays it with `ac.playPcmResponse(res)`.
  Measured Sep 17: first audio ~220 ms (196–319), stream ~1.7 dB quieter than the clips
  (`streamGainDb: 1.7`). The ElevenLabs key stays on the backend. That design is what
  shipped in PR #2

## Still open (audio layer)

- Does a `response` line duck the metronome? The spec says it "plays over the beat";
  the controller ducks it (`DEFAULTS.duck.response`)
- Gate tail length — 250 ms is a guess; untested on the demo laptop. Use "Mic → STT test"
  on the bench. Moot while `micGate` is `'off'`
- Metronome clicks leak into the mic between lines (the gate only covers the voice).
  Relying on getUserMedia `echoCancellation`

## STT integration

STT is live during the demo (team, Sep 12). Request the mic with
`{ echoCancellation: true }` and feed the socket from `micToPcm16(micStream,
{ sampleRate: 16000, onFrame })` — silence while a line is audible if the gate is on,
mic otherwise, stream never stops.

Answers from Rana (Sep 13):
- The pipeline has no fixed event names: it reads what the caller says and decides
- Video: team target ~3:00, never over 4:00 (submission limit 5:00). Script is 2:30
  on paper; the rest is buffer for the live run

Measured controller trigger→sound on a MacBook: 21 ms idle, 33 ms for a critical cut-in.
