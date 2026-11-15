"""Style passes for existing SVG art: cel shade, rim light, texture and outline.

Flat vector art (stock icons, hand-written SVGs, traced logos) can look
cheap next to the generated characters. ``finish`` on an SVG layer wraps the
artwork in an SVG filter that adds the same finish the character generator
draws by hand:

- ``shade`` (0..1): a cel shadow band on the side away from the light.
- ``rim`` (0..1): a thin light band on the lit edge.
- ``texture`` (0..1): fractal paper grain inside the shape.
- ``outline`` (0..0.05): an ink line around the shape, as a fraction of the
  artwork size, with ``line`` as its colour.
- ``light``: direction the light comes from, ``[x, y]`` (default ``[-1, -1]``,
  top left).
- ``per``: ``silhouette`` shades the whole drawing as one shape; ``shapes``
  shades each top-level element on its own (good for separated parts).

Browser renderers draw SVG layers, so this runs while the asset is staged,
before line boil.
"""

import math
import re

VIEWBOX = re.compile(r'viewBox="([^"]+)"')
SIZE = re.compile(r'\s(width|height)="([\d.]+)')
OPEN = re.compile(r"<svg\b[^>]*>", re.S)

DEFAULTS = {"shade": 0.35, "rim": 0.4, "texture": 0.0, "outline": 0.0, "line": "#141018",
            "shade_color": "#1B1430", "rim_color": "#FFF6E0", "light": [-1, -1], "per": "silhouette"}


def _box(svg):
    match = VIEWBOX.search(svg)
    if match:
        parts = [float(value) for value in match.group(1).replace(",", " ").split()]
        if len(parts) == 4:
            return parts
    head = OPEN.search(svg)
    sizes = dict(SIZE.findall(head.group(0))) if head else {}
    return [0.0, 0.0, float(sizes.get("width", 100)), float(sizes.get("height", 100))]


def _filter(style, box, uid):
    x, y, w, h = box
    size = min(w, h)
    lx, ly = style["light"]
    norm = math.hypot(lx, ly) or 1.0
    lx, ly = lx / norm, ly / norm
    band, edge = 0.07 * size, 0.022 * size
    outline = float(style["outline"]) * size
    margin = outline + 0.02 * size
    parts = [f'<filter id="{uid}" filterUnits="userSpaceOnUse" x="{x - margin:.2f}" y="{y - margin:.2f}" '
             f'width="{w + 2 * margin:.2f}" height="{h + 2 * margin:.2f}" color-interpolation-filters="sRGB">']
    result = "SourceGraphic"
    if style["shade"] > 0:
        parts.append(
            f'<feOffset in="SourceAlpha" dx="{lx * band:.2f}" dy="{ly * band:.2f}" result="{uid}-lit"/>'
            f'<feComposite in="SourceAlpha" in2="{uid}-lit" operator="out" result="{uid}-band"/>'
            f'<feGaussianBlur in="{uid}-band" stdDeviation="{0.004 * size:.2f}" result="{uid}-soft"/>'
            f'<feComposite in="{uid}-soft" in2="SourceAlpha" operator="in" result="{uid}-sm"/>'
            f'<feFlood flood-color="{style["shade_color"]}" flood-opacity="{style["shade"]:.3f}"/>'
            f'<feComposite in2="{uid}-sm" operator="in" result="{uid}-shadow"/>'
            f'<feComposite in="{uid}-shadow" in2="{result}" operator="atop" result="{uid}-shaded"/>')
        result = f"{uid}-shaded"
    if style["rim"] > 0:
        parts.append(
            f'<feOffset in="SourceAlpha" dx="{-lx * edge:.2f}" dy="{-ly * edge:.2f}" result="{uid}-away"/>'
            f'<feComposite in="SourceAlpha" in2="{uid}-away" operator="out" result="{uid}-rm"/>'
            f'<feFlood flood-color="{style["rim_color"]}" flood-opacity="{style["rim"]:.3f}"/>'
            f'<feComposite in2="{uid}-rm" operator="in" result="{uid}-rim"/>'
            f'<feComposite in="{uid}-rim" in2="{result}" operator="atop" result="{uid}-rimmed"/>')
        result = f"{uid}-rimmed"
    if style["texture"] > 0:
        amount = float(style["texture"])
        parts.append(
            f'<feTurbulence type="fractalNoise" baseFrequency="{12 / size:.5f}" numOctaves="3" seed="7"/>'
            f'<feColorMatrix values="0 0 0 0 0.1  0 0 0 0 0.08  0 0 0 0 0.12  0 0 0 {amount * 0.9:.3f} '
            f'-{amount * 0.25:.3f}"/>'
            f'<feComposite in2="SourceAlpha" operator="in" result="{uid}-grain"/>'
            f'<feComposite in="{uid}-grain" in2="{result}" operator="atop" result="{uid}-grained"/>')
        result = f"{uid}-grained"
    if outline > 0:
        parts.append(
            f'<feMorphology in="SourceAlpha" operator="dilate" radius="{outline:.2f}" result="{uid}-fat"/>'
            f'<feFlood flood-color="{style["line"]}"/>'
            f'<feComposite in2="{uid}-fat" operator="in" result="{uid}-ink"/>'
            f'<feMerge><feMergeNode in="{uid}-ink"/><feMergeNode in="{result}"/></feMerge>')
    elif result != "SourceGraphic":
        parts.append(f'<feMerge><feMergeNode in="{result}"/></feMerge>')
    parts.append("</filter>")
    return "".join(parts)


def _top_level_spans(body):
    """Yield (start, end) of each top-level element in ``body`` (simple tag depth scan)."""
    depth, start = 0, None
    for match in re.finditer(r"<(/?)([a-zA-Z][\w:-]*)[^>]*?(/?)>", body):
        closing, name, selfclosing = match.group(1), match.group(2), match.group(3)
        if not closing and depth == 0:
            start = match.start()
            if name == "defs":
                start = None
        if closing:
            depth -= 1
            if depth == 0 and start is not None:
                yield start, match.end()
                start = None
        elif selfclosing:
            if depth == 0 and start is not None:
                yield start, match.end()
                start = None
        else:
            depth += 1


def apply(svg, style, uid="studio-style"):
    """Return ``svg`` with the style pass applied."""
    style = {**DEFAULTS, **(style or {})}
    head = OPEN.search(svg)
    tail = svg.rfind("</svg>")
    if not head or tail < 0:
        return svg
    box = _box(svg)
    defs = f"<defs>{_filter(style, box, uid)}</defs>"
    body = svg[head.end():tail]
    if style["per"] == "shapes":
        pieces, cursor = [], 0
        for start, end in _top_level_spans(body):
            pieces.append(body[cursor:start])
            pieces.append(f'<g filter="url(#{uid})">{body[start:end]}</g>')
            cursor = end
        pieces.append(body[cursor:])
        wrapped = "".join(pieces)
    else:
        wrapped = f'<g filter="url(#{uid})">{body}</g>'
    return svg[:head.end()] + defs + wrapped + svg[tail:]
