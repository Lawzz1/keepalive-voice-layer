"""/speak without the network: a fake ElevenLabs stands in for the real one."""

import json
from pathlib import Path
from urllib.parse import unquote

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from safety_gate import FALLBACK_ACTIVE
from speak_router import SARAH, make_speak_router

MANIFEST = Path(__file__).resolve().parent.parent / "web" / "audio" / "manifest.json"
PCM = b"\x01\x00" * 4800  # 0.2 s of 24 kHz PCM16


class FakeUpstream:
    status_code = 200
    text = ""

    def iter_content(self, chunk_size):
        for i in range(0, len(PCM), chunk_size):
            yield PCM[i:i + chunk_size]

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    sent = []

    def fake_post(self, url, **kw):
        sent.append({"url": url, **kw})
        return FakeUpstream()

    monkeypatch.setattr(requests.Session, "post", fake_post)
    app = FastAPI()
    app.include_router(make_speak_router(api_key="test-key", warm_every_s=0, log=lambda m: None, **SARAH))
    c = TestClient(app)
    c.sent = sent
    return c


def test_passes_and_streams_pcm(client):
    r = client.post("/speak", json={"text": "No, nothing by mouth.", "protocol_state": "active"})
    assert r.status_code == 200
    assert r.content == PCM
    assert r.headers["X-Gate"] == "closing_added"
    assert unquote(r.headers["X-Spoken-Text"]) == "No, nothing by mouth. Keep pushing to the beat."
    assert r.headers["X-Audio-Format"] == "pcm_s16le;rate=24000;channels=1"
    upstream = client.sent[0]
    assert upstream["params"] == {"output_format": "pcm_24000"}
    assert upstream["json"]["text"] == "No, nothing by mouth. Keep pushing to the beat."
    assert upstream["headers"]["xi-api-key"] == "test-key"


def test_forbidden_text_never_reaches_elevenlabs(client):
    r = client.post("/speak", json={"text": "Give him 0.3 mg of epinephrine."})
    assert (r.headers["X-Gate"], r.headers["X-Gate-Reason"]) == ("replaced", "dose")
    assert client.sent[0]["json"]["text"] == FALLBACK_ACTIVE


def test_missing_key_is_500():
    app = FastAPI()
    app.include_router(make_speak_router(api_key=None, warm_every_s=0, **SARAH))
    assert TestClient(app).post("/speak", json={"text": "hi"}).status_code == 500


@pytest.mark.skipif(not MANIFEST.exists(), reason="rendered clips not present")
def test_live_voice_matches_the_clips():
    spec = json.loads(MANIFEST.read_text())["spec"]
    assert (spec["voice_id"], spec["model_id"], spec["voice_settings"]) == (
        SARAH["voice_id"], SARAH["model_id"], SARAH["voice_settings"])
