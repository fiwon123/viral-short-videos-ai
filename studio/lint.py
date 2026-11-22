"""Non-blocking warnings about authoring that silently does less than it says.

Validation rejects broken input; lint flags input that renders but probably
isn't what the author meant, so an AI author can fix it before a render.
"""

import json
import math

MAX_PARTICLES = 300
SAMPLES_PER_SECOND = 24


def _solid_states(objects, keys_by_id, t):
    """World box (or sphere) of every visible solid object at shot fraction ``t``."""
    from .physics3d import SOLID, _extent, _local_box, _rotation, _sample, _scale_at, _visible_at
    states = {}
    for obj in objects:
        if obj.get("kind") not in SOLID:
            continue
        keys = keys_by_id.get(obj["id"], [])
        if not _visible_at(obj, keys, t):
            continue
        position = _sample(keys, "position", t, obj["position"])
        rotation = _sample(keys, "rotation", t, obj.get("rotation", [0, 0, 0]))
        centre, half = _local_box(obj, _scale_at(obj, keys, t))
        rows = _rotation(rotation)
        middle = [position[i] + sum(rows[i][j] * centre[j] for j in range(3)) for i in range(3)]
        sphere = obj["kind"] == "sphere"
        states[obj["id"]] = {"centre": middle, "half": half if sphere else _extent(half, rotation), "sphere": sphere,
                             "rows": rows, "local": half, "glb": obj["kind"] == "glb"}
    return states


def _penetration(a, b):
    """How deep two solids overlap (0 when apart), and whether one simply contains the other."""
    if a["sphere"] and b["sphere"]:
        gap = math.dist(a["centre"], b["centre"])
        return max(0.0, max(a["half"]) + max(b["half"]) - gap), False
    if a["sphere"] or b["sphere"]:
        ball, box = (a, b) if a["sphere"] else (b, a)
        radius = max(ball["half"])
        inside = all(abs(ball["centre"][i] - box["centre"][i]) + radius <= box["half"][i] + 1e-6 for i in range(3))
        if inside:
            return 0.0, True  # A ball inside a room or tank, not a collision.
        from .physics3d import sphere_box
        return sphere_box(ball["centre"], radius, box)[0], False
    depth = [min(a["centre"][i] + a["half"][i], b["centre"][i] + b["half"][i])
             - max(a["centre"][i] - a["half"][i], b["centre"][i] - b["half"][i]) for i in range(3)]
    if min(depth) <= 0:
        return 0.0, False
    contains = all(depth[i] >= 2 * min(a["half"][i], b["half"][i]) - 1e-6 for i in range(3))
    return _obb_depth(a, b), contains


def _obb_depth(a, b):
    from .physics3d import sat
    return sat(a, b)[0]


def contact_warnings(shot, objects):
    """3D objects that pass into each other, sink into or hover just above what is under them."""
    three = shot.get("three") or {}
    keys_by_id = three.get("objects", {})
    ignored = set((shot.get("checks") or {}).get("ignore_3d", []))
    objects = [obj for obj in objects if obj["id"] not in ignored]

    def moves(obj_id):
        keys = keys_by_id.get(obj_id, [])
        values = {json.dumps([key.get("position"), key.get("rotation"), key.get("scale")]) for key in keys
                  if any(prop in key for prop in ("position", "rotation", "scale"))}
        return len(values) > 1
    moving = {obj["id"]: moves(obj["id"]) for obj in objects}
    duration = float(shot.get("duration", 1))
    count = max(2, round(duration * SAMPLES_PER_SECOND))
    warnings, reported = [], set()
    for index in range(count + 1):
        t = index / count
        states = _solid_states(objects, keys_by_id, t)
        names = sorted(states)
        for i, first in enumerate(names):
            for second in names[i + 1:]:
                a, b = states[first], states[second]
                pair = (first, second)
                if not moving[first] and not moving[second] and max(a["half"][0], a["half"][2], b["half"][0],
                                                                    b["half"][2]) > 1.5:
                    continue  # Fixed scenery (floors, set models) overlaps by design.
                depth, contains = _penetration(a, b)
                size = 2 * min(min(a["half"]), min(b["half"]))
                # A box around a model with ears and arms is coarse, so models need a deeper overlap.
                limit = max(0.02, (0.35 if a["glb"] or b["glb"] else 0.06) * size)
                if depth > limit and not contains and pair not in reported:
                    reported.add(pair)
                    warnings.append(f"{shot['id']}: 3D {first} and {second} pass into each other at "
                                    f"{t * duration:.2f}s ({depth:.2f} deep). Move them apart, make one a physics "
                                    f"body, or key around the contact.")
                # Resting just above a surface reads as floating.
                for upper, lower, up, low in ((first, second, a, b), (second, first, b, a)):
                    if up["sphere"] or low["sphere"]:
                        continue
                    over = all(abs(up["centre"][k] - low["centre"][k]) < low["half"][k] for k in (0, 2))
                    gap = (up["centre"][1] - up["half"][1]) - (low["centre"][1] + low["half"][1])
                    hover = (upper, lower, "hover")
                    if over and 0.01 < gap < max(0.06, 0.25 * up["half"][1] * 2) and hover not in reported \
                            and index == count:
                        reported.add(hover)
                        warnings.append(f"{shot['id']}: 3D {upper} hovers {gap:.2f} above {lower} at the end of the "
                                        f"shot. Lower it onto the surface.")
    return warnings


COVER_TOLERANCE = 0.005  # a share of the frame: under this the strip is smaller than ~5 px at 1080


