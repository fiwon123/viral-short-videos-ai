"""Animatable paint: keyed ``fill``, ``stroke_width`` and ``stroke_color``.

Both renderers draw shapes and text from pre-rasterised sprites, so paint
can't change per frame on its own. This load-time expander samples the paint
track, rasterises one sprite per distinct look (``paint_frames``), and keys
``frame`` to step through them at the composed rate. Motion keys are
resampled with ``keys.compose`` so authored easing is kept.

Polygon ``points`` morph too: every key's outline is resampled by arc length
to a shared point count and rotated to line up with the first, so any
polygon can morph into any other without twisting.

Fills interpolate in RGB: solid to solid, solid to gradient, and gradient to
gradient with the same number of stops (stop colours, positions and angle).
Gradients with different stop counts switch at the key. ``ease`` and
``ease_props`` (``fill``, ``stroke_width``, ``stroke_color``) apply as usual.
"""

import json
import math

from .design import DEFAULT_PALETTE, resolve_color
from .easing import ease

PAINT = ("fill", "stroke_width", "stroke_color", "points")
KINDS = ("rect", "ellipse", "polygon", "text")
MAX_FRAMES = 120
RATE_DEFAULT = 24


def _rgb(paint, palette):
    colour = resolve_color(paint, palette, "#000000")
    return [int(colour[i:i + 2], 16) for i in (1, 3, 5)] if isinstance(colour, str) and colour.startswith("#") \
        else [0, 0, 0]


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb)


def _fill_state(fill, palette):
    if isinstance(fill, dict):
        return {**{key: value for key, value in fill.items() if key != "stops"},
                "stops": [(float(stop["at"]), _rgb(stop["color"], palette)) for stop in fill["stops"]]}
    return {"solid": _rgb(fill, palette)}


def _as_gradient(solid, like):
    return {**{key: value for key, value in like.items() if key != "stops"},
            "stops": [(at, solid["solid"]) for at, _ in like["stops"]]}


def _mix_rgb(a, b, t):
    return [x + (y - x) * t for x, y in zip(a, b)]


def _mix_fill(a, b, t):
    if "solid" in a and "solid" in b:
        return {"solid": _mix_rgb(a["solid"], b["solid"], t)}
    if "solid" in a:
        a = _as_gradient(a, b)
    if "solid" in b:
        b = _as_gradient(b, a)
    if len(a["stops"]) != len(b["stops"]):
        return b if t >= 1 else a
    mixed = {**(b if t >= 0.5 else a)}
    mixed["stops"] = [(sa + (sb - sa) * t, _mix_rgb(ca, cb, t)) for (sa, ca), (sb, cb) in zip(a["stops"], b["stops"])]
    if "angle" in a or "angle" in b:
        mixed["angle"] = a.get("angle", 90) + (b.get("angle", 90) - a.get("angle", 90)) * t
    if "radius" in a or "radius" in b:
        mixed["radius"] = a.get("radius", 0.75) + (b.get("radius", 0.75) - a.get("radius", 0.75)) * t
    return mixed


def _fill_spec(state):
    if "solid" in state:
        return _hex(state["solid"])
    spec = {key: value for key, value in state.items() if key != "stops"}
    if "angle" in spec:
        spec["angle"] = round(spec["angle"], 1)
    if "radius" in spec:
        spec["radius"] = round(spec["radius"], 4)
    spec["stops"] = [{"at": round(max(0.0, min(1.0, at)), 4), "color": _hex(rgb)} for at, rgb in state["stops"]]
    return spec


