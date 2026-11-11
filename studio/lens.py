"""Anchor 2D layers to 3D events on screen.

VFX layers live in canvas fractions while the 3D action lives in world units, so
placing a dust puff on the exact floor contact needs the same projection the
renderer uses: perspective camera, vertical field of view, 9:16 aspect.
"""

import math


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _norm(a):
    length = math.sqrt(_dot(a, a)) or 1.0
    return [v / length for v in a]


def screen(point, camera, *, width=720, height=1280):
    """Canvas fractions for a world point, or None when it is behind the camera."""
    position, target = camera["position"], camera["target"]
    forward = _norm(_sub(target, position))
    right = _norm(_cross(forward, [0, 1, 0]))
    up = _cross(right, forward)
    delta = _sub(point, position)
    depth = _dot(delta, forward)
    if depth <= 0.01:
        return None
    half = math.tan(math.radians(camera.get("fov", 43)) / 2)
    aspect = width / height
    x = _dot(delta, right) / (depth * half * aspect)
    y = _dot(delta, up) / (depth * half)
    return (x + 1) / 2, (1 - y) / 2


def distance(point, camera):
    return math.dist(point, camera["position"])
