# /speak — integration into the team backend

Three files, no other dependencies than `fastapi` and `requests`:

| File | What |
|---|---|
| `speak_router.py` | `POST /speak` as a FastAPI router, plus `GET /speak/health` |
| `safety_gate.py` | the deterministic text gate (agent-spec section 4) |
| `test_safety_gate.py`, `test_speak_router.py` | 29 tests, no network needed |

## Wire it in

Copy the files next to `main.py`, then:

```python
import os
from speak_router import SARAH, make_speak_router

app.include_router(make_speak_router(api_key=os.environ["ELEVENLABS_API_KEY"], **SARAH))
```

`SARAH` holds the exact voice, model and settings the protocol clips were rendered
with. Keep them as they are: any change and the live answers stop sounding like
the pre-recorded lines.

Run the tests with `python -m pytest -q` from that folder.

## Contract

**Request** — `POST /speak`, JSON:

```json
{ "text": "what the agent wants to say", "protocol_state": "active" }
```

`protocol_state`: `active` during CPR (strict rules), `handoff` or `idle` after.

**Response** — a stream of raw PCM16, little-endian, 24 kHz, mono
(`application/octet-stream`). Headers:

| Header | Meaning |
|---|---|
| `X-Spoken-Text` | URL-encoded text that is actually spoken, after the gate. **Use this for captions and for the echo filter**, not the agent's original text |
| `X-Gate` | `passed`, `closing_added`, `trimmed` or `replaced` |
| `X-Gate-Reason` | why it was replaced: `dose`, `death`, `dont_call`, `stop_compressions`, `pulse_check`, `by_mouth`, `too_long`, `empty` |
| `X-Upstream-Ms` | ElevenLabs response time |
| `X-Audio-Format` | `pcm_s16le;rate=24000;channels=1` |

Browser side (already in `audio-controller.js`):

```js
const res = await fetch('/speak', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ text, protocol_state: 'active' }),
});
await audio.playPcmResponse(res, { text: decodeURIComponent(res.headers.get('X-Spoken-Text')) });
```

A critical clip cuts the answer and the browser stops the download; the router
closes the ElevenLabs stream when that happens.

## The gate

| Rule | When | Result |
|---|---|---|
| a dose (`0.3 mg`, `5 ml`, units…) | always | replaced |
| "he's dead", "can't be saved" | always | replaced |
| "don't call", "no need to call" | always | replaced |
| stop / pause / rest / slow + compressions or pushing ("don't stop" is allowed) | during CPR | replaced |
| check the pulse | during CPR | replaced |
| water, drink, aspirin, pills | during CPR | replaced |
| over 18 words, including the closing | during CPR | replaced |
| no "Keep pushing to the beat." at the end | during CPR | appended |
| more than 3 sentences | after handoff | trimmed to 3 |

The fallback during CPR is *"Keep pushing to the beat. Emergency services will
guide you."* Every replacement is logged — each one is an agent mistake worth
fixing in the prompt.

## The echo filter

The mic stays open while the app speaks, so the backend drops transcripts that
match what the app is saying at that moment. The texts to compare against:

- pre-recorded lines: `web/audio/manifest.json` → `clips[id].text`, or the
  controller's `clipstart` event (`detail.id`, `detail.text`, `detail.startAt`,
  `detail.duration`)
- live answers: the `X-Spoken-Text` header above

## Performance

One pooled HTTPS connection to ElevenLabs, kept warm with a light request every
45 s, one retry on a dropped connection. Measured on a MacBook, Sep 17: ElevenLabs
response median **141 ms** (244 ms without the pooled connection); click → audible
**~0.3 s** end to end.
