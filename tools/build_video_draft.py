#!/usr/bin/env python3
"""Build the demo video's draft kit before the dashboard exists.

    python3 tools/build_video_draft.py

Everything lands in video/assets/:

    audio/         the lines the draft still needed (cached), and the stems:
                   narration, app, caller, metronome — plus the full guide mix
    cards/         1920x1080 title cards, the architecture slide, the end card,
                   and TO RECORD placeholders where dashboard footage will go
    keepalive_audio_draft.mp3      the whole soundtrack, for listening
    keepalive_draft_slideshow.mp4  the cards over that soundtrack, for the team
    EDIT_PLAN.md                   every cue with its timecode

The soundtrack follows docs/demo-voiceover.md and behaves like the controller:
-4 dB metronome duck under the app's lines, a line stepping back -12 dB while
the caller talks, the agonal alert cutting a line that then replays.

The caller is a placeholder voice. In the real video a teammate speaks live.
"""

import html
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "server"))
import render_directives as rd  # noqa: E402
from safety_gate import gate  # noqa: E402

SR = 48000
BPM = 110
CLIPS = ROOT / "web" / "audio"
VO = ROOT / "video" / "voiceover"
ASSETS = ROOT / "video" / "assets"
AUDIO = ASSETS / "audio"
CARDS = ASSETS / "cards"

# Same numbers as web/audio-controller.js
DUCK_DB, DUCK_ATTACK, DUCK_RELEASE = -4, 0.040, 0.150
YIELD_DB, YIELD_ATTACK, YIELD_RELEASE = -12, 0.060, 0.200
CUT_FADE = 0.012
CLICK_HZ, CLICK_PEAK_DB, CLICK_MS, CLICK_DECAY_MS = 3000, -3, 30, 5
REACT = 0.35   # caller stops talking → the app's answer starts

CALLER_VOICE = "TX3LPaxmHKxFdv7VOQHJ"  # Liam — placeholder for the teammate who plays the caller
CALLER_MODEL = "eleven_multilingual_v2"
CALLER_SETTINGS = {"stability": 0.3, "similarity_boost": 0.75, "style": 0.6,
                   "use_speaker_boost": True, "speed": 1.05}

EXTRA = {
    "caller_01": ("caller", "Help! My dad just collapsed, he's not breathing!"),
    "caller_02": ("caller", "He's gasping! Is he breathing again?"),
    "caller_03": ("caller", "I heard a crack in his chest! Did I break his rib?"),
    "caller_04": ("caller", "The paramedics are here!"),
    # Said by the agent after the handoff; in the demo it goes through /speak, so it
    # passes the same gate and comes out in the app's voice.
    "agent_grounding": ("app", gate("The paramedics are in charge now. Take a slow, deep breath "
                                    "with me. You did everything you could.", "handoff").text),
}


# --- audio helpers ---------------------------------------------------------------

_wav_cache = {}


def read_wav(path):
    if path not in _wav_cache:
        with wave.open(str(path)) as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SR, 1, 2):
                raise SystemExit(f"{path}: expected 48 kHz mono 16-bit")
            data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        _wav_cache[path] = data.astype(np.float32) / 32768
    return _wav_cache[path]


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def duck_gain(n, segments, depth_db, attack, release):
    """Per-sample gain: depth_db inside the segments, linear-in-dB ramps at the edges."""
    env = np.zeros(n, np.float32)
    for s, e in segments:
        si, ei = int(s * SR), int(e * SR)
        a, r = max(1, int(attack * SR)), max(1, int(release * SR))
        idx = np.arange(si, min(si + a, n))
        env[idx] = np.minimum(env[idx], depth_db * (idx - si) / a)
        lo, hi = min(si + a, n), min(ei, n)
        env[lo:hi] = np.minimum(env[lo:hi], depth_db)
        idx = np.arange(ei, min(ei + r, n))
        env[idx] = np.minimum(env[idx], depth_db * (1 - (idx - ei) / r))
    return (10 ** (env / 20)).astype(np.float32)


