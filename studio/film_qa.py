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
* pop           a single frame that jumps away and back (a glitch, not two cuts)
* first-frame   frame 0 is a different picture from the opening (the poster is wrong)
* off-beat      a montage whose cuts mostly miss the music's beat (when the
                render's timeline.json carries the track's beat grid)
* sound-early / sound-late
                an impulsive sound effect (a hit, a click, a pop) heard more than
                45 ms before or 125 ms after the picture event it lands on: the
                frame where motion starts or stops in the same shot. Caption
                changes are not events, a sound on a cut is on the cut, and a
                sustained or unmatched sound is listed but not judged
                (``metrics.sync``). Needs the render's timeline.json.

Writes ``film-qa/report.json``, ``film-qa/energy.png`` (the curve, with shot
boundaries and dead runs) and ``film-qa/sheet.png`` (a contact sheet at up to
4 frames a second) beside the video. The verdict is red when any note is high,
amber when any is medium, green otherwise; red exits 1 so it can gate delivery.

Stops and the route come from flags or from the episode's ``treatment.md``
(``Route:`` and ``Stop:`` lines). A declared stop is a planned hold: dead runs
inside it are not reported. The ``continuous`` route (one world, a camera
travelling through it) relaxes the one-framing rule.

Method adapted from the motion-per-second and stillness gates in huashu-motion,
huashu-art-motion and lanshu-create-ai-presenter-video, and the per-cue sync gate
in cinetic (all MIT). The sync tolerances follow ITU-R BT.1359 detectability.
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
POP = 6.0           # a frame that changes this much from both neighbours, which match, is a pop
LOW = 1.0           # a second under this much motion is low-energy
BURST = 3.0         # at least one second should reach this
DEAD = (0.8, 1.5)   # seconds of stillness: medium, high
FROZEN_END = 1.0
BLANK_RUN = 0.3
FRAMING = (6.0, 12.0)
ROUTES = ("continuous", "montage", "hybrid")
WIDTH = 90
# Sound against picture. Viewers notice sound that leads its picture by about 45 ms and sound that
# trails it by about 125 ms (ITU-R BT.1359); each limit is widened by half a frame because the
# picture event is only known to the frame.
SYNC_EARLY, SYNC_LATE = 0.045, 0.125
SYNC_SEARCH = 0.33   # seconds either side of the sound to look for its picture event
SYNC_EVENT = 1.0     # a picture event changes the frame-to-frame motion by at least this much...
SYNC_CLEAR = 5.0     # ...and by this many times the usual change around it
SYNC_RISE = 10.0     # dB in 15 ms: a sound that does not rise this sharply has no attack to sync
LEVEL_HOP = 0.005    # seconds per audio level step


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


def meta_from_text(text):
    """Route and stops declared in treatment text (``Route: hybrid``, ``Stop: 8.0-8.6``)."""
    meta = {"route": None, "stops": []}
    for line in text.splitlines():
        match = re.match(r"\s*[-*]?\s*\**(route|stops?)\**\s*:\**\s*(.+)", line, re.I)
        if not match:
            continue
        if match.group(1).lower() == "route":
            word = match.group(2).strip().split()[0].strip("*`").lower() if match.group(2).strip() else ""
            meta["route"] = word if word in ROUTES else None
        else:
            meta["stops"] += parse_stops([match.group(2)])
    return meta


def read_meta(path):
    if not path or not Path(path).is_file():
        return {"route": None, "stops": []}
    return meta_from_text(Path(path).read_text(encoding="utf-8"))


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


def beat_from_timeline(path):
    if not path or not Path(path).is_file():
        return None
    return (json.loads(Path(path).read_text(encoding="utf-8")).get("music") or {}).get("beat")


def cues_from_timeline(path):
    """Sound effect cues as ``{"sound", "at", "shot"}``, ``at`` in seconds from the start."""
    if not path or not Path(path).is_file():
        return []
    timeline = json.loads(Path(path).read_text(encoding="utf-8"))
    fps = float(timeline.get("fps", 24))
    return [{"sound": cue.get("sound") or cue.get("cue") or Path(str(cue.get("source", "sfx"))).stem,
             "at": cue["start"] / fps, "shot": shot["id"]}
            for scene in timeline.get("scenes", []) for shot in scene.get("shots", [])
            for cue in shot.get("sfx", []) if "start" in cue]


