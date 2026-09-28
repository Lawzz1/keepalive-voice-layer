#!/usr/bin/env python3
"""Turn the storyboard into a watchable animatic.

Nine frames held for their real durations over the real soundtrack: the clips
the app actually speaks, a 110 BPM metronome that starts where it starts in the
scene, and the closing narration. It is not the film — it is the film's timing,
so the shoot knows how long each shot has to last and the edit has a reference.

    python3 tools/build_animatic.py            # → video/assets/animatic.mp4
"""

import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIPS = ROOT / "web" / "audio"
VOICE = ROOT / "video" / "voiceover"
OUT = ROOT / "video" / "assets"
SCRATCH = Path(tempfile.mkdtemp(prefix="animatic-"))

W, H = 1920, 1080
RATE = 48000
BPM = 110
CLICK_HZ = 3000

# id, start second, what it is
TIMELINE = [
    (12.0, CLIPS / "cpr_adult_step1_call911.wav", 1.0),
    (23.5, CLIPS / "cpr_adult_step2_posture.wav", 1.0),
    (28.0, CLIPS / "cpr_adult_step3_compressions.wav", 1.0),
    (48.0, CLIPS / "qa_rib_cracking.wav", 1.0),
    (66.0, CLIPS / "qa_paramedic_arrival_debrief.wav", 1.0),
    (78.0, VOICE / "close_amb.wav", 1.0),
]
METRONOME_FROM, METRONOME_TO = 35.5, 70.0
TOTAL = 90.0

# start, duration, title, spoken line under the picture
FRAMES = [
    (0.0, 4.0, "1", ""),
    (4.0, 3.0, "2", ""),
    (7.0, 5.0, "3", ""),
    (12.0, 11.5, "4", "Help! My dad just collapsed, he is not breathing!"),
    (23.5, 24.5, "5", "Hands are placed on the center of his chest.  /  Ready to compress."),
    (48.0, 18.0, "6", "I heard a crack in his chest, did I break a rib?"),
    (66.0, 6.0, "7", "The paramedics are here!"),
    (72.0, 8.0, "8", ""),
    (80.0, 10.0, "9", ""),
]


def run(cmd, **kw):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, **kw)


def metronome(path: Path, start: float, end: float, total: float):
    """A 3 kHz click on every beat, silence elsewhere — the real cadence."""
    n = int(total * RATE)
    buf = bytearray(n * 2)
    period = 60.0 / BPM
    decay = 0.005
    beat = start
    while beat < end:
        at = int(beat * RATE)
        for i in range(int(0.03 * RATE)):
            if at + i >= n:
                break
            t = i / RATE
            v = math.sin(2 * math.pi * CLICK_HZ * t) * math.exp(-t / decay) * 0.35
            struct.pack_into("<h", buf, (at + i) * 2, int(v * 32767))
        beat += period
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(bytes(buf))


def soundtrack(path: Path):
    click = SCRATCH / "metronome.wav"
    metronome(click, METRONOME_FROM, METRONOME_TO, TOTAL)

    inputs, filters, labels = [], [], []
    inputs += ["-i", str(click)]
    filters.append(f"[0:a]volume=1.0,aformat=sample_fmts=s16:sample_rates={RATE}:channel_layouts=mono[a0]")
    labels.append("[a0]")

    idx = 1
    for start, src, vol in TIMELINE:
        if not src.exists():
            print(f"missing, skipped: {src.name}", file=sys.stderr)
            continue
        inputs += ["-i", str(src)]
        filters.append(
            f"[{idx}:a]adelay={int(start*1000)}|{int(start*1000)},volume={vol},"
            f"aformat=sample_fmts=s16:sample_rates={RATE}:channel_layouts=mono[a{idx}]")
        labels.append(f"[a{idx}]")
        idx += 1

    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,"
                   f"alimiter=limit=0.95,apad,atrim=0:{TOTAL}[out]")
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs,
         "-filter_complex", ";".join(filters), "-map", "[out]",
         "-c:a", "aac", "-b:a", "192k", str(path)])


def frames(storyboard_svgs: dict, card: Path) -> Path:
    """Render each storyboard panel as a full 1920x1080 frame."""
    from playwright.sync_api import sync_playwright

    out = SCRATCH / "frames"
    out.mkdir()
    css = ("body{margin:0;width:1920px;height:1080px;background:#0b0d11;overflow:hidden;"
           "font-family:-apple-system,Helvetica,Arial,sans-serif}"
           ".sub{position:absolute;left:0;right:0;bottom:56px;text-align:center;"
           "color:#8ddcff;font-size:34px;font-weight:300}"
           "svg{display:block;width:1920px;height:1080px}"
           "img{width:1920px;height:1080px;display:block}")

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": W, "height": H})
        for start, dur, no, line in FRAMES:
            if no == "9":
                body = f'<img src="file://{card}">'
            else:
                body = f'<svg viewBox="0 0 640 360">{storyboard_svgs[no]}</svg>'
            if line:
                body += f'<div class="sub">“{line}”</div>'
            page.set_content(f"<!doctype html><meta charset=utf-8><style>{css}</style>{body}")
            page.screenshot(path=str(out / f"{no}.png"))
        b.close()
    return out


def assemble(frame_dir: Path, audio: Path, dest: Path):
    listing = SCRATCH / "frames.txt"
    lines = []
    for start, dur, no, _ in FRAMES:
        lines.append(f"file '{frame_dir / (no + '.png')}'")
        lines.append(f"duration {dur}")
    lines.append(f"file '{frame_dir / (FRAMES[-1][2] + '.png')}'")   # concat needs the tail
    listing.write_text("\n".join(lines))

    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", str(listing),
         "-i", str(audio),
         "-vf", "fps=25,format=yuv420p", "-c:v", "libx264", "-crf", "20",
         "-c:a", "copy", "-shortest", str(dest)])


def main():
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required")
    sys.path.insert(0, str(ROOT / "tools"))
    from storyboard_art import PANEL_SVG            # the drawings live next door

    OUT.mkdir(parents=True, exist_ok=True)
    card = OUT / "end_card.png"
    if not card.exists():
        sys.exit(f"end card missing: {card}")

    audio = SCRATCH / "soundtrack.m4a"
    soundtrack(audio)
    frame_dir = frames(PANEL_SVG, card)
    dest = OUT / "animatic.mp4"
    assemble(frame_dir, audio, dest)

    size = dest.stat().st_size / 1e6
    print(f"{dest}  ({size:.1f} MB, {TOTAL:.0f} s)")


if __name__ == "__main__":
    main()