def click_buffer():
    n = int(SR * CLICK_MS / 1000)
    i = np.arange(n)
    x = np.minimum(1, i / (0.001 * SR)) * np.exp(-i / (CLICK_DECAY_MS / 1000 * SR)) * np.sin(2 * np.pi * CLICK_HZ * i / SR)
    return (x / np.abs(x).max() * 10 ** (CLICK_PEAK_DB / 20)).astype(np.float32)


def merge(segments, gap):
    out = []
    for s, e in sorted(segments):
        if out and s - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


# --- step 1: lines the draft still needs -----------------------------------------------

def render_extras():
    AUDIO.mkdir(parents=True, exist_ok=True)
    cache_path = AUDIO / "extras.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    spec = json.loads((CLIPS / "manifest.json").read_text())["spec"]
    voices = {
        "caller": (CALLER_VOICE, CALLER_MODEL, CALLER_SETTINGS),
        "app": (spec["voice_id"], spec["model_id"], spec["voice_settings"]),
    }
    engines = {}
    for cid, (kind, text) in EXTRA.items():
        voice, model, settings = voices[kind]
        out = AUDIO / f"{cid}.wav"
        key = {"text": text, "voice": voice, "model": model}
        if out.exists() and cache.get(cid) == key:
            continue
        if kind not in engines:
            engines[kind] = rd.elevenlabs_engine(voice, model, settings)
        rd.render_one(text, engines[kind], out)
        cache[cid] = key
    cache_path.write_text(json.dumps(cache, indent=2) + "\n")


# --- step 2: the timeline ------------------------------------------------------------

def texts():
    t = {k: v["text"] for k, v in json.loads((CLIPS / "manifest.json").read_text())["clips"].items()}
    t.update({k: v["text"] for k, v in json.loads((VO / "manifest.json").read_text())["clips"].items()})
    t.update({k: v[1] for k, v in EXTRA.items()})
    return t


def build_timeline():
    txt = texts()
    cues = []

    def add(t, track, cid, folder, note=""):
        path = folder / f"{cid}.wav"
        end = t + len(read_wav(path)) / SR
        cue = {"t": t, "end": end, "track": track, "id": cid, "path": path, "text": txt[cid], "note": note}
        cues.append(cue)
        return cue

    def cut(cue, at):
        cue["end"] = at + CUT_FADE
        cue["cut"] = at
        cue["note"] = (cue["note"] + " · " if cue["note"] else "") + "cut by the agonal alert"

    metro = []

    # 0:00 hook
    v1 = add(1.0, "narration", "vo_01_hook", VO)
    v2 = add(v1["end"] + 1.2, "narration", "vo_02_stat", VO)

    # 0:15 live run
    c1 = add(15.0, "caller", "caller_01", AUDIO, "placeholder voice")
    a1 = add(c1["end"] + REACT, "app", "cpr_01_confirm", CLIPS, "protocol locks")
    a3 = add(a1["end"] + 0.25, "app", "cpr_03_position", CLIPS, "SVG manikin: hand placement")
    a4 = add(a3["end"] + 0.25, "app", "cpr_04_start_beat", CLIPS, "metronome starts")
    beat_on = a4["t"]
    a5 = add(a4["end"] + 4.0, "app", "cpr_05_recoil", CLIPS)
    c2 = add(a5["t"] + 1.5, "caller", "caller_02", AUDIO, "placeholder voice · our line steps back")
    cut_at = c2["end"] + REACT
    # like the controller: the alert starts once the cut line has faded out
    alert = add(cut_at + CUT_FADE, "app", "cpr_02_agonal", CLIPS, "critical: cuts the line")
    cut(a5, cut_at)
    a5b = add(alert["end"] + 0.25, "app", "cpr_05_recoil", CLIPS, "replayed after the cut")
    aed = add(a5b["end"] + 1.5, "app", "cpr_07_aed", CLIPS, "pending team OK")
    c3 = add(aed["end"] + 3.0, "caller", "caller_03", AUDIO, "placeholder voice")
    rib = add(c3["end"] + REACT, "app", "qa_rib_pop", CLIPS, "instant pre-recorded answer")
    live_end = max(85.0, rib["end"] + 2.0)
    metro.append((beat_on, live_end))

    # 1:25 architecture, 1:35 hybrid
    v3 = add(live_end + 1.0, "narration", "vo_03_architecture", VO)
    v4 = add(v3["end"] + 3.5, "narration", "vo_04_hybrid", VO)

    # 1:55 paramedics
    ems_scene = max(111.0, v4["end"] + 3.0)
    c4 = add(ems_scene + 3.0, "caller", "caller_04", AUDIO, "placeholder voice")
    a6 = add(c4["end"] + REACT, "app", "cpr_06_paramedics", CLIPS, "timers freeze")
    metro.append((ems_scene, a6["end"]))
    g = add(a6["end"] + 1.0, "app", "agent_grounding", AUDIO, "agent via /speak, same voice")

    # 2:15 close
    v5 = add(max(g["end"] + 3.0, 136.0), "narration", "vo_05_close", VO)
    length = v5["end"] + 4.0

    scenes = [
        ("01_hook", 0.0, v2["t"]),
        ("02_stat", v2["t"], c1["t"]),
        ("03_todo_live_run", c1["t"], live_end),
        ("04_architecture", live_end, v4["t"]),
        ("05_todo_hybrid", v4["t"], ems_scene),
        ("06_todo_paramedics", ems_scene, v5["t"] - 1.0),
        ("07_end", v5["t"] - 1.0, length),
    ]
    return sorted(cues, key=lambda c: c["t"]), metro, scenes, length


