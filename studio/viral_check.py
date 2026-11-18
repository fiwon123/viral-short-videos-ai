"""Viral check: score a Short's hook, pacing, loop and packaging before and after render.

    python -m studio.viral_check EPISODE [--channel CHANNEL] [--video video.mp4]

Manifest checks (no render needed):

* hook-speech   the first line starts later than 0.5 s
* hook-motion   nothing moves in the first half second
* hook-text     no words on screen in the first second (caption or text layer)
* hook-hit      no sound effect or line lands in the first 0.25 s
* first-shot    the opening shot runs longer than 3 s without a camera move
* pacing        a shot holds longer than 6 s, or the average shot is over 4 s
* runtime       outside the 15-60 s sweet spot (over 180 s is not a Short)
* captions      no captions, or a static style on a short-form episode
* packaging     missing or long thumbnail text, long title, title not echoed early

Rendered-video checks (``--video``, uses ffmpeg):

* first-frame   the first frame is nearly flat (black, blank or a fade-in)
* first-second  little visible change across the first second
* silent-start  the soundtrack starts later than 0.35 s
* loop          how closely the last frame matches the first (a loop replays cleanly)
* loudness      integrated loudness far from -14 LUFS

The score starts at 100 and loses points per note. It is a checklist, not a
prediction: strong topics and characters matter more than any single rule.
"""

import argparse
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np

WEIGHTS = {"high": 15, "medium": 8, "low": 3}


def _note(kind, severity, note, fix):
    return {"kind": kind, "severity": severity, "note": note, "fix": fix}


def _shots(episode):
    return [shot for scene in episode.get("scenes", []) for shot in scene.get("shots", [])]


def _words(text):
    return [word for word in re.findall(r"[a-z0-9']+", (text or "").lower()) if len(word) > 3]


def manifest_notes(source, expanded):
    from .motion_report import MOVE, _speeds
    notes = []
    shots = _shots(source)
    expanded_shots = {shot["id"]: shot for shot in _shots(expanded)}
    if not shots:
        return [_note("runtime", "high", "The episode has no shots.", "Add shots.")]
    fps = float(source.get("fps", 24))
    first = shots[0]
    first_expanded = expanded_shots.get(first["id"], first)
    speech = first.get("speech") or []
    if speech:
        start = float(speech[0].get("at", 0.2))
        if start > 0.5:
            notes.append(_note("hook-speech", "high", f"The first line starts at {start:.2f}s.",
                               "Start talking within 0.5 s; viewers decide in the first second."))
    hits = [float(cue.get("at", 0)) + float(cue.get("offset", 0) or 0) + float(cue.get("lead", 0) or 0)
            for cue in first.get("sfx") or []]
    if speech:
        hits.append(float(speech[0].get("at", 0)) + float(speech[0].get("lead", 0) or 0))
    if not any(at <= 0.25 for at in hits):
        notes.append(_note("hook-hit", "low", "No sound effect or line lands in the first 0.25 s.",
                           "Put a hit (pop, whoosh, impact) at t=0 so the first frame sounds like something happened."))
    moving = bool(first.get("camera") or first.get("three"))
    for layer in first_expanded.get("layers", []):
        _, speeds = _speeds(layer, float(first["duration"]), fps)
        if any(speed > MOVE * 3 for speed in speeds[:max(2, round(0.5 * fps))]):
            moving = True
            break
    if not moving:
        notes.append(_note("hook-motion", "high", "Nothing moves in the first half second.",
                           "Open on an action already in motion: a pop, a fall, a camera push."))
    text_now = any(layer.get("kind") == "text" for layer in first.get("layers", []))
    if not text_now and not (speech and float(speech[0].get("at", 0.2)) <= 1.0):
        notes.append(_note("hook-text", "medium", "No words appear in the first second.",
                           "Add a hook caption or title so muted viewers know the question."))
    if float(first["duration"]) > 3.0 and not moving:
        notes.append(_note("first-shot", "medium", f"The opening shot holds {float(first['duration']):.1f}s.",
                           "Cut or move the camera by 3 s to keep the hook tight."))
    durations = [float(shot["duration"]) for shot in shots]
    for shot in shots:
        if float(shot["duration"]) > 6.0 and not shot.get("camera") and not shot.get("three"):
            notes.append(_note("pacing", "medium", f"Shot {shot['id']} holds {float(shot['duration']):.1f}s.",
                               "Split it, add a camera move, or add a visible change every 2-3 s."))
    if sum(durations) / len(durations) > 4.0:
        notes.append(_note("pacing", "low", f"Average shot length is {sum(durations) / len(durations):.1f}s.",
                           "Short-form usually changes the picture every 2-4 s."))
    runtime = sum(durations)
    if runtime > 180:
        notes.append(_note("runtime", "high", f"Runtime {runtime:.0f}s is over the 3-minute Shorts limit.",
                           "Cut to under 60 s, or publish as a regular video."))
    elif runtime > 60:
        notes.append(_note("runtime", "medium", f"Runtime {runtime:.0f}s is long for a Short.",
                           "15-45 s keeps completion and replays high; cut setup before the payoff."))
    elif runtime < 8:
        notes.append(_note("runtime", "low", f"Runtime {runtime:.1f}s is very short.",
                           "Fine for a loop gag; otherwise give the payoff room to land."))
    captions = source.get("captions") or {}
    if any(shot.get("speech") for shot in shots) and captions.get("enabled") is False:
        notes.append(_note("captions", "high", "Captions are off.", "Most short-form views are muted; burn captions."))
    thumbnail = source.get("thumbnail") or {}
    text = thumbnail.get("text", "")
    if not text:
        notes.append(_note("packaging", "medium", "The thumbnail has no text.",
                           "Add 2-4 words that promise the payoff."))
    elif len(text.split()) > 5:
        notes.append(_note("packaging", "low", f"Thumbnail text has {len(text.split())} words.",
                           "Keep it to 2-4 big words."))
    title = source.get("title", "")
    if len(title) > 60:
        notes.append(_note("packaging", "low", f"The title is {len(title)} characters.",
                           "Under 60 keeps it whole in feeds."))
    opening = " ".join(line.get("text", "") for line in speech[:2]) + " " + text
    if title and _words(title) and not set(_words(title)) & set(_words(opening)):
        notes.append(_note("packaging", "low", "The title's key words are not in the opening line or thumbnail.",
                           "Echo the title's promise in the first line so the click is rewarded at once."))
    return notes


