"""Animation lint: find dead holds, linear moves, unstaggered starts and snaps.

Reads the authored episode and its expanded keys, samples every layer, and
reports concrete, fixable notes per shot plus a speed chart PNG:

    python -m studio.motion_report EPISODE --channel CHANNEL [--out report.png]

Checks:

* dead hold    nothing on screen moves for longer than ``--hold`` seconds
* linear       an authored move that travels far with a ``linear`` ease
* lockstep     three or more layers start moving on the same frame
* snap         a layer jumps further than a quarter screen in one frame
* frozen       a character rig is on screen with no ``alive`` and no motion
"""

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from .design import pose_at, poses

MOVE = 0.02       # Screens per second that counts as visible motion.
SCALE_MOVE = 0.03  # Scale change per second that counts as motion.


def _speeds(layer, duration, fps):
    points = poses(layer)
    frames = max(2, round(duration * fps))
    samples = [pose_at(points, index / (frames - 1)) for index in range(frames)]
    speeds = [0.0]
    for a, b in zip(samples, samples[1:]):
        travel = math.hypot(b["x"] - a["x"], b["y"] - a["y"]) * fps
        turn = abs(b["rotate"] - a["rotate"]) * fps / 360
        grow = (abs(b["scale_x"] - a["scale_x"]) + abs(b["scale_y"] - a["scale_y"])) * fps / 2
        fade = abs(b["opacity"] - a["opacity"]) * fps
        speeds.append(travel + turn + grow * (MOVE / SCALE_MOVE) + fade * 0.2)
    return samples, speeds


def _top_level(shot):
    """Layers worth judging: no parent, or the root group of a rig instance."""
    return [layer for layer in shot.get("layers", []) if not layer.get("parent")]


def shot_report(source_shot, shot, fps, hold):
    duration = float(shot["duration"])
    notes, curves = [], {}
    layers = shot.get("layers", [])
    moving = [False] * max(2, round(duration * fps))
    starts = {}
    for layer in layers:
        samples, speeds = _speeds(layer, duration, fps)
        visible = [s["visible"] and s["opacity"] > 0.05 for s in samples]
        for index, speed in enumerate(speeds):
            if visible[index] and speed > MOVE:
                moving[index] = True
        if layer in _top_level(shot):
            curves[layer["id"]] = speeds
            for index in range(1, len(speeds)):
                if speeds[index] > MOVE * 3 and speeds[index - 1] <= MOVE * 3:
                    starts.setdefault(index, []).append(layer["id"])
                    break
        for index in range(1, len(samples)):
            jump = math.hypot(samples[index]["x"] - samples[index - 1]["x"],
                              samples[index]["y"] - samples[index - 1]["y"])
            if jump > 0.25 and visible[index] and visible[index - 1]:
                notes.append({"kind": "snap", "layer": layer["id"], "at": round(index / fps, 2),
                              "note": f"{layer['id']} jumps {jump:.2f} screens in one frame; add in-betweens "
                                      f"or hide it across the cut."})
                break
    if shot.get("camera"):
        from .camera import resolve_camera
        from .design import camera_points
        track = camera_points({**shot, "camera": resolve_camera(shot)})
        if track:
            frames = len(moving)
            cams = [pose_at(track, index / (frames - 1)) for index in range(frames)]
            for index in range(1, frames):
                a, b = cams[index - 1], cams[index]
                drift = (math.hypot(b["x"] - a["x"], b["y"] - a["y"]) + abs(b["zoom"] - a["zoom"])
                         + abs(b["rotate"] - a["rotate"]) / 360) * fps
                if drift > MOVE * 0.5:
                    moving[index] = True
    if (shot.get("three") or {}).get("camera") or shot.get("three"):
        moving = [True] * len(moving)  # 3D shots: judged by eye and the 3D camera keys.
    run = 0
    for index, flag in enumerate(moving + [True]):
        if not flag:
            run += 1
            continue
        if run / fps >= hold:
            start = (index - run) / fps
            notes.append({"kind": "dead-hold", "at": round(start, 2), "seconds": round(run / fps, 2),
                          "note": f"Nothing moves from {start:.2f}s to {index / fps:.2f}s. Add a reaction, "
                                  f"camera drift, `alive` or a `wiggle`, or cut sooner."})
        run = 0
    for frame, ids in sorted(starts.items()):
        group = [item for other, more in starts.items() if abs(other - frame) <= 1 for item in more]
        if len(set(group)) >= 3 and frame == min(f for f in starts if abs(f - frame) <= 1):
            notes.append({"kind": "lockstep", "at": round(frame / fps, 2), "layers": sorted(set(group)),
                          "note": f"{len(set(group))} layers start moving together at {frame / fps:.2f}s; "
                                  f"stagger them by 2–4 frames for overlap."})
    for layer in source_shot.get("layers", []):
        keys = layer.get("keyframes", [])
        previous = {"x": layer.get("x", 0), "y": layer.get("y", 0)}
        for key in keys:
            if float(key["at"]) <= 0:  # A key at 0 sets the start; it is not a move.
                previous = {"x": key.get("x", previous["x"]), "y": key.get("y", previous["y"])}
                continue
            distance = math.hypot(key.get("x", previous["x"]) - previous["x"], key.get("y", previous["y"]) - previous["y"])
            if distance > 0.12 and key.get("ease", "linear") == "linear" and not (key.get("ease_props") or {}):
                notes.append({"kind": "linear", "layer": layer["id"], "at": round(key["at"] * duration, 2),
                              "note": f"{layer['id']} travels {distance:.2f} screens with a linear ease into "
                                      f"{key['at'] * duration:.2f}s; use smooth/out/back or `auto`."})
                break
            previous = {"x": key.get("x", previous["x"]), "y": key.get("y", previous["y"])}
        if layer.get("kind") == "use" and "alive" not in layer and not keys and not layer.get("motion") \
                and not layer.get("pose_keys") and not layer.get("path") and duration > 1.5:
            notes.append({"kind": "frozen", "layer": layer["id"],
                          "note": f"{layer['id']} stands still for the whole {duration:g}s shot; add `alive` "
                                  f"or a pose change."})
    return notes, curves


