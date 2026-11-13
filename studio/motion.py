"""Small manifest-ready motion recipes for weight and polish.

Each helper returns ordinary keyframes in the 0..1 shot clock. They are
deliberately declarative so the same output works in Python, HyperFrames and
Remotion. Use ``merge`` to combine recipes that touch different properties.
"""

import math


def _at(value, duration):
    return round(max(0.0, min(1.0, value / max(duration, 1e-6))), 6)


def merge(*tracks):
    """Combine keyframe lists; later values win at the same time."""
    merged = {}
    for track in tracks:
        for key in track:
            moment = key["at"]
            merged[moment] = {**merged.get(moment, {"at": moment}), **key}
    return [merged[moment] for moment in sorted(merged)]


def pop(t0=0.0, duration=0.4, amount=0.14, *, ease="back"):
    """Scale up past 1, then settle. Good for titles and prop reveals."""
    return [
        {"at": _at(t0, duration), "scale_x": 1 - amount, "scale_y": 1 - amount, "ease": "in"},
        {"at": _at(t0 + duration * 0.55, duration), "scale_x": 1 + amount,
         "scale_y": 1 + amount, "ease": ease},
        {"at": _at(t0 + duration, duration), "scale_x": 1, "scale_y": 1, "ease": "smooth"},
    ]


def anticipate(t0=0.0, duration=0.35, amount=0.08):
    """Pull back before a move, then release. The classic 'wind-up'."""
    return [
        {"at": _at(t0, duration), "scale_x": 1, "scale_y": 1, "ease": "sine"},
        {"at": _at(t0 + duration * 0.32, duration), "scale_x": 1 - amount,
         "scale_y": 1 + amount * 0.35, "ease": "smooth"},
        {"at": _at(t0 + duration, duration), "scale_x": 1, "scale_y": 1, "ease": "out"},
    ]


def impact(t0=0.0, duration=0.22, amount=0.2):
    """Squash on contact, stretch on rebound, settle. Use at a sound hit."""
    return [
        {"at": _at(t0, duration), "scale_x": 1, "scale_y": 1, "ease": "in"},
        {"at": _at(t0 + duration * 0.18, duration), "scale_x": 1 + amount,
         "scale_y": 1 - amount, "ease": "out"},
        {"at": _at(t0 + duration * 0.48, duration), "scale_x": 1 - amount * 0.35,
         "scale_y": 1 + amount * 0.5, "ease": "sine"},
        {"at": _at(t0 + duration, duration), "scale_x": 1, "scale_y": 1, "ease": "smooth"},
    ]


def settle(t0=0.0, duration=0.5, amount=0.06):
    """A damped overshoot after an entrance or a camera stop."""
    return [
        {"at": _at(t0, duration), "x": 0, "y": 0, "ease": "out"},
        {"at": _at(t0 + duration * 0.4, duration), "x": amount * 0.35, "y": -amount * 0.2,
         "ease": "sine"},
        {"at": _at(t0 + duration * 0.72, duration), "x": -amount * 0.15, "y": amount * 0.08,
         "ease": "sine"},
        {"at": _at(t0 + duration, duration), "x": 0, "y": 0, "ease": "smooth"},
    ]


def float_loop(duration=2.0, amplitude=0.012, cycles=1.0):
    """A calm vertical drift for idle characters and props."""
    keys = []
    count = max(8, round(duration * 24))
    for index in range(count + 1):
        progress = index / count
        keys.append({
            "at": round(progress, 6),
            "y": round(math.sin(progress * cycles * math.tau) * amplitude, 6),
            "ease": "sine",
        })
    return keys


def breathe(duration=2.4, amount=0.015, cycles=1.0):
    """Subtle scale pulse for a held character."""
    keys = []
    count = max(8, round(duration * 24))
    for index in range(count + 1):
        progress = index / count
        pulse = 1 + math.sin(progress * cycles * math.tau) * amount
        keys.append({"at": round(progress, 6), "scale_x": pulse, "scale_y": pulse, "ease": "sine"})
    return keys


def enter(from_x=0.0, from_y=0.0, duration=0.4, *, ease="out"):
    """Move from an offset into the layer's authored pose."""
    return [
        {"at": 0, "x": from_x, "y": from_y, "ease": "linear"},
        {"at": _at(duration, duration), "x": 0, "y": 0, "ease": ease},
    ]


def exit(to_x=0.0, to_y=0.0, duration=0.4, *, ease="in"):
    """Move away from the authored pose at the end of a shot."""
    return [
        {"at": 0, "x": 0, "y": 0, "ease": "linear"},
        {"at": 1, "x": to_x, "y": to_y, "ease": ease},
    ]