# --- step 3: mix -------------------------------------------------------------------

def mix(cues, metro, length):
    n = int(length * SR)
    stems = {k: np.zeros(n, np.float32) for k in ("narration", "app", "caller", "metronome")}
    callers = [(c["t"], c["end"]) for c in cues if c["track"] == "caller"]

    for c in cues:
        x = read_wav(c["path"]).copy()
        if "cut" in c:
            keep = int((c["cut"] - c["t"]) * SR)
            fade = int(CUT_FADE * SR)
            x = x[: keep + fade]
            x[keep:] *= np.linspace(1, 0, len(x) - keep, dtype=np.float32)
        if c["track"] == "app":
            # the caller talks over our line → it steps back (never for the critical alert)
            if c["id"] != "cpr_02_agonal":
                local = [(s - c["t"], e - c["t"]) for s, e in callers if s < c["end"] and e > c["t"]]
                if local:
                    x *= duck_gain(len(x), local, YIELD_DB, YIELD_ATTACK, YIELD_RELEASE)
        i = int(c["t"] * SR)
        stems[c["track"]][i:i + len(x)] += x[: n - i]

    click = click_buffer()
    period = 60 / BPM
    for on, off in metro:
        t = on
        while t < off:
            i = int(t * SR)
            stems["metronome"][i:i + len(click)] += click[: max(0, n - i)]
            t += period
    app_lines = merge([(c["t"], c["end"]) for c in cues if c["track"] == "app"], gap=0.3)
    stems["metronome"] *= duck_gain(n, app_lines, DUCK_DB, DUCK_ATTACK, DUCK_RELEASE)

    for k, x in stems.items():
        write_wav(AUDIO / f"stem_{k}.wav", x)

    total = sum(stems.values())
    with tempfile.NamedTemporaryFile(suffix=".f32") as tmp:
        tmp.write(total.astype("<f4").tobytes())
        tmp.flush()
        for out, codec in ((AUDIO / "guide_mix.wav", ["-c:a", "pcm_s16le"]),
                           (ASSETS / "keepalive_audio_draft.mp3", ["-c:a", "libmp3lame", "-b:a", "192k"])):
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", tmp.name,
                            # sample-peak limiter at -1.5 dBFS keeps true peaks under -1 dBTP
                            "-af", "alimiter=limit=0.84:level=disabled", *codec, str(out)], check=True)


# --- step 4: cards -------------------------------------------------------------------

