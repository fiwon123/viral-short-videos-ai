"""Manifest-native motion: recipes, paths, wiggle and follow-through.

Each field lives on a layer and expands at load time into plain keys (see
``studio/keys.py``), so both renderers get it for free:

``motion``  timed recipes applied on top of the authored pose (seconds)::

    "motion": [{"recipe": "anticipate", "t": 0.4},
               {"recipe": "jump", "t": 0.6, "height": 0.12},
               {"recipe": "impact", "t": 1.05}]

    pop, anticipate, impact, settle, shake, spin, enter, exit, drop, jump,
    nod, wobble. ``t`` is the start in seconds, ``d`` the duration.

``path``    move along a smooth curve through points, optionally facing the
            direction of travel::

    "path": {"points": [[0.1, 0.8], [0.5, 0.3], [0.9, 0.7]], "at": [0.1, 0.8],
             "ease": "smooth", "orient": true}

``wiggle``  seeded smooth noise on any property, for idle life and jitter::

    "wiggle": [{"prop": "rotate", "amp": 3, "freq": 1.5}]

``follow``  spring-driven secondary motion::

    "follow": {"target": "hero", "lag": 0.08}                    # chase position
    "follow": {"target": "hero", "mode": "drag", "gain": 6}      # swing like a tail

Order inside a shot: recipes, paths and wiggle first, then follow (so a
follower sees its target's final motion).
"""

import math
import random

from .design import pose_at, poses
from .easing import ease
from .keys import compose

GRAVITY = 5.0  # Screen heights per second squared: cartoon-weighted falls.


def _window(t, start, duration):
    if duration <= 0:
        return 1.0 if t >= start else 0.0
    return max(0.0, min(1.0, (t - start) / duration))


def _segments(t, start, duration, stops):
    """Piecewise value over [start, start+duration]: stops are (fraction, value, ease)."""
    local = _window(t, start, duration)
    previous_at, previous_value = stops[0][0], stops[0][1]
    if local <= previous_at:
        return previous_value
    for at, value, mode in stops[1:]:
        if local <= at:
            span = max(1e-6, at - previous_at)
            return previous_value + (value - previous_value) * ease((local - previous_at) / span, mode)
        previous_at, previous_value = at, value
    return stops[-1][1]


def _scale_pair(sx, sy):
    return {"scale_xy": ("mul", (sx, sy))}