def report(source, expanded, hold=1.0):
    fps = float(source.get("fps", 24))
    by_id = {shot["id"]: shot for scene in expanded["scenes"] for shot in scene["shots"]}
    shots, charts = [], {}
    for scene in source["scenes"]:
        for shot in scene["shots"]:
            notes, curves = shot_report(shot, by_id[shot["id"]], fps, hold)
            shots.append({"shot": shot["id"], "duration": shot["duration"], "notes": notes})
            charts[shot["id"]] = curves
    return {"fps": fps, "issues": sum(len(item["notes"]) for item in shots), "shots": shots}, charts


def chart(charts, fps, target, width=900, row=120):
    palette = ["#E8590C", "#1C7ED6", "#2F9E44", "#AE3EC9", "#F08C00", "#0CA678", "#D6336C", "#5C7CFA"]
    image = Image.new("RGB", (width, max(row, row * len(charts))), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    for index, (shot_id, curves) in enumerate(charts.items()):
        top = index * row
        draw.rectangle((0, top, width - 1, top + row - 1), outline="#DDDDDD")
        draw.text((6, top + 4), shot_id, fill="#333333")
        peak = max([max(curve) for curve in curves.values() if curve] + [0.5])
        for colour, (layer_id, curve) in zip(palette * 4, curves.items()):
            if max(curve) <= MOVE:
                continue
            points = [(60 + (width - 70) * i / max(1, len(curve) - 1),
                       top + row - 8 - (row - 24) * min(1.0, value / peak)) for i, value in enumerate(curve)]
            draw.line(points, fill=colour, width=2)
            draw.text((points[0][0] + 4, top + 16 + 11 * (list(curves).index(layer_id) % 8)), layer_id[:24], fill=colour)
    image.save(target)
    return target


def main():
    from .core import load, validate_channel
    from .pipeline import prepare_episode
    from .project import resolve_channel

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--channel", type=Path)
    parser.add_argument("--hold", type=float, default=1.0, help="seconds of total stillness that count as dead")
    parser.add_argument("--out", type=Path, help="speed chart PNG (default: next to the episode)")
    args = parser.parse_args()
    channel_path = args.channel or resolve_channel(Path(__file__).resolve().parents[1])
    channel = load(channel_path, "channel")
    validate_channel(channel, channel_path.parent)
    source = load(args.episode, "episode")
    expanded = prepare_episode(source, channel, channel_path.parent)
    data, charts = report(source, expanded, args.hold)
    target = args.out or args.episode.parent / "motion-report.png"
    data["chart"] = str(chart(charts, data["fps"], target))
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
