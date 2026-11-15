"""Spot sound effects from the animation itself.

Professional sound design hits every meaningful motion. This scans each shot's
expanded keyframes and proposes cues an editor would place by hand:

* whoosh  a layer accelerates past a fast screen speed (panned to its x)
* impact  a fast layer stops within a couple of frames
* pop     a layer appears (opacity or scale snaps up)
* swish   a fast spin
* whoosh  whip, slide and zoom transitions; impact on camera shakes

Proposals skip moments that already have a cue, keep per-category spacing and
cap density so the mix never turns into noise. ``--apply`` writes them into
the episode as ``"spotted": true`` cues; re-running replaces only those.

    python -m studio.spotting EPISODE --channel CHANNEL [--apply]
"""

import argparse
import json
import math
from pathlib import Path

from .design import pose_at, poses

FAST = 1.3        # screens per second that reads as a whoosh
STOP_FROM = 0.9   # speed before a stop that reads as an impact
SPIN = 540        # degrees per second that reads as a swish
SPACING = {"whoosh": 0.22, "impact": 0.14, "pop": 0.09, "swish": 0.25}
DENSITY = 4       # cues per second at most, after merging
SOUNDS = {"whoosh": ["whoosh"], "impact": ["thud", "impact", "bonk"], "pop": ["pop"],
          "swish": ["swish", "whoosh"]}
FALLBACK_CUES = {"whoosh": "whoosh", "pop": "pop", "swish": "whoosh"}
WHIPS = {"whip-left", "whip-right", "slide-left", "slide-right", "slide-up", "slide-down", "zoom-in", "zoom-out"}


def _clamp(value, low, high):
    return max(low, min(high, value))


def layer_events(layer, duration, fps):
    if layer.get("kind") == "particles" or not layer.get("keyframes"):
        return []
    points = poses(layer)
    frames = max(2, round(duration * fps))
    samples = [pose_at(points, index / (frames - 1)) for index in range(frames)]
    events = []
    speeds = [0.0]
    for index in range(1, frames):
        a, b = samples[index - 1], samples[index]
        move = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
        grow = abs(b["scale"] - a["scale"]) * 0.5
        speeds.append((move + grow) * fps)
    hidden = lambda pose: pose["opacity"] < 0.12 or not pose["visible"] or pose["scale"] < 0.3
    for index in range(1, frames):
        at = index / fps
        pose, before = samples[index], samples[index - 1]
        speed, previous = speeds[index], speeds[index - 1]
        visible = not hidden(pose)
        if visible and speed >= FAST and previous < FAST:
            peak = max(speeds[index:index + round(0.3 * fps)] or [speed])
            events.append({"kind": "whoosh", "at": at - 0.06, "strength": peak / FAST, "x": pose["x"]})
        window = speeds[max(0, index - 2):index]
        if visible and window and max(window) >= STOP_FROM and speed <= 0.25 * max(window):
            events.append({"kind": "impact", "at": at, "strength": max(window) / STOP_FROM, "x": pose["x"]})
        recent = samples[max(0, index - round(0.15 * fps))]
        if visible and hidden(before) and hidden(recent):
            events.append({"kind": "pop", "at": at, "strength": 1.0, "x": pose["x"]})
        spin = abs(pose["rotate"] - before["rotate"]) * fps
        prior = abs(before["rotate"] - samples[max(0, index - 2)]["rotate"]) * fps
        if visible and spin >= SPIN and prior < SPIN:
            events.append({"kind": "swish", "at": at - 0.04, "strength": spin / SPIN, "x": pose["x"]})
    return events


def shot_events(shot, fps):
    duration = float(shot["duration"])
    events = []
    for layer in shot.get("layers", []):
        events.extend(layer_events(layer, duration, fps))
    camera = shot.get("camera") or {}
    for shake in camera.get("shakes", []):
        events.append({"kind": "impact", "at": float(shake["at"]) * duration,
                       "strength": 1 + float(shake.get("amplitude", 0.02)) * 20, "x": 0.5})
    transition = shot.get("transition") or {}
    if transition.get("type") in WHIPS:
        events.append({"kind": "whoosh", "at": 0.0, "strength": 1.6, "x": 0.5})
    return events


