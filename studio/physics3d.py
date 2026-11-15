"""Baked 3D rigid-body physics: falls, bounces, rolls and collisions as object keys.

    "three": {"scene": "lab", "physics": {
        "gravity": -9.8, "ground": 0, "walls": [-3, 3, -2, 2],
        "bodies": {"ball": {"velocity": [1.5, 2, 0], "bounce": 0.6, "friction": 0.3},
                   "crate": {"spin": [0, 0, 180], "bounce": 0.2},
                   "post": {"fixed": true}}}}

Each body starts at its scene position (or the shot's first key for it). Bodies
are treated as spheres for collisions with each other (radius from the scale:
half the largest axis, or ``radius``). Against the ground and the tops of other
objects a box uses its rotated height, so a tumbling crate never pushes a
corner through the floor and settles onto a face. Spheres roll: their spin
follows their travel. ``spin`` is degrees per second, ``walls`` is
``[x_min, x_max, z_min, z_max]``, ``start`` (seconds) holds bodies still until
then, and ``fixed`` bodies only push.

Every other solid object in the scene (box, sphere, cylinder, cone, capsule,
GLB model) is a fixed collider at its keyed position, so a ball bounces off a
standing character instead of passing through it, and a crate can land on a
table. GLB sizes come from the model's own bounds. ``"colliders": false`` turns
that off and ``"colliders": ["table", "hero"]`` limits it to a list.
The result is ordinary position and rotation keys, so any renderer and the
camera rigs see the same motion. Physics owns the position and rotation of
its bodies; other keys (visibility, opacity, morphs) still apply.
"""

import math

RATE = 30
SUBSTEPS = 8
CONTACT = 0.004  # Resting-contact tolerance in scene units.


SOLID = {"box", "sphere", "cylinder", "cone", "capsule", "glb"}


def _size(obj):
    scale = obj.get("scale", [1, 1, 1])
    base = 0.5  # Built-in geometries are unit sized (sphere radius 0.5, box 1 x 1 x 1).
    return [abs(float(v)) * base for v in scale]


def _local_box(obj):
    """Centre offset and half extents of an object in its own (scaled) space."""
    scale = [abs(float(v)) for v in obj.get("scale", [1, 1, 1])]
    bounds = obj.get("_bounds") if obj.get("kind") == "glb" else None
    if bounds:
        low, high = bounds
        centre = [(low[i] + high[i]) / 2 * scale[i] for i in range(3)]
        half = [(high[i] - low[i]) / 2 * scale[i] for i in range(3)]
        return centre, half
    return [0.0, 0.0, 0.0], [v * 0.5 for v in scale]


def _rotation(r):
    """Rows of the three.js Euler 'XYZ' rotation matrix (radians)."""
    cx, sx, cy, sy, cz, sz = math.cos(r[0]), math.sin(r[0]), math.cos(r[1]), math.sin(r[1]), math.cos(r[2]), math.sin(r[2])
    return [[cy * cz, -cy * sz, sy],
            [cx * sz + sx * sy * cz, cx * cz - sx * sy * sz, -sx * cy],
            [sx * sz - cx * sy * cz, sx * cz + cx * sy * sz, cx * cy]]


def _extent(half, r):
    """World half extents of a rotated box."""
    rows = _rotation(r)
    return [sum(abs(rows[i][j]) * half[j] for j in range(3)) for i in range(3)]


def _sample(keys, prop, t, default):
    """Linear value of a keyed property at shot fraction ``t``."""
    points = [(float(key["at"]), key[prop]) for key in keys if prop in key]
    if not points:
        return default
    if t <= points[0][0]:
        return points[0][1]
    for (a, va), (b, vb) in zip(points, points[1:]):
        if t <= b:
            k = (t - a) / max(b - a, 1e-9)
            return [x + (y - x) * k for x, y in zip(va, vb)]
    return points[-1][1]


