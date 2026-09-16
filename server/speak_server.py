#!/usr/bin/env python3
"""Reference /speak endpoint: agent text → safety gate → the app's voice → PCM stream.

Not the team backend: a working reference for it, and a way to test the whole
one-voice path from the bench. It also serves web/, so the bench and the API
share one origin.

    pip install -r server/requirements.txt
    python3 server/speak_server.py        # → http://localhost:8766

The ElevenLabs key comes from .env and never leaves this process. The server
binds to localhost only: on the network, anyone could spend the credits.
"""

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "server"))
import render_directives as rd  # noqa: E402  (.env loading, API base URL)
from safety_gate import gate  # noqa: E402

rd.load_dotenv()
KEY = os.environ.get("ELEVENLABS_API_KEY")

# The live voice is whatever the clips were rendered with, so it matches them by
# construction: re-render the clips with another voice and this follows.
SPEC = json.loads((ROOT / "web" / "audio" / "manifest.json").read_text())["spec"]
VOICE_ID = SPEC["voice_id"]
MODEL_ID = SPEC["model_id"]
VOICE_SETTINGS = SPEC["voice_settings"]
SAMPLE_RATE = 24000
AUDIO_FORMAT = f"pcm_s16le;rate={SAMPLE_RATE};channels=1"

app = FastAPI(title="KeepAlive speak")


class SpeakRequest(BaseModel):
    text: str
    protocol_state: str = "active"  # active | handoff | idle


@app.get("/health")
def health():
    return {"voice_id": VOICE_ID, "model_id": MODEL_ID, "engine": SPEC.get("engine"), "key": bool(KEY)}


@app.post("/speak")
def speak(req: SpeakRequest):
    if not KEY:
        raise HTTPException(500, "ELEVENLABS_API_KEY missing in .env")
    result = gate(req.text, req.protocol_state)
    if result.action == "replaced":
        print(f"[gate] replaced ({result.reason}): {req.text!r}", flush=True)

    t0 = time.perf_counter()
    upstream = requests.post(
        f"{rd.API_BASE}/text-to-speech/{VOICE_ID}/stream",
        params={"output_format": f"pcm_{SAMPLE_RATE}"},
        headers={"xi-api-key": KEY},
        json={"text": result.text, "model_id": MODEL_ID, "voice_settings": VOICE_SETTINGS},
        stream=True,
        timeout=30,
    )
    if upstream.status_code != 200:
        detail = upstream.text[:300]
        upstream.close()
        raise HTTPException(502, f"ElevenLabs {upstream.status_code}: {detail}")
    upstream_ms = round((time.perf_counter() - t0) * 1000)

    def body():
        try:
            for chunk in upstream.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        finally:
            upstream.close()  # also when the browser cancels: a critical line cut the answer

    return StreamingResponse(
        body(),
        media_type="application/octet-stream",
        headers={
            "X-Audio-Format": AUDIO_FORMAT,
            "X-Spoken-Text": quote(result.text),
            "X-Gate": result.action,
            "X-Gate-Reason": result.reason,
            "X-Upstream-Ms": str(upstream_ms),
            "Cache-Control": "no-store",
        },
    )


# After the API routes, so /speak and /health win.
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    if not KEY:
        print("warning: no ELEVENLABS_API_KEY in .env — /speak will return 500", file=sys.stderr)
    uvicorn.run(app, host="127.0.0.1", port=8766)