def _backdrops(shot):
    """The layers that are the set: ``plane: background``, or a bottom layer that fills the frame.
    Layers with keys or depth are left out (their box moves in ways the check does not model)."""
    layers = shot.get("layers", [])
    found = [layer for layer in layers if layer.get("plane") == "background"]
    if not found and layers:
        first = layers[0]
        if float(first.get("width", 0)) >= 1 and float(first.get("height", 0)) >= 1 \
                and abs(float(first.get("x", 0.5)) - 0.5) < 0.01 and abs(float(first.get("y", 0.5)) - 0.5) < 0.01:
            found = [first]
    return [layer for layer in found if "width" in layer and "height" in layer and not layer.get("keyframes")
            and not float(layer.get("z", 0) or 0) and layer.get("kind") in ("image", "svg", "rect", "video")]


def coverage_warnings(shot, rate=48):
    """Warn when the 2D camera's view leaves a shot's backdrop: empty canvas shows at the frame's edge.

    The view of a layer with parallax ``p`` is the camera with its zoom and offset scaled by ``p``, as the
    painters apply it; the visible region in layer space is then compared with the layer's box.
    """
    from .camera import resolve_camera
    from .design import camera_points, pose_at
    if shot.get("three") or not shot.get("camera"):
        return []
    backdrops = _backdrops(shot)
    if not backdrops:
        return []
    duration = float(shot.get("duration", 1))
    probe = dict(shot)
    probe["camera"] = resolve_camera(shot, seconds=duration)
    points = camera_points(probe)
    if not points:
        return []
    warnings = []
    for layer in backdrops:
        amount = max(0.0, min(2.0, float(layer.get("parallax", 1))))
        if not amount:
            continue
        half_w, half_h = float(layer["width"]) / 2, float(layer["height"]) / 2
        cx0, cy0 = float(layer.get("x", 0.5)), float(layer.get("y", 0.5))
        worst, spans, inside = 0.0, [], None
        steps = max(2, int(duration * rate))
        for step in range(steps + 1):
            progress = step / steps
            camera = pose_at(points, progress)
            zoom = 1 + (float(camera.get("zoom", 1)) - 1) * amount
            x, y = float(camera.get("x", 0)) * amount, float(camera.get("y", 0)) * amount
            turn = abs(math.radians(float(camera.get("rotate", 0)) * amount))
            # The view's half extents in layer space, grown to hold the frame when the camera rotates.
            vw = (0.5 * math.cos(turn) + 0.5 * math.sin(turn)) / max(zoom, 1e-6)
            vh = (0.5 * math.cos(turn) + 0.5 * math.sin(turn)) / max(zoom, 1e-6)
            centre_x, centre_y = 0.5 - x / max(zoom, 1e-6), 0.5 - y / max(zoom, 1e-6)
            gap = max(cx0 - half_w - (centre_x - vw), (centre_x + vw) - (cx0 + half_w),
                      cy0 - half_h - (centre_y - vh), (centre_y + vh) - (cy0 + half_h))
            if gap > COVER_TOLERANCE:
                worst = max(worst, gap)
                if inside is None:
                    inside = progress
            elif inside is not None:
                spans.append((inside, progress))
                inside = None
        if inside is not None:
            spans.append((inside, 1.0))
        if spans:
            times = ", ".join(f"{a * duration:.2f}-{b * duration:.2f}s" for a, b in spans[:3])
            warnings.append(f"{shot['id']}/{layer['id']}: the camera's view leaves this backdrop by up to "
                            f"{worst:.1%} of the frame at {times}, so empty canvas shows at the edge. Give the "
                            f"backdrop bleed (larger width/height, the art drawn past the frame), or keep the "
                            f"camera inside it.")
    return warnings


def lint(source, expanded, library=None):
    """Return a list of human-readable warnings."""
    warnings = []
    fps = float(source.get("fps", 24))
    for scene in source.get("scenes", []):
        for shot in scene.get("shots", []):
            duration = float(shot.get("duration", 1))
            for layer in shot.get("layers", []):
                if layer.get("kind") == "particles":
                    count = int(layer.get("count") or max(1, round(float(layer.get("rate", 30)) * duration)))
                    if count > MAX_PARTICLES:
                        warnings.append(f"{shot['id']}/{layer['id']}: {count} particles requested; only "
                                        f"{MAX_PARTICLES} render. Lower rate or split into two emitters.")
            camera = shot.get("camera") or {}
            if not shot.get("three") and any("fov" in key for key in camera.get("keyframes", [])):
                warnings.append(f"{shot['id']}: 2D camera keys ignore fov; use zoom (or a three camera).")
    scenes3d = (library[0]["scenes"] if library else {})
    for scene in expanded.get("scenes", []):
        for shot in scene.get("shots", []):
            stage = scenes3d.get((shot.get("three") or {}).get("scene"))
            if stage:
                warnings.extend(contact_warnings(shot, stage["objects"]))
            warnings.extend(coverage_warnings(shot))
            duration = float(shot.get("duration", 1))
            frame = 1 / (fps * max(duration, 1e-6))
            for layer in shot.get("layers", []):
                times = [float(key["at"]) for key in layer.get("keyframes", [])]
                close = [(a, b) for a, b in zip(times, times[1:]) if b - a < frame * 0.9]
                if close:
                    a, b = close[0]
                    warnings.append(f"{shot['id']}/{layer['id']}: keys at {a:g} and {b:g} are under one frame "
                                    f"apart in a {duration:g}s shot, so the change snaps. Space them or "
                                    f"use a hold ease.")
    return warnings