def caption_changes(path):
    """Seconds at which a caption line or a highlighted word appears or leaves (not picture events)."""
    if not path or not Path(path).is_file():
        return []
    timeline = json.loads(Path(path).read_text(encoding="utf-8"))
    fps = float(timeline.get("fps", 24))
    times = set()
    for caption in timeline.get("captions", []):
        times.update((caption["start"], caption["end"]))
        for word in caption.get("words") or []:
            times.update((word["start"], word["end"]))
    return sorted(value / fps for value in times)


def audio_level(video):
    """The video's audio as a dB level every LEVEL_HOP seconds, or None when it has no audio."""
    from .music import RATE, decode  # ffmpeg decode, mono
    try:
        samples = decode(video)
    except subprocess.CalledProcessError:
        return None
    hop = int(RATE * LEVEL_HOP)
    steps = len(samples) // hop
    if steps < 4:
        return None
    rms = np.sqrt(np.mean(samples[:steps * hop].reshape(steps, hop) ** 2, axis=1))
    return np.maximum(20 * np.log10(rms + 1e-6), -60.0)  # digital silence would dwarf every real attack


def sound_onset(level, at):
    """(seconds, dB) of the first strong 15 ms rise in ``level`` from just before ``at`` to 0.25 s after.

    A cue cannot sound before its own start; the 20 ms before it only absorb frame rounding.
    """
    span = 3
    first = max(0, int((at - 0.02) / LEVEL_HOP))
    last = min(len(level), int((at + 0.25) / LEVEL_HOP))
    if last - first <= span:
        return None, 0.0
    rise = level[first + span:last] - level[first:last - span]
    if rise.max() < SYNC_RISE:
        return None, float(rise.max())
    # The first strong rise, not the steepest: the next cue can fall inside the window and climb harder.
    index = int(np.argmax(rise >= SYNC_RISE))
    while index + 1 < len(rise) and rise[index + 1] > rise[index]:
        index += 1  # to the top of that rise
    return (first + index + span) * LEVEL_HOP, float(rise[index])


def impulsive(level, at):
    """True when the sound starting at ``at`` falls by 6 dB within 0.1-0.2 s (a hit, a click, a pop),
    False for a sustained sound (a creak, a rattle, a swish), which has no single moment to sync to."""
    top = int(at / LEVEL_HOP)
    peak = float(level[top:top + 6].max()) if top < len(level) else -60.0
    tail = level[top + int(0.1 / LEVEL_HOP):top + int(0.2 / LEVEL_HOP)]
    return len(tail) > 0 and peak - float(tail.mean()) >= 6.0


