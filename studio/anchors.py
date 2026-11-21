"""Anchors: time keys and cues to a spoken word or to the music's beat.

Authored times are numbers: a keyframe's ``at`` is a fraction of the resolved
shot, a motion recipe's ``t`` and a sound cue's ``at`` are seconds from the shot
start. Acting a line out on its word, or landing a cut on the beat, then means
hand arithmetic that breaks whenever a take is re-measured or the track changes.
An anchor names the moment instead and is resolved into the number at load time:

    {"at_word": {"word": "barbell"}, "scale": 1.2}           first "barbell" in the shot's lines
    {"at_word": {"line": 1, "word": "two GB", "edge": "end", "offset": 0.05}}
    {"at_word": "barbell"}                                    shorthand
    {"at_beat": 12}                                           the 13th beat of the track (0-based)
    {"at_beat": {"bar": 4, "beat": 3, "offset": -0.02}}       bar and beat counted from 1
    shot: {"snap": "beat"}                                    stretch the shot to end on the next beat ("bar": the next downbeat)

Keyframes, camera keys and motion recipes (``t``) and sound cues (``at``) take
``at_word`` or ``at_beat`` in place of their number. Words are matched in the
line's caption text (its ``text`` unless ``caption`` is set), ignoring case,
punctuation and ``*emphasis*``; ``occurrence`` picks a later repeat. Without
``line`` the shot's lines are searched in order.

Word times come from the measured takes when the command has an audio pass
(``render``, ``still``, ``audio``, ``check-visual``: see ``pipeline.prepare_measured``);
other commands estimate them from the text, which is close enough to validate
and lint. Beats come from ``music.beat`` (``{"bpm", "offset", "per_bar"}``), set
by the music library for an imported track, measured from the file otherwise.
"""

import copy
from functools import lru_cache
from pathlib import Path
import re

GAP = 0.18            # the pause audio.plan_shot leaves between lines
HOLD = 0.14           # the visual hold it adds after a line that overruns the shot
WORDS_PER_SECOND = 2.6
KEYS = ("at_word", "at_beat")


def present(episode):
    """True when any shot uses a word or beat anchor, or snaps to the beat."""
    for shot in _shots(episode):
        if shot.get("snap"):
            return True
        for _, item, _ in _anchored(shot):
            if any(key in item for key in KEYS):
                return True
    return False


def needs_beats(episode):
    return any(shot.get("snap") or any("at_beat" in item for _, item, _ in _anchored(shot))
               for shot in _shots(episode))


def _shots(episode):
    return [shot for scene in episode.get("scenes", []) for shot in scene.get("shots", [])]


def _anchored(shot):
    """(kind, item, field) for everything in a shot that can carry an anchor."""
    for layer in shot.get("layers", []):
        for key in layer.get("keyframes", []) or []:
            yield "key", key, "at"
        for spec in layer.get("motion", []) or []:
            yield "motion", spec, "t"
    for key in (shot.get("camera") or {}).get("keyframes", []) or []:
        yield "key", key, "at"
    for cue in shot.get("sfx", []) or []:
        yield "sfx", cue, "at"


def _norm(word):
    return re.sub(r"[^\w']", "", word.lower().replace("*", ""))


def _weights(words):
    return [max(1, len(word.strip(".,!?;:*"))) + (2 if word[-1:] in ".!?" else 0) for word in words]


def _pause_after(line):
    if line.get("pause_after") is not None:
        return float(line["pause_after"])
    return 0.3 if line.get("punchline") else 0.0