CARD_CSS = """
* { box-sizing: border-box; margin: 0; }
body { width: 1920px; height: 1080px; background: #0b0d11; color: #e7e9ee;
       font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; display: grid; place-items: center; }
.wrap { width: 1560px; }
.big { font-size: 76px; font-weight: 700; line-height: 1.15; letter-spacing: -0.01em; }
.dim { color: #8b91a0; }
.red { color: #ff4d4f; }
.small { font-size: 30px; color: #8b91a0; margin-top: 40px; }
.todo { border: 4px dashed #ffb14a; border-radius: 28px; padding: 70px 80px; }
.todo .tag { color: #ffb14a; font-size: 30px; font-weight: 700; letter-spacing: .12em; }
.todo h1 { font-size: 64px; margin: 18px 0 30px; }
.todo li { font-size: 32px; line-height: 1.55; color: #c9cdd6; }
.todo .time { font-size: 30px; color: #8b91a0; margin-top: 30px; font-family: Menlo, monospace; }
.flow { display: flex; align-items: center; gap: 22px; margin: 26px 0; }
.box { background: #171a21; border: 2px solid #2b303b; border-radius: 18px; padding: 26px 30px; font-size: 32px;
       text-align: center; min-width: 250px; }
.box b { display: block; font-size: 24px; color: #8b91a0; font-weight: 500; margin-top: 8px; }
.arrow { font-size: 44px; color: #5b6273; }
.lock { border-color: #2ec28a; }
.gate { border-color: #ffb14a; }
.fast { color: #2ec28a; } .slow { color: #ffb14a; }
h2 { font-size: 52px; margin-bottom: 36px; }
"""


def todo(title, items, start, end):
    lis = "".join(f"<li>{html.escape(x)}</li>" for x in items)
    return (f'<div class="wrap todo"><div class="tag">TO RECORD · DASHBOARD FOOTAGE</div>'
            f"<h1>{html.escape(title)}</h1><ul>{lis}</ul>"
            f'<div class="time">{mmss(start)}–{mmss(end)} · {end - start:.0f} s</div></div>')


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def cards_html(scenes):
    span = {name: (s, e) for name, s, e in scenes}
    return {
        "01_hook": '<div class="wrap big">Your hands are busy saving a life.<br>'
                   '<span class="dim">Why does emergency software require your hands?</span></div>',
        "02_stat": '<div class="wrap"><div class="big">350,000+ cardiac arrests outside a hospital, '
                   'every year, in the US.<br><span class="red">Most don\'t survive.</span></div>'
                   '<div class="small">Source: American Heart Association</div></div>',
        "03_todo_live_run": todo("Live run — one unedited take", [
            "Caller speaks → live transcript appears",
            "● PROTOCOL LOCKED: AHA-BLS badge + red Call 911 button",
            "SVG manikin: hand placement, then sternum + ripple on the beat (110 BPM)",
            "“Gasping” → critical alert cuts in (callout)",
            "Rib question → instant answer, metronome keeps going",
            "Latency pill visible the whole time · clock + “Unedited live run” tag",
        ], *span["03_todo_live_run"]),
        "04_architecture": """<div class="wrap"><h2>AssemblyAI provides the ears. <span class="dim">A locked protocol makes the decisions.</span></h2>
            <div class="flow"><div class="box">Rescuer's voice</div><div class="arrow">→</div>
              <div class="box">AssemblyAI<br>Universal-3.5 Pro<b>streaming STT · local triage 1.4 ms</b></div><div class="arrow">→</div>
              <div class="box lock">🔒 Protocol engine<b>deterministic</b></div><div class="arrow">→</div>
              <div class="box">Pre-recorded line<b class="fast">~0.02 s</b></div></div>
            <div class="flow"><div class="box" style="visibility:hidden">Rescuer's voice</div><div class="arrow" style="visibility:hidden">→</div>
              <div class="box">Any other question<b>agent writes the answer</b></div><div class="arrow">→</div>
              <div class="box gate">Safety gate<b>deterministic check</b></div><div class="arrow">→</div>
              <div class="box">Same voice<b class="slow">~0.3 s</b></div></div>
            <div class="small">LLM ≠ medical decision · every word the AI says is checked before it's spoken</div></div>""",
        "05_todo_hybrid": todo("Close-up: speed, and the safety gate", [
            "Latency pill: protocol ~0.02 s · live answer ~0.3 s",
            "Rescue timeline / event log scrolling back through the run",
            "Optional: an unscripted question answered live",
        ], *span["05_todo_hybrid"]),
        "06_todo_paramedics": todo("Paramedics arrive", [
            "“The paramedics are here!” → timers freeze, compression count",
            "EMS handoff card fills the screen",
            "Agent's grounding line, same voice as the app",
        ], *span["06_todo_paramedics"]),
        "07_end": """<div class="wrap" style="text-align:center"><div class="big">KeepAlive</div>
            <div class="big dim" style="font-size:52px;margin-top:24px">When seconds count, your hands should save a life,<br>not hold a phone.</div>
            <div class="small">Built with AssemblyAI streaming STT · ElevenLabs · open source (MIT)<br>
            AssemblyAI Voice Agent Hackathon · lablab.ai · Team KeepAlive</div></div>""",
    }


