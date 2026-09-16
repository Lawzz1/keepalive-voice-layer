#!/usr/bin/env python3
"""
keep-Alive — pre-rendered voice directive generator.

Renders the deterministic BLS protocol lines, normalises them to the team audio
spec (48 kHz / 16-bit mono, -14 LUFS, True Peak -1.0 dBTP) and writes a manifest
the browser audio controller (web/audio-controller.js) loads at startup.

Modes:

    voices       list the voices on your ElevenLabs account
    audition     render the 3 test lines across several candidate voices, so you
                 can A/B them through a phone speaker before committing
    render       render the full 10-clip protocol set with the chosen voice
    placeholder  render the full set with macOS `say` — no API key needed, lets the
                 controller run end-to-end before the voice is chosen
    voiceover    render the demo video narration (a different voice from the app)

Requirements:
    pip install requests
    ffmpeg + ffprobe on PATH

Usage:
    export ELEVENLABS_API_KEY=...

    python tools/render_directives.py voices
    python tools/render_directives.py audition --voices VOICE_A VOICE_B VOICE_C
    python tools/render_directives.py render --voice-id VOICE_A
    python tools/render_directives.py render --voice-id VOICE_A --only cpr_02_agonal
    python tools/render_directives.py placeholder
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "web" / "audio"
AUDITION_DIR = ROOT / "web" / "audition"   # served next to web/audition.html
VOICEOVER_DIR = ROOT / "video" / "voiceover"

API_BASE = "https://api.elevenlabs.io/v1"

# Low-latency model — the same one the live micro-Q&A path will use, so the
# pre-rendered lines and the live ones sound like the same voice.
MODEL_ID = "eleven_flash_v2_5"

# Team audio spec (Rana, Sep 10)
TARGET_LUFS = -14.0
TARGET_TP = -1.0
TARGET_LRA = 7.0
SAMPLE_RATE = 48000
CHANNELS = 1

# TTS output starts with 50-150 ms of silence. On a critical line that is dead
# air after the interrupt, so trim both ends, keeping a hair of room tone.
TRIM = (
    "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.02,"
    "areverse,"
    "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.08,"
    "areverse"
)

# Voice settings tuned for an emergency dispatcher read: steady, low expression,
# slightly slower than default. Style at 0 keeps the model from acting.
VOICE_SETTINGS = {
    "stability": 0.75,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
    "speed": 0.95,
}

# priority levels consumed by the audio controller:
#   critical  interrupts whatever is playing, jumps the queue
#   normal    queued, ducks the metronome while it plays
#   response  answer to a user question, plays over the beat, never queued behind
#             a protocol line (if one is playing it waits, but only for that one)
DIRECTIVES = [
    {
        "id": "cpr_01_confirm",
        "priority": "normal",
        # AHA: call emergency services first. Wording from Rana, Sep 16.
        "text": "Call 911 now and put it on speaker! Roll the patient flat on their back. "
                "Kneel beside their chest.",
    },
    {
        "id": "cpr_02_agonal",
        "priority": "critical",
        "text": "Do not stop. Gasping is agonal breathing, not normal breathing. "
                "Kneel beside their chest immediately.",
    },
    {
        "id": "cpr_03_position",
        "priority": "normal",
        "text": "Place the heel of one hand on the center of the chest. "
                "Interlock your other hand on top. Lock your elbows straight.",
    },
    {
        "id": "cpr_04_start_beat",
        "priority": "normal",
        "text": "Push hard and fast to this beat. Push down two inches, "
                "then let the chest come all the way up. One, two, three, four.",
    },
    {
        "id": "cpr_05_recoil",
        "priority": "normal",
        "text": "Keep pushing to the beat. Allow full chest recoil. "
                "Do not lean on the chest.",
    },
    {
        # AHA: get an AED as early as possible. Proposed Sep 16, not yet confirmed with Rana.
        "id": "cpr_07_aed",
        "priority": "normal",
        "text": "If anyone is with you, send them to find an AED right now. "
                "Do not stop pushing.",
    },
    {
        "id": "cpr_06_paramedics",
        "priority": "normal",
        "text": "Stop compressions and step back. Let the paramedics take over. "
                "The emergency timeline is saved on your screen. "
                "Take a slow, deep breath.",
    },
    {
        "id": "qa_rib_pop",
        "priority": "response",
        "text": "A rib pop can happen during effective CPR. "
                "Do not stop, keep pushing to the beat.",
    },
    {
        "id": "qa_bed_surface",
        "priority": "response",
        "text": "Move them to a firm floor if you can do so safely. Then resume pushing.",
    },
    {
        "id": "qa_vomit",
        "priority": "response",
        "text": "Roll them onto their side, clear the mouth, roll them back "
                "and immediately resume compressions.",
    },
    {
        "id": "qa_fallback",
        "priority": "response",
        "text": "Continue chest compressions to the beat. "
                "Emergency services will guide further.",
    },
]

# Demo video narration (docs/demo-voiceover.md). Not played by the app, so no
# need to match the live agent: a higher-quality model and a little more life
# than the dispatcher read.
NARRATOR_MODEL_ID = "eleven_multilingual_v2"
NARRATOR_SETTINGS = {
    "stability": 0.55,
    "similarity_boost": 0.75,
    "style": 0.15,
    "use_speaker_boost": True,
    "speed": 1.0,
}

VOICEOVER = [
    {
        "id": "vo_01_hook",
        "text": "Your hands are busy saving a life. "
                "Why does emergency software require your hands?",
    },
    {
        "id": "vo_02_stat",
        "text": "Every year, over 350,000 Americans have a cardiac arrest outside a hospital. "
                "Most don't survive.",
    },
    {
        "id": "vo_03_architecture",
        # "Assembly A.I." with dots: the model stresses "A.I." instead of running it together
        "text": "Assembly A.I. provides the ears, but it never makes the medical decision. "
                "Every critical step comes from a locked protocol.",
    },
    {
        "id": "vo_04_hybrid",
        "text": "Protocol lines play in milliseconds. Questions nobody scripted go to "
                "Assembly A.I.'s Voice Agent API, which answers in about a second. "
                "And the metronome never stops.",
    },
    {
        "id": "vo_05_close",
        "text": "KeepAlive. When seconds count, your hands should save a life, "
                "not hold a phone.",
    },
]

# Short, long, critical — covers the three reads you need to judge a voice on.
AUDITION_LINES = [
    ("short", "Roll the patient flat on their back now."),
    ("long", "Place the heel of one hand on the center of the chest. "
             "Interlock your other hand on top. Lock your elbows straight."),
    ("alert", "Do not stop. Gasping is agonal breathing, not normal breathing."),
]


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def check_tools():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            die(f"{tool} not found on PATH — install ffmpeg first")


def load_dotenv():
    """KEY=value lines from .env in the repo root, so the API key never has to be
    typed into a terminal or pasted into a chat. Real environment variables win."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        die(f"no ELEVENLABS_API_KEY — put ELEVENLABS_API_KEY=... in {ROOT / '.env'}")
    return key


