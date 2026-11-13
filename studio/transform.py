"""Small 2D affine helpers shared by the Python renderer.

Matrices use the same six-value form as the Canvas API:
``(a, b, c, d, e, f)`` maps ``(x, y)`` to ``(a*x + c*y + e, b*x + d*y + f)``.
Keeping the maths in one place lets pivots, parent layers, cameras and
supersampling share the same transform instead of each inventing one.
"""

import math


IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def multiply(first, second):
    """Return ``first * second``: apply ``second`` first, then ``first``."""
    a, b, c, d, e, f = first
    g, h, i, j, k, l = second
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * l + e,
        b * k + d * l + f,
    )


def translate(x, y):
    return (1.0, 0.0, 0.0, 1.0, float(x), float(y))


def scale(x, y=None):
    return (float(x), 0.0, 0.0, float(x if y is None else y), 0.0, 0.0)


def rotate(degrees):
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return (cosine, sine, -sine, cosine, 0.0, 0.0)


def apply(matrix, x, y):
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def inverse(matrix):
    a, b, c, d, e, f = matrix
    determinant = a * d - b * c
    if abs(determinant) < 1e-12:
        raise ValueError("Cannot invert a singular layer transform")
    return (
        d / determinant,
        -b / determinant,
        -c / determinant,
        a / determinant,
        (c * f - d * e) / determinant,
        (b * e - a * f) / determinant,
    )


def layer_matrix(pose, width, height, pivot, *, parent=None, parent_origin=None, camera=None,
                 parallax=1.0, box=None):
    """Compose a layer's local pose, its parent, and the shot camera.

    ``pivot`` is a fraction of the layer box. A child's ``x`` and ``y`` are
    offsets from its parent's pivot in canvas fractions, which keeps rigs
    readable while leaving flat layers unchanged when no parent is present.
    """
    box_width, box_height = box if box else (width, height)
    px = float(pivot[0]) * box_width
    py = float(pivot[1]) * box_height
    translation = translate(float(pose["x"]) * width, float(pose["y"]) * height)
    if parent_origin is not None:
        translation = multiply(translate(*parent_origin), translation)
    local = multiply(
        translation,
        multiply(rotate(float(pose.get("rotate", 0.0))),
                 multiply(scale(float(pose.get("scale", 1.0))),
                          translate(-px, -py))),
    )
    world = multiply(parent, local) if parent is not None else local
    if camera is not None and parallax:
        world = multiply(camera_matrix(_parallax_camera(camera, parallax), width, height), world)
    return world


def camera_matrix(camera, width, height):
    """Camera around the canvas centre. ``x``/``y`` are canvas-fraction offsets."""
    matrix = multiply(translate(float(camera.get("x", 0.0)) * width,
                                float(camera.get("y", 0.0)) * height),
                      multiply(translate(width / 2, height / 2),
                               multiply(rotate(float(camera.get("rotate", 0.0))),
                                        multiply(scale(float(camera.get("zoom", 1.0))),
                                                 translate(-width / 2, -height / 2)))))
    return matrix


def _parallax_camera(camera, amount):
    """Scale a camera move down for backgrounds and up for foregrounds."""
    amount = max(0.0, min(2.0, float(amount)))
    return {
        **camera,
        "x": float(camera.get("x", 0.0)) * amount,
        "y": float(camera.get("y", 0.0)) * amount,
        "zoom": 1.0 + (float(camera.get("zoom", 1.0)) - 1.0) * amount,
        "rotate": float(camera.get("rotate", 0.0)) * amount,
    }


def bbox(matrix, width, height, padding=2):
    """Integer bounding box of a transformed rectangle, clipped by the caller."""
    corners = [apply(matrix, x, y) for x in (0, width) for y in (0, height)]
    left = math.floor(min(x for x, _ in corners)) - padding
    top = math.floor(min(y for _, y in corners)) - padding
    right = math.ceil(max(x for x, _ in corners)) + padding
    bottom = math.ceil(max(y for _, y in corners)) + padding
    return left, top, max(1, right - left), max(1, bottom - top)
