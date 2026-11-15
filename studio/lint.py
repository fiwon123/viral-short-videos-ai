"""Non-blocking warnings about authoring that silently does less than it says.

Validation rejects broken input; lint flags input that renders but probably
isn't what the author meant, so an AI author can fix it before a render.
"""

import math

MAX_PARTICLES = 300
SAMPLES_PER_SECOND = 24


def _solid_states(objects, keys_by_id, t):
    """World box (or sphere) of every visible solid object at shot fraction ``t``."""
    from .physics3d import SOLID, _extent, _local_box, _rotation, _sample
    states = {}
    for obj in objects:
        if obj.get("kind") not in SOLID:
            continue
        keys = keys_by_id.get(obj["id"], [])
        visible = obj.get("visible", True)
        for key in keys:
            if float(key["at"]) <= t + 1e-9 and "visible" in key:
                visible = key["visible"]
        if visible is False:
            continue
        position = _sample(keys, "position", t, obj["position"])
        rotation = _sample(keys, "rotation", t, obj.get("rotation", [0, 0, 0]))
        centre, half = _local_box(obj)
        rows = _rotation(rotation)
        middle = [position[i] + sum(rows[i][j] * centre[j] for j in range(3)) for i in range(3)]
        sphere = obj["kind"] == "sphere"
        states[obj["id"]] = {"centre": middle, "half": half if sphere else _extent(half, rotation), "sphere": sphere,
                             "rows": rows, "local": half}
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
                depth, contains = _penetration(a, b)
                size = 2 * min(min(a["half"]), min(b["half"]))
                pair = (first, second)
                if depth > max(0.02, 0.06 * size) and not contains and pair not in reported:
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
