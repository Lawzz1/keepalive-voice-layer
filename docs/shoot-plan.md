# Shoot plan — Sep 25–26

One evening of filming, two people: a rescuer on camera (Lev, who also speaks the
caller lines) and a second person lying on the floor as the patient. Everything
below was rehearsed against the live server on Sep 22; the phrases are tested,
not guessed.

## Before anyone lies down

- **Run the leak test in the actual room** (`web/leak-test.html`). The laptop mic
  hears its own speakers, and a hard floor reflects more than the room we
  measured in. Two minutes, and it tells us whether the mic gate needs changing.
- **Turn the ntfy relay off.** `NTFY_TOPIC` has a hardcoded default, so every
  dispatch sends a real push. Set it empty before recording.
- **Silence everything else**: phone on do-not-disturb, notifications off, other
  tabs closed. A notification chime in the one good take is a reshoot.
- **Screen recording at 1920×1080 or larger**, system audio captured with the
  picture, cursor hidden, browser in full screen with no bars.
- **Charge both cameras.** The phone films the room; the laptop records itself.

## The caller lines — say them in this order

Tested against the live router: every one of them locks the protocol with
confidence 1.00, including with an accent and a dropped word.

| # | Say this | What should happen |
|---|---|---|
| 1 | "Help! My dad just collapsed, he is not breathing!" | PROTOCOL LOCKED, step 1 speaks |
| 2 | "Hands are placed on the center of his chest." | step 2 speaks |
| 3 | "Ready to compress." | step 3 speaks, metronome starts |
| 4 | "I heard a crack in his chest, did I break a rib?" | companion answers over the beat |
| 5 | "My arms are burning, I cannot push anymore." | companion answers, swap prompt |
| 6 | "The paramedics are here!" | timers freeze, handoff card |

Say them **loudly and slowly**, one sentence at a time, and wait for the app to
finish speaking before the next one. The words that carry the meaning are
*collapsed*, *breathing*, *crack / rib*, *paramedics* — land those clearly and
the rest can be imperfect.

**Press Reset before every take.** The session keeps its state between runs: in
rehearsal the agonal flag stayed on from an earlier phrase and the companion went
silent because the protocol was already finished. A stale session is the most
likely reason a take fails.

## Shots, in filming order

Film the room first while everyone is fresh, then the screen.

**1 · The opening, 8–10 s.** A person on the floor, seen from above, not moving.
The laptop beside them, screen on. No faces of the patient in focus — shoot from
the chest up to the shoulders. This is the shot that says the app is for a real
room, not a browser tab.

**2 · Hands on the chest, 30 s, looped later.** Very close, from the side, hands
interlocked on the sternum, pushing to the app's metronome so the rhythm in the
picture matches the clicks in the sound. Dark blanket or floor underneath, light
from a window or one lamp to the side. This clip also replaces the third-party
animation inside the cockpit, so shoot it clean and steady — phone on a stack of
books, not handheld.

**3 · The live run, one take, twice.** Screen recording, the six lines above,
no cuts. The second take is insurance, not a better version: keep going even if
something goes slightly wrong, because a real run with a small stumble is more
convincing than a perfect one that looks staged.

**4 · Close-ups from the screen, 5 s each.** The 110 BPM ring pulsing. The depth
gauge. The latency line. The SIMULATED 911 CAD label. The EMS handoff card. Shoot
these after the run, with the app in the right state, so we can cut to them
during editing without pausing the run.

**5 · The rescuer, 5 s.** Hands busy on the chest, eyes on the patient, never
touching the laptop. That is the whole pitch in one frame.

## What must be visible on the screen during the run

- the live transcript appearing as the caller speaks
- PROTOCOL LOCKED the moment the emergency is recognised
- the SIMULATED 911 CAD label wherever dispatch appears
- the 110 BPM ring and the depth gauge during compressions
- the latency numbers
- a clock or timer, so the run is visibly unedited

## After filming

- Copy everything off the devices the same evening, twice, to two places.
- The 30 s hands loop goes to Rana for `client/public/videos/`, replacing the
  animation with unknown licensing.
- Editing follows `video/assets/EDIT_PLAN.md`; the narration is already recorded.

## If the voice PRs are not merged by the morning of Sep 25

Then the app on camera speaks with the browser's synthetic voice, and the video
shows a product we would rather not show. Ask Rana directly for a merge before
filming. Do not film from a private build that the judges cannot reach — the
video has to match what the live link does.