def render_cards(scenes):
    from playwright.sync_api import sync_playwright

    CARDS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1920, "height": 1080})
        for name, body in cards_html(scenes).items():
            page.set_content(f"<!doctype html><meta charset=utf-8><style>{CARD_CSS}</style>{body}")
            page.screenshot(path=str(CARDS / f"{name}.png"))
        b.close()


def slideshow(scenes, length):
    lines = []
    for name, s, e in scenes:
        lines += [f"file '{CARDS / (name + '.png')}'", f"duration {e - s:.3f}"]
    lines.append(f"file '{CARDS / (scenes[-1][0] + '.png')}'")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(lines) + "\n")
        concat = f.name
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", concat,
                    "-i", str(AUDIO / "guide_mix.wav"),
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-t", f"{length:.3f}",
                    str(ASSETS / "keepalive_draft_slideshow.mp4")], check=True)
    Path(concat).unlink()


# --- step 5: edit plan ---------------------------------------------------------------

def edit_plan(cues, scenes, length):
    rel = lambda p: p.relative_to(ROOT)  # noqa: E731
    rows = [f"| {mmss(c['t'])} | {mmss(c['end'])} | {c['track']} | `{rel(c['path'])}` | {c['text']} | {c['note']} |"
            for c in cues]
    scene_rows = [f"| {mmss(s)} | {mmss(e)} | `video/assets/cards/{n}.png` | "
                  f"{'**record dashboard**' if 'todo' in n else 'ready'} |" for n, s, e in scenes]
    (ASSETS / "EDIT_PLAN.md").write_text(f"""# KeepAlive demo — edit plan (draft)

Generated by `tools/build_video_draft.py` from `docs/demo-voiceover.md`. Length
**{mmss(length)}**. Re-run the script after any script or clip change.

## Picture

| From | To | Card | Status |
|---|---|---|---|
{chr(10).join(scene_rows)}

Cards marked *record dashboard* are placeholders: replace them with the screen
recording of the real dashboard (1080p, UI zoomed, cursor hidden).

## Sound

Four stems in `video/assets/audio/` line up with each other and with the table
below: `stem_narration.wav`, `stem_app.wav`, `stem_caller.wav`,
`stem_metronome.wav`, plus `guide_mix.wav` (all four, true peak under -1 dBTP).
Stems, the mix, the MP3 and the MP4 are not committed — re-run the script.

- **Live run:** in the final video the sound comes from the real recording — the
  app, the metronome and the teammate playing the caller. The app/caller/metronome
  stems are the guide for timing, not the final audio.
- **Caller:** placeholder voice (ElevenLabs "Liam"). Replace with the teammate.
- **Narration** (Eric) and the architecture/close segments are final.

## Cues

| Start | End | Track | File | Text | Note |
|---|---|---|---|---|---|
{chr(10).join(rows)}
""")


def main():
    rd.load_dotenv()
    rd.check_tools()
    render_extras()
    cues, metro, scenes, length = build_timeline()
    mix(cues, metro, length)
    render_cards(scenes)
    slideshow(scenes, length)
    edit_plan(cues, scenes, length)
    for c in cues:
        print(f"  {mmss(c['t']):>7}  {c['track']:<9} {c['id']:<18} {c['note']}")
    print(f"\nlength {mmss(length)} → {ASSETS.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
