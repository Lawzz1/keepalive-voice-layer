# keep-Alive — audio layer

keep-Alive is a hackathon project (AssemblyAI) that talks a bystander through CPR.
The phone lies on the floor on speaker: it plays a 110 BPM compression metronome
and spoken protocol directives, while AssemblyAI streaming STT listens for
questions ("I heard a rib pop") and for agonal gasping.

This folder is the audio layer only. The main app and repo belong to Rana; this
work will land there as a contributor PR, so keep it self-contained.

Demo format (team, Sep 12): shown on a laptop as a web-based dashboard — a concept
demo of how it works, not a shipped phone app. Laptop speakers + laptop mic are the
real target; phone-specific work (iOS quirks, floor test) is secondary.

Team (Sep 13): Rana (lead — pipelines, FastAPI backend, dashboard), Rida Zafar
(joined Sep 13; software engineering undergrad, first hackathon), and me.
Decided Sep 13 by Rana: backend first, dashboard after — Rana and Rida build it
together. The dashboard includes a 3D human body showing correct CPR hand
placement — it should sync to `cpr_03_position` via the controller's `clipstart`
event (detail.id). So the dashboard lands late, and the
demo video can only be screen-recorded at the very end: everything else for the
video (voiceover text, recorded narration) must be ready before that.
Hackathon: lablab.ai AssemblyAI Voice Agent Hackathon, team page "keep-alive".
Runs Sep 1–30, 2026. Prizes: 5 equal winners, each $1,000 cash + $1,000 API
credits (no ranking between them). Submissions must be original and MIT-compliant,
so the code ends up MIT-licensed. Payout can take up to 90 days.
**Submission deadline: Sep 30, 6:00 PM EEST (= 17:00 CEST).** ~3,000 registered
participants as of Sep 14. The public page lists no submission format or judging
criteria — check the team page once joined.
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
- Conversation, questions, post-event debrief and paramedic handoff: **AssemblyAI Voice
  Agent API** (decided Sep 16 by Rana) — one WebSocket for STT + LLM + TTS + turn-taking
  + tool calling, ~1 s. Replaces the separate LLM + ElevenLabs plan
- Dashboard HUD latency pill: "Protocol Directive: ~15 ms · AssemblyAI Live Agent: ~1.0 s".
  The controller reports trigger→sound per line as `clipstart` `detail.latencyMs`
- 911 (decided Sep 16, AHA/ERC: call first, then compress): line 1 says "Call 911 now and
  put it on speaker!…"; a persistent red "Call 911 (Speakerphone)" button on the
  dashboard; the agent repeats the 911 instruction if asked about an ambulance
- The dashboard shows which live event triggered each line, so judges can see it's real
- The qa_* clips stay as instant fallbacks if a live answer is slow — not yet confirmed with the team

My scope:
1. Pre-rendered voice directives (ElevenLabs → normalised WAV + manifest) — assigned
2. The 2:30 demo video voiceover — assigned; draft due Sep 25, and the dashboard lands last
3. Browser audio controller — built on my own initiative, offered to the team, not requested

## Audio spec (Rana, Sep 10) — don't change without asking her

