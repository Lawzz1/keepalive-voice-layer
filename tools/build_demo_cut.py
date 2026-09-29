#!/usr/bin/env python3
"""Cut the filmed material into the submission video.

The scene was shot vertically on a phone, in two streams: the room (a man
collapses, a bystander works on him) and the phone's own screen recording. They
are put side by side where they belong together, so a judge sees the hands and
what the app is doing at the same moment — which is the whole claim of the
project.

Sound comes from the room take: the app's voice was captured live on the
cobblestones, so nothing here is dubbed.

    python3 tools/build_demo_cut.py            # → video/assets/keepalive_demo.mp4
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path.home() / "Downloads"
OUT = ROOT / "video" / "assets"
CARD = OUT / "end_card.png"
CLOSING = ROOT / "video" / "voiceover" / "vo_05_close.wav"
SCRATCH = Path(tempfile.mkdtemp(prefix="cut-"))

W, H, FPS = 1920, 1080, 30
# two portrait frames side by side, centred with a gap
TALL = 1000
GAP = 60

# The phone's screen recordings carry iOS chrome: a white status bar on top and
# Safari's address bar underneath. Measured on the source, both get cropped away.
# Measured per file: the Safari toolbar is taller in the later recordings.
SCREEN_CROPS = {
    "IMG_4272": (80, 84),
    "IMG_4273": (80, 84),
    "IMG_4274": (80, 84),
    "88": (72, 144),
    "89": (72, 144),
}


def screen_filter(name: str) -> str:
    if name not in SCREEN_CROPS:
        return ""
    top, bottom = SCREEN_CROPS[name]
    return f"crop=iw:ih-{top + bottom}:0:{top},"


def screen_trim(name: str) -> int:
    top, bottom = SCREEN_CROPS.get(name, (0, 0))
    return top + bottom


BG = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
      f"boxblur=30:2,eq=brightness=-0.24:saturation=0.7")

# (name, left source, left in, right source or None, right in, duration, what it is)
SEGMENTS = [
    ("z_hook",    "-",        0.0,  "TITLE:What if you are the only person there?", 0.0, 3.2,
     "крючок: чёрный экран с вопросом"),
    ("a_walk",    "IMG_4266", 0.6,  None,       0.0,  9.2, "идёт, хватается за грудь, падает"),
    ("b_run",     "IMG_4266", 13.4, None,       0.0,  5.6, "спасатель подбегает и опускается"),
    ("c_hands",   "IMG_4267", 0.4,  "IMG_4272", 2.0,  9.0, "руки на грудине · на экране фраза и вызов"),
    ("d_cpr",     "IMG_4269", 2.0,  "IMG_4273", 0.5, 12.5, "компрессии · на экране пошёл ритм"),
    # 4270 opens on the rescuer asking about the rib — that line has to be heard
    ("e_rib",     "IMG_4270", 0.3,  "IMG_4274", 0.5, 11.0, "«Did I break his rib?» · ответ · парамедики"),
    ("f_report",  "IMG_4274", 14.5, None,       0.0, 11.0, "карточка передачи парамедикам"),
    # Sarah finishes the report, and the cut goes straight to the site
    ("j_read",    "88",       2.6,  None,       0.0, 15.6, "Сара читает отчёт до последнего слова"),
    ("k_themes",  "-",        6.0,  "TOUR:vo_14_themes:1.0:1.07:0.5:0.30", 0.5,  5.4,
     "три темы интерфейса · Эрик про режимы"),
    ("l_arch",    "-",       19.0,  "TOUR:vo_12_ears:1.04:1.18:0.5:0.44",  0.4,  8.6,
     "живой прогон на сайте · Эрик про архитектуру"),
    ("m_speed",   "-",       36.0,  "TOUR:vo_13_speed:1.25:1.48:0.64:0.46", 0.3,  7.4,
     "наезд на кольцо ритма · Эрик про задержки"),
    ("n_beat",    "-",        0.0,  "BLACK",    0.0,  1.0, "секунда черноты"),
    ("g_back",    "IMG_4271", 0.8,  None,       0.0,  7.5, "он садится, камера отходит"),
]



def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode:
        sys.exit(r.stderr.decode()[-1600:])


def single(src: Path, start: float, dur: float, dest: Path, crop: str = ""):
    """One vertical frame, centred over a blurred copy of itself."""
    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-ss", str(start), "-t", str(dur), "-i", str(src),
         "-filter_complex",
         f"[0:v]{crop}{BG}[bg];[0:v]{crop}scale=-2:{H}[fg];"
         f"[bg][fg]overlay=(W-w)/2:0,fps={FPS},format=yuv420p[v]",
         "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         str(dest)])


def probe_size(src: Path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
                          str(src)], capture_output=True, text=True).stdout.strip()
    w, h = (int(x) for x in out.split("x")[:2])
    return w, h


def side_by_side(left: Path, lstart: float, right: Path, rstart: float,
                 dur: float, dest: Path, rcrop: str = "", rtrim: int = 0):
    """Room on the left, the phone's own screen on the right, same moment."""
    lw, lh = probe_size(left)
    rw, rh = probe_size(right)
    rh -= rtrim
    lw = (round(TALL * lw / lh) // 2) * 2
    rw = (round(TALL * rw / rh) // 2) * 2
    total = lw + GAP + rw + 12                      # +12 for the two 3 px frames
    x_left = (W - total) // 2
    x_right = x_left + lw + 6 + GAP
    y = (H - (TALL + 6)) // 2

    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-ss", str(lstart), "-t", str(dur), "-i", str(left),
         "-ss", str(rstart), "-t", str(dur), "-i", str(right),
         "-filter_complex",
         f"[0:v]{BG}[bg];"
         f"[0:v]scale={lw}:{TALL}[l];[1:v]{rcrop}scale={rw}:{TALL}[r];"
         f"[l]pad={lw+6}:{TALL+6}:3:3:0x232a36[lp];"
         f"[r]pad={rw+6}:{TALL+6}:3:3:0x232a36[rp];"
         f"[bg][lp]overlay={x_left}:{y}[t];"
         f"[t][rp]overlay={x_right}:{y},fps={FPS},format=yuv420p[v]",
         "-map", "[v]", "-map", "0:a",           # the room take carries the voice
         "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         str(dest)])


def push_in(src: Path, start: float, dur: float, dest: Path,
            fx: float = 0.90, fy: float = 0.41, zoom: float = 4.0):
    """The shot that carries the whole idea: the room falls away into the phone.

    A slow push toward the phone lying by the victim's head while the rest of
    the frame blurs and darkens, ending almost black — so the screen recording
    that follows feels like going inside the device rather than cutting to it.
    fx/fy are where the phone sits in the vertical frame, 0..1.
    """
    frames = int(dur * FPS)
    # the vertical image is centred on the canvas: find the phone on the canvas
    px = f"(({W}-iw)/2+{fx}*iw)"
    py = f"({fy}*ih)"
    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-ss", str(start), "-t", str(dur), "-i", str(src),
         "-filter_complex",
         f"[0:v]{BG}[bg];[0:v]scale=-2:{H}[fg];"
         f"[bg][fg]overlay=(W-w)/2:0,fps={FPS},"
         f"zoompan=z='1+({zoom}-1)*on/{frames}':"
         f"x='{px}-(iw/zoom/2)':y='{py}-(ih/zoom/2)':"
         f"d=1:s={W}x{H}:fps={FPS},"
         # boxblur takes no time expressions here, so it is switched on part way
         f"boxblur=luma_radius=9:luma_power=1:enable='gt(t,{dur*0.55:.2f})',"
         f"fade=t=out:st={dur-1.1:.2f}:d=1.1,format=yuv420p[v]",
         "-map", "[v]", "-map", "0:a",
         "-af", f"afade=t=out:st={dur-1.1:.2f}:d=1.1",
         "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         str(dest)])


def fade_in_single(src: Path, start: float, dur: float, dest: Path):
    """A screen segment that comes up out of the black the push-in ended on."""
    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-ss", str(start), "-t", str(dur), "-i", str(src),
         "-filter_complex",
         f"[0:v]{BG}[bg];[0:v]scale=-2:{H}[fg];"
         f"[bg][fg]overlay=(W-w)/2:0,fps={FPS},fade=t=in:st=0:d=0.9,format=yuv420p[v]",
         "-map", "[v]", "-map", "0:a", "-af", "afade=t=in:st=0:d=0.9",
         "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         str(dest)])


def narrated(src: Path, start: float, dur: float, dest: Path,
             voice: Path, voice_at: float, duck_db: float = -13.0, crop: str = ""):
    """The app speaks first, then hands the floor to the narrator.

    Never both at once: the source audio plays at full level, fades out just
    before Eric starts, and stays out until the end of the segment. Two voices
    over one another is the fastest way to make a demo unwatchable.
    """
    fade_at = max(0.0, voice_at - 0.5)
    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-ss", str(start), "-t", str(dur), "-i", str(src),
         "-i", str(voice),
         "-filter_complex",
         f"[0:v]{crop}{BG}[bg];[0:v]{crop}scale=-2:{H}[fg];"
         f"[bg][fg]overlay=(W-w)/2:0,fps={FPS},format=yuv420p[v];"
         f"[0:a]afade=t=out:st={fade_at:.2f}:d=0.5,"
         f"aformat=sample_rates=48000:channel_layouts=stereo[room];"
         f"[1:a]adelay={int(voice_at*1000)}|{int(voice_at*1000)},"
         f"aformat=sample_rates=48000:channel_layouts=stereo[nar];"
         f"[room][nar]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[a]",
         "-map", "[v]", "-map", "[a]", "-t", str(dur),
         "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         str(dest)])


def tour(src: Path, start: float, dur: float, dest: Path, voice: Path,
         voice_at: float, z_from: float, z_to: float, cx: float, cy: float):
    """A move across the recorded site tour, under one narration line.

    The capture has no sound of its own, so the narrator is alone here by
    construction — nothing to duck. The camera move is done in post because the
    desktop layout fits one screen: scrolling it would only jitter.
    cx/cy are the centre of interest, 0..1 of the frame.
    """
    frames = max(1, int(dur * FPS))
    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-ss", str(start), "-t", str(dur), "-i", str(src),
         "-i", str(voice),
         "-filter_complex",
         f"[0:v]fps={FPS},scale={W*2}:{H*2},"
         f"zoompan=z='{z_from}+({z_to}-{z_from})*on/{frames}':"
         f"x='{cx}*iw-(iw/zoom/2)':y='{cy}*ih-(ih/zoom/2)':"
         f"d=1:s={W}x{H}:fps={FPS},format=yuv420p[v];"
         f"[1:a]adelay={int(voice_at*1000)}|{int(voice_at*1000)},"
         f"apad,atrim=0:{dur},aformat=sample_rates=48000:channel_layouts=stereo[a]",
         "-map", "[v]", "-map", "[a]", "-t", str(dur),
         "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         str(dest)])


def title_card(text: str, dur: float, dest: Path, size: int = 76):
    """The first seconds decide whether a judge keeps watching."""
    esc = text.replace("'", "\u2019").replace(":", "\\:")
    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-f", "lavfi", "-t", str(dur), "-i", f"color=c=black:s={W}x{H}:r={FPS}",
         "-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo",
         "-vf",
         f"drawtext=text='{esc}':fontcolor=white:fontsize={size}:"
         f"x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=18:"
         f"alpha='if(lt(t,0.5),t/0.5,if(lt(t,{dur-0.6}),1,({dur}-t)/0.6))',"
         f"format=yuv420p",
         "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         str(dest)])


def black(dur: float, dest: Path):
    """A held breath. Nothing on screen, nothing in the speakers."""
    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-f", "lavfi", "-t", str(dur), "-i", f"color=c=black:s={W}x{H}:r={FPS}",
         "-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         str(dest)])


def ending(dest: Path):
    """Two seconds of black, then the card under the closing line."""
    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-f", "lavfi", "-t", "2.2", "-i", f"color=c=black:s={W}x{H}:r={FPS}",
         "-loop", "1", "-t", "7.8", "-i", str(CARD),
         "-f", "lavfi", "-t", "2.2", "-i", "anullsrc=r=48000:cl=stereo",
         "-i", str(CLOSING),
         "-filter_complex",
         f"[1:v]scale={W}:{H},fps={FPS},format=yuv420p,fade=t=in:st=0:d=0.6[card];"
         f"[0:v][card]concat=n=2:v=1:a=0[v];"
         f"[3:a]adelay=900|900,apad=pad_dur=1.2,aformat=sample_rates=48000:channel_layouts=stereo[na];"
         f"[2:a][na]concat=n=2:v=0:a=1[a]",
         "-map", "[v]", "-map", "[a]", "-shortest",
         "-c:v", "libx264", "-crf", "20", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         str(dest)])


