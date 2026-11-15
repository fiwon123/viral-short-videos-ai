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
    """Positive degrees turn counter-clockwise on screen, like PIL and browser/painter.mjs."""
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return (cosine, -sine, sine, cosine, 0.0, 0.0)


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


def skew(x_degrees, y_degrees):
    """Shear matrix using the same degrees as the browser renderer."""
    return (1.0, math.tan(math.radians(float(y_degrees))),
            math.tan(math.radians(float(x_degrees))), 1.0, 0.0, 0.0)


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
    uniform = float(pose.get("scale", 1.0))
    local = multiply(
        translation,
        multiply(rotate(float(pose.get("rotate", 0.0))),
                 multiply(skew(pose.get("skew_x", 0.0), pose.get("skew_y", 0.0)),
                          multiply(scale(float(pose.get("scale_x", uniform)),
                                         float(pose.get("scale_y", uniform))),
                                   translate(-px, -py)))),
    )
    if parent is not None:
        # Children inherit depth and camera through the parent's world matrix.
        return multiply(parent, local)
    world = local
    depth = depth_scale(pose.get("z", 0.0), camera)
    if depth != 1.0:
        centre = (width / 2, height / 2)
        world = multiply(translate(*centre), multiply(scale(depth), multiply(translate(-centre[0], -centre[1]), world)))
    if camera is not None and parallax:
        lens = _parallax_camera(camera, parallax)
        # Depth scales the pan (near layers slide more); zoom stays a uniform lens change.
        pan = depth_pan(pose.get("z", 0.0), camera)
        lens["x"], lens["y"] = lens["x"] * pan, lens["y"] * pan
        world = multiply(camera_matrix(lens, width, height), world)
    return world


def focal(camera):
    """Focal distance in screen heights for the camera's vertical field of view."""
    fov = float((camera or {}).get("fov", 50) or 50)
    return 1 / (2 * math.tan(math.radians(max(10.0, min(110.0, fov))) / 2))


def depth_scale(z, camera):
    """Scale of a top-level layer at depth ``z`` relative to how it was authored.

    Layers are laid out as seen from the rest camera (camera ``z`` = 0), so a
    far sky is authored full-size. Moving the camera's ``z`` into the scene
    then grows near layers faster than far ones. Mirrored by ``depthScale`` in
    browser/painter.mjs.
    """
    z = float(z or 0.0)
    cz = float((camera or {}).get("z", 0.0) or 0.0)
    if not cz:
        return 1.0
    f = focal(camera)
    return max(0.05, f + z) / max(0.05, f + z - cz)


def depth_pan(z, camera):
    """How much of a camera pan a layer at depth ``z`` follows (1 at the picture plane)."""
    z = float(z or 0.0)
    if not z:
        return 1.0
    f = focal(camera)
    return f / max(0.05, f + z)


def depth_fade(z, camera):
    """Fade layers that reach the camera so a fly-through passes cleanly."""
    distance = focal(camera) + float(z or 0.0) - float((camera or {}).get("z", 0.0) or 0.0)
    return max(0.0, min(1.0, (distance - 0.08) / 0.25))


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
