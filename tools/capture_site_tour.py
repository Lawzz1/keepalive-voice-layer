#!/usr/bin/env python3
"""Record a clean tour of the live cockpit for the demo video.

The phone recording of the interface shakes, sits in a vertical frame and has
the app's own voice on it. This drives the real site in a 1920x1080 browser and
records it, so the tour fills the frame, moves smoothly and carries no audio —
leaving the narration to Eric alone.

    python3 tools/capture_site_tour.py            # → video/assets/site_tour.mp4
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "video" / "assets"
SITE = "https://keepalive-fmdh.onrender.com"
W, H = 1920, 1080

# Scrolling by hand looks like scrolling by hand. This eases in and out.
SMOOTH_SCROLL = """
(target, ms) => new Promise(done => {
  const start = window.scrollY, delta = target - start, t0 = performance.now();
  const ease = p => p < 0.5 ? 4*p*p*p : 1 - Math.pow(-2*p + 2, 3) / 2;
  (function step(now) {
    const p = Math.min(1, (now - t0) / ms);
    window.scrollTo(0, start + delta * ease(p));
    if (p < 1) requestAnimationFrame(step); else done();
  })(t0);
})
"""


def record(dest_dir: Path) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--hide-scrollbars", "--force-device-scale-factor=1"])
        context = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(dest_dir),
            record_video_size={"width": W, "height": H},
        )
        page = context.new_page()
        page.goto(SITE, wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(1800)

        def scroll_to(y, ms=1700, hold=900):
            page.evaluate(SMOOTH_SCROLL, [y, ms])
            page.wait_for_timeout(ms + hold)

        # 1 — the top: simulated dispatch, latency, the judge bar
        page.wait_for_timeout(1400)
        scroll_to(160, 1200, 700)

        # 2 — the three display modes, held long enough to see each one land
        for theme in ["Tactical", "High-Contrast", "Clinical"]:
            try:
                page.get_by_role("button", name=re.compile(theme, re.I)).first.click(timeout=4000)
            except Exception:
                pass
            page.wait_for_timeout(2600)

        # 3 — start a real run, so the tour shows the app working, not a static page
        for label in ["Dad collapsed", "Hands placed"]:
            button = page.get_by_role("button", name=re.compile(label, re.I))
            try:
                button.first.click(timeout=4000)
            except Exception:
                pass
            page.wait_for_timeout(2600)

        # 4 — down to the pacing panel while the metronome runs
        scroll_to(430, 1800, 2400)

        # 5 — the rhythm ring and the depth gauge, held long enough to read
        scroll_to(760, 1600, 2600)

        # 6 — the companion answering
        try:
            page.get_by_role("button", name=re.compile("cracking rib", re.I)).first.click(timeout=4000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
        scroll_to(1150, 1500, 2800)

        # 7 — the handover card at the bottom
        scroll_to(1700, 1900, 2600)
        scroll_to(2100, 1500, 2200)

        context.close()          # the file is only written on close
        browser.close()

    videos = sorted(dest_dir.glob("*.webm"))
    if not videos:
        sys.exit("playwright wrote no video")
    return videos[-1]


def main():
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required")
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="tour-"))

    raw = record(tmp)
    dest = OUT / "site_tour.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(raw),
         "-vf", f"scale={W}:{H},fps=30,format=yuv420p",
         "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-an", str(dest)],
        check=True)

    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(dest)], capture_output=True, text=True).stdout.strip()
    print(f"{dest}  ({float(dur):.1f} s, silent, {W}x{H})")


if __name__ == "__main__":
    main()
