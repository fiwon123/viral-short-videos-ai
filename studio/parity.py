"""Render the shared parity fixture and produce comparison sheets."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw, ImageOps

from .core import ffmpeg
from .support import matrix

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "parity"
TIMES = (0.6, 2.0, 3.5, 4.7)


def _frame(video, at, target):
    ffmpeg("-y", "-ss", str(at), "-i", str(video), "-frames:v", "1", "-q:v", "2", str(target))
    return target


def _sheet(paths, labels, target):
    tiles = []
    for path, label in zip(paths, labels):
        with Image.open(path) as image:
            tile = ImageOps.contain(image.convert("RGB"), (270, 480))
        canvas = Image.new("RGB", (290, 520), "#0B1020")
        canvas.paste(tile, ((290 - tile.width) // 2, 24))
        ImageDraw.Draw(canvas).text((12, 8), label, fill="#F8FAFC")
        tiles.append(canvas)
    sheet = Image.new("RGB", (290 * len(tiles), 520), "#0B1020")
    for index, tile in enumerate(tiles):
        sheet.paste(tile, (index * 290, 0))
    sheet.save(target)


def run(renderers=("python", "hyperframes"), out_root=None):
    out_root = Path(out_root or (ROOT / "output" / "parity")).resolve()
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    reports = {}
    frames = {}
    for renderer in renderers:
        package = out_root / renderer / "package"
        command = [sys.executable, str(ROOT / "video.py"), "render",
                   str(FIXTURE / "episode.json"), "--channel", str(FIXTURE / "channel.json"),
                   "--renderer", renderer, "--preview", "--out", str(package)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            reports[renderer] = {"ok": False, "error": result.stderr[-1200:]}
            continue
        stills = []
        for index, at in enumerate(TIMES):
            target = out_root / renderer / f"frame-{index}.png"
            _frame(package / "video.mp4", at, target)
            stills.append(target)
        frames[renderer] = stills
        reports[renderer] = {"ok": True, "package": str(package), "frames": [str(path) for path in stills]}
    if frames:
        for renderer, stills in frames.items():
            _sheet(stills, [f"{renderer} {at:g}s" for at in TIMES], out_root / f"{renderer}-sheet.png")
    if "python" in frames and "hyperframes" in frames:
        diffs = []
        for index, (left, right) in enumerate(zip(frames["python"], frames["hyperframes"])):
            with Image.open(left) as a, Image.open(right) as b:
                a = a.convert("RGB")
                b = b.convert("RGB").resize(a.size)
                diff = ImageOps.grayscale(ImageChops.difference(a, b))
                value = sum(diff.getdata()) / (255 * diff.width * diff.height)
                diffs.append(round(value, 5))
                diff.save(out_root / f"diff-{index}.png")
        reports["mean_difference"] = diffs
    reports["support"] = matrix()
    (out_root / "parity.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renderers", default="python,hyperframes")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        result = run(tuple(item.strip() for item in args.renderers.split(",") if item.strip()), args.out)
        print(json.dumps({"out": str((args.out or (ROOT / "output" / "parity")).resolve()),
                          "renderers": {key: value.get("ok") for key, value in result.items()
                                        if isinstance(value, dict) and "ok" in value},
                          "mean_difference": result.get("mean_difference")}, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(f"studio: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