def main():
    if not CARD.exists():
        sys.exit(f"missing end card: {CARD}")
    OUT.mkdir(parents=True, exist_ok=True)

    parts = []
    for name, lsrc, lstart, rsrc, rstart, dur, what in SEGMENTS:
        left = SRC / f"{lsrc}.MOV"
        if not left.exists():
            left = SRC / f"{lsrc}.MP4"
        if lsrc != "-" and not left.exists():
            sys.exit(f"missing footage: {left}")
        dest = SCRATCH / f"{name}.mp4"
        if rsrc and rsrc.startswith("TITLE:"):
            title_card(rsrc[6:], dur, dest)
        elif rsrc == "BLACK":
            black(dur, dest)
        elif rsrc and rsrc.startswith("TOUR:"):
            _, vo, zf, zt, cx, cy = rsrc.split(":")
            tour(OUT / "site_tour.mp4", lstart, dur, dest,
                 ROOT / "video" / "voiceover" / f"{vo}.wav", rstart,
                 float(zf), float(zt), float(cx), float(cy))
        elif rsrc and rsrc.startswith("VO:"):
            narrated(left, lstart, dur, dest,
                     ROOT / "video" / "voiceover" / f"{rsrc[3:]}.wav", rstart,
                     crop=screen_filter(lsrc))
        elif rsrc == "PUSH":
            push_in(left, lstart, dur, dest)
        elif rsrc == "FADEIN":
            fade_in_single(left, lstart, dur, dest)
        elif rsrc:
            side_by_side(left, lstart, SRC / f"{rsrc}.MOV", rstart, dur, dest,
                         screen_filter(rsrc), screen_trim(rsrc))
        else:
            single(left, lstart, dur, dest, screen_filter(lsrc))
        parts.append(dest)
        print(f"  {name:10} {dur:5.1f}s  {what}")

    end = SCRATCH / "h_end.mp4"
    ending(end)
    parts.append(end)
    print(f"  {'h_end':10} {10.0:5.1f}s  чернота, карточка, закадровый голос")

    listing = SCRATCH / "parts.txt"
    listing.write_text("\n".join(f"file '{p}'" for p in parts))

    dest = OUT / "keepalive_demo.mp4"
    joined = SCRATCH / "joined.mp4"
    run(["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", str(joined)])

    # The app's voice was recorded outdoors on a phone. It is real, which is the
    # point — but a judge on laptop speakers should still be able to read it.
    srt = OUT / "keepalive_demo.srt"
    if srt.exists():
        style = ("FontName=Helvetica,Fontsize=21,PrimaryColour=&H00FFFFFF,"
                 "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
                 "Alignment=2,MarginV=52")
        run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(joined),
             "-vf", f"subtitles={srt}:force_style='{style}'",
             "-c:v", "libx264", "-crf", "20", "-preset", "medium",
             "-c:a", "copy", str(dest)])
    else:
        shutil.copy(joined, dest)

    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", str(dest)],
                         capture_output=True, text=True).stdout.strip()
    mb = dest.stat().st_size / 1e6
    print(f"\n{dest}  ({float(out):.1f} s, {mb:.1f} MB)")


if __name__ == "__main__":
    main()
