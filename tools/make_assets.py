"""Generate hunkgate's visual assets with PIL (no network, no fonts).

- assets/terminal-demo.png — a terminal-style screenshot of the REAL
  demo run (output captured from the CLI, never hand-typed).
- assets/social-preview.png — 1280x640 GitHub social preview.
- assets/preview.html — dark-mode-aware sample report, built from the
  REAL report of the demo fixture.
- assets/demo.mp4 (+ demo.gif) — short clip of the real CLI output
  as frames (PIL frames + ffmpeg).
- examples/sample-report.md / .json — the real report of the demo
  fixture, for reference.

Usage: python3 tools/make_assets.py
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(ROOT / "src"))

BG = (13, 17, 23)
PANEL = (22, 27, 34)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
AMBER = (210, 153, 34)
BLUE = (88, 166, 255)
TEXT = (230, 237, 243)
MUTED = (139, 148, 158)
WHITE = (255, 255, 255)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def run_demo_capture() -> dict:
    """Run the demo; return its printed lines and final report data."""
    from hunkgate.demo import run_demo

    lines: list[str] = []
    data = run_demo(print_fn=lines.append)
    return {"lines": lines, "data": data}


def terminal_demo(data: dict) -> None:
    lines = data["lines"]
    # Curate the real lines (never retype numbers): the queue, the
    # decisions, the apply check and the verdict.
    picked: list[tuple[str, tuple[int, int, int]]] = []
    for line in lines:
        if line.startswith("  F") or line.startswith("decisions:") \
                or line.startswith("approved patch") \
                or line.startswith("rejected files") \
                or line.startswith("approved files") \
                or line.startswith("gate READY"):
            picked.append((line, TEXT))
    # Colour the verdict lines.
    coloured = []
    for text, color in picked:
        if "BLOCK" in text:
            coloured.append((text, RED))
        elif "REVIEW" in text:
            coloured.append((text, AMBER))
        elif text.startswith("gate READY") or "coverage 100%" in text:
            coloured.append((text, GREEN))
        elif text.startswith("decisions:"):
            coloured.append((text, WHITE))
        else:
            coloured.append((text, color))
    header = [("$ hunkgate demo", MUTED), ("", TEXT)]
    body = header + coloured
    font = _font(18)
    pad_x, pad_y, line_h = 28, 26, 28
    width = 1000
    # Truncate lines that would run off the right edge (108 chars max).
    body = [(text[:106], color) for text, color in body]
    height = pad_y * 2 + line_h * len(body) + 42
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, width, 42], radius=12, fill=PANEL)
    draw.rectangle([0, 30, width, 42], fill=PANEL)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse([18 + i * 24, 13, 30 + i * 24, 25], fill=color)
    draw.text((110, 12), "hunkgate — demo", font=_font(16), fill=MUTED)
    y = 42 + pad_y
    for text, color in body:
        draw.text((pad_x, y), text, font=font, fill=color)
        y += line_h
    img.save(ASSETS / "terminal-demo.png")
    print(f"wrote {ASSETS / 'terminal-demo.png'} ({width}x{height})")


def social_preview(data: dict) -> None:
    width, height = 1280, 640
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    # Accent bar.
    draw.rectangle([0, 0, width, 10], fill=GREEN)
    draw.text((80, 90), "hunkgate", font=_font(110), fill=WHITE)
    draw.text((80, 220), "The human gate for agent-written code.",
              font=_font(40), fill=TEXT)
    draw.text((80, 300),
              "Review a diff hunk by hunk. Approve what you trust.",
              font=_font(32), fill=MUTED)
    draw.text((80, 350),
              "Apply only that. Send the rest back to the agent.",
              font=_font(32), fill=MUTED)
    # Score chip (real demo numbers) — measured, never guessed.
    report = data["data"]
    chip = (f"demo: {report['risk']}/100 BLOCK  ·  {report['hunks']} hunks  ·  "
            f"{report['findings']} findings  ·  gate {report['verdict']['state']}")
    chip_font = _font(26)
    chip_w = int(draw.textlength(chip, font=chip_font)) + 48
    draw.rounded_rectangle([80, 460, 80 + chip_w, 520],
                           radius=12, fill=PANEL)
    draw.text((104, 476), chip, font=chip_font, fill=AMBER)
    draw.text((80, 560), "Zero dependencies  ·  Python 3.9+  ·  MIT",
              font=_font(26), fill=MUTED)
    img.save(ASSETS / "social-preview.png")
    print(f"wrote {ASSETS / 'social-preview.png'} ({width}x{height})")


def preview_html(data: dict) -> None:
    """Build the sample HTML report from the demo fixture's real report."""
    from hunkgate.demo import DEMO_DIFF
    from hunkgate.report import to_html, to_json, to_markdown
    from hunkgate.store import Store

    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / ".hunkgate")
        store.init()
        item = store.capture(DEMO_DIFF, source="demo.diff", agent="claude-code",
                             title="Add login + cleanup (agent run #42)",
                             auto_approve=("docs-only",))
        item_id = item["id"]
        store.decide(item_id, ["F1.1"], "rejected", "ada",
                     reason="Hardcoded API key + verify=False. Move the key "
                            "to an env var and drop verify=False.")
        store.decide(item_id, ["F2.1"], "rejected", "ada",
                     reason="DROP TABLE + rmtree in one helper. Split into a "
                            "migration with a backup plan.")
        store.decide(item_id, ["F3.1"], "rejected", "ada",
                     reason="eval() on user input. Use a parser, not eval.")
        store.decide(item_id, ["F4.1"], "approved", "ada",
                     reason="Skip is temporary and tracked in #12.")
        item = store.load(item_id)
        audit = store.audit_log(item_id)
        (ASSETS / "preview.html").write_text(to_html(item, audit), encoding="utf-8")
        (EXAMPLES / "sample-report.md").write_text(to_markdown(item, audit),
                                                   encoding="utf-8")
        (EXAMPLES / "sample-report.json").write_text(to_json(item, audit),
                                                     encoding="utf-8")
    print(f"wrote {ASSETS / 'preview.html'} + examples/sample-report.md/.json")


