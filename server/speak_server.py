#!/usr/bin/env python3
"""Local server for the bench: serves web/ and the /speak router on one origin.

    pip install -r server/requirements.txt
    python3 server/speak_server.py        # → http://localhost:8766
    python3 server/speak_server.py --port 8767

The team backend doesn't need this file — it includes `speak_router` instead
(see server/INTEGRATION.md). The ElevenLabs key comes from .env. The server binds
to localhost only: on the network, anyone could spend the credits.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "server"))
import render_directives as rd  # noqa: E402  (.env loading)
from speak_router import make_speak_router  # noqa: E402

rd.load_dotenv()
KEY = os.environ.get("ELEVENLABS_API_KEY")

# The live voice is whatever the clips were rendered with, so it matches them by
# construction: re-render the clips with another voice and this follows.
SPEC = json.loads((ROOT / "web" / "audio" / "manifest.json").read_text())["spec"]

app = FastAPI(title="KeepAlive speak")
speak = make_speak_router(api_key=KEY, voice_id=SPEC["voice_id"], model_id=SPEC["model_id"],
                          voice_settings=SPEC["voice_settings"], log=lambda m: print(m, flush=True))
app.include_router(speak)
app.get("/health")(speak.health)
# After the API routes, so /speak and /health win.
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser(description="KeepAlive bench + /speak")
    ap.add_argument("--port", type=int, default=8766)
    port = ap.parse_args().port
    if not KEY:
        print("warning: no ELEVENLABS_API_KEY in .env — /speak will return 500", file=sys.stderr)
    uvicorn.run(app, host="127.0.0.1", port=port)