def _choose(kind, sounds):
    for name in SOUNDS[kind]:
        if name in sounds:
            return {"sound": name}
    if kind in FALLBACK_CUES:
        return {"cue": FALLBACK_CUES[kind]}
    return None


def propose(shot, fps, sounds):
    """Cue proposals for one shot, merged, spaced and density-capped."""
    duration = float(shot["duration"])
    existing = [float(cue["at"]) for cue in shot.get("sfx", []) if not cue.get("spotted")]
    events = sorted(shot_events(shot, fps), key=lambda event: -event["strength"])
    kept = []
    for event in events:
        at = _clamp(event["at"], 0.0, max(0.0, duration - 0.05))
        if any(abs(at - other) < 0.15 for other in existing):
            continue
        if any(item["kind"] == event["kind"] and abs(at - item["at"]) < SPACING[event["kind"]] for item in kept):
            continue
        if any(abs(at - item["at"]) < 0.06 for item in kept):  # Different kinds on one frame: keep the louder.
            continue
        if sum(1 for item in kept if abs(at - item["at"]) < 0.5) >= DENSITY // 2:
            continue
        kept.append({**event, "at": at})
    cues = []
    for event in sorted(kept, key=lambda item: item["at"]):
        source = _choose(event["kind"], sounds)
        if source is None:
            continue
        base = {"whoosh": 0.26, "impact": 0.42, "pop": 0.3, "swish": 0.24}[event["kind"]]
        gain = round(_clamp(base * (0.75 + 0.25 * min(3.0, event["strength"])), 0.12, 0.7), 3)
        cue = {"at": round(event["at"], 3), **source, "gain": gain,
               "pan": round(_clamp((event["x"] - 0.5) * 1.4, -0.8, 0.8), 2),
               "pitch_variance": 0.06, "spotted": True}
        # Whooshes sit above the voice band's mud; impacts get attack for small speakers.
        if event["kind"] in {"whoosh", "swish"}:
            cue["highpass"] = 180
        elif event["kind"] == "impact":
            cue["punch"] = 0.4
        cues.append(cue)
    return cues


def spot(source_episode, expanded_episode, sounds):
    by_id = {shot["id"]: shot for scene in expanded_episode["scenes"] for shot in scene["shots"]}
    report = {}
    for scene in source_episode["scenes"]:
        for shot in scene["shots"]:
            expanded = by_id.get(shot["id"], shot)
            cues = propose(expanded, source_episode["fps"], sounds)
            report[shot["id"]] = cues
    return report


def apply(source_episode, report):
    for scene in source_episode["scenes"]:
        for shot in scene["shots"]:
            kept = [cue for cue in shot.get("sfx", []) if not cue.get("spotted")]
            merged = sorted(kept + report.get(shot["id"], []), key=lambda cue: float(cue["at"]))
            if merged:
                shot["sfx"] = merged
            else:
                shot.pop("sfx", None)
    return source_episode


def main():
    from .audio_library import load_audio_library
    from .core import load, validate_channel
    from .pipeline import prepare_episode
    from .project import resolve_channel

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--channel", type=Path)
    parser.add_argument("--apply", action="store_true", help="write spotted cues into the episode")
    args = parser.parse_args()
    channel_path = args.channel or resolve_channel(Path(__file__).resolve().parents[1])
    channel = load(channel_path, "channel")
    validate_channel(channel, channel_path.parent)
    source = load(args.episode, "episode")
    expanded = prepare_episode(source, channel, channel_path.parent)
    library = load_audio_library(channel, channel_path.parent)
    sounds = set((library[0] if library else {}).get("sounds", {}))
    report = spot(source, expanded, sounds)
    if args.apply:
        raw = json.loads(args.episode.read_text(encoding="utf-8"))
        apply(raw, report)
        args.episode.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"applied": args.apply, "cues": sum(len(v) for v in report.values()), "shots": report},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
