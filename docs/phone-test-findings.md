# Phone test — what I found, Sep 25

Ran the live site on a real phone this evening, the way a judge would. Two
findings: one I fixed, one that needs you.

## 1 · Fixed in PR #3 — the EMS briefing spoke with the browser voice

Open the handover card, press **Read Aloud**, and the briefing came out in the
browser's Google voice while everything else in the app spoke with the human one.
The one moment a paramedic listens to the app was the one moment it sounded like
a robot.

`EMSHandoverModal.jsx` calls `window.speechSynthesis` directly, so it never went
through the path PR #1 and #2 added. My miss — I patched the hook and forgot the
modal.

**Also fixed while I was in there.** Routing the briefing through `/speak`
revealed that the safety gate was trimming it to three sentences and dropping the
last line — *"Public access AED was deployed."* That cap exists to stop the model
rambling at the rescuer after the event, but the handover report is built from the
incident log, and the fact that an AED was used is something the paramedic needs.
So there is now a `briefing` state: the forbidden phrases still apply — doses,
"he's dead", "don't call" — and the length cap does not.

The Read Aloud button can also stop mid-sentence now; the stream is cancelled
instead of being left to play out.

Verified against your backend, locally:

| | |
|---|---|
| `POST /speak` (`protocol_state=briefing`) | 200 |
| gate | passed, all four sentences intact |
| ElevenLabs upstream | 132 ms |
| tests | 60/60 unittest, 32 pytest |

## 2 · Needs you — the screen goes dark during a run

I opened the site on a phone, started the flow with a judge pill, put the phone
down and did not touch it. **Dark in under a minute.**

The wake-lock hook itself is written correctly — it requests `screen`, tracks the
release and re-acquires. The problem is the call site: in the built bundle it
reads `fe(e||pe||j||v&&!g)`, and during a run none of those flags is true. It
looks tied to the microphone path, which is not the path a judge uses.

Two changes, both small:

1. **Request the lock when the protocol locks**, or when the first directive
   plays — not only on the mic path.
2. **Re-acquire it on `visibilitychange`.** The browser releases the sentinel
   whenever the page is hidden or the screen dims once, and it does not come back
   on its own. So even where it works today, it stops working the first time
   someone switches apps and comes back.

This is the detail the whole pitch rests on: a phone lying on the floor while the
rescuer's hands are busy. A judge who puts the phone down and watches the screen
go dark sees the story break in front of them — and it is the kind of thing they
remember when scoring.

## Smaller things from the same session

- `viewport-fit=cover` is set, but there is no `safe-area-inset` anywhere in the
  CSS, so the bottom of the page can sit under the iPhone home indicator.
- On a 375 px screen only three of the judge pills are reachable; **Auto-Run** and
  **Reset** are further along a horizontal scroll inside that strip, which a judge
  is unlikely to discover.

Neither blocks filming. The wake lock does.
