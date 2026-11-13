"""Shared easing maths for Python and the browser renderers.

String easings keep the existing manifest vocabulary. Objects add a custom
cubic-bezier or a spring. ``auto`` is resolved by the pose interpolator, which
needs the neighbouring keys; here it behaves like a smooth ramp so a single
value still returns a usable result.
"""

import math


def cubic_bezier(t, x1, y1, x2, y2):
    """Solve a CSS-style cubic-bezier for the y value at progress ``t``."""
    t = max(0.0, min(1.0, t))
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0

    def curve(u, a, b):
        return 3 * a * u * (1 - u) ** 2 + 3 * b * u * u * (1 - u) + u ** 3

    low, high = 0.0, 1.0
    for _ in range(24):
        middle = (low + high) / 2
        if curve(middle, x1, x2) < t:
            low = middle
        else:
            high = middle
    return curve((low + high) / 2, y1, y2)


def spring(t, stiffness=140.0, damping=12.0, mass=1.0):
    """Normalised damped spring. ``t`` is 0..1 over the segment."""
    t = max(0.0, min(1.0, t))
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    stiffness = max(0.01, float(stiffness))
    damping = max(0.0, float(damping))
    mass = max(0.0001, float(mass))
    omega = math.sqrt(stiffness / mass)
    zeta = damping / (2 * math.sqrt(stiffness * mass))
    if zeta < 1:
        wd = omega * math.sqrt(1 - zeta * zeta)
        value = 1 - math.exp(-zeta * omega * t) * (
            math.cos(wd * t) + (zeta * omega / max(wd, 1e-6)) * math.sin(wd * t))
    else:
        value = 1 - math.exp(-omega * t) * (1 + omega * t)
    return value


def ease(t, mode):
    t = max(0.0, min(1.0, t))
    if isinstance(mode, dict):
        kind = mode.get("type")
        if kind == "cubic-bezier":
            points = mode.get("points") or [0.4, 0.0, 0.2, 1.0]
            return cubic_bezier(t, *points)
        if kind == "spring":
            return spring(t, mode.get("stiffness", 140.0), mode.get("damping", 12.0),
                          mode.get("mass", 1.0))
        return t
    if mode == "in":
        return t * t
    if mode == "out":
        return 1 - (1 - t) ** 2
    if mode == "smooth":
        return t * t * (3 - 2 * t)
    if mode == "sine":
        return 0.5 - 0.5 * math.cos(math.pi * t)
    if mode == "expo":
        return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)
    if mode == "circ":
        return math.sqrt(max(0.0, 1 - (1 - t) ** 2))
    if mode == "quint":
        return 1 - (1 - t) ** 5
    if mode == "back":
        c1, c3 = 1.70158, 2.70158
        return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
    if mode == "elastic":
        if t in (0.0, 1.0):
            return t
        return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1
    if mode == "bounce":
        n1, d1 = 7.5625, 2.75
        if t < 1 / d1:
            return n1 * t * t
        if t < 2 / d1:
            t -= 1.5 / d1
            return n1 * t * t + 0.75
        if t < 2.5 / d1:
            t -= 2.25 / d1
            return n1 * t * t + 0.9375
        t -= 2.625 / d1
        return n1 * t * t + 0.984375
    if mode == "spring":
        return 1 - math.exp(-6 * t) * math.cos(9 * t)
    if mode == "hold":
        return 0.0 if t < 1 else 1.0
    if mode == "auto":
        return t * t * (3 - 2 * t)
    return t


def catmull_rom(p0, p1, p2, p3, t):
    """Uniform Catmull-Rom between p1 and p2."""
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        2 * p1
        + (-p0 + p2) * t
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
        + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
    )
