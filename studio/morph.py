"""SVG shape morphing: blend one SVG into another with a keyable ``morph``.

    {"kind": "svg", "file": "mouth-closed.svg", "morph_to": "mouth-open.svg",
     "keyframes": [{"at": 0.4, "morph": 1, "ease": "back"}, {"at": 0.8, "morph": 0}]}

The two files must share the same structure: the same elements and path
commands in the same order, differing only in numbers and hex colours (draw
one, then duplicate and edit its points). Every number and colour is
interpolated, so outlines, gradients and fills all blend. ``morph`` runs from
0 (``file``) to 1 (``morph_to``); values outside that range hold the end shapes. The browser
renderers draw SVG, so the blend is staged as ``MORPH_LEVELS`` frames and the
expander keys ``frame`` through them.
"""

import re

from .easing import ease

MORPH_LEVELS = 25  # Frames from file (0) to morph_to (1).
TOKEN = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _split(svg):
    tokens = TOKEN.findall(svg)
    return TOKEN.sub("\0", svg), tokens


def _colour(token):
    value = token[1:]
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    return [int(value[i:i + 2], 16) for i in (0, 2, 4)]


def compatible(first, second):
    """None when the SVGs can morph, else the first difference found."""
    skeleton_a, tokens_a = _split(first)
    skeleton_b, tokens_b = _split(second)
    if skeleton_a != skeleton_b or len(tokens_a) != len(tokens_b):
        lines_a, lines_b = skeleton_a.split("\n"), skeleton_b.split("\n")
        for number, (a, b) in enumerate(zip(lines_a, lines_b), 1):
            if a != b:
                return f"line {number} differs in structure: {a.strip()[:60]!r} vs {b.strip()[:60]!r}"
        return "the files have a different number of elements or path commands"
    for a, b in zip(tokens_a, tokens_b):
        if a.startswith("#") != b.startswith("#"):
            return f"a colour lines up with a number ({a} vs {b})"
    return None


def blend(first, second, t):
    """The SVG text ``t`` of the way from ``first`` to ``second``."""
    problem = compatible(first, second)
    if problem:
        raise ValueError(f"SVGs cannot morph: {problem}. Keep the same elements and commands; change only numbers.")
    skeleton, tokens_a = _split(first)
    _, tokens_b = _split(second)
    out = []
    for a, b in zip(tokens_a, tokens_b):
        if a.startswith("#"):
            rgb = [x + (y - x) * t for x, y in zip(_colour(a), _colour(b))]
            out.append("#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb))
        else:
            value = float(a) + (float(b) - float(a)) * t
            text = f"{value:.3f}".rstrip("0").rstrip(".")
            out.append("0" if text in ("-0", "") else text)
    parts = skeleton.split("\0")
    return "".join(part + (out[index] if index < len(out) else "") for index, part in enumerate(parts))


def _value(layer, progress):
    points = [(0.0, float(layer.get("morph", 0)), "linear")]
    for key in layer.get("keyframes", []):
        if "morph" in key:
            if float(key["at"]) == 0:
                points.pop()
            points.append((float(key["at"]), float(key["morph"]), key.get("ease", "linear")))
    for (start, before, _), (end, after, mode) in zip(points, points[1:]):
        if progress <= end:
            t = (progress - start) / (end - start) if end > start else 1.0
            return before + (after - before) * ease(t, "smooth" if mode == "auto" else mode)
    return points[-1][1]


def expand(episode):
    """Key ``frame`` from ``morph`` on SVG layers with ``morph_to``."""
    from .keys import RATE, compose
    fps = float(episode.get("fps", RATE))
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            duration = float(shot.get("duration", 1))
            for layer in shot.get("layers", []):
                if layer.get("kind") != "svg" or not layer.get("morph_to"):
                    continue
                if layer.get("boil"):
                    raise ValueError(f"{layer['id']}: morph and boil both use sprite frames; pick one")
                levels = MORPH_LEVELS

                def modifier(seconds, layer=layer):
                    value = _value(layer, seconds / duration if duration else 0.0)
                    return {"frame": ("set", max(0, min(levels - 1, round(value * (levels - 1)))))}
                compose(layer, duration, [modifier], rate=min(RATE, fps))
                layer["morph_levels"] = levels
    return episode
