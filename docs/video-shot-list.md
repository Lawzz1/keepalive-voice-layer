# KeepAlive demo video — what the dashboard needs to show

For Rana and Rida. The narration, the voice lines, the architecture slide and
the end card are ready. The only missing picture is the dashboard. This is the
list of shots the video needs from it, in order, with their length.

Watch `keepalive_draft_slideshow.mp4` first: it is the whole video with dashed
"TO RECORD" cards where these shots go, over the real soundtrack.

## The shots

### 1 · Live run — one unedited take (0:15–1:25, 70 s)

This is the heart of the video. Record it in **one take, no cuts**, with the
real app, a teammate playing the caller out loud.

Must be visible:

- **Live transcript** of what the caller says, appearing as they speak
- **● PROTOCOL LOCKED: AHA-BLS** badge the moment the emergency is recognised
- **Red "Call 911 (Speakerphone)" button**, always on screen
- **3D body**: hand placement highlighted while "Place the heel of one hand…"
  plays, then **3D hands pumping on the metronome beat** from "Push hard and
  fast…" on — the money shot, keep it large
- **Critical alert callout** when the caller says "he's gasping" and the alert
  cuts in
- **Latency pill** the whole time: `Protocol ~20 ms · Live answer ~0.3 s`, with
  live measured numbers
- A **clock** and an **"Unedited live run"** tag in a corner

What happens, so the screen can follow it:

| ~time | Caller | App |
|---|---|---|
| 0:15 | "Help! My dad just collapsed, he's not breathing!" | — |
| 0:18 | | "Call 911 now and put it on speaker!…" |
| 0:24 | | "Place the heel of one hand…" |
| 0:31 | | "Push hard and fast to this beat…" · metronome starts |
| 0:43 | | "Keep pushing to the beat…" |
| 0:45 | "He's gasping! Is he breathing again?" | the line steps back while they talk |
| 0:47 | | **alert cuts in**: "Do not stop. Gasping is agonal breathing…" |
| 0:54 | | the cut line replays |
| 1:00 | | "If anyone is with you, send them to find an AED…" |
| 1:08 | "I heard a crack in his chest!…" | |
| 1:11 | | "A rib pop can happen during effective CPR…" |

Real timings will differ a little. That's fine: the script has ~30 s spare.

### 2 · Speed and safety close-up (1:35–1:51, 16 s)

- The **latency pill**, large
- The **rescue timeline / event log** scrolling back through the run
- Optional: one unscripted question answered live

### 3 · Paramedics arrive (1:51–2:15, 24 s)

- Caller: "The paramedics are here!" → **timers freeze**, compression count shown
- **EMS handoff card** fills the screen
- The agent's grounding line plays in the same voice ("The paramedics are in
  charge now…")

## Hooks the dashboard can use

The audio controller already emits what the screen needs — no polling:

| Screen element | Controller |
|---|---|
| 3D hands on the beat | `audio.beatPhase()` → `{ index, phase }`, read it every frame |
| Hand placement highlight, alert callout | `clipstart` / `clipend` events, `detail.id` (e.g. `cpr_03_position`, `cpr_02_agonal`) |
| Captions | `clipstart` `detail.text` |
| Latency pill | `clipstart` `detail.latencyMs` (protocol) and the live answer timing |
| "App is speaking" indicator | `gate` event, `detail.gated` |

## How to record

- Screen at **1920×1080 or larger**, browser zoom **125%+**, cursor hidden
- Dark theme, no browser bars (full-screen or kiosk window)
- System sound captured together with the picture (the metronome must be in
  the recording)
- The laptop mic hears its own speakers: run `leak-test.html` once in the
  recording room first
- Record **two full takes**, keep the better one uncut

## Deadline

The hackathon closes **Sep 30, 18:00 EEST**. The edit takes about a day once the
footage exists, so the dashboard shots are needed by **Sep 27** to submit
comfortably on Sep 28–29.