def _resample(points, count):
    """Closed polygon with ``count`` points: every original vertex is kept, and the extra
    points are spread along the edges in proportion to their length."""
    points = [[float(x), float(y)] for x, y in points]
    edges = [math.dist(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]
    total = sum(edges) or 1.0
    extra = max(0, count - len(points))
    shares = [extra * edge / total for edge in edges]
    splits = [int(share) for share in shares]
    for index in sorted(range(len(edges)), key=lambda i: shares[i] - splits[i], reverse=True)[:extra - sum(splits)]:
        splits[index] += 1
    result = []
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        result.append(point)
        for step in range(1, splits[index] + 1):
            k = step / (splits[index] + 1)
            result.append([point[0] + (nxt[0] - point[0]) * k, point[1] + (nxt[1] - point[1]) * k])
    return result


def _align(points, reference):
    """Rotate the point order so it lines up with ``reference`` (least total travel)."""
    best = min(range(len(points)), key=lambda shift: sum(
        math.dist(points[(i + shift) % len(points)], reference[i]) for i in range(len(points))))
    return points[best:] + points[:best]


def _outlines(layer):
    keyed = [key["points"] for key in layer.get("keyframes", []) if "points" in key]
    if layer.get("kind") != "polygon" or not keyed:
        return {}
    shapes = [layer.get("points") or keyed[0]] + keyed
    count = max(24, max(len(shape) for shape in shapes))
    base = _resample(shapes[0], count)
    return {id(shape): _align(_resample(shape, count), base) for shape in shapes} | {"base": base}


def track(layer, palette):
    """Paint keyframe points ``(at, state, ease, ease_props)``, cumulative like pose keys."""
    stroke = layer.get("stroke") or {}
    outlines = _outlines(layer)
    state = {"fill": _fill_state(layer.get("fill", "foreground"), palette),
             "stroke_width": float(stroke.get("width", 0)),
             "stroke_color": _rgb(stroke.get("color", "background"), palette),
             "points": outlines.get("base")}
    points = [(0.0, state, "linear", {})]
    for key in layer.get("keyframes", []):
        state = dict(state)
        if "points" in key and outlines:
            state["points"] = outlines[id(key["points"])]
        if "fill" in key:
            state["fill"] = _fill_state(key["fill"], palette)
        if "stroke_width" in key:
            state["stroke_width"] = float(key["stroke_width"])
        if "stroke_color" in key:
            state["stroke_color"] = _rgb(key["stroke_color"], palette)
        if float(key["at"]) == 0:
            points.pop()
        points.append((float(key["at"]), state, key.get("ease", "linear"), key.get("ease_props") or {}))
    return points


def paint_at(points, progress):
    for index in range(1, len(points)):
        start, before, _, _ = points[index - 1]
        end, after, mode, ease_props = points[index]
        if progress > end:
            continue
        t = (progress - start) / (end - start) if end > start else 1.0

        def eased(name):
            chosen = ease_props.get(name, mode)
            return ease(t, "smooth" if chosen == "auto" else chosen)
        return {"fill": _mix_fill(before["fill"], after["fill"], eased("fill")),
                "stroke_width": before["stroke_width"] + (after["stroke_width"] - before["stroke_width"])
                * eased("stroke_width"),
                "stroke_color": _mix_rgb(before["stroke_color"], after["stroke_color"], eased("stroke_color")),
                "points": [_mix_rgb(a, b, eased("points")) for a, b in zip(before["points"], after["points"])]
                if before["points"] else None}
    return points[-1][1]


def look(state):
    """Layer fields for one sampled paint state."""
    result = {"fill": _fill_spec(state["fill"])}
    if state.get("points"):
        result["points"] = [[round(x, 4), round(y, 4)] for x, y in state["points"]]
    width = round(max(0.0, min(1.0, state["stroke_width"])), 4)
    if width > 0:
        result["stroke"] = {"width": width, "color": _hex(state["stroke_color"])}
    return result


def expand_layer(layer, duration, palette, fps=RATE_DEFAULT):
    from .keys import RATE, compose
    rate = min(RATE, float(fps))
    points = track(layer, palette)
    step = max(1.0 / rate, duration / MAX_FRAMES)
    frames, index = [], {}

    def modifier(seconds):
        snapped = min(duration, round(seconds / step) * step)
        sample = look(paint_at(points, snapped / duration if duration else 0.0))
        signature = json.dumps(sample, sort_keys=True)
        if signature not in index:
            index[signature] = len(frames)
            frames.append(sample)
        return {"frame": ("set", index[signature])}

    compose(layer, duration, [modifier], rate=rate)
    layer["paint_frames"] = frames
    return layer


def expand(episode, channel):
    palette = (channel or {}).get("palette") or DEFAULT_PALETTE
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            duration = float(shot.get("duration", 1))
            for layer in shot.get("layers", []):
                if layer.get("kind") in KINDS and any(prop in key for key in layer.get("keyframes", [])
                                                      for prop in PAINT):
                    expand_layer(layer, duration, palette, episode.get("fps", RATE_DEFAULT))
    return episode