def _frames(video, start=None, from_end=None, seconds=1.0, fps=24, size=(48, 84)):
    command = ["ffmpeg", "-v", "error"]
    if from_end is not None:
        command += ["-sseof", str(-from_end)]
    elif start:
        command += ["-ss", str(start)]
    command += ["-i", str(video), "-t", str(seconds), "-vf", f"fps={fps},scale={size[0]}:{size[1]},format=gray",
                "-f", "rawvideo", "-"]
    data = subprocess.run(command, capture_output=True, check=True).stdout
    frame = size[0] * size[1]
    count = len(data) // frame
    return np.frombuffer(data[:count * frame], dtype=np.uint8).reshape(count, size[1], size[0]).astype(np.float32)


def video_notes(video):
    notes, metrics = [], {}
    opening = _frames(video, seconds=1.0)
    ending = _frames(video, from_end=0.25, seconds=0.25)
    if len(opening):
        metrics["first_frame_contrast"] = round(float(opening[0].std()), 1)
        if opening[0].std() < 6:
            notes.append(_note("first-frame", "high", "The first frame is nearly flat (black, blank or fading in).",
                               "Open on a readable picture; feeds autoplay from frame one."))
        change = float(np.mean([np.abs(b - a).mean() for a, b in zip(opening, opening[1:])])) if len(opening) > 1 else 0
        metrics["first_second_change"] = round(change, 2)
        if change < 0.6:
            notes.append(_note("first-second", "medium", "The picture barely changes in the first second.",
                               "Start mid-action or move the camera in the opening second."))
    if len(opening) and len(ending):
        difference = float(np.abs(ending[-1] - opening[0]).mean())
        metrics["loop_match"] = round(max(0.0, 1 - difference / 64), 2)
        if metrics["loop_match"] < 0.75:
            notes.append(_note("loop", "low", f"Last and first frames match {metrics['loop_match']:.0%}.",
                               "End on a frame that leads back into the opening so replays feel seamless."))
    silence = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-af", "silencedetect=n=-45dB:d=0.1",
                              "-f", "null", "-"], capture_output=True, text=True).stderr
    match = re.search(r"silence_start: (-?[\d.]+)\D.*?silence_end: ([\d.]+)", silence, re.S)
    if match and float(match.group(1)) <= 0.05:
        metrics["sound_starts"] = round(float(match.group(2)), 2)
        if float(match.group(2)) > 0.35:
            notes.append(_note("silent-start", "medium", f"Sound starts at {float(match.group(2)):.2f}s.",
                               "Start music, a sound effect or the voice on frame one."))
    loudness = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-af", "ebur128", "-f", "null", "-"],
                              capture_output=True, text=True).stderr
    found = re.findall(r"I:\s+(-?[\d.]+) LUFS", loudness)
    if found:
        metrics["integrated_lufs"] = float(found[-1])
        if abs(float(found[-1]) + 14) > 2.5:
            notes.append(_note("loudness", "low", f"Loudness is {float(found[-1]):.1f} LUFS.",
                               "Master near -14 LUFS so it is not quieter than the feed."))
    return notes, metrics


def check(source, expanded, video=None):
    notes = manifest_notes(source, expanded)
    metrics = {}
    if video:
        extra, metrics = video_notes(video)
        notes += extra
    score = max(0, 100 - sum(WEIGHTS[note["severity"]] for note in notes))
    return {"score": score, "notes": notes, "metrics": metrics,
            "reminder": "A checklist, not a prediction. Topic, character and timing matter most."}


def main():
    from .core import load, validate_channel
    from .pipeline import prepare_episode
    from .project import resolve_channel

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--channel", type=Path)
    parser.add_argument("--video", type=Path, help="rendered MP4 for pixel and audio checks")
    args = parser.parse_args()
    channel_path = args.channel or resolve_channel(Path(__file__).resolve().parents[1])
    channel = load(channel_path, "channel")
    validate_channel(channel, channel_path.parent)
    source = load(args.episode, "episode")
    expanded = prepare_episode(source, channel, channel_path.parent, episode_dir=args.episode.parent)
    print(json.dumps(check(source, expanded, args.video), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