def fetch_voices():
    r = requests.get(f"{API_BASE}/voices", headers={"xi-api-key": api_key()}, timeout=30)
    if r.status_code != 200:
        die(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    return r.json().get("voices", [])


def list_voices():
    for v in fetch_voices():
        labels = v.get("labels") or {}
        tags = ", ".join(f"{k}={val}" for k, val in labels.items())
        print(f"{v['voice_id']}  {v['name']:<22} {v.get('category') or '':<13} {tags}")


# --- synthesis engines -------------------------------------------------------
# Each engine is a function (text, tmp_dir) -> path of the raw audio it wrote.

def elevenlabs_engine(voice_id, model_id=MODEL_ID, settings=VOICE_SETTINGS, retries=3):
    url = f"{API_BASE}/text-to-speech/{voice_id}"
    headers = {"xi-api-key": api_key(), "Content-Type": "application/json"}

    def synth(text, tmp_dir):
        payload = {"text": text, "model_id": model_id, "voice_settings": settings}
        for attempt in range(1, retries + 1):
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                path = tmp_dir / "raw.mp3"
                path.write_bytes(r.content)
                return path
            if r.status_code in (429, 500, 502, 503) and attempt < retries:
                wait = 2 ** attempt
                print(f"    {r.status_code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            die(f"ElevenLabs {r.status_code}: {r.text[:300]}")

    return synth


def say_engine(voice=None, rate=165):
    if shutil.which("say") is None:
        die("placeholder mode needs macOS `say`")

    def synth(text, tmp_dir):
        path = tmp_dir / "raw.aiff"
        cmd = ["say", "-r", str(rate), "-o", str(path)]
        if voice:
            cmd += ["-v", voice]
        subprocess.run(cmd + [text], check=True)
        return path

    return synth


# --- loudness ----------------------------------------------------------------

def measure_loudness(path, pre=None):
    """loudnorm analysis pass — returns the measured values as a dict."""
    chain = f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json"
    if pre:
        chain = f"{pre},{chain}"
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-i", str(path),
        "-af", chain,
        "-f", "null", "-",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True).stderr
    start = out.rfind("{")
    end = out.rfind("}")
    if start == -1 or end == -1:
        die(f"could not parse loudnorm output for {path}")
    return json.loads(out[start:end + 1])


def apply_gain_limit(src, dst, gain_db, ceiling_db):
    """Trim, gain, then a peak limiter run at 4x oversampling so it catches
    inter-sample peaks too — close enough to a true-peak limiter."""
    limit = 10 ** (ceiling_db / 20)
    flt = (
        f"{TRIM},"
        f"aresample={SAMPLE_RATE * 4},"
        f"volume={gain_db:.2f}dB,"
        f"alimiter=limit={limit:.4f}:attack=1:release=60:level=disabled,"
        f"aresample={SAMPLE_RATE}"
    )
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-af", flt,
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "-c:a", "pcm_s16le",
        str(dst),
    ]
    subprocess.run(cmd, check=True)


