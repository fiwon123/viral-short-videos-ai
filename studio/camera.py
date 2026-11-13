"""Resolve camera presets and procedural shake into ordinary keyframes.

Both renderers already understand a camera track, so presets are expanded once
at load time instead of being implemented twice.
"""

import math

from .easing import ease


PRESETS = {
    "push-in": [
        {"at": 0.0, "zoom": 1.0},
        {"at": 1.0, "zoom": 1.12, "ease": "sine"},
    ],
    "pull-out": [
        {"at": 0.0, "zoom": 1.12},
        {"at": 1.0, "zoom": 1.0, "ease": "sine"},
    ],
    "crash-zoom": [
        {"at": 0.0, "zoom": 1.0},
        {"at": 0.65, "zoom": 1.35, "ease": "expo"},
        {"at": 1.0, "zoom": 1.12, "ease": "smooth"},
    ],
    "whip-pan": [
        {"at": 0.0, "x": -0.12},
        {"at": 0.55, "x": 0.12, "ease": "expo"},
        {"at": 1.0, "x": 0.0, "ease": "smooth"},
    ],
    "dolly": [
        {"at": 0.0, "x": 0.08, "zoom": 1.05},
        {"at": 1.0, "x": -0.08, "zoom": 1.0, "ease": "sine"},
    ],
    "float": [
        {"at": 0.0, "y": -0.01},
        {"at": 0.5, "y": 0.01, "ease": "sine"},
        {"at": 1.0, "y": -0.01, "ease": "sine"},
    ],
    "handheld": [],
}


def _base(camera):
    return {
        "x": float(camera.get("x", 0)),
        "y": float(camera.get("y", 0)),
        "zoom": float(camera.get("zoom", 1)),
        "rotate": float(camera.get("rotate", 0)),
    }


def _sample(keys, base, at):
    state = dict(base)
    previous = 0.0
    for key in keys:
        end = float(key["at"])
        if at <= end:
            span = max(1e-6, end - previous)
            t = max(0.0, min(1.0, (at - previous) / span))
            t = ease(t, key.get("ease", "linear"))
            for name in state:
                if name in key:
                    state[name] = state[name] + (float(key[name]) - state[name]) * t
            return state
        for name in state:
            if name in key:
                state[name] = float(key[name])
        previous = end
    return state


def _jitter(t, *, amplitude, frequency, phase):
    return amplitude * (
        math.sin(t * frequency * math.tau + phase)
        + 0.45 * math.sin(t * frequency * 2.17 * math.tau + phase * 1.7)
    )


def resolve_camera(shot, samples=None):
    """Return a camera object with a concrete ``keyframes`` list."""
    source = dict(shot.get("camera") or {})
    if samples is None:
        samples = int(source.get("samples", 60))
    samples = max(2, min(240, samples))
    preset = source.pop("preset", None)
    if preset and not source.get("keyframes"):
        if preset == "orbit":
            source["keyframes"] = [
                {"at": index / samples,
                 "x": math.cos(index / samples * math.tau) * 0.035,
                 "y": math.sin(index / samples * math.tau) * 0.014,
                 "ease": "linear"}
                for index in range(samples + 1)
            ]
        else:
            source["keyframes"] = [dict(key) for key in PRESETS.get(preset, [])]
    keyframes = [dict(key) for key in source.get("keyframes", [])]
    shake = source.get("shake")
    handheld = source.get("handheld")
    shakes = list(source.get("shakes") or [])
    if shake:
        shakes.append({"at": 0, "duration": 1, **shake})
    if handheld or preset == "handheld":
        info = handheld or {}
        shakes.append({"at": 0, "duration": 1, "amplitude": float(info.get("amplitude", 0.004)),
                       "frequency": float(info.get("frequency", 1.7)),
                       "decay": 0.0, "seed": float(info.get("seed", 2.0))})
    if shakes:
        base = _base(source)
        generated = []
        for index in range(samples + 1):
            at = index / samples
            state = _sample(keyframes, base, at)
            for item in shakes:
                start = float(item.get("at", 0))
                duration = max(1e-4, float(item.get("duration", 1)))
                local = at - start
                if local < 0 or local > duration:
                    continue
                phase = local / duration
                amplitude = float(item.get("amplitude", 0.008))
                frequency = float(item.get("frequency", 11.0))
                decay = float(item.get("decay", 0.35))
                seed = float(item.get("seed", 1.0))
                envelope = math.exp(-decay * phase * 4.0)
                state["x"] = state["x"] + _jitter(local, amplitude=amplitude * envelope,
                                                   frequency=frequency, phase=seed)
                state["y"] = state["y"] + _jitter(local, amplitude=amplitude * 0.7 * envelope,
                                                   frequency=frequency * 1.31, phase=seed + 1.2)
                state["rotate"] = state.get("rotate", 0) + _jitter(
                    local, amplitude=amplitude * 180 * envelope, frequency=frequency * 0.73,
                    phase=seed + 2.4)
            generated.append({"at": round(at, 6), **{key: round(value, 6) for key, value in state.items()}})
        keyframes = generated
    return {**source, "keyframes": keyframes}
