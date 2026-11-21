"""Film QA: measure a rendered Short the way a viewer sees it, and gate delivery.

    python -m studio.film_qa VIDEO [--episode episode.json] [--route hybrid] [--stop 8.0-8.6] [--out DIR]

The manifest checks (``viral-check``, ``motion-report``) read what was authored.
A shot with a camera block or a 3D scene counts as "moving" there even when the
picture freezes for seconds. This tool reads the pixels instead:

* energy        motion per second: the summed frame-to-frame change across each
                second (mean 0-255 level change per frame, summed, / 10). A flat curve is a flat film, however
                good each frame is.
* flat          most seconds are low-energy (under 1.0)
* no-burst      no second ever reaches 3.0: nothing lands hard
* slow-open     the first second is low-energy
* dead          a run of near-identical frames outside a declared stop
* frozen-end    the film ends on a still run of a second or more
* blank         a run of empty frames (flat colour, no edges)
* one-framing   the longest stretch without a hard cut (a Short reads as a slide
                when one framing holds for most of it)

Writes ``film-qa/report.json``, ``film-qa/energy.png`` (the curve, with shot
boundaries and dead runs) and ``film-qa/sheet.png`` (a contact sheet at up to
4 frames a second) beside the video. The verdict is red when any note is high,
amber when any is medium, green otherwise; red exits 1 so it can gate delivery.

Stops and the route come from flags or from the episode's ``treatment.md``
(``Route:`` and ``Stop:`` lines). A declared stop is a planned hold: dead runs
inside it are not reported. The ``continuous`` route (one world, a camera
travelling through it) relaxes the one-framing rule.

Method adapted from the motion-per-second and stillness gates in huashu-motion,
huashu-art-motion and lanshu-create-ai-presenter-video (all MIT).
"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw

STILL = 0.12        # mean per-frame change (0-255 levels) under which a frame reads as frozen
CUT = 18.0          # a per-frame change this large, well above its neighbours, is a hard cut
LOW = 1.0           # a second under this much motion is low-energy
BURST = 3.0         # at least one second should reach this
DEAD = (0.8, 1.5)   # seconds of stillness: medium, high
FROZEN_END = 1.0
BLANK_RUN = 0.3
FRAMING = (6.0, 12.0)
ROUTES = ("continuous", "montage", "hybrid")
WIDTH = 90


def _note(kind, severity, note, fix, **extra):
    return {"kind": kind, "severity": severity, "note": note, "fix": fix, **extra}


def probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    num, den = (stream.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den or 1)
    return {"width": int(stream["width"]), "height": int(stream["height"]), "fps": fps,
            "duration": float(data["format"]["duration"])}


def frames(video, info, fps):
    height = max(2, round(WIDTH * info["height"] / info["width"] / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                          f"fps={fps},scale={WIDTH}:{height}:flags=area,format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    size = WIDTH * height * 3  # colour, so a cut between two equally bright grounds still registers
    count = len(raw) // size
    return np.frombuffer(raw[:count * size], dtype=np.uint8).reshape(count, height, WIDTH, 3).astype(np.float32)


def parse_stops(values):
    stops = []
    for value in values or []:
        for part in re.split(r"[,;]\s*", str(value)):
            match = re.match(r"\s*(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*s?\s*$", part)
            if match and float(match.group(2)) > float(match.group(1)):
                stops.append((float(match.group(1)), float(match.group(2))))
    return stops


def read_meta(path):
    """Route and stops declared in a treatment.md (``Route: hybrid``, ``Stop: 8.0-8.6``)."""
    meta = {"route": None, "stops": []}
    if not path or not Path(path).is_file():
        return meta
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*[-*]?\s*\**(route|stops?)\**\s*:\**\s*(.+)", line, re.I)
        if not match:
            continue
        if match.group(1).lower() == "route":
            word = match.group(2).strip().split()[0].strip("*`").lower() if match.group(2).strip() else ""
            meta["route"] = word if word in ROUTES else None
        else:
            meta["stops"] += parse_stops([match.group(2)])
    return meta


def runs(mask):
    """(start, length) of each run of True values."""
    found, start = [], None
    for index, value in enumerate(list(mask) + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            found.append((start, index - start))
            start = None
    return found


def shots_from_timeline(path):
    if not path or not Path(path).is_file():
        return []
    timeline = json.loads(Path(path).read_text(encoding="utf-8"))
    fps = float(timeline.get("fps", 24))
    return [{"id": shot["id"], "start": shot["start"] / fps, "end": shot["end"] / fps}
            for scene in timeline.get("scenes", []) for shot in scene.get("shots", [])]


def _shot_at(shots, seconds):
    for shot in shots:
        if shot["start"] <= seconds < shot["end"]:
            return shot["id"]
    return None


def analyse(stack, fps, route=None, stops=(), shots=()):
    """Notes and metrics from a stack of frames (grey ``n,h,w`` or colour ``n,h,w,3``) sampled at ``fps``."""
    count = len(stack)
    duration = count / fps
    change = np.zeros(count, dtype=np.float32)
    if count > 1:
        change[1:] = np.abs(np.diff(stack, axis=0)).reshape(count - 1, -1).mean(axis=1)
    grey = stack.mean(axis=3) if stack.ndim == 4 else stack
    cuts = []
    for index in range(1, count):
        around = np.concatenate([change[max(1, index - 4):index], change[index + 1:index + 5]])
        floor = float(np.median(around)) if len(around) else 0.0
        if change[index] > CUT and change[index] > 3 * max(floor, 1.0):
            cuts.append(index)
    moving = change.copy()
    moving[cuts] = 0  # a cut is a change of picture, not motion
    seconds = int(np.ceil(duration - 0.5)) if duration >= 1 else 1
    energy = [round(float(moving[round(s * fps):round((s + 1) * fps)].sum()) / 10, 2) for s in range(seconds)]
    notes = []

    still = change < STILL
    still[0] = False
    still[cuts] = False
    dead_runs = []
    for start, length in runs(still):
        begin, seconds_long = start / fps, length / fps
        planned = [(a, b) for a, b in stops if min(b, begin + seconds_long) - max(a, begin) >= 0.5 * seconds_long]
        if seconds_long < DEAD[0] or planned:
            continue
        end = begin + seconds_long
        shot = _shot_at(shots, begin)
        where = f" in shot {shot}" if shot else ""
        dead_runs.append((begin, end))
        if start + length >= count and seconds_long >= FROZEN_END:
            notes.append(_note("frozen-end", "high", f"The last {seconds_long:.1f} s are frozen{where}.",
                               "End on motion: a settle, a drift, a reaction, or a move back into frame one "
                               "for a loop. A frozen ending reads as a stalled video.",
                               at=round(begin, 2), seconds=round(seconds_long, 2), shot=shot))
        else:
            severity = "high" if seconds_long >= DEAD[1] else "medium"
            notes.append(_note("dead", severity,
                               f"Nothing moves for {seconds_long:.1f} s at {begin:.1f}-{end:.1f} s{where}.",
                               "Give the hold a drift (3-6 % scale, slow), a reaction, a blink or an idle "
                               "loop, or cut. Declare it as a Stop in treatment.md only if the silence is the joke.",
                               at=round(begin, 2), seconds=round(seconds_long, 2), shot=shot))

    whole = energy if duration - int(duration) < 0.5 else energy[:-1] or energy
    low_share = sum(value < LOW for value in whole) / max(1, len(whole))
    if low_share >= 0.6:
        notes.append(_note("flat", "high", f"{low_share:.0%} of the seconds are low-energy (under {LOW}).",
                           "Rebuild the rhythm, not the polish: change shot size, add a burst of quick beats, "
                           "and give every stretch something new within two seconds."))
    elif low_share >= 0.4:
        notes.append(_note("flat", "medium", f"{low_share:.0%} of the seconds are low-energy (under {LOW}).",
                           "Find the flat stretches on energy.png and give each an event: a cut, a landing, a "
                           "camera move starting or stopping, a reaction."))
    peak = int(np.argmax(energy)) if energy else 0
    if energy and max(energy) < BURST:
        notes.append(_note("no-burst", "medium", f"The strongest second only reaches {max(energy):.1f}.",
                           "Give the payoff a hard landing: a crash zoom, a slam, an impact with squash, "
                           "a quick run of cuts on the beat."))
    if energy and energy[0] < LOW:
        notes.append(_note("slow-open", "medium", f"The first second has little motion ({energy[0]:.1f}).",
                           "Open mid-action: the subject is already moving on frame one."))

    edges = np.abs(np.diff(grey, axis=2)).mean(axis=(1, 2)) + np.abs(np.diff(grey, axis=1)).mean(axis=(1, 2))
    blank = (grey.std(axis=(1, 2)) < 3.0) & (edges < 0.8)
    for start, length in runs(blank):
        if length / fps >= BLANK_RUN:
            notes.append(_note("blank", "high", f"Empty picture for {length / fps:.1f} s at {start / fps:.1f} s.",
                               "Keep the subject in frame on every beat; a dip to black reads as a broken video.",
                               at=round(start / fps, 2), seconds=round(length / fps, 2)))

    bounds = [0] + cuts + [count]
    lengths = [(b - a) / fps for a, b in zip(bounds, bounds[1:])]
    longest = max(lengths) if lengths else duration
    framing_limit = FRAMING if route != "continuous" else (FRAMING[1], float("inf"))
    if longest > framing_limit[1]:
        notes.append(_note("one-framing", "high", f"One framing holds for {longest:.1f} s without a cut.",
                           "Give the payoff its own shot size: cut to a close-up on the reaction or an insert "
                           "on the prop. A Short with one wide framing reads as a slide."))
    elif longest > framing_limit[0]:
        notes.append(_note("one-framing", "medium" if route != "continuous" else "low",
                           f"One framing holds for {longest:.1f} s without a cut.",
                           "Change shot size at the turn, or declare Route: continuous in treatment.md if one "
                           "travelling camera carries the film."))

    per_shot = []
    for shot in shots:
        first, last = round(shot["start"] * fps), min(count, round(shot["end"] * fps))
        if last <= first:
            continue
        span = moving[first:last]
        per_shot.append({"id": shot["id"], "start": round(shot["start"], 2), "end": round(shot["end"], 2),
                         "motion": round(float(span.sum()) / 10 / max(1e-6, (last - first) / fps), 2),
                         "still": round(float(still[first:last].mean()), 2)})
    metrics = {
        "duration": round(duration, 2), "analysis_fps": fps, "energy": energy,
        "peak_second": peak, "peak_at": round(peak / max(1, len(energy)), 2) if energy else 0,
        "mean_energy": round(float(np.mean(energy)), 2) if energy else 0,
        "low_share": round(low_share, 2), "still_share": round(float(still[1:].mean()) if count > 1 else 1.0, 2),
        "cuts": [round(index / fps, 2) for index in cuts], "cuts_per_minute": round(len(cuts) / duration * 60, 1)
        if duration else 0, "median_framing": round(float(np.median(lengths)), 2) if lengths else 0,
        "longest_framing": round(longest, 2), "route": route, "stops": [list(stop) for stop in stops],
        "shots": per_shot,
    }
    return notes, metrics, dead_runs


def verdict(notes):
    severities = {note["severity"] for note in notes}
    return "red" if "high" in severities else "amber" if "medium" in severities else "green"


def chart(metrics, dead_runs, target, width=900, height=240):
    energy = metrics["energy"] or [0]
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    left, bottom, top = 50, height - 28, 18
    span = width - left - 10
    duration = max(metrics["duration"], len(energy))
    scale = max(max(energy), BURST * 1.5)

    def x(seconds):
        return left + span * seconds / duration

    def y(value):
        return bottom - (bottom - top) * min(1.0, value / scale)

    for begin, end in dead_runs:
        draw.rectangle((x(begin), top, x(end), bottom), fill="#FFE3E3")
    for stop in metrics["stops"]:
        draw.rectangle((x(stop[0]), top, x(stop[1]), bottom), fill="#E7F5FF")
    for level, colour in ((LOW, "#FA5252"), (BURST, "#40C057")):
        draw.line((left, y(level), width - 10, y(level)), fill=colour, width=1)
        draw.text((4, y(level) - 6), f"{level:g}", fill=colour)
    bar = span / duration
    for second, value in enumerate(energy):
        colour = "#FA5252" if value < LOW else "#339AF0" if value < BURST else "#2F9E44"
        draw.rectangle((x(second) + 1, y(value), x(second) + bar - 1, bottom), fill=colour)
    for shot in metrics["shots"]:
        draw.line((x(shot["start"]), top, x(shot["start"]), bottom), fill="#868E96", width=1)
        draw.text((x(shot["start"]) + 3, top - 14), str(shot["id"])[:10], fill="#495057")
    for cut in metrics["cuts"]:
        draw.line((x(cut), bottom, x(cut), bottom + 8), fill="#000000", width=2)
    for second in range(0, int(duration) + 1, max(1, int(duration) // 15 or 1)):
        draw.text((x(second) - 3, bottom + 10), str(second), fill="#495057")
    draw.line((left, bottom, width - 10, bottom), fill="#212529")
    image.save(target)
    return target


def sheet(video, duration, target, columns=8, tile=135):
    rate = min(4.0, 64 / max(duration, 0.1))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                    f"fps={rate:.4f},scale={tile}:-2,drawtext=text='%{{pts\\:hms}}':x=4:y=4:fontsize=12:"
                    f"fontcolor=white:box=1:boxcolor=black@0.5,tile={columns}x{max(1, int(np.ceil(duration * rate / columns)))}",
                    "-frames:v", "1", str(target)], capture_output=True, check=False)
    if not Path(target).is_file():  # drawtext needs a font; fall back to plain tiles
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                        f"fps={rate:.4f},scale={tile}:-2,tile={columns}x{max(1, int(np.ceil(duration * rate / columns)))}",
                        "-frames:v", "1", str(target)], capture_output=True, check=False)
    return target if Path(target).is_file() else None


def run(video, out=None, route=None, stops=(), treatment=None, timeline=None, images=True):
    video = Path(video)
    meta = read_meta(treatment)
    route = route or meta["route"]
    stops = list(stops) + meta["stops"]
    info = probe(video)
    fps = min(30.0, round(info["fps"], 3))
    if timeline is None and (video.parent / "timeline.json").is_file():
        timeline = video.parent / "timeline.json"
    notes, metrics, dead_runs = analyse(frames(video, info, fps), fps, route, stops, shots_from_timeline(timeline))
    out = Path(out) if out else video.parent / "film-qa"
    out.mkdir(parents=True, exist_ok=True)

    def where(path):  # relative to the video's folder, so a renamed render package stays valid
        try:
            return str(Path(path).resolve().relative_to(video.parent.resolve()))
        except ValueError:
            return str(Path(path).resolve())

    report = {"video": video.name, "verdict": verdict(notes), "notes": notes, "metrics": metrics,
              "report": where(out / "report.json"),
              "reminder": "Numbers say whether it moves, not whether it is good. Watch it at 1x with sound."}
    if images:
        report["energy_chart"] = where(chart(metrics, dead_runs, out / "energy.png"))
        made = sheet(video, metrics["duration"], out / "sheet.png")
        if made:
            report["sheet"] = where(made)
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def summary(report):
    return {"verdict": report["verdict"], "report": report["report"],
            "high": sum(note["severity"] == "high" for note in report["notes"]),
            "medium": sum(note["severity"] == "medium" for note in report["notes"]),
            "mean_energy": report["metrics"]["mean_energy"], "low_share": report["metrics"]["low_share"],
            "longest_framing": report["metrics"]["longest_framing"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--episode", type=Path, help="episode.json; its treatment.md supplies route and stops")
    parser.add_argument("--route", choices=ROUTES)
    parser.add_argument("--stop", action="append", default=[], help="planned still stretch, e.g. 8.0-8.6 (repeatable)")
    parser.add_argument("--timeline", type=Path, help="timeline.json for per-shot numbers (default: beside the video)")
    parser.add_argument("--out", type=Path, help="report folder (default: film-qa/ beside the video)")
    args = parser.parse_args()
    treatment = args.episode.parent / "treatment.md" if args.episode else None
    report = run(args.video, args.out, args.route, parse_stops(args.stop), treatment, args.timeline)
    for key in ("video", "report", "energy_chart", "sheet"):
        if key in report:
            report[key] = str((args.video.parent / report[key]).resolve())
    print(json.dumps(report, indent=2))
    return 1 if report["verdict"] == "red" else 0


if __name__ == "__main__":
    raise SystemExit(main())
