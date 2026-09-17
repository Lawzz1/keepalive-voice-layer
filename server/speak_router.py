"""POST /speak as a FastAPI router: agent text → safety gate → the app's voice → PCM stream.

Drop it into any FastAPI app:

    from speak_router import SARAH, make_speak_router
    app.include_router(make_speak_router(api_key=os.environ["ELEVENLABS_API_KEY"], **SARAH))

The response is raw little-endian PCM16, 24 kHz, mono (`application/octet-stream`);
the browser plays it with `audio.playPcmResponse(res)`. The ElevenLabs key never
leaves the server. One pooled HTTPS connection to ElevenLabs is kept warm, so an
answer skips the TCP + TLS handshake (median 244 → 141 ms, measured Sep 17).
"""

import threading
import time
from urllib.parse import quote

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from safety_gate import gate

API_BASE = "https://api.elevenlabs.io/v1"
SAMPLE_RATE = 24000
AUDIO_FORMAT = f"pcm_s16le;rate={SAMPLE_RATE};channels=1"

# The voice, model and settings the protocol clips were rendered with. Live answers
# must use exactly these, or the app stops sounding like one voice.
# (test_speak_router.py checks this against web/audio/manifest.json.)
SARAH = {
    "voice_id": "EXAVITQu4vr4xnSDxMaL",
    "model_id": "eleven_flash_v2_5",
    "voice_settings": {
        "stability": 0.75,
        "similarity_boost": 0.75,
        "style": 0.0,
        "use_speaker_boost": True,
        "speed": 0.95,
    },
}


class SpeakRequest(BaseModel):
    text: str
    protocol_state: str = "active"  # active | handoff | idle


def make_speak_router(api_key, voice_id, model_id, voice_settings, warm_every_s=45, log=print):
    router = APIRouter()
    http = requests.Session()
    http.mount("https://", requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=8))
    state = {"last_warm_ms": None}

    def keep_warm():
        # A light request now and then, so the pooled connection doesn't go stale
        # while the rescuer is quiet. A keep-alive, for KeepAlive.
        while True:
            t0 = time.perf_counter()
            try:
                http.get(f"{API_BASE}/voices/{voice_id}", headers={"xi-api-key": api_key}, timeout=10).close()
                state["last_warm_ms"] = round((time.perf_counter() - t0) * 1000)
            except requests.RequestException:
                state["last_warm_ms"] = None
            time.sleep(warm_every_s)

    if api_key and warm_every_s:
        threading.Thread(target=keep_warm, daemon=True).start()

    @router.get("/speak/health")
    def health():
        return {"voice_id": voice_id, "model_id": model_id, "key": bool(api_key),
                "last_warm_ms": state["last_warm_ms"]}

    @router.post("/speak")
    def speak(req: SpeakRequest):
        if not api_key:
            raise HTTPException(500, "ELEVENLABS_API_KEY missing")
        result = gate(req.text, req.protocol_state)
        if result.action == "replaced":
            log(f"[gate] replaced ({result.reason}): {req.text!r}")

        t0 = time.perf_counter()
        for attempt in (1, 2):
            try:
                upstream = http.post(
                    f"{API_BASE}/text-to-speech/{voice_id}/stream",
                    params={"output_format": f"pcm_{SAMPLE_RATE}"},
                    headers={"xi-api-key": api_key},
                    json={"text": result.text, "model_id": model_id, "voice_settings": voice_settings},
                    stream=True,
                    timeout=30,
                )
                break
            except requests.ConnectionError as err:
                # the pooled connection was closed on the other side: one retry on a fresh one
                if attempt == 2:
                    raise HTTPException(502, f"ElevenLabs unreachable: {err}")
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
                "X-Spoken-Text": quote(result.text),  # what is actually said: use it for captions and the echo filter
                "X-Gate": result.action,
                "X-Gate-Reason": result.reason,
                "X-Upstream-Ms": str(upstream_ms),
                "Cache-Control": "no-store",
            },
        )

    router.health = health
    return router