def estimate_clock(episode):
    """Word and shot times from the text alone, laid out the way the audio pass lays out takes."""
    fps = float(episode.get("fps", 30))
    clock, start = {"fps": fps, "shots": {}}, 0.0
    for shot in _shots(episode):
        lines, previous = [], -GAP
        length = float(shot.get("duration", 0))
        for line in shot.get("speech", []) or []:
            at = float(line["at"]) if "at" in line else previous + GAP
            at += float(line.get("lead", 0) or 0)
            text = line.get("caption", line.get("text", ""))
            words = [word for word in text.split() if _norm(word)]
            pace = float(line.get("pace", 1) or 1)
            seconds = max(0.4, len(words) / WORDS_PER_SECOND / pace)
            timed, cursor = [], at
            total = sum(_weights(words)) or 1
            for word, weight in zip(words, _weights(words)):
                span = seconds * weight / total
                timed.append({"text": word, "start": cursor, "end": cursor + span})
                cursor += span
            lines.append({"start": at, "end": at + seconds, "words": timed})
            length = max(length, at + seconds + max(_pause_after(line), HOLD))
            previous = at + seconds + _pause_after(line)
        clock["shots"][shot["id"]] = {"start": start, "duration": length, "lines": lines, "measured": False}
        start += length
    return clock


def clock_from_timeline(episode, timeline):
    """Measured word and shot times from a resolved audio timeline."""
    fps = float(timeline["fps"])
    captions = iter(timeline.get("captions", []))
    clock = {"fps": fps, "shots": {}}
    for scene in timeline["scenes"]:
        for shot in scene["shots"]:
            lines = []
            for speech in shot.get("speech", []):
                caption = next(captions, None) or {}
                words = [{"text": word["text"], "start": (word["start"] - shot["start"]) / fps,
                          "end": (word["end"] - shot["start"]) / fps} for word in caption.get("words", [])]
                lines.append({"start": (speech["start"] - shot["start"]) / fps,
                              "end": (speech["end"] - shot["start"]) / fps, "words": words})
            clock["shots"][shot["id"]] = {"start": shot["start"] / fps, "duration": (shot["end"] - shot["start"]) / fps,
                                          "lines": lines, "measured": True}
    return clock


def word_time(spec, shot_id, timing):
    """Seconds from the shot start for an ``at_word`` spec."""
    if isinstance(spec, str):
        spec = {"word": spec}
    lines = timing["lines"]
    if not lines:
        raise ValueError(f"Shot {shot_id} anchors to a word but has no speech.")
    if "line" in spec:
        index = int(spec["line"])
        if not -len(lines) <= index < len(lines):
            raise ValueError(f"Shot {shot_id} has {len(lines)} line(s); at_word asks for line {index}.")
        search = [lines[index]]
    else:
        search = lines
    target, edge = spec["word"], spec.get("edge", "start")
    occurrence = int(spec.get("occurrence", 1))
    found = None
    if isinstance(target, int):
        words = search[0]["words"]
        if not -len(words) <= target < len(words):
            raise ValueError(f"Shot {shot_id}: word index {target} is outside a line of {len(words)} words.")
        found = (words[target], words[target])
    else:
        wanted = [_norm(part) for part in str(target).split() if _norm(part)]
        seen = 0
        for line in search:
            names = [_norm(word["text"]) for word in line["words"]]
            for index in range(len(names) - len(wanted) + 1):
                if names[index:index + len(wanted)] == wanted:
                    seen += 1
                    if seen == occurrence:
                        found = (line["words"][index], line["words"][index + len(wanted) - 1])
                        break
            if found:
                break
        if not found:
            heard = " / ".join(" ".join(word["text"] for word in line["words"]) for line in search)
            raise ValueError(f"Shot {shot_id}: no word '{target}' (occurrence {occurrence}) in: {heard}")
    first, last = found
    moment = {"start": first["start"], "end": last["end"], "middle": (first["start"] + last["end"]) / 2}[edge]
    return moment + float(spec.get("offset", 0) or 0)


def beat_index(spec, grid):
    per_bar = int(grid.get("per_bar", 4))
    if isinstance(spec, (int, float)):
        return float(spec), 0.0
    beat = (int(spec.get("bar", 1)) - 1) * per_bar + float(spec.get("beat", 1)) - 1
    return beat, float(spec.get("offset", 0) or 0)


def beat_seconds(spec, grid):
    beat, offset = beat_index(spec, grid)
    return float(grid.get("offset", 0)) + beat * 60.0 / float(grid["bpm"]) + offset


