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
* reach        an ``ik`` target is farther than the limb can reach, so the hand
               points at it but never touches it
* contrast     text (below WCAG 3:1) or a foreground shape (below 1.4:1) nearly
               matches the solid colour behind it; judged from authored fills
               and the palette
"""

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from .design import DEFAULT_PALETTE, layer_order, pose_at, poses, resolve_color

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
                and not layer.get("pose_keys") and not layer.get("path") and not layer.get("ik") and duration > 1.5:
            notes.append({"kind": "frozen", "layer": layer["id"],
                          "note": f"{layer['id']} stands still for the whole {duration:g}s shot; add `alive` "
                                  f"or a pose change."})
    return notes, curves


TEXT_CONTRAST = 3.0   # WCAG large-text minimum.
SHAPE_CONTRAST = 1.4  # Below this a shape all but vanishes into what is behind it.
SOLID = ("rect", "ellipse", "polygon")


def _rgb(paint, palette):
    """Average RGB of a palette role, hex or gradient; None when unknown."""
    if isinstance(paint, dict):
        stops = [_rgb(stop.get("color"), palette) for stop in paint.get("stops", [])]
        stops = [stop for stop in stops if stop]
        return tuple(sum(channel) / len(stops) for channel in zip(*stops)) if stops else None
    colour = resolve_color(paint, palette)
    if not isinstance(colour, str) or not colour.startswith("#") or len(colour) < 7:
        return None
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def _luminance(rgb):
    def linear(value):
        value /= 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
    red, green, blue = (linear(value) for value in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _box(layer, pose):
    scale = pose.get("scale", 1)
    w = float(layer.get("width", 0.55)) * abs(pose.get("scale_x", scale))
    h = float(layer.get("height", 0.2)) * abs(pose.get("scale_y", scale))
    return pose["x"] - w / 2, pose["y"] - h / 2, pose["x"] + w / 2, pose["y"] + h / 2


def contrast_notes(shot, palette, progress=(0.15, 0.5, 0.9)):
    """Flag top-level text and shapes whose colour nearly matches the solid fill behind them."""
    palette = palette or DEFAULT_PALETTE
    ground = _rgb(shot.get("background", "background"), palette) or _rgb("#000000", palette)
    layers = [layer for layer in layer_order(shot.get("layers", [])) if not layer.get("parent")]
    layers.sort(key=lambda layer: layer.get("plane") != "background")
    tracks = {layer["id"]: poses(layer) for layer in layers}
    notes, flagged = [], set()
    for at in progress:
        behind = []  # (box, rgb) of solid layers painted so far.
        for layer in layers:
            pose = pose_at(tracks[layer["id"]], at)
            if not pose["visible"] or pose["opacity"] < 0.5:
                continue
            kind = layer["kind"]
            box = _box(layer, pose)
            if kind in ("text",) + SOLID and layer["id"] not in flagged:
                fill = _rgb(layer.get("fill", "foreground"), palette)
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                hit = next(((rgb, backdrop) for rect, rgb, backdrop in reversed(behind)
                            if rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]), (ground, True))
                under, backdrop = hit
                full = box[0] <= 0 and box[1] <= 0 and box[2] >= 1 and box[3] >= 1
                # Scenery is layered low-contrast on purpose, and a shape stacked on a same-colour
                # foreground shape is building one form, so only text and stand-alone shapes count.
                scenery = kind != "text" and (layer.get("plane") == "background"
                                              or (fill == under and not backdrop))
                if fill and not full and not scenery:
                    helpers = [fill] + [_rgb((layer.get(key) or {}).get("color", "background"), palette)
                                        for key in ("stroke", "shadow")
                                        if isinstance(layer.get(key), dict) and layer[key].get("width", 1)]
                    best = max(contrast(rgb, under) for rgb in helpers if rgb)
                    floor = TEXT_CONTRAST if kind == "text" else SHAPE_CONTRAST
                    if best < floor:
                        flagged.add(layer["id"])
                        what = "text" if kind == "text" else "shape"
                        notes.append({"kind": "contrast", "layer": layer["id"], "ratio": round(best, 2),
                                      "at": round(at * float(shot["duration"]), 2),
                                      "note": f"{layer['id']} ({what}) is {best:.1f}:1 against what is behind it "
                                              f"(needs {floor:g}:1); change its fill, add a `stroke` or `shadow`, "
                                              f"or put a contrasting card behind it."})
            if kind in SOLID and isinstance(layer.get("fill", "foreground"), str) and pose["opacity"] >= 0.9:
                rgb = _rgb(layer.get("fill", "foreground"), palette)
                if rgb:
                    behind.append((box, rgb, layer.get("plane") == "background"))
    return notes


def reach_notes(source_shot, shot, width, height):
    """Flag ik keys whose target sits beyond the chain's full reach."""
    from .ik import Skeleton
    groups = [layer for layer in source_shot.get("layers", []) if layer.get("ik")]
    if not groups:
        return []
    skeleton = Skeleton(shot, width, height)
    notes = []
    for group in groups:
        prefix = group["id"] + "/"

        def find(name):
            return next((item for item in (prefix + name, name) if item in skeleton.layers), None)
        for spec in group["ik"]:
            chain = [find(name) for name in spec["chain"]]
            end = find(spec["end"]) if spec.get("end") else None
            tip = spec.get("tip") or (skeleton.layers[chain[-1]].get("tip") if chain[-1] else None)
            if None in chain or (not end and not tip):
                continue
            for key in spec.get("keys", []):
                if key.get("release"):
                    continue
                seconds = min(skeleton.duration, float(key["t"]) + float(key.get("d", 0.25)))
                if "layer" in key:
                    target_id = find(key["layer"])
                    if not target_id:
                        continue
                    target = skeleton.world(target_id, seconds)[0]
                else:
                    target = (float(key["x"]) * width, float(key["y"]) * height)
                joints = [skeleton.world(part, seconds)[0] for part in chain]
                effector = skeleton.world(end, seconds)[0] if end else skeleton.point(chain[-1], seconds, tip)
                points = joints + [effector]
                reach = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
                distance = math.dist(joints[0], target)
                if reach > 0 and distance > reach * 1.05:
                    notes.append({"kind": "reach", "layer": group["id"], "at": round(seconds, 2),
                                  "note": f"{group['id']} {'/'.join(spec['chain'])} can't reach its target at "
                                          f"{seconds:.2f}s ({distance / reach:.1f}x its length); it points but "
                                          f"won't touch. Move the character or the target closer."})
    return notes


def report(source, expanded, hold=1.0, palette=None):
    fps = float(source.get("fps", 24))
    by_id = {shot["id"]: shot for scene in expanded["scenes"] for shot in scene["shots"]}
    shots, charts = [], {}
    for scene in source["scenes"]:
        for shot in scene["shots"]:
            notes, curves = shot_report(shot, by_id[shot["id"]], fps, hold)
            notes += contrast_notes(by_id[shot["id"]], palette)
            notes += reach_notes(shot, by_id[shot["id"]], float(source.get("width", 1080)),
                                 float(source.get("height", 1920)))
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
    data, charts = report(source, expanded, args.hold, channel.get("palette"))
    target = args.out or args.episode.parent / "motion-report.png"
    data["chart"] = str(chart(charts, data["fps"], target))
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
