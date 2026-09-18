#!/usr/bin/env python3
"""Compare the lines spoken in a recording with the clips we render.

Rana records the cockpit talking; this says which of our clips still match his
engine word for word, which drifted, and which lines he speaks that we have no
clip for. The echo filter compares texts, so drift is not cosmetic.

    python3 tools/line_audit.py demo.mp4          # transcribes, then compares
    python3 tools/line_audit.py transcript.txt    # already have the text

Prints a `render --only` command for the clips that need a new take.
"""

import argparse
import difflib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_directives import DIRECTIVES  # noqa: E402

WHISPER_MODEL = "small.en"
DRIFT_OK = 0.97          # at or above this the wording is the same line
DRIFT_SAME_LINE = 0.55   # below this it isn't the same line at all
TEXT_SUFFIXES = {".txt", ".md", ".srt", ".vtt"}


def transcribe(media: Path) -> str:
    """media → text, via ffmpeg and whisper."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(media),
             "-ac", "1", "-ar", "16000", str(wav)],
            check=True)
        print(f"transcribing with whisper {WHISPER_MODEL}…", file=sys.stderr)
        subprocess.run(
            ["whisper", str(wav), "--model", WHISPER_MODEL, "--language", "en",
             "--output_dir", tmp, "--output_format", "txt", "--fp16", "False"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return (Path(tmp) / "audio.txt").read_text()


def sentences(text: str) -> list[str]:
    text = re.sub(r"^\d+\n[\d:,.\->\s]+\n", "", text, flags=re.M)   # srt/vtt timing
    text = re.sub(r"\s+", " ", text)
    text = text.replace("...", "…")      # "Ready: 3... 2... 1..." is one sentence
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if p.strip()]


def norm(s: str) -> list[str]:
    """Words only: punctuation and digit spelling differ between TTS and STT."""
    s = s.lower()
    for a, b in (("1", "one"), ("2", "two"), ("3", "three"), ("911", "nine one one")):
        s = s.replace(a, b)
    return re.findall(r"[a-z]+", s)


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def best_window(target: str, spoken: list[str], max_span: int = 4):
    """The run of consecutive spoken sentences closest to one of our lines."""
    best = (0.0, -1, 0)
    for i in range(len(spoken)):
        for span in range(1, max_span + 1):
            if i + span > len(spoken):
                break
            score = similarity(target, " ".join(spoken[i:i + span]))
            if score > best[0]:
                best = (score, i, span)
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="recording, or a transcript")
    ap.add_argument("--keep-transcript", type=Path, metavar="FILE",
                    help="write the transcript here for a second look")
    args = ap.parse_args()

    if not args.source.exists():
        print(f"no such file: {args.source}", file=sys.stderr)
        return 1

    text = (args.source.read_text() if args.source.suffix.lower() in TEXT_SUFFIXES
            else transcribe(args.source))
    if args.keep_transcript:
        args.keep_transcript.write_text(text)

    spoken = sentences(text)
    if not spoken:
        print("nothing transcribed", file=sys.stderr)
        return 1

    claimed: set[int] = set()
    matched, drifted, missing = [], [], []

    for clip in DIRECTIVES:
        score, start, span = best_window(clip["text"], spoken)
        heard = " ".join(spoken[start:start + span]) if start >= 0 else ""
        if score >= DRIFT_OK:
            matched.append((clip["id"], score))
            claimed.update(range(start, start + span))
        elif score >= DRIFT_SAME_LINE:
            drifted.append((clip["id"], score, clip["text"], heard))
            claimed.update(range(start, start + span))
        else:
            missing.append((clip["id"], clip["text"]))

    print(f"\n{len(spoken)} sentences heard · {len(DIRECTIVES)} clips compared\n")

    if matched:
        print(f"MATCHES ({len(matched)}) — nothing to do")
        for cid, score in matched:
            print(f"  {cid:<18} {score:.0%}")

    if drifted:
        print(f"\nDRIFTED ({len(drifted)}) — the echo filter will not match these")
        for cid, score, ours, heard in drifted:
            print(f"\n  {cid}  {score:.0%}")
            print(f"    ours:  {ours}")
            print(f"    heard: {heard}")

    if missing:
        print(f"\nNOT IN THE RECORDING ({len(missing)}) — he may not have reached them")
        for cid, ours in missing:
            print(f"  {cid:<18} {ours[:60]}…")

    unclaimed = [s for i, s in enumerate(spoken) if i not in claimed and len(norm(s)) >= 4]
    if unclaimed:
        print(f"\nSPOKEN BUT UNRECORDED ({len(unclaimed)}) — candidates for new clips")
        for s in unclaimed:
            near_id, near = "", 0.0
            for clip in DIRECTIVES:
                score = similarity(clip["text"], s)
                if score > near:
                    near_id, near = clip["id"], score
            hint = f"   (closest: {near_id} {near:.0%})" if near >= 0.3 else ""
            print(f"  · {s}{hint}")

    if drifted:
        ids = " ".join(cid for cid, *_ in drifted)
        print("\nRe-render with his wording after updating DIRECTIVES:")
        print(f"  python3 tools/render_directives.py render "
              f"--voice-id EXAVITQu4vr4xnSDxMaL --only {ids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