def sync(change, cuts, glitch, fps, cues, level, shots=(), captions=()):
    """Match each sound cue to the picture event it lands on.

    The picture event is the frame where motion changes most sharply (a move starting or stopping),
    in the same stretch between hard cuts; a sound within tolerance of a cut is on the cut.
    Returns notes and one row per cue, with a status: synced, early, late, on-cut, unmatched (no clear
    picture event of its own), sustained (no attack to sync), soft (no sharp rise) or edge (first/last frames).
    """
    count = len(change)
    event = np.zeros(count, dtype=np.float32)
    if count > 1:
        event[1:] = np.abs(np.diff(change))
    candidates = event.copy()
    for index in list(cuts) + sorted(glitch) + [int(round(seconds * fps)) for seconds in captions]:
        candidates[max(0, index - 1):index + 2] = 0  # cuts, glitches and caption changes are not actions
    early, late = SYNC_EARLY + 0.5 / fps, SYNC_LATE + 0.5 / fps
    notes, rows = [], []
    onsets = [sound_onset(level, cue["at"]) for cue in cues]
    heard_all = [heard for heard, _ in onsets if heard is not None]
    for cue, (heard, _) in zip(cues, onsets):
        row = {"sound": cue["sound"], "cue": round(cue["at"], 3), "shot": cue.get("shot")}
        rows.append(row)
        if cue["at"] < 2 / fps or cue["at"] > (count - 2) / fps:
            row["status"] = "edge"
            continue
        if heard is None:
            row["status"] = "soft"  # a swell or a masked sound: no attack to judge
            continue
        row["heard"] = round(heard, 3)
        if not impulsive(level, heard):
            row["status"] = "sustained"
            continue
        frame = int(round(heard * fps))
        cut = min(cuts, key=lambda index: abs(index / fps - heard), default=None)
        if cut is not None and -early <= heard - cut / fps <= late:
            row.update(status="on-cut", picture=round(cut / fps, 3), offset_ms=round(1000 * (heard - cut / fps)))
            continue
        before = max([index for index in cuts if index <= frame], default=0)
        after = min([index for index in cuts if index > frame], default=count)
        first = max(before + 2, 1, frame - int(SYNC_SEARCH * fps))
        last = min(after - 1, count, frame + int(SYNC_SEARCH * fps) + 1)
        if last <= first:
            row["status"] = "unmatched"
            continue
        around = event[max(1, frame - int(fps)):min(count, frame + int(fps))]
        floor = float(np.median(around)) + 1e-3 if len(around) else float("inf")
        # Clear peaks only, and the one nearest the sound: the strongest event in the window is
        # often the next beat (a reaction after a landing), which would flag a synced cue.
        peaks = [index for index in range(first, last)
                 if candidates[index] >= SYNC_EVENT and candidates[index] / floor >= SYNC_CLEAR
                 and candidates[index] >= candidates[index - 1]
                 and (index + 1 >= count or candidates[index] >= candidates[index + 1])]
        if not peaks:
            row["status"] = "unmatched"  # nothing on screen starts or stops sharply near it
            continue
        peak = min(peaks, key=lambda index: (abs(index / fps - heard), -candidates[index]))
        start = peak  # a landing under a shake spreads over frames: sync to where the change begins
        while start - 1 >= first and candidates[start - 1] >= 0.5 * candidates[peak]:
            start -= 1
        seen = start / fps
        if any(abs(other - seen) < abs(heard - seen) for other in heard_all if other != heard):
            row.update(status="unmatched", picture=round(seen, 3))  # that event belongs to another cue
            continue
        offset = heard - seen
        row.update(picture=round(seen, 3), offset_ms=round(1000 * offset))
        if -early <= offset <= late:
            row["status"] = "synced"
            continue
        row["status"] = "early" if offset < 0 else "late"
        shot = cue.get("shot") or _shot_at(shots, heard)
        where = f" in shot {shot}" if shot else ""
        frames_off = abs(offset) * fps
        if offset < 0:
            text = f"The {cue['sound']} at {heard:.2f} s plays {-offset * 1000:.0f} ms before its picture{where}."
        else:
            text = f"The {cue['sound']} at {heard:.2f} s plays {offset * 1000:.0f} ms after its picture{where}."
        notes.append(_note(f"sound-{row['status']}", "medium", text,
                           f"The nearest picture event is at {seen:.2f} s (a move starting or stopping). Move the "
                           f"cue {frames_off:.0f} frame(s) {'later' if offset < 0 else 'earlier'}, or anchor it to "
                           "the key that makes the contact. If the sound belongs to something else, ignore this.",
                           at=round(heard, 3), picture=round(seen, 3), offset_ms=round(1000 * offset), shot=shot))
    return notes, rows


def on_beat(cuts, beat, fps):
    """Share of cut times within a frame (at least 40 ms) of the track's beat grid."""
    if not cuts or not beat or not beat.get("bpm"):
        return None
    period, offset = 60.0 / float(beat["bpm"]), float(beat.get("offset", 0))
    tolerance = max(1.0 / fps, 0.04)
    near = [abs((cut - offset + period / 2) % period - period / 2) <= tolerance for cut in cuts]
    return round(sum(near) / len(near), 2)