def _colliders(objects, spec, bodies, object_keys):
    """Fixed axis-aligned boxes (and spheres) for the scene's other solid objects."""
    choice = spec.get("colliders", "auto")
    if choice is False:
        return []
    chosen = set(choice) if isinstance(choice, list) else None
    taken = {body["id"] for body in bodies}
    result = []
    for obj in objects:
        if obj["id"] in taken or obj.get("kind") not in SOLID or (chosen is not None and obj["id"] not in chosen):
            continue
        centre, half = _local_box(obj)
        keys = (object_keys or {}).get(obj["id"], [])
        rotation = list(map(float, next((key["rotation"] for key in keys if "rotation" in key), obj.get("rotation", [0, 0, 0]))))
        rows = _rotation(rotation)
        offset = [sum(rows[i][j] * centre[j] for j in range(3)) for i in range(3)]
        result.append({"id": obj["id"], "sphere": obj["kind"] == "sphere", "keys": keys,
                       "position": list(map(float, obj["position"])), "offset": offset,
                       "half": _extent(half, rotation)})
    return result


def oriented(centre, rotation, half, offset=(0.0, 0.0, 0.0)):
    """An oriented box: world centre, rotation rows and local half extents."""
    rows = _rotation(rotation)
    middle = [centre[i] + sum(rows[i][j] * offset[j] for j in range(3)) for i in range(3)]
    return {"centre": middle, "rows": rows, "local": list(half)}


def sat(a, b):
    """Overlap depth and push axis (unit, from a towards b) of two oriented boxes; (0, None) when apart."""
    axes_a = [[a["rows"][i][j] for i in range(3)] for j in range(3)]
    axes_b = [[b["rows"][i][j] for i in range(3)] for j in range(3)]
    candidates = axes_a + axes_b
    for u in axes_a:
        for v in axes_b:
            cross = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
            length = math.sqrt(sum(c * c for c in cross))
            if length > 1e-6:
                candidates.append([c / length for c in cross])
    offset = [b["centre"][i] - a["centre"][i] for i in range(3)]
    best, best_axis = math.inf, None
    for axis in candidates:
        reach_a = sum(abs(sum(axes_a[j][i] * axis[i] for i in range(3))) * a["local"][j] for j in range(3))
        reach_b = sum(abs(sum(axes_b[j][i] * axis[i] for i in range(3))) * b["local"][j] for j in range(3))
        along = sum(offset[i] * axis[i] for i in range(3))
        overlap = reach_a + reach_b - abs(along)
        if overlap <= 0:
            return 0.0, None
        if overlap < best:
            best, best_axis = overlap, [value if along >= 0 else -value for value in axis]
    return best, best_axis


def sphere_box(centre, radius, box):
    """Overlap depth and push axis (from the box towards the sphere) of a sphere and an oriented box."""
    delta = [centre[i] - box["centre"][i] for i in range(3)]
    local = [sum(box["rows"][i][j] * delta[i] for i in range(3)) for j in range(3)]
    clamped = [max(-box["local"][j], min(box["local"][j], local[j])) for j in range(3)]
    closest = [box["centre"][i] + sum(box["rows"][i][j] * clamped[j] for j in range(3)) for i in range(3)]
    away = [centre[i] - closest[i] for i in range(3)]
    distance = math.sqrt(sum(d * d for d in away))
    if distance >= radius:
        return 0.0, None
    if distance > 1e-6:
        return radius - distance, [d / distance for d in away]
    # Centre inside the box: leave through the nearest face.
    depth, axis = min((box["local"][j] - abs(local[j]), j) for j in range(3))
    sign = 1.0 if local[axis] >= 0 else -1.0
    return depth + radius, [box["rows"][i][axis] * sign for i in range(3)]


def body_contact(a, b):
    """Overlap and normal (from a to b) of two bodies, using their real box or sphere shapes."""
    if a["box"] and b["box"]:
        return sat(oriented(a["p"], a["r"], a["half"], a["centre"]), oriented(b["p"], b["r"], b["half"], b["centre"]))
    if a["box"] or b["box"]:
        box, ball = (a, b) if a["box"] else (b, a)
        depth, normal = sphere_box(ball["p"], ball["radius"], oriented(box["p"], box["r"], box["half"], box["centre"]))
        if normal is None:
            return 0.0, None
        return depth, (normal if box is a else [-value for value in normal])
    delta = [b["p"][k] - a["p"][k] for k in range(3)]
    distance = math.sqrt(sum(d * d for d in delta)) or 1e-6
    return a["radius"] + b["radius"] - distance, [d / distance for d in delta]


