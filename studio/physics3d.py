"""Baked 3D rigid-body physics: falls, bounces, rolls and collisions as object keys.

    "three": {"scene": "lab", "physics": {
        "gravity": -9.8, "ground": 0, "walls": [-3, 3, -2, 2],
        "bodies": {"ball": {"velocity": [1.5, 2, 0], "bounce": 0.6, "friction": 0.3},
                   "crate": {"spin": [0, 0, 180], "bounce": 0.2},
                   "post": {"fixed": true}}}}

Each body starts at its scene position (or the shot's first key for it). Bodies
are treated as spheres for collisions with each other (radius from the scale:
half the largest axis, or ``radius``) and use their half height for the ground,
so boxes land flat. Spheres roll: their spin follows their travel. ``spin`` is
degrees per second, ``walls`` is ``[x_min, x_max, z_min, z_max]``, ``start``
(seconds) holds bodies still until then, and ``fixed`` bodies only push.
The result is ordinary position and rotation keys, so any renderer and the
camera rigs see the same motion. Physics owns the position and rotation of
its bodies; other keys (visibility, opacity, morphs) still apply.
"""

import math

RATE = 30
SUBSTEPS = 8


def _size(obj):
    scale = obj.get("scale", [1, 1, 1])
    base = 0.5  # Built-in geometries are unit sized (sphere radius 0.5, box 1 x 1 x 1).
    return [abs(float(v)) * base for v in scale]


def simulate(objects, spec, duration, start_keys=None):
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
        half = _size(obj)
        first = (start_keys or {}).get(body_id, {})
        bodies.append({
            "id": body_id, "fixed": bool(body.get("fixed")),
            "p": list(map(float, first.get("position", obj["position"]))),
            "r": list(map(float, first.get("rotation", obj.get("rotation", [0, 0, 0])))),
            "v": list(map(float, body.get("velocity", [0, 0, 0]))),
            "w": [math.radians(float(v)) for v in body.get("spin", [0, 0, 0])],
            "radius": float(body.get("radius", max(half))), "half_y": float(body.get("half_height", half[1])),
            "bounce": float(body.get("bounce", 0.45)), "friction": float(body.get("friction", 0.35)),
            "mass": float(body.get("mass", 1.0)), "rolls": obj.get("kind") in ("sphere", "glb") or body.get("rolls"),
        })
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
                if ground is not None and body["p"][1] - body["half_y"] < ground:
                    body["p"][1] = ground + body["half_y"]
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
                    delta = [b["p"][k] - a["p"][k] for k in range(3)]
                    distance = math.sqrt(sum(d * d for d in delta)) or 1e-6
                    overlap = a["radius"] + b["radius"] - distance
                    if overlap <= 0 or (a["fixed"] and b["fixed"]):
                        continue
                    normal = [d / distance for d in delta]
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
            baked = simulate(scenes[three["scene"]]["objects"], spec, float(shot["duration"]), first)
            for object_id, keys in baked.items():
                others = [{name: value for name, value in key.items() if name not in ("position", "rotation")}
                          for key in existing.get(object_id, [])]
                others = [key for key in others if len(key) > 2 or (len(key) == 2 and "ease" not in key)]
                merged = {key["at"]: key for key in keys}
                for key in others:
                    merged.setdefault(key["at"], {"at": key["at"]}).update(key)
                existing[object_id] = [merged[at] for at in sorted(merged)]
    return episode
