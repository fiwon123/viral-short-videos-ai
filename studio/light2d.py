"""Scene light on flat 2D layers: body shading and a rim light from one direction.

Put a ``light`` on the episode or a shot and mark layers ``lit``::

    "light": {"angle": 135, "color": "#FFE7B8", "intensity": 0.45, "shadow": 0.4,
              "shadow_color": "#2B1F4F", "rim": 0.7}
    {"id": "pip", "kind": "use", "ref": "pip", "lit": true}

``angle`` is where the light comes from on screen (0 right, 90 top, 135 top
left). Every lit tile is shaded in its own space from its alpha shape: a wide
blur of the silhouette acts as a soft dome whose normals give the body a lit
side and a shadow side, and a narrow blur gives the edge normals for a rim
light on the edges that face the light. The direction is turned into each
layer's space from its world rotation (and flips), so a spinning prop keeps its
light on the same side of the screen. Children of a lit layer are lit, and a
number on ``lit`` scales the effect for that layer.

``browser/painter.mjs`` (``lightTile``) mirrors this maths. Results are cached per
tile and 5-degree angle bucket.
"""

import math

import numpy as np
from PIL import Image

DEFAULTS = {"angle": 135.0, "color": "#FFF1D6", "intensity": 0.45, "shadow": 0.4, "shadow_color": "#2B2350",
            "rim": 0.6, "softness": 0.04, "depth": 0.22, "elevation": 0.7}
BUCKET = 5.0


def _hex(value):
    value = value.lstrip("#")
    return [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def resolve(light, palette):
    """Defaults filled and palette names turned into hex."""
    if not light:
        return None
    spec = {**DEFAULTS, **light}
    for key in ("color", "shadow_color"):
        value = spec[key]
        if not str(value).startswith("#"):
            spec[key] = palette.get(value, DEFAULTS[key])
    return spec


def expand(episode, channel):
    """Merge episode light into shots and pass ``lit`` from parents to children."""
    palette = (channel or {}).get("palette", {})
    base = episode.get("light")
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            light = shot.get("light", base)
            if light is not None and light is not False and base and shot.get("light") is not None:
                light = {**base, **shot["light"]}
            if not light:
                shot.pop("light", None)
                continue
            shot["light"] = resolve(light, palette)
            by_id = {layer["id"]: layer for layer in shot.get("layers", [])}
            memo = {}

            def strength(layer_id, seen=()):
                if layer_id in memo or layer_id not in by_id or layer_id in seen:
                    return memo.get(layer_id, 0.0)
                layer = by_id[layer_id]
                own = layer.get("lit")
                if own is None:
                    value = strength(layer.get("parent"), seen + (layer_id,))
                else:
                    value = 1.0 if own is True else 0.0 if own is False else float(own)
                memo[layer_id] = value
                return value
            for layer in shot.get("layers", []):
                value = strength(layer["id"])
                if value and layer.get("kind") != "group":
                    layer["lit"] = value
                else:
                    layer.pop("lit", None)
    return episode


def local_direction(angle, world_rotation, flip_x=False, flip_y=False):
    """Light direction (towards the light) in a layer's own y-down space, bucketed."""
    angle = round(float(angle) / BUCKET) * BUCKET
    world = round(math.degrees(world_rotation) / BUCKET) * BUCKET
    sx, sy = math.cos(math.radians(angle)), -math.sin(math.radians(angle))
    w = math.radians(world)
    lx, ly = math.cos(w) * sx + math.sin(w) * sy, -math.sin(w) * sx + math.cos(w) * sy
    return (-lx if flip_x else lx), (-ly if flip_y else ly)


def _box(values, radius, axis):
    """Mean over [i-r, i+r] with zeros outside; mirrored by boxBlur in painter.mjs."""
    if radius < 1:
        return values
    pad = [(0, 0)] * values.ndim
    pad[axis] = (radius + 1, radius)
    total = np.cumsum(np.pad(values, pad), axis=axis)
    upper = np.take(total, range(2 * radius + 1, total.shape[axis]), axis=axis)
    lower = np.take(total, range(0, total.shape[axis] - 2 * radius - 1), axis=axis)
    return (upper - lower) / (2 * radius + 1)


def _blur(values, radius):
    for _ in range(2):
        values = _box(_box(values, radius, 1), radius, 0)
    return values


def shade_array(rgba, direction, spec, strength=1.0):
    """Shade a straight-alpha float RGBA array (H, W, 4) in 0-1."""
    height, width = rgba.shape[:2]
    alpha = rgba[..., 3]
    size = min(width, height)
    small = max(1, round(float(spec["softness"]) * size))
    large = max(2, round(float(spec["depth"]) * size))
    lx, ly = direction
    elevation = float(spec["elevation"])
    norm = math.sqrt(lx * lx + ly * ly + elevation * elevation)
    l3 = (lx / norm, ly / norm, elevation / norm)

    dome = _blur(alpha, large)
    gy, gx = np.gradient(dome)
    nx, ny, nz = -gx * large, -gy * large, np.ones_like(gx)
    length = np.sqrt(nx * nx + ny * ny + 1)
    lambert = (nx * l3[0] + ny * l3[1] + nz * l3[2]) / length
    flat = l3[2]
    side = np.clip((lambert - flat) / max(1e-6, 1 - flat), -1, 1)

    edge = _blur(alpha, small)
    ey, ex = np.gradient(edge)
    magnitude = np.sqrt(ex * ex + ey * ey)
    facing = np.where(magnitude > 1e-6, -(ex * lx + ey * ly) / np.maximum(magnitude, 1e-6), 0.0)
    rim = np.clip(magnitude * 2 * small, 0, 1) * np.clip(facing, 0, 1) * alpha

    k = float(strength)
    light = np.array(_hex(spec["color"]))
    dark = np.array(_hex(spec["shadow_color"]))
    rgb = rgba[..., :3]
    lit = np.clip(side, 0, 1)[..., None] * float(spec["intensity"]) * k
    shadow = np.clip(-side, 0, 1)[..., None] * float(spec["shadow"]) * k
    rgb = rgb * (1 - shadow + shadow * dark)
    rgb = 1 - (1 - rgb) * (1 - light * lit)
    rgb = 1 - (1 - rgb) * (1 - light * (rim[..., None] * float(spec["rim"]) * k))
    return np.concatenate([np.clip(rgb, 0, 1), alpha[..., None]], axis=2)


def shade_tile(tile, direction, spec, strength=1.0):
    data = np.asarray(tile.convert("RGBA"), dtype=np.float64) / 255
    out = shade_array(data, direction, spec, strength)
    return Image.fromarray(np.round(out * 255).astype(np.uint8), "RGBA")
