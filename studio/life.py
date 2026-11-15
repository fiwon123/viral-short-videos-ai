"""Give rigged characters automatic life: breathe, blink, glance, sway, talk.

A still character between key poses reads as dead. Put ``alive`` on a ``use``
layer (or any layer) and this expander adds the small, continuous, seeded
motion animators layer under acting:

    {"id": "pip", "kind": "use", "ref": "pip", "x": 0.5, "y": 0.86,
     "alive": {"talk": "Pip", "energy": 1}}

``alive: true`` turns everything on. Each part is found by its ``role`` tag
(see ``studio/character.py``): body/head breathe and sway, ears and antennae
follow through a beat later, arms drift, eyes blink at natural intervals,
pupils make quick glances, and the mouth swaps from the rest shape to an open
shape that flaps with the speaker's voice. Motion is added on top of whatever
keys the author wrote, so acting keys still drive the big moves.
"""

from hashlib import sha256
import math
import random

from .design import pose_at, poses

RATE = 24  # Samples per second for the composed keys.
DEFAULTS = {"breathe": 1.0, "blink": 1.0, "look": 1.0, "sway": 1.0, "talk": None, "energy": 1.0}
PROPS = ("x", "y", "scale", "scale_x", "scale_y", "rotate", "opacity", "skew_x", "skew_y",
         "blur", "tint_opacity", "frame", "visible")


def _settings(value):
    if value is True:
        return dict(DEFAULTS)
    settings = {**DEFAULTS, **(value or {})}
    for key in ("breathe", "blink", "look", "sway"):
        if settings[key] is True:
            settings[key] = 1.0
        elif settings[key] is False or settings[key] is None:
            settings[key] = 0.0
    return settings


def _rng(*parts):
    return random.Random(int.from_bytes(sha256("\0".join(map(str, parts)).encode()).digest()[:8], "big"))


def blink_curve(duration, rng, amount):
    """Scale-y multiplier for the eyes: quick close, short hold, slower open."""
    times, t = [], rng.uniform(0.5, 1.4)
    while t < duration - 0.2:
        times.append(t)
        if rng.random() < 0.18:  # Occasional double blink.
            times.append(t + 0.26)
        t += rng.uniform(2.2, 4.6) / max(0.4, amount)

    def curve(now):
        value = 1.0
        for start in times:
            local = now - start
            if 0 <= local < 0.06:
                value = min(value, 1 - 0.92 * (local / 0.06))
            elif 0.06 <= local < 0.10:
                value = min(value, 0.08)
            elif 0.10 <= local < 0.19:
                value = min(value, 0.08 + 0.92 * ((local - 0.10) / 0.09) ** 0.7)
        return value
    return curve, times


def glance_curve(duration, rng, reach):
    """Pupil offset: hold a look, then a fast 3-frame saccade to the next."""
    targets, t = [(0.0, 0.0, 0.0)], rng.uniform(0.8, 1.8)
    while t < duration:
        targets.append((t, rng.uniform(-1, 1) * reach, rng.uniform(-0.5, 0.4) * reach))
        t += rng.uniform(1.1, 2.8)

    def curve(now):
        x = y = 0.0
        for index, (start, tx, ty) in enumerate(targets):
            if now < start:
                break
            px, py = (targets[index - 1][1], targets[index - 1][2]) if index else (0.0, 0.0)
            k = min(1.0, (now - start) / 0.1)
            k = 1 - (1 - k) ** 3
            x, y = px + (tx - px) * k, py + (ty - py) * k
        return x, y
    return curve


