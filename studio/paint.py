"""Animatable paint: keyed ``fill``, ``stroke_width`` and ``stroke_color``.

Both renderers draw shapes and text from pre-rasterised sprites, so paint
can't change per frame on its own. This load-time expander samples the paint
track, rasterises one sprite per distinct look (``paint_frames``), and keys
``frame`` to step through them at the composed rate. Motion keys are
resampled with ``keys.compose`` so authored easing is kept.

Fills interpolate in RGB: solid to solid, solid to gradient, and gradient to
gradient with the same number of stops (stop colours, positions and angle).
Gradients with different stop counts switch at the key. ``ease`` and
``ease_props`` (``fill``, ``stroke_width``, ``stroke_color``) apply as usual.
"""

import json

from .design import DEFAULT_PALETTE, resolve_color
from .easing import ease

PAINT = ("fill", "stroke_width", "stroke_color")
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


def track(layer, palette):
    """Paint keyframe points ``(at, state, ease, ease_props)``, cumulative like pose keys."""
    stroke = layer.get("stroke") or {}
    state = {"fill": _fill_state(layer.get("fill", "foreground"), palette),
             "stroke_width": float(stroke.get("width", 0)),
             "stroke_color": _rgb(stroke.get("color", "background"), palette)}
    points = [(0.0, state, "linear", {})]
    for key in layer.get("keyframes", []):
        state = dict(state)
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
                "stroke_color": _mix_rgb(before["stroke_color"], after["stroke_color"], eased("stroke_color"))}
    return points[-1][1]


def look(state):
    """Layer fields for one sampled paint state."""
    result = {"fill": _fill_spec(state["fill"])}
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