- Clips: 48 kHz / 16-bit mono WAV, -14 LUFS integrated, True Peak -1.0 dBTP
- Ducking: metronome drops **-4 dB** over 40 ms when a line starts, returns over 150 ms.
  -14 dB → -8 dB on Sep 14 (Rana's OK), -8 → -4 on Sep 16 after listening on a phone:
  the rescuer has to keep compressing *while* the voice talks, so the beat must stay
  clearly audible. **-4 dB still needs Rana's OK.**
- Metronome click: 3 kHz, -3 dBFS peak, 5 ms decay (Sep 16). At 1.5 kHz it sat inside the
  speech band and was masked; 3 kHz cuts through a phone speaker at a lower level
- A limiter (DynamicsCompressor, threshold -3 dB, ratio 20) sits between the buses and the
  speaker: a -3 dBFS click plus a -1 dBTP voice would otherwise clip
- The STT stream is gated while a directive is audible (the phone must not transcribe itself)
- **Voice locked Sep 16: "Sarah — Mature, Reassuring, Confident"**, `EXAVITQu4vr4xnSDxMaL`.
  Runner-up Eric (`cjVigY5qzO86Huf0OWal`) — use him for the demo video narration, so the
  narrator doesn't sound like the app. Re-render: `render --voice-id EXAVITQu4vr4xnSDxMaL`
- TTS for pre-rendered lines: ElevenLabs `eleven_flash_v2_5`. Live answers now come from
  the Voice Agent API's own TTS (Sep 16), so the two voices differ unless matched

## Layout

- `tools/render_directives.py` — renderer. Modes: `voices`, `audition`, `render`, `placeholder`
- `web/audio-controller.js` — the controller, one ES module, no dependencies, no build step
- `web/index.html` — test bench: scenarios, level scope, queue and event log
- `web/audio/` — rendered clips + `manifest.json` (generated, gitignored until the voice is locked)
- `web/audition.html` — voice audition page: plays the candidates through the controller, metronome underneath
- `web/audition/` — audition renders + manifest (gitignored)
- `web/leak-test.html` — measures how much of the app's voice leaks into the mic
- `server/speak_server.py` — reference `POST /speak` (FastAPI): agent text → `safety_gate`
  → ElevenLabs in the clips' voice (read from `web/audio/manifest.json`) → PCM16 24 kHz
  stream. Also serves `web/`. Binds to 127.0.0.1 only — the key must not be reachable from
  the network. A reference for Rana's backend, not the backend itself
- `server/safety_gate.py` + `test_safety_gate.py` — the deterministic text gate from
  `docs/agent-spec.md` section 4 (25 tests)
- `video/voiceover/` — demo video narration, voice Eric (`voiceover` mode)
- `.env` — `ELEVENLABS_API_KEY=...`, read by the renderer (gitignored, never commit)

## Commands

```bash
python3 tools/render_directives.py placeholder             # macOS say, no API key
python3 tools/render_directives.py audition --voices A B C # needs ELEVENLABS_API_KEY
python3 tools/render_directives.py render --voice-id A
python3 -m http.server 8765 -d web                         # bench at localhost:8765
python3 server/speak_server.py                             # bench + /speak at localhost:8766
python3 -m pytest -q server                                # safety gate tests
```

Measured Sep 17 through the bench's "Live answer" panel: click → Sarah audible in
294–361 ms (ElevenLabs answers in 207–276 ms); a critical clip cuts a live answer.

## Clip ids and priorities

| id | priority |
|---|---|
| cpr_01_confirm | normal |
| cpr_02_agonal | critical |
| cpr_03_position | normal |
| cpr_04_start_beat | normal |
| cpr_05_recoil | normal |
| cpr_06_paramedics | normal |
| cpr_07_aed | normal — proposed Sep 16 (AHA: get an AED early), not yet confirmed with Rana |
| qa_rib_pop | response |
| qa_bed_surface | response |
| qa_vomit | response |
| qa_fallback | response |

- critical: cuts whatever is playing, plays next
- response: waits for the line currently playing, then jumps ahead of queued protocol lines
- normal: FIFO

Clip text lives in `DIRECTIVES` in the renderer; the manifest is generated from it.

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
- Voice Agent replies: `openStream()` at `reply.started`, `push()` each `reply.audio`
  `data`, `end()` at `reply.done` completed / `flush()` if interrupted. They queue as
  `response`; a critical clip cuts them and their late chunks are ignored; they leave
  the mic open (`streamGate: false`) so the agent's barge-in still hears the caller
- `micToPcm16(micStream, { onFrame })` → base64 PCM16 24 kHz frames for `input.audio`,
  zeros while our clip is audible, frames never stop
- `clipstart` carries `latencyMs` (trigger → audible) and, for agent replies,
  `turnLatencyMs` (caller stopped talking → agent audible) for the HUD pill
- `userSpeaking(true/false)` ← the Voice Agent's `input.speech.started` /
  `input.speech.stopped`: the line that's playing steps back -12 dB instead of talking
  over the caller, and queued lines wait until they stop. A **critical** alert never
  yields (`yieldPriorities`) — agonal-breathing must be heard over a panicking rescuer
- **Mic leak measured Sep 17** (web/leak-test.html; MacBook built-in speakers + mic, Chrome
  152, demo volume, quiet room): noise -55.2 · app voice with echo cancellation -48.6 ·
  without -16.4 · rescuer's shout -9.9 dBFS (p95). Echo cancellation removes 32 dB; the
  shout is 38.7 dB above the leak; the leak is 6.6 dB above room noise. Conclusion:
  `micGate: 'off'` is viable **together with** the backend text filter — proposed to Rana,
  not switched yet (the gate is part of her spec, and the filter is backend work)
- `micGate` option — **the open question for barge-in**: `'mute'` (current) sends silence
  while our voice plays, which is safe but deaf: the Voice Agent can't report that the
  caller started speaking, so nobody can interrupt a 6-8 s protocol line. `'attenuate'`
  (-18 dB) lets a shout through; `'off'` relies on echo cancellation. Measure the leak on
  the demo laptop ("Mic → STT test" on the bench) before choosing. A third option, for
  the backend: keep the mic open and drop transcripts that match the line we are
  speaking at that moment — we know the text and the exact timing

## Open questions for Rana

- **One voice everywhere** (the user's requirement, Sep 17) — proposed design in
  `docs/agent-spec.md`, not yet agreed with Rana: the Voice Agent never speaks itself; it
  calls a `say(text)` tool, the backend runs a deterministic safety gate on the text, then
  voices it as Sarah with ElevenLabs Flash (`pcm_24000`, streamed) and the browser plays
  it with `ac.playPcmResponse(res)`. `reply.audio` is ignored. Measured Sep 17: first
  audio ~220 ms (196–319), stream ~1.7 dB quieter than the clips (`streamGainDb: 1.7`).
  The ElevenLabs key stays on the backend. The spec also has the agent's system prompt,
  tool schemas and a 30-question test list
- Voice Agent API integration (adopted Sep 16): does its TTS voice match the
  pre-rendered voice? (No ElevenLabs/custom voice option found in the docs — hence the
  `say` tool design above.) How does agent audio reach the browser controller, so a critical
  line can cut the agent off mid-answer? How does our mic gate coexist with its
  barge-in / turn detection?

- Does a `response` line duck the metronome? The spec says it "plays over the beat";
  the controller ducks it for now (`DEFAULTS.duck.response`)
- Gate tail length — 250 ms is a guess, needs a test on the demo laptop (its mic hears
  its own speakers). Use "Mic → STT test" on the bench
- Metronome clicks leak into the mic between lines (the gate only covers the voice).
  Relying on getUserMedia echoCancellation — check on the demo laptop how much survives

## STT integration

STT is live during the demo (team, Sep 12). The STT sender should take
`ac.gateMic(micStream)` instead of the raw mic: silence while a line is audible, mic
otherwise, stream never stops. Request the mic with `{ echoCancellation: true }`.

Answers from Rana (Sep 13):
- The pipeline has no fixed event names: it reads what the caller says and decides
- LLM not chosen: Claude or GPT-4o mini if the hackathon provides an AI/ML API key,
  otherwise gpt-oss-120b or Llama 3.3 70B
- Video: team target ~3:00, never over 4:00 (submission limit 5:00). Script is 2:30
  on paper; the rest is buffer for the live run
- Still unanswered (Rana answers the morning of Sep 14): AssemblyAI model, the
  backend → browser contract / where live-answer TTS runs, who plays the caller,
  the "at least two inches" wording

Voice Agent API wire format (AssemblyAI events reference, checked Sep 16):
- Mic in: `input.audio` with `audio` = base64 PCM16 mono **24 kHz** (not 16 kHz)
- Agent voice out: `reply.audio` chunks, `data` = base64 PCM16; `reply.started` / `reply.done`
  (`status`: completed | interrupted); captions via `transcript.agent.delta` (`start_ms`, `end_ms`)
- Turns: `input.speech.started` / `input.speech.stopped`, partials `transcript.user.delta`
- Tools: `tool.call` (`call_id`, `name`, `arguments`) → `tool.result`; context via `conversation.message`
- No client-side "cancel reply" event is documented: to cut the agent for a critical line,
  stop its playback locally. The agent replies to every user turn by default — it must
  not talk over the deterministic engine (tool-first prompt, or mute agent replies
  while a protocol line is active)
- Measured controller trigger→sound on a MacBook: 21 ms idle, 33 ms for a critical cut-in

Proposed backend → browser contract (not agreed yet): over a WebSocket, the backend
sends `{"play": "<clip id>"}` for protocol lines → `ac.play(id)`; live answers
arrive as text or audio → `ac.playBuffer(...)`.