def _place(kind, item, field, seconds, shot, timing, authored):
    duration = timing["duration"]
    if seconds < -1e-6 or seconds > duration + 1e-6:
        raise ValueError(f"Shot {shot['id']}: the anchor lands at {seconds:.2f} s, outside the shot "
                         f"(0-{duration:.2f} s). Anchor to a moment inside it, or move the cue to its shot.")
    seconds = min(max(seconds, 0.0), duration)
    if kind == "key":
        item[field] = round(seconds / duration, 6) if duration else 0.0
    elif kind == "motion":
        item[field] = round(seconds / duration * authored, 6) if duration else 0.0
    else:
        item[field] = round(seconds, 4)


def resolve(episode, clock=None, grid=None):
    """A copy of ``episode`` with every anchor replaced by its number and snapped shots stretched.

    ``clock`` is from ``clock_from_timeline`` (measured) or ``estimate_clock`` (default);
    ``grid`` is a beat grid dict, or a callable returning one, needed only for beat anchors and snaps.
    """
    if not present(episode):
        return episode
    episode = copy.deepcopy(episode)
    clock = clock or estimate_clock(episode)
    shift = 0.0
    beats = None
    for shot in _shots(episode):
        timing = clock["shots"].get(shot["id"])
        if timing is None:
            raise ValueError(f"Shot {shot['id']} is not in the timing clock; re-run the audio pass.")
        timing = {**timing, "start": timing["start"] + shift}
        authored = float(shot["duration"])
        snap = shot.pop("snap", None)
        if snap:
            beats = beats or _grid(grid)
            period = 60.0 / float(beats["bpm"]) * (int(beats.get("per_bar", 4)) if snap == "bar" else 1)
            first = float(beats.get("offset", 0))
            end = timing["start"] + timing["duration"]
            steps = max(0, -(-(end - first - 1e-6) // period))
            grown = max(timing["duration"], first + steps * period - timing["start"])
            # The authored length becomes the snapped length, so the audio pass (which only ever
            # lengthens a shot to fit its takes) resolves it to exactly this, on the beat.
            shift += grown - timing["duration"]
            shot["duration"] = round(grown, 4)
            authored = grown
            timing["duration"] = grown
        for kind, item, field in _anchored(shot):
            if "at_word" in item:
                seconds = word_time(item.pop("at_word"), shot["id"], timing)
            elif "at_beat" in item:
                beats = beats or _grid(grid)
                seconds = beat_seconds(item.pop("at_beat"), beats) - timing["start"]
            else:
                continue
            _place(kind, item, field, seconds, shot, timing, authored)
        for key_list in [layer.get("keyframes") for layer in shot.get("layers", [])] + \
                [(shot.get("camera") or {}).get("keyframes")]:
            if key_list:
                key_list.sort(key=lambda key: key.get("at", 0))
    return episode


def _grid(grid):
    grid = grid() if callable(grid) else grid
    if not grid or not grid.get("bpm"):
        raise ValueError("A beat anchor needs a tempo: add music from the channel library, a music file, "
                         "or music.beat: {\"bpm\": ..., \"offset\": ...}.")
    return grid


@lru_cache(maxsize=16)
def _measured(path, stamp):
    from .music import beat_grid as measure
    return measure(Path(path))


def music_grid(music, base=None):
    """The beat grid for an expanded episode ``music`` spec, or None."""
    if not music:
        return None
    if music.get("beat"):
        return {"per_bar": 4, "offset": 0.0, **music["beat"]}
    if music.get("preset") == "pulse":
        return {"bpm": 120.0, "offset": 0.0, "per_bar": 4}  # audio.music_bed plays half-second notes
    path = music.get("library_file") or (Path(base) / music["file"] if base and music.get("file") else None)
    if not path or not Path(path).is_file():
        return None
    found = _measured(str(Path(path).resolve()), Path(path).stat().st_mtime)
    return {"per_bar": 4, **found} if found else None