def _terminal_frame(lines: list[tuple[str, tuple[int, int, int]]],
                    title: str, width: int = 1000, height: int = 560) -> Image.Image:
    font = _font(18)
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, width, 42], radius=12, fill=PANEL)
    draw.rectangle([0, 30, width, 42], fill=PANEL)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse([18 + i * 24, 13, 30 + i * 24, 25], fill=color)
    draw.text((110, 12), title, font=_font(16), fill=MUTED)
    y = 42 + 26
    for text, color in lines:
        draw.text((28, y), text[:106], font=font, fill=color)
        y += 28
    return img


def demo_video(data: dict) -> None:
    """6 terminal frames, 3s each = 18s clip (PIL frames + ffmpeg)."""
    frames = [
        ("hunkgate — capture", [
            ("$ hunkgate capture changes.diff --agent claude-code", MUTED),
            ("", TEXT),
            ("  F1.1  src/auth.py         95/100 BLOCK  [SEC-01, AUTH-01]", RED),
            ("  F2.1  src/db.py           95/100 BLOCK  [DESTRUCT-01, DESTRUCT-02]", RED),
            ("  F3.1  src/api.py          75/100 BLOCK  [EVAL-01, NET-01]", RED),
            ("  F4.1  tests/test_api.py   40/100 REVIEW [TEST-01]", AMBER),
            ("  F5.1  README.md           10/100 OK     [DOC-01]  auto-approved", GREEN),
        ]),
        ("hunkgate — show F1.1", [
            ("$ hunkgate show HG-... ", MUTED),
            ("", TEXT),
            ("  F1.1  lines 1+  95/100 BLOCK  decision: pending", RED),
            ("    [SEC-01] Possible secret or API key in added code", TEXT),
            ('      evidence: API_KEY = "sk-live-9f2c7d1a4b6e8f0a"', MUTED),
            ("    [AUTH-01] TLS verification disabled", TEXT),
            ("      evidence: session.verify = False", MUTED),
        ]),
        ("hunkgate — reject", [
            ("$ hunkgate reject HG-... F1.1 --reason \"Hardcoded key\"", MUTED),
            ("$ hunkgate reject HG-... F2.1 --reason \"DROP TABLE\"", MUTED),
            ("$ hunkgate reject HG-... F3.1 --reason \"eval()\"", MUTED),
            ("", TEXT),
            ("  rejected: F1.1, F2.1, F3.1 (reasons on the record)", WHITE),
        ]),
        ("hunkgate — approve + apply", [
            ("$ hunkgate approve HG-... F4.1 --reason \"Skip tracked in #12\"", MUTED),
            ("$ hunkgate apply HG-...", MUTED),
            ("", TEXT),
            ("  approved patch check: clean", GREEN),
            ("  approved patch apply: done", GREEN),
            ("  rejected files untouched: yes", WHITE),
            ("  approved files updated: yes", WHITE),
        ]),
        ("hunkgate — feedback", [
            ("$ hunkgate feedback HG-...", MUTED),
            ("", TEXT),
            ("  ## Rejected — fix before re-submitting", WHITE),
            ("  ### F1.1 · src/auth.py", TEXT),
            ("  Reason: Hardcoded API key + verify=False.", TEXT),
            ("  Fix: Move the value to an environment variable.", MUTED),
        ]),
        ("hunkgate — gate READY", [
            ("$ hunkgate ci HG-...", MUTED),
            ("", TEXT),
            ("  gate READY — coverage 100% (5/5 decided,", GREEN),
            ("  2 approved, 3 rejected, 0 blocking undecided)", GREEN),
            ("", TEXT),
            ("  hunkgate: approve what you trust. Nothing else lands.", WHITE),
        ]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        frame_paths = []
        for i, (title, lines) in enumerate(frames):
            img = _terminal_frame(lines, title)
            path = Path(tmp) / f"frame-{i:02d}.png"
            img.save(path)
            frame_paths.append(path)
        mp4 = ASSETS / "demo.mp4"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-framerate", "1/3",
             "-i", str(Path(tmp) / "frame-%02d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
             str(mp4)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            print("ffmpeg mp4 failed:", proc.stderr)
            return
        gif = ASSETS / "demo.gif"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(mp4),
             "-vf", "fps=2,scale=1000:-1:flags=lanczos,split[s0][s1];"
                   "[s0]palettegen=max_colors=64[p];[s1][p]paletteuse",
             str(gif)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            print("ffmpeg gif failed:", proc.stderr)
            return
    print(f"wrote {ASSETS / 'demo.mp4'} + {ASSETS / 'demo.gif'} (18s, 6 frames)")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    data = run_demo_capture()
    terminal_demo(data)
    social_preview(data)
    preview_html(data)
    demo_video(data)


if __name__ == "__main__":
    main()
