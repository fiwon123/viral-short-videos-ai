"""3D camera rigs: describe a move, get camera keys.

Put ``camera_rig`` on a shot's ``three`` block instead of hand-writing
position/target keys::

    "three": {"scene": "lab", "camera_rig": {"kind": "orbit", "from": -30, "to": 40}}

Kinds (angles in degrees, distances in scene units):

* ``orbit``  circle the target: ``from``/``to`` azimuth, ``radius``, ``height``
* ``dolly``  move along the view line: ``from``/``to`` distance to the target
* ``crane``  rise or fall while looking at the target: ``from``/``to`` height
* ``flyby``  straight pass: ``from``/``to`` positions, looking at ``target``
* ``follow`` trail an object: ``object``, ``offset``, ``lag`` (seconds)

Every rig takes ``ease``, ``at`` ([start, end] shot progress), ``target`` and
``handheld`` (a small seeded drift). Missing values come from the scene's
camera, so ``{"kind": "orbit", "to": 45}`` already works.
"""

import math

from .easing import ease

RATE = 30


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _add(a, b):
    return [a[i] + b[i] for i in range(3)]


def _lerp(a, b, t):
    return [a[i] + (b[i] - a[i]) * t for i in range(3)]


def _object_track(scene, shot_three, object_id):
    base = next((obj for obj in scene["objects"] if obj["id"] == object_id), None)
    if base is None:
        raise ValueError(f"camera_rig follows unknown object: {object_id}")
    keys = (shot_three.get("objects") or {}).get(object_id, [])
    points = [(0, {"position": list(base["position"])}, "linear", {})]
    state = {"position": list(base["position"])}
    for key in keys:
        if "position" in key:
            state = {"position": list(key["position"])}
        if key["at"] == 0:
            points.pop()
        points.append((key["at"], dict(state), key.get("ease", "linear"), {}))

    def at(progress):
        for index in range(1, len(points)):
            a, start, _, _ = points[index - 1]
            b, end, mode, _ = points[index]
            if progress <= b:
                t = (progress - a) / (b - a) if b > a else 1.0
                return _lerp(start["position"], end["position"], ease(t, mode))
        return points[-1][1]["position"]
    return at


def camera_keys(rig, scene, shot_three, duration):
    camera = scene["camera"]
    target = list(rig.get("target", camera["target"]))
    start_position = list(camera["position"])
    offset = _sub(start_position, target)
    radius0 = math.hypot(offset[0], offset[2])
    azimuth0 = math.degrees(math.atan2(offset[0], offset[2]))
    height0 = offset[1]
    kind = rig["kind"]
    mode = rig.get("ease", "smooth")
    window = rig.get("at") or [0, 1]
    fov = rig.get("fov")
    handheld = float(rig.get("handheld", 0))
    follow = _object_track(scene, shot_three, rig["object"]) if kind == "follow" else None
    count = max(2, round(duration * RATE))
    keys = []
    for index in range(count + 1):
        progress = index / count
        local = 0.0 if progress <= window[0] else 1.0 if progress >= window[1] else \
            (progress - window[0]) / max(1e-6, window[1] - window[0])
        k = ease(local, mode)
        look = list(target)
        if kind == "orbit":
            angle = math.radians(float(rig.get("from", azimuth0)) + (float(rig.get("to", azimuth0 + 30))
                                                                       - float(rig.get("from", azimuth0))) * k)
            radius = float(rig.get("radius", radius0))
            height = float(rig.get("height", height0))
            position = [target[0] + math.sin(angle) * radius, target[1] + height, target[2] + math.cos(angle) * radius]
        elif kind == "dolly":
            length = math.sqrt(sum(v * v for v in offset)) or 1.0
            direction = [v / length for v in offset]
            distance = float(rig.get("from", length)) + (float(rig.get("to", length * 0.6)) - float(rig.get("from", length))) * k
            position = _add(target, [v * distance for v in direction])
        elif kind == "crane":
            height = float(rig.get("from", height0)) + (float(rig.get("to", height0 + 2)) - float(rig.get("from", height0))) * k
            angle = math.radians(azimuth0)
            radius = float(rig.get("radius", radius0))
            position = [target[0] + math.sin(angle) * radius, target[1] + height, target[2] + math.cos(angle) * radius]
        elif kind == "flyby":
            position = _lerp(list(rig.get("from", start_position)), list(rig["to"]), k)
        elif kind == "follow":
            lag = float(rig.get("lag", 0.15)) / max(duration, 1e-6)
            subject = follow(max(0.0, progress - lag))
            look = follow(progress)
            position = _add(subject, list(rig.get("offset", offset)))
        else:
            raise ValueError(f"Unknown camera_rig kind: {kind}")
        if handheld:
            t = progress * duration
            position = [position[0] + handheld * (math.sin(t * 1.7) + 0.5 * math.sin(t * 3.1 + 1)),
                        position[1] + handheld * 0.7 * math.sin(t * 2.3 + 2),
                        position[2] + handheld * 0.5 * math.sin(t * 1.3 + 4)]
        key = {"at": round(progress, 5), "position": [round(v, 4) for v in position],
               "target": [round(v, 4) for v in look], "ease": "linear"}
        if fov is not None:
            first, last = (fov if isinstance(fov, list) else [fov, fov])[:2]
            key["fov"] = round(first + (last - first) * k, 3)
        keys.append(key)
    return keys


def expand(episode, library):
    if not library:
        return episode
    scenes = library[0]["scenes"]
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            three = shot.get("three")
            if not three or "camera_rig" not in three:
                continue
            rig = three.pop("camera_rig")
            if three["scene"] not in scenes:
                continue
            three["camera"] = camera_keys(rig, scenes[three["scene"]], three, float(shot["duration"]))
    return episode