def compose(layer, duration, modifiers):
    """Resample a layer's keys and apply additive/multiplicative modifiers."""
    points = poses(layer)
    times = {round(i / RATE, 4) for i in range(int(duration * RATE) + 1)} | {round(duration, 4)}
    times |= {round(float(key["at"]) * duration, 4) for key in layer.get("keyframes", [])}
    keys, changed = [], set()
    for seconds in sorted(times):
        progress = min(1.0, seconds / duration) if duration else 0.0
        pose = dict(pose_at(points, progress))
        for modifier in modifiers:
            for prop, (op, value) in modifier(seconds).items():
                if prop == "scale_xy":
                    pose["scale_x"] *= value[0]
                    pose["scale_y"] *= value[1]
                    changed |= {"scale_x", "scale_y"}
                    continue
                pose[prop] = pose[prop] * value if op == "mul" else pose[prop] + value
                changed.add(prop)
        keys.append((progress, pose))
    animated = set(changed)
    first = keys[0][1]
    for _, pose in keys:
        animated |= {prop for prop in PROPS if pose[prop] != first[prop]}
    result = []
    for progress, pose in keys:
        key = {"at": round(progress, 5)}
        for prop in PROPS:
            if prop in animated:
                value = pose[prop]
                key[prop] = round(value, 5) if isinstance(value, float) else value
        result.append(key)
    # Start values become the layer's base pose so the first key matches.
    for prop in animated:
        value = first[prop]
        layer[prop] = round(value, 5) if isinstance(value, float) else value
    layer["keyframes"] = [key for key in result if key["at"] > 0] or result[-1:]
    for key in layer["keyframes"]:
        key["ease"] = "linear"
    return layer


def _wave(period, phase):
    return lambda t: math.sin(2 * math.pi * t / period + phase)


def animate(shot, layer, settings):
    duration = float(shot["duration"])
    prefix = layer["id"] + "/"
    members = [item for item in shot["layers"] if item["id"].startswith(prefix)] or [layer]
    roles = {}
    for item in members:
        roles.setdefault(item.get("role", "body" if item is layer else None), []).append(item)
    energy = float(settings["energy"])
    rng = _rng(shot["id"], layer["id"], settings.get("seed", 0))
    phase = rng.uniform(0, math.tau)
    breath = _wave(rng.uniform(2.4, 3.1), phase)
    sway = _wave(rng.uniform(3.4, 4.4), phase + 1.1)
    plan = {}

    def add(item, fn):
        plan.setdefault(item["id"], (item, []))[1].append(fn)

    b = settings["breathe"] * energy
    if b:
        for item in roles.get("body", []):
            add(item, lambda t: {"scale_xy": ("mul", (1 - 0.012 * b * breath(t), 1 + 0.024 * b * breath(t)))})
        for item in roles.get("arm", []):
            side = -1 if item["id"].endswith("-l") else 1
            add(item, lambda t, side=side: {"rotate": ("add", side * 2.5 * b * breath(t - 0.35))})
        for item in roles.get("shadow", []):
            add(item, lambda t: {"scale_x": ("mul", 1 + 0.015 * b * breath(t))})
    s = settings["sway"] * energy
    if s:
        for item in roles.get("head", []) or roles.get("body", []):
            add(item, lambda t: {"rotate": ("add", 1.6 * s * sway(t))})
        for item in roles.get("ear", []) + roles.get("antenna", []):
            add(item, lambda t: {"rotate": ("add", 4.5 * s * sway(t - 0.28))})  # Follow-through lag.
    k = settings["blink"]
    if k and roles.get("eye"):
        blink, _ = blink_curve(duration, rng, k)
        for item in roles["eye"]:
            add(item, lambda t: {"scale_y": ("mul", blink(t))})
        for item in roles.get("brow", []):
            add(item, lambda t: {"y": ("add", (1 - blink(t)) * 0.004)})
    g = settings["look"]
    if g and roles.get("pupil"):
        eye_width = min(float(item.get("width", 0.04)) for item in roles.get("eye", [{"width": 0.04}]))
        glance = glance_curve(duration, rng, eye_width * 0.16 * g)
        for item in roles["pupil"]:
            add(item, lambda t: {"x": ("add", glance(t)[0]), "y": ("add", glance(t)[1] * 0.6)})
    speaker = settings.get("talk")
    if speaker:
        for item in roles.get("mouth", []):
            shape = item.get("mouth_shape", "rest")
            if shape == "rest":
                item["quiet_for"] = speaker
                item.pop("variant_group", None)
            elif shape == "open":
                item.update({"mouth_for": speaker, "talk_only": True, "visible": True})
                item.pop("variant_group", None)
                item["keyframes"] = [key for key in item.get("keyframes", []) if "visible" not in key]
    for item, modifiers in plan.values():
        compose(item, duration, modifiers)


def expand(episode):
    """Apply ``alive`` on every layer that declares it. Run after defs expansion."""
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            for layer in list(shot.get("layers", [])):
                if "alive" not in layer:
                    continue
                settings = _settings(layer.pop("alive"))
                if settings is not None:
                    animate(shot, layer, settings)
    return episode