def simulate(objects, spec, duration, start_keys=None, object_keys=None):
    """Return {object_id: [keys]} for the physics bodies."""
    gravity = float(spec.get("gravity", -9.8))
    ground = spec.get("ground", 0.0)
    walls = spec.get("walls")
    start = float(spec.get("start", 0.0))
    by_id = {obj["id"]: obj for obj in objects}
    bodies = []
    for body_id, body in spec.get("bodies", {}).items():
        if body_id not in by_id:
            raise ValueError(f"physics body {body_id} is not an object in the scene")
        obj = by_id[body_id]
        centre, half = _local_box(obj)
        first = (start_keys or {}).get(body_id, {})
        bodies.append({
            "id": body_id, "fixed": bool(body.get("fixed")),
            "p": list(map(float, first.get("position", obj["position"]))),
            "r": list(map(float, first.get("rotation", obj.get("rotation", [0, 0, 0])))),
            "v": list(map(float, body.get("velocity", [0, 0, 0]))),
            "w": [math.radians(float(v)) for v in body.get("spin", [0, 0, 0])],
            "radius": float(body.get("radius", max(half))), "half": half, "centre": centre,
            "half_y": body.get("half_height"), "box": obj.get("kind") not in ("sphere",),
            "bounce": float(body.get("bounce", 0.45)), "friction": float(body.get("friction", 0.35)),
            "mass": float(body.get("mass", 1.0)), "rolls": obj.get("kind") == "sphere" or bool(body.get("rolls")),
        })
    statics = _colliders(objects, spec, bodies, object_keys)

    def below(body):
        """Distance from the body's origin down to its lowest point."""
        if body["half_y"] is not None:
            return float(body["half_y"])
        if not body["box"]:
            return body["radius"]
        rows = _rotation(body["r"])
        offset = sum(rows[1][j] * body["centre"][j] for j in range(3))
        return _extent(body["half"], body["r"])[1] - offset

    def land(body, floor, dt):
        """Rest on a floor at height ``floor``: bounce, friction, rolling and settling."""
        body["p"][1] = floor + below(body)
        if body["v"][1] < 0:
            body["v"][1] = -body["v"][1] * body["bounce"] if -body["v"][1] > 0.6 else 0.0
        # Rolling resistance is far below sliding friction, so balls keep rolling and crates skid to a stop.
        grip = body["friction"] * (0.08 if body["rolls"] else 1.0)
        speed = math.hypot(body["v"][0], body["v"][2])
        slow = max(0.0, 1 - grip * abs(gravity) * dt / speed) if speed > 1e-6 else 0.0
        body["v"][0] *= slow
        body["v"][2] *= slow
        if body["rolls"]:
            body["w"] = [body["v"][2] / body["radius"], body["w"][1] * 0.98, -body["v"][0] / body["radius"]]
        else:
            body["w"] = [value * max(0.0, 1 - 8 * dt) for value in body["w"]]
            # Settle onto the nearest flat face so boxes don't rest on a corner.
            quarter = math.pi / 2
            body["r"] = [value + (round(value / quarter) * quarter - value) * min(1.0, 12 * dt)
                         for value in body["r"]]

    def collide_static(body, collider, t, dt):
        position = _sample(collider["keys"], "position", t, collider["position"])
        centre = [position[i] + collider["offset"][i] for i in range(3)]
        half = collider["half"]
        p = body["p"]
        if collider["sphere"]:
            delta = [p[i] - centre[i] for i in range(3)]
            distance = math.sqrt(sum(d * d for d in delta)) or 1e-6
            overlap = body["radius"] + max(half) - distance
            if overlap > 0:
                normal = [d / distance for d in delta]
                if normal[1] > 0.7:
                    land(body, centre[1] + max(half) * normal[1] + (1 - normal[1]) * 0, dt)
                    return
                push(body, normal, overlap)
            return
        top = centre[1] + half[1]
        inside_xz = all(centre[i] - half[i] <= p[i] <= centre[i] + half[i] for i in (0, 2))
        if inside_xz and p[1] >= centre[1]:
            if p[1] - below(body) < top + (CONTACT if body["v"][1] <= 0 else 0):
                land(body, top, dt)
            return
        if body["box"]:
            depth, normal = sat({"centre": centre, "rows": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "local": half},
                                oriented(p, body["r"], body["half"], body["centre"]))
            if normal is not None:
                push(body, normal, depth)
            return
        closest = [max(centre[i] - half[i], min(centre[i] + half[i], p[i])) for i in range(3)]
        delta = [p[i] - closest[i] for i in range(3)]
        distance = math.sqrt(sum(d * d for d in delta))
        if distance >= body["radius"]:
            return
        if distance > 1e-6:
            push(body, [d / distance for d in delta], body["radius"] - distance)
        else:  # Centre inside the box: leave by the shallowest side.
            depth = [(half[i] - abs(p[i] - centre[i]), i) for i in range(3)]
            amount, axis = min(depth)
            normal = [0.0, 0.0, 0.0]
            normal[axis] = 1.0 if p[axis] >= centre[axis] else -1.0
            push(body, normal, amount + body["radius"])

    def push(body, normal, overlap):
        for k in range(3):
            body["p"][k] += normal[k] * overlap
        closing = sum(body["v"][k] * normal[k] for k in range(3))
        if closing < 0:
            for k in range(3):
                body["v"][k] -= (1 + body["bounce"]) * closing * normal[k]

    frames = max(1, round(duration * RATE))
    dt = 1.0 / (RATE * SUBSTEPS)
    keys = {body["id"]: [] for body in bodies}

    def record(frame):
        for body in bodies:
            keys[body["id"]].append({"at": round(frame / frames, 5),
                                     "position": [round(v, 4) for v in body["p"]],
                                     "rotation": [round(v, 4) for v in body["r"]], "ease": "linear"})

    record(0)
    for frame in range(1, frames + 1):
        for _ in range(SUBSTEPS):
            now = frame / RATE
            if now < start:
                continue
            for body in bodies:
                if body["fixed"]:
                    continue
                body["v"][1] += gravity * dt
                for axis in range(3):
                    body["p"][axis] += body["v"][axis] * dt
                    body["r"][axis] += body["w"][axis] * dt
                # A resting body keeps contact through the tiny gaps settling opens, so it flattens promptly.
                if ground is not None and body["p"][1] - below(body) < ground + (CONTACT if body["v"][1] <= 0 else 0):
                    land(body, ground, dt)
                for collider in statics:
                    collide_static(body, collider, now / max(duration, 1e-6), dt)
                if walls:
                    for axis, low, high in ((0, walls[0], walls[1]), (2, walls[2], walls[3])):
                        if body["p"][axis] - body["radius"] < low:
                            body["p"][axis] = low + body["radius"]
                            body["v"][axis] = abs(body["v"][axis]) * body["bounce"]
                        elif body["p"][axis] + body["radius"] > high:
                            body["p"][axis] = high - body["radius"]
                            body["v"][axis] = -abs(body["v"][axis]) * body["bounce"]
            for i, a in enumerate(bodies):
                for b in bodies[i + 1:]:
                    if a["fixed"] and b["fixed"]:
                        continue
                    overlap, normal = body_contact(a, b)
                    if overlap <= 0:
                        continue
                    inv_a = 0.0 if a["fixed"] else 1 / a["mass"]
                    inv_b = 0.0 if b["fixed"] else 1 / b["mass"]
                    for k in range(3):
                        a["p"][k] -= normal[k] * overlap * inv_a / (inv_a + inv_b)
                        b["p"][k] += normal[k] * overlap * inv_b / (inv_a + inv_b)
                    closing = sum((b["v"][k] - a["v"][k]) * normal[k] for k in range(3))
                    if closing < 0:
                        restitution = min(a["bounce"], b["bounce"])
                        impulse = -(1 + restitution) * closing / (inv_a + inv_b)
                        for k in range(3):
                            a["v"][k] -= impulse * normal[k] * inv_a
                            b["v"][k] += impulse * normal[k] * inv_b
        record(frame)
    return keys


def expand(episode, library):
    if not library:
        return episode
    scenes = library[0]["scenes"]
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            three = shot.get("three")
            if not three or "physics" not in three or three["scene"] not in scenes:
                continue
            spec = three.pop("physics")
            existing = three.setdefault("objects", {})
            first = {object_id: next((key for key in keys if "position" in key), {})
                     for object_id, keys in existing.items()}
            baked = simulate(scenes[three["scene"]]["objects"], spec, float(shot["duration"]), first, existing)
            for object_id, keys in baked.items():
                others = [{name: value for name, value in key.items() if name not in ("position", "rotation")}
                          for key in existing.get(object_id, [])]
                others = [key for key in others if len(key) > 2 or (len(key) == 2 and "ease" not in key)]
                merged = {key["at"]: key for key in keys}
                for key in others:
                    merged.setdefault(key["at"], {"at": key["at"]}).update(key)
                existing[object_id] = [merged[at] for at in sorted(merged)]
    return episode