def recipe(spec, duration, aspect):
    """Return a modifier function for one motion recipe."""
    name = spec["recipe"]
    t0 = float(spec.get("t", 0))
    amount = spec.get("amount")
    defaults = {"pop": 0.35, "anticipate": 0.3, "impact": 0.24, "settle": 0.5, "shake": 0.35, "spin": 0.5,
                "enter": 0.45, "exit": 0.4, "drop": 1.4, "jump": 0.55, "nod": 0.35, "wobble": 0.8}
    d = float(spec.get("d", defaults.get(name, 0.4)))
    if name == "pop":
        a = float(amount if amount is not None else 0.14)
        appear = spec.get("appear", True)

        def modifier(t):
            if t < t0:
                return {"opacity": ("mul", 0.0)} if appear else {}
            value = _segments(t, t0, d, [(0, 0.2, "linear"), (0.55, 1 + a, "back"), (1, 1.0, "smooth")])
            return _scale_pair(value, value)
        return modifier
    if name == "anticipate":
        a = float(amount if amount is not None else 0.1)
        return lambda t: _scale_pair(_segments(t, t0, d, [(0, 1, "linear"), (0.55, 1 + a * 0.6, "sine"), (1, 1, "out")]),
                                     _segments(t, t0, d, [(0, 1, "linear"), (0.55, 1 - a, "sine"), (1, 1, "out")]))
    if name == "impact":
        a = float(amount if amount is not None else 0.22)
        return lambda t: _scale_pair(
            _segments(t, t0, d, [(0, 1, "linear"), (0.15, 1 + a, "out"), (0.45, 1 - a * 0.35, "sine"), (1, 1, "smooth")]),
            _segments(t, t0, d, [(0, 1, "linear"), (0.15, 1 - a, "out"), (0.45, 1 + a * 0.45, "sine"), (1, 1, "smooth")]))
    if name == "settle":
        a = float(amount if amount is not None else 0.03)
        direction = spec.get("direction", [1, 0])

        def modifier(t):
            if t < t0 or t > t0 + d:
                return {}
            local = (t - t0) / d
            offset = a * math.exp(-5 * local) * math.sin(local * math.pi * 3)
            return {"x": ("add", offset * direction[0]), "y": ("add", offset * direction[1])}
        return modifier
    if name == "shake":
        a = float(amount if amount is not None else 0.012)
        rng = random.Random(int(spec.get("seed", 7)))
        phases = [rng.uniform(0, math.tau) for _ in range(3)]

        def modifier(t):
            if t < t0 or t > t0 + d:
                return {}
            decay = 1 - (t - t0) / d
            wobble = math.sin((t - t0) * 52 + phases[0]) * 0.6 + math.sin((t - t0) * 31 + phases[1]) * 0.4
            return {"x": ("add", a * decay * wobble),
                    "rotate": ("add", a * 120 * decay * math.sin((t - t0) * 44 + phases[2]))}
        return modifier
    if name == "spin":
        turns = float(spec.get("turns", 1))
        mode = spec.get("ease", "smooth")
        return lambda t: {"rotate": ("add", 360 * turns * ease(_window(t, t0, d), mode))}
    if name in {"enter", "exit"}:
        offset = spec.get("from" if name == "enter" else "to", [0, 0.3] if name == "enter" else [0, 0.3])
        mode = spec.get("ease", "back" if name == "enter" else "in")
        if name == "enter":
            return lambda t: {"x": ("add", offset[0] * (1 - ease(_window(t, t0, d), mode))),
                              "y": ("add", offset[1] * (1 - ease(_window(t, t0, d), mode)))}
        return lambda t: {"x": ("add", offset[0] * ease(_window(t, t0, d), mode)),
                          "y": ("add", offset[1] * ease(_window(t, t0, d), mode))}
    if name == "drop":
        return _drop(t0, float(spec.get("height", 0.4)), int(spec.get("bounces", 2)),
                     float(spec.get("restitution", 0.42)), float(spec.get("squash", 0.2)))
    if name == "jump":
        return _jump(t0, d, float(spec.get("height", 0.1)), float(spec.get("squash", 0.18)),
                     spec.get("to"))
    if name == "nod":
        a = float(amount if amount is not None else 8)
        return lambda t: {"rotate": ("add", a * math.sin(_window(t, t0, d) * math.pi * 2) * (1 - _window(t, t0, d)))}
    if name == "wobble":
        a = float(amount if amount is not None else 10)
        return lambda t: {} if t < t0 else {
            "rotate": ("add", a * math.exp(-4 * (t - t0) / d) * math.sin((t - t0) / d * math.pi * 6))}
    raise ValueError(f"Unknown motion recipe: {name}")


def _drop(t0, height, bounces, restitution, squash):
    """Fall from ``height`` above the authored pose, bounce, squash on contact."""
    events, t, v, y, remaining = [], 0.0, 0.0, -height, bounces
    samples = []
    step = 1 / 480
    while t < 4.0:
        v += GRAVITY * step
        y += v * step
        t += step
        if y >= 0:
            y = 0.0
            events.append((t, abs(v)))
            if remaining > 0 and abs(v) > 0.25:
                v = -abs(v) * restitution
                remaining -= 1
            else:
                samples.append((t, 0.0))
                break
        samples.append((t, y))
    end = samples[-1][0]

    def offset(local):
        if local <= 0:
            return -height
        if local >= end:
            return 0.0
        low, high = 0, len(samples) - 1
        while low < high:
            middle = (low + high) // 2
            if samples[middle][0] < local:
                low = middle + 1
            else:
                high = middle
        return samples[low][1]

    def modifier(t):
        local = t - t0
        result = {"y": ("add", offset(local))}
        sx = sy = 1.0
        for moment, speed in events:
            k = local - moment
            if -0.02 <= k <= 0.16:
                strength = squash * min(1.0, speed / 2.5) * math.exp(-max(0.0, k) * 22) * (1 if k >= 0 else 0.5)
                sx, sy = sx * (1 + strength), sy * (1 - strength)
        if local < 0:
            result["opacity"] = ("mul", 0.0)
        result["scale_xy"] = ("mul", (sx, sy))
        return result
    return modifier