def _shot_at(shots, seconds):
    for shot in shots:
        if shot["start"] <= seconds < shot["end"]:
            return shot["id"]
    return None


def analyse(stack, fps, route=None, stops=(), shots=(), beat=None, cues=(), level=None, captions=()):
    """Notes and metrics from a stack of frames (grey ``n,h,w`` or colour ``n,h,w,3``) sampled at ``fps``."""
    count = len(stack)
    duration = count / fps
    change = np.zeros(count, dtype=np.float32)
    if count > 1:
        change[1:] = np.abs(np.diff(stack, axis=0)).reshape(count - 1, -1).mean(axis=1)
    grey = stack.mean(axis=3) if stack.ndim == 4 else stack
    # A pop: frame i jumps away from both neighbours while they match each other (shown a frame
    # early, a key on the wrong side of a cut). It is a glitch, not two cuts and not motion.
    pops = []
    for index in range(1, count - 1):
        a, b = change[index], change[index + 1]
        if a > POP and b > POP:
            around = float(np.abs(stack[index + 1] - stack[index - 1]).mean())
            if around < min(a, b) / 3:
                pops.append(index)
    glitch = set(pops) | {index + 1 for index in pops}
    first_jump = False
    if count >= 4 and 1 not in glitch:
        after = float(np.median(change[2:min(count, 8)]))
        first_jump = bool(change[1] > CUT and change[1] > 3 * max(after, 1.0))
        if first_jump:
            glitch.add(1)
    cuts = []
    for index in range(1, count):
        if index in glitch:
            continue
        around = np.concatenate([change[max(1, index - 4):index], change[index + 1:index + 5]])
        floor = float(np.median(around)) if len(around) else 0.0
        if change[index] > CUT and change[index] > 3 * max(floor, 1.0):
            cuts.append(index)
    moving = change.copy()
    moving[cuts] = 0  # a cut is a change of picture, not motion
    moving[sorted(glitch)] = 0
    seconds = int(np.ceil(duration - 0.5)) if duration >= 1 else 1
    energy = [round(float(moving[round(s * fps):round((s + 1) * fps)].sum()) / 10, 2) for s in range(seconds)]
    notes = []
    if first_jump:
        notes.append(_note("first-frame", "high", "Frame 0 is a different picture from the rest of the opening.",
                           "Frame 0 is the poster feeds show: make it the opening shot. Usually a camera or layer "
                           "key that is not applied at t=0, or a transition starting on the wrong frame.", at=0.0))
    for index in pops:
        shot = _shot_at(shots, index / fps)
        where = f" in shot {shot}" if shot else ""
        notes.append(_note("pop", "high", f"A single-frame pop at {index / fps:.2f} s (frame {index}){where}.",
                           "Look at the frame and its neighbours: an element shown one frame early, a key on the "
                           "wrong side of a cut, or a visibility switch that flips back.", at=round(index / fps, 3),
                           shot=shot))

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

    sync_rows = []
    if cues and level is not None:
        sync_notes, sync_rows = sync(change, cuts, glitch, fps, cues, level, shots, captions)
        notes.extend(sync_notes)
    cut_times = [index / fps for index in cuts]
    beat_share = on_beat(cut_times, beat, fps)
    if beat_share is not None and route == "montage" and len(cuts) >= 3 and beat_share < 0.5:
        notes.append(_note("off-beat", "low", f"Only {beat_share:.0%} of the cuts land on the beat.",
                           "In a montage, cut on the beat: give the shots snap: beat, or time keys with at_beat."))
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
        "cuts_on_beat": beat_share, "bpm": (beat or {}).get("bpm"),
        "pops": [round(index / fps, 3) for index in pops], "first_frame_jump": first_jump,
        "shots": per_shot, "sync": sync_rows,
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
    cues = cues_from_timeline(timeline)
    notes, metrics, dead_runs = analyse(frames(video, info, fps), fps, route, stops, shots_from_timeline(timeline),
                                        beat_from_timeline(timeline), cues, audio_level(video) if cues else None,
                                        caption_changes(timeline))
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