def normalise(src, dst):
    """Hit -14 LUFS / -1 dBTP and return the measured result.

    loudnorm alone can't do it for speech: TTS has a peak-to-loudness ratio of
    15-18 dB and the spec leaves 13, so loudnorm drops out of linear mode and its
    dynamic mode lands 1-1.5 LU short on clips this short. Instead: gain to
    target, limit the peaks, re-measure, and nudge the gain until it converges."""
    m = measure_loudness(src, pre=TRIM)
    gain = TARGET_LUFS - float(m["input_i"])
    margin = 0.3
    for _ in range(6):
        apply_gain_limit(src, dst, gain, TARGET_TP - margin)
        got = measure_loudness(dst)
        lufs, tp = float(got["input_i"]), float(got["input_tp"])
        if tp > TARGET_TP:
            margin += 0.2
            continue
        err = TARGET_LUFS - lufs
        if abs(err) <= 0.2:
            break
        gain += err
    return lufs, tp


def duration_ms(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    return int(round(float(out) * 1000))


def render_one(text, synth, out_path):
    """Synthesise, normalise, and report the written file against the spec."""
    with tempfile.TemporaryDirectory() as tmp:
        raw = synth(text, Path(tmp))
        lufs, tp = normalise(raw, out_path)
    ms = duration_ms(out_path)
    flag = ""
    if abs(lufs - TARGET_LUFS) > 0.5 or tp > TARGET_TP:
        flag = "   <-- off spec"
    print(f"  {out_path.name:<28} {ms / 1000:5.1f}s  {lufs:6.1f} LUFS  {tp:5.1f} dBTP{flag}")
    return ms


# --- commands ----------------------------------------------------------------

def cmd_audition(args):
    """Render the audition lines per voice and keep a manifest that
    web/audition.html plays through the real controller, metronome underneath.
    Re-running with other voices adds them to the same page."""
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    known = {v["voice_id"]: v for v in fetch_voices()}
    missing = [v for v in args.voices if v not in known]
    if missing:
        die(f"not on this account: {', '.join(missing)} — `voices` lists what is")

    manifest_path = out_dir / "manifest.json"
    manifest = {"voices": {}, "clips": {}}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    for voice_id in args.voices:
        v = known[voice_id]
        print(f"{v['name']}  ({voice_id})")
        manifest["voices"][voice_id] = {
            "name": v["name"],
            "category": v.get("category"),
            "labels": v.get("labels") or {},
        }
        synth = elevenlabs_engine(voice_id)
        for tag, text in AUDITION_LINES:
            clip_id = f"{voice_id}__{tag}"
            ms = render_one(text, synth, out_dir / f"{clip_id}.wav")
            manifest["clips"][clip_id] = {
                "file": f"{clip_id}.wav",
                "text": text,
                "priority": "normal",
                "duration_ms": ms,
                "voice_id": voice_id,
                "tag": tag,
            }

    manifest["spec"] = {
        "engine": "elevenlabs",
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS,
        "lufs": TARGET_LUFS,
        "true_peak_dbtp": TARGET_TP,
        "sample_rate": SAMPLE_RATE,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\n{len(manifest['voices'])} voices ready — open http://localhost:8765/audition.html")
    print("Listen on the demo laptop's speakers, at demo volume, from where the audience sits.")


def write_clips(out_dir, targets, synth, engine_spec, merge):
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"

    manifest = {"spec": {}, "clips": {}}
    if merge and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        old = manifest.get("spec", {})
        old_voice = (old.get("engine"), old.get("voice_id"))
        new_voice = (engine_spec["engine"], engine_spec["voice_id"])
        if old_voice != new_voice:
            die(f"manifest was rendered with {old_voice[0]}:{old_voice[1]} — "
                f"re-render the full set instead of mixing voices")

    for d in targets:
        filename = f"{d['id']}.wav"
        ms = render_one(d["text"], synth, out_dir / filename)
        manifest["clips"][d["id"]] = {
            "file": filename,
            "text": d["text"],
            "priority": d.get("priority", "narration"),
            "duration_ms": ms,
        }

    manifest["spec"] = {
        **engine_spec,
        "lufs": TARGET_LUFS,
        "true_peak_dbtp": TARGET_TP,
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "format": "wav_pcm_s16le",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    total = sum(c["duration_ms"] for c in manifest["clips"].values())
    print(f"\n{len(manifest['clips'])} clips, {total / 1000:.1f}s total")
    print(f"manifest: {manifest_path}")


def cmd_render(args):
    targets = DIRECTIVES
    if args.only:
        targets = [d for d in DIRECTIVES if d["id"] in args.only]
        missing = set(args.only) - {d["id"] for d in targets}
        if missing:
            die(f"unknown id(s): {', '.join(sorted(missing))}")

    engine_spec = {
        "engine": "elevenlabs",
        "voice_id": args.voice_id,
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS,
    }
    write_clips(Path(args.out), targets, elevenlabs_engine(args.voice_id),
                engine_spec, merge=bool(args.only))


def cmd_placeholder(args):
    engine_spec = {"engine": "say", "voice_id": args.say_voice or "system-default"}
    write_clips(Path(args.out), DIRECTIVES, say_engine(args.say_voice),
                engine_spec, merge=False)


def cmd_voiceover(args):
    engine_spec = {
        "engine": "elevenlabs",
        "voice_id": args.voice_id,
        "model_id": NARRATOR_MODEL_ID,
        "voice_settings": NARRATOR_SETTINGS,
    }
    targets = VOICEOVER
    if args.only:
        targets = [d for d in VOICEOVER if d["id"] in args.only]
        missing = set(args.only) - {d["id"] for d in targets}
        if missing:
            die(f"unknown id(s): {', '.join(sorted(missing))}")
    synth = elevenlabs_engine(args.voice_id, NARRATOR_MODEL_ID, NARRATOR_SETTINGS)
    write_clips(Path(args.out), targets, synth, engine_spec, merge=bool(args.only))


def main():
    p = argparse.ArgumentParser(description="keep-Alive directive renderer")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_voices = sub.add_parser("voices", help="list available voices")
    p_voices.set_defaults(func=lambda a: list_voices(), needs_ffmpeg=False)

    p_aud = sub.add_parser("audition", help="render 3 test lines per candidate voice")
    p_aud.add_argument("--voices", nargs="+", required=True, metavar="VOICE_ID")
    p_aud.add_argument("--out", default=str(AUDITION_DIR))
    p_aud.set_defaults(func=cmd_audition, needs_ffmpeg=True)

    p_ren = sub.add_parser("render", help="render the full protocol set")
    p_ren.add_argument("--voice-id", required=True)
    p_ren.add_argument("--only", nargs="+", metavar="ID",
                       help="re-render only these clip ids")
    p_ren.add_argument("--out", default=str(AUDIO_DIR))
    p_ren.set_defaults(func=cmd_render, needs_ffmpeg=True)

    p_ph = sub.add_parser("placeholder", help="render the full set with macOS `say`")
    p_ph.add_argument("--say-voice", help="macOS voice name (see `say -v '?'`)")
    p_ph.add_argument("--out", default=str(AUDIO_DIR))
    p_ph.set_defaults(func=cmd_placeholder, needs_ffmpeg=True)

    p_vo = sub.add_parser("voiceover", help="render the demo video narration")
    p_vo.add_argument("--voice-id", required=True, help="narrator voice — not the app's voice")
    p_vo.add_argument("--only", nargs="+", metavar="ID",
                      help="re-render only these lines; the others keep their take")
    p_vo.add_argument("--out", default=str(VOICEOVER_DIR))
    p_vo.set_defaults(func=cmd_voiceover, needs_ffmpeg=True)

    args = p.parse_args()
    load_dotenv()
    if args.needs_ffmpeg:
        check_tools()
    args.func(args)


if __name__ == "__main__":
    main()