def _jump(t0, d, height, squash, to):
    """Anticipation squash, stretched arc, landing squash: the classic cartoon hop."""
    crouch, air, land = 0.18, 0.62, 0.2
    dx = (to or [0, 0])[0] if to else 0.0
    dy = (to or [0, 0])[1] if to else 0.0

    def modifier(t):
        local = _window(t, t0, d)
        result = {}
        sx = sy = 1.0
        if local < crouch:
            k = math.sin(local / crouch * math.pi / 2)
            sx, sy = 1 + squash * k, 1 - squash * k
        elif local < crouch + air:
            k = (local - crouch) / air
            arc = 4 * k * (1 - k)
            stretch = squash * 0.8 * (1 - abs(2 * k - 1)) ** 2 if k < 0.5 else 0.0
            sx, sy = 1 - stretch * 0.5, 1 + stretch
            result["y"] = ("add", -height * arc + dy * ease(k, "sine"))
            result["x"] = ("add", dx * ease(k, "sine"))
        else:
            k = (local - crouch - air) / land
            bump = math.sin(min(1.0, k) * math.pi) * (1 - k)
            sx, sy = 1 + squash * bump, 1 - squash * bump
            result["x"], result["y"] = ("add", dx), ("add", dy)
        if t > t0 + d:
            result["x"], result["y"] = ("add", dx), ("add", dy)
        result["scale_xy"] = ("mul", (sx, sy))
        return result
    return modifier


# ---------------------------------------------------------------- path

def _catmull(points, closed):
    if closed:
        points = [points[-1], *points, points[0], points[1]]
    else:
        points = [points[0], *points, points[-1]]
    curve = []
    for i in range(1, len(points) - 2):
        p0, p1, p2, p3 = points[i - 1], points[i], points[i + 1], points[i + 2]
        for step in range(24):
            u = step / 24
            u2, u3 = u * u, u * u * u
            curve.append(tuple(0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * u + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * u2
                                      + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * u3) for k in range(2)))
    curve.append(tuple(points[-2]))
    return curve


def path(spec, duration, aspect):
    points = [tuple(map(float, point)) for point in spec["points"]]
    if len(points) < 2:
        raise ValueError("A path needs at least two points")
    curve = _catmull(points, bool(spec.get("closed")))
    lengths = [0.0]
    for a, b in zip(curve, curve[1:]):
        lengths.append(lengths[-1] + math.hypot((b[0] - a[0]) * aspect, b[1] - a[1]))
    total = lengths[-1] or 1.0
    start, end = (spec.get("at") or [0, 1])
    t0, t1 = float(start) * duration, float(end) * duration
    mode = spec.get("ease", "smooth")
    orient = spec.get("orient", False)
    offset = 0.0 if orient is True else float(orient or 0)

    def locate(fraction):
        target = fraction * total
        low, high = 0, len(lengths) - 1
        while low < high:
            middle = (low + high) // 2
            if lengths[middle] < target:
                low = middle + 1
            else:
                high = middle
        index = max(1, low)
        a, b = curve[index - 1], curve[index]
        span = lengths[index] - lengths[index - 1] or 1.0
        k = (target - lengths[index - 1]) / span
        return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k), (b[0] - a[0], b[1] - a[1])

    def modifier(t):
        fraction = ease(_window(t, t0, t1 - t0), mode)
        (x, y), (dx, dy) = locate(fraction)
        result = {"x": ("set", x), "y": ("set", y)}
        if orient is not False and orient is not None:
            result["rotate"] = ("set", math.degrees(math.atan2(dy, dx * aspect)) + offset)
        return result
    return modifier


# ---------------------------------------------------------------- wiggle

def _noise(seed, octaves):
    rng = random.Random(seed)
    lattice = [rng.uniform(-1, 1) for _ in range(512)]

    def value(x):
        total, amplitude, frequency, norm = 0.0, 1.0, 1.0, 0.0
        for octave in range(octaves):
            p = x * frequency + octave * 37.1
            i = math.floor(p)
            f = p - i
            f = f * f * (3 - 2 * f)
            a, b = lattice[i % 512], lattice[(i + 1) % 512]
            total += (a + (b - a) * f) * amplitude
            norm += amplitude
            amplitude *= 0.5
            frequency *= 2
        return total / norm
    return value


def wiggle(spec, duration, index):
    prop = spec["prop"]
    amp = float(spec.get("amp", {"rotate": 3, "scale": 0.03}.get(prop, 0.006)))
    freq = float(spec.get("freq", 1.5))
    noise = _noise(int(spec.get("seed", 11 + index * 17)), int(spec.get("octaves", 2)))
    start, end = spec.get("at") or [0, 1]
    t0, t1 = float(start) * duration, float(end) * duration

    def modifier(t):
        if t < t0 or t > t1:
            return {}
        fade = min(1.0, (t - t0) / 0.2, (t1 - t) / 0.2) if t1 - t0 > 0.4 else 1.0
        value = noise(t * freq) * amp * fade
        if prop == "scale":
            return {"scale_xy": ("mul", (1 + value, 1 + value))}
        if prop == "opacity":
            return {"opacity": ("mul", max(0.0, 1 + value))}
        return {prop: ("add", value)}
    return modifier


# ---------------------------------------------------------------- follow

def _track(layer, duration, props):
    points = poses(layer)
    return lambda t: (pose_at(points, max(0.0, min(1.0, t / duration))) if duration else points[0][1])


def follow(spec, layer, by_id, duration, aspect):
    target_id = spec["target"]
    if target_id not in by_id and "/" in layer["id"]:
        target_id = layer["id"].rsplit("/", 1)[0] + "/" + target_id
    if target_id not in by_id:
        raise ValueError(f"{layer['id']} follows unknown layer {spec['target']}")
    target = _track(by_id[target_id], duration, None)
    stiffness = float(spec.get("stiffness", 140))
    damping = float(spec.get("damping", 12 if spec.get("mode") != "drag" else 7))
    lag = float(spec.get("lag", 0.0))
    step = 1 / 240
    times = [i * step for i in range(int(duration / step) + 2)]
    if spec.get("mode") == "drag":
        gain = float(spec.get("gain", 6.0))
        angle, velocity, samples = 0.0, 0.0, []
        previous = [target(0)["x"], target(0)["y"]]
        speed = [0.0, 0.0]
        for t in times:
            pose = target(max(0.0, t - lag))
            new_speed = [(pose["x"] - previous[0]) / step * aspect, (pose["y"] - previous[1]) / step]
            accel = [(new_speed[0] - speed[0]) / step, (new_speed[1] - speed[1]) / step]
            previous, speed = [pose["x"], pose["y"]], new_speed
            drive = -gain * (accel[0] + 0.4 * accel[1]) / 60
            force = -stiffness * angle - damping * velocity + drive
            velocity += force * step
            angle += velocity * step
            samples.append(max(-45.0, min(45.0, angle)))

        def modifier(t):
            return {"rotate": ("add", samples[min(len(samples) - 1, int(t / step))])}
        return modifier
    props = spec.get("props", ["x", "y"])
    offset = spec.get("offset", [0, 0])
    origin = target(0)
    state = {prop: origin[prop] + (offset[i] if i < 2 and prop in ("x", "y") else 0) for i, prop in enumerate(props)}
    velocity = {prop: 0.0 for prop in props}
    samples = []
    for t in times:
        goal = target(max(0.0, t - lag))
        for i, prop in enumerate(props):
            aim = goal[prop] + (offset[i] if i < 2 and prop in ("x", "y") else 0)
            force = stiffness * (aim - state[prop]) - damping * velocity[prop]
            velocity[prop] += force * step
            state[prop] += velocity[prop] * step
        samples.append(dict(state))

    def modifier(t):
        sample = samples[min(len(samples) - 1, int(t / step))]
        return {prop: ("set", value) for prop, value in sample.items()}
    return modifier


# ---------------------------------------------------------------- expand

def expand(episode):
    aspect = float(episode.get("width", 1080)) / float(episode.get("height", 1920))
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            duration = float(shot["duration"])
            layers = shot.get("layers", [])
            followers = []
            for layer in layers:
                modifiers = []
                if "path" in layer:
                    modifiers.append(path(layer.pop("path"), duration, aspect))
                for spec in layer.pop("motion", []) or []:
                    modifiers.append(recipe(spec, duration, aspect))
                for index, spec in enumerate(layer.pop("wiggle", []) or []):
                    modifiers.append(wiggle(spec, duration, index))
                if modifiers:
                    compose(layer, duration, modifiers)
                if "follow" in layer:
                    followers.append(layer)
            by_id = {layer["id"]: layer for layer in layers}
            for layer in followers:
                specs = layer.pop("follow")
                specs = specs if isinstance(specs, list) else [specs]
                compose(layer, duration, [follow(spec, layer, by_id, duration, aspect) for spec in specs])
    return episode
