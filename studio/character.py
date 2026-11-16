"""Generate a rig-ready, shaded cartoon character from one JSON spec.

Hand-written single-SVG characters can't act: the whole body is one sprite.
This builds a character as separate parts (body, optional head, eyes with
pupils, brows, a mouth set, arms, legs, ears/antenna, contact shadow), each
an SVG with cel shading, rim light, gloss and optional paper texture, plus a
channel rig whose layers carry ``role`` tags. Roles let ``alive`` (see
``studio/life.py``) add blinking, breathing, glances, sway and talking.

    python -m studio.character workspace/<slug>/channel --spec art/characters/pip.json

Spec (all optional except ``id``; sizes are fractions of character height):

    {"id": "pip", "height": 0.3,
     "palette": {"body": "#F9CD54", "line": "#191B32", "accent": "#FF9855"},
     "body": {"shape": "bean", "width": 0.62, "height": 0.7},
     "head": null,
     "eyes": {"style": "round", "size": 0.12, "spacing": 0.26, "y": 0.34},
     "mouth": {"width": 0.17, "y": 0.6},
     "arms": {"length": 0.28, "width": 0.07}, "legs": {"length": 0.13, "width": 0.09},
     "ears": "none", "antenna": false, "texture": 0.0, "boil": 0.4}

Outputs ``art/characters/<id>/*.svg``, ``preview.svg`` (assembled) and the
rig ``<id>`` in the channel rig library (created and linked if missing).
"""

import argparse
import colorsys
import json
import math
from pathlib import Path
import re

UNIT = 1000.0  # Character height in design units; feet sit at y = 0.
SHAPES = {"circle": 2.0, "egg": 2.3, "bean": 2.5, "blob": 2.8, "pear": 2.4, "box": 4.5, "tall": 3.0}

DEFAULT = {
    "height": 0.3, "canvas": [1080, 1920], "line_width": 14, "texture": 0.0,
    "palette": {"body": "#F9CD54", "line": "#191B32", "eye": "#FFFFFF", "pupil": "#191B32",
                "mouth": "#6E2335", "tongue": "#FF7A8A", "cheek": "#FF8A80", "accent": "#FF9855"},
    "body": {"shape": "bean", "width": 0.62, "height": 0.72},
    "head": None,
    "eyes": {"style": "round", "size": 0.12, "spacing": 0.26, "y": 0.34, "pupil": 0.55},
    "brows": True, "cheeks": True, "belly": True,
    "mouth": {"width": 0.17, "y": 0.6},
    "arms": {"length": 0.28, "width": 0.07},
    "legs": {"length": 0.13, "width": 0.09},
    "ears": "none", "antenna": False,
    "shading": {"shade": 0.24, "rim": 0.45, "gloss": 0.5},
}


# ---------------------------------------------------------------- colour

def _rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{round(max(0, min(1, c)) * 255):02X}" for c in rgb)


def shade(color, amount):
    """Darken toward a cooler, more saturated shadow like painted cel art."""
    h, l, s = colorsys.rgb_to_hls(*_rgb(color))
    h = (h + (0.03 if 0.1 < h < 0.6 else -0.03) * amount * 3) % 1
    return _hex(colorsys.hls_to_rgb(h, max(0, l * (1 - amount)), min(1, s * (1 + amount * 0.6))))


def light(color, amount):
    h, l, s = colorsys.rgb_to_hls(*_rgb(color))
    return _hex(colorsys.hls_to_rgb(h, min(1, l + (1 - l) * amount), s * (1 - amount * 0.3)))


# ---------------------------------------------------------------- geometry

def superellipse(cx, cy, w, h, n, warp=None, count=56):
    points = []
    for index in range(count):
        theta = 2 * math.pi * index / count
        c, s = math.cos(theta), math.sin(theta)
        x = w / 2 * math.copysign(abs(c) ** (2 / n), c)
        y = h / 2 * math.copysign(abs(s) ** (2 / n), s)
        if warp:
            x *= warp((y + h / 2) / h)
        points.append((cx + x, cy + y))
    return points


def smooth_path(points, closed=True):
    """Catmull-Rom through points as cubic Béziers."""
    count = len(points)
    d = [f"M{points[0][0]:.1f} {points[0][1]:.1f}"]
    last = count if closed else count - 1
    for i in range(last):
        p0 = points[(i - 1) % count] if closed or i > 0 else points[i]
        p1, p2 = points[i], points[(i + 1) % count]
        p3 = points[(i + 2) % count] if closed or i + 2 < count else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    return " ".join(d) + (" Z" if closed else "")


def _warp(shape):
    if shape == "pear":
        return lambda t: 0.66 + 0.42 * t
    if shape == "bean":
        return lambda t: 0.88 + 0.16 * t
    if shape == "tall":
        return lambda t: 0.9 + 0.12 * t
    return None


def half_width(shape_spec, t):
    """Half width of a body shape at fraction t from top (0) to bottom (1), in design units."""
    shape = shape_spec.get("shape", "bean")
    n = SHAPES.get(shape, 2.5)
    y = abs(2 * t - 1)
    base = (1 - y ** n) ** (1 / n) if y < 1 else 0.0
    warp = _warp(shape)
    return shape_spec["width"] * UNIT / 2 * base * (warp(t) if warp else 1.0)


class Part:
    """One SVG part. Coordinates are design units inside its own box."""

    def __init__(self, name, width, height, pivot, role, parent=None, offset=(0, 0)):
        self.name, self.width, self.height = name, width, height
        self.pivot, self.role, self.parent, self.offset = pivot, role, parent, offset
        self.defs, self.body = [], []
        self.extra = {}

    def svg(self, standalone=True):
        inner = "".join(self.defs and ["<defs>", *self.defs, "</defs>"]) + "".join(self.body)
        if not standalone:
            return inner
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width:.1f} {self.height:.1f}" '
                f'width="{self.width:.0f}" height="{self.height:.0f}">{inner}</svg>\n')


def shaded_shape(part, d, box, color, spec, uid):
    """Fill, cel shadow, rim light, gloss, texture and outline for one closed path."""
    x0, y0, w, h = box
    sh = spec["shading"]
    line = spec["palette"]["line"]
    lw = spec["line_width"]
    clip = f"{uid}-clip"
    part.defs.append(f'<clipPath id="{clip}"><path d="{d}"/></clipPath>')
    dx, dy = -0.10 * w, -0.08 * h
    rx, ry = 0.035 * w, 0.03 * h
    layers = [f'<rect x="{x0 - w}" y="{y0 - h}" width="{w * 3}" height="{h * 3}" fill="{shade(color, sh["shade"])}"/>',
              f'<path d="{d}" transform="translate({dx:.1f} {dy:.1f})" fill="{color}"/>']
    if sh.get("rim", 0) > 0:
        layers.append(f'<path d="{d} {_translate_path(d, rx, ry)}" fill-rule="evenodd" '
                      f'fill="{light(color, 0.55)}" opacity="{sh["rim"]}"/>')
    if sh.get("gloss", 0) > 0:
        layers.append(f'<ellipse cx="{x0 + w * 0.3:.1f}" cy="{y0 + h * 0.2:.1f}" rx="{w * 0.09:.1f}" '
                      f'ry="{h * 0.05:.1f}" transform="rotate(-30 {x0 + w * 0.3:.1f} {y0 + h * 0.2:.1f})" '
                      f'fill="#FFFFFF" opacity="{0.55 * sh["gloss"]:.2f}"/>')
    if spec.get("texture", 0) > 0:
        tex = f"{uid}-tex"
        part.defs.append(
            f'<filter id="{tex}" x="0" y="0" width="100%" height="100%">'
            f'<feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="3" seed="7"/>'
            f'<feColorMatrix values="0 0 0 0 0.1  0 0 0 0 0.08  0 0 0 0 0.12  0 0 0 {spec["texture"] * 0.9:.2f} -{spec["texture"] * 0.25:.2f}"/></filter>')
        layers.append(f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" filter="url(#{tex})"/>')
    part.body.append(f'<path d="{d}" fill="{color}"/><g clip-path="url(#{clip})">{"".join(layers)}')
    return lambda extra="": part.body.append(
        f'{extra}</g><path d="{d}" fill="none" stroke="{line}" stroke-width="{lw}" stroke-linejoin="round"/>')


def _translate_path(d, dx, dy):
    """Shift an absolute path (M, L, Q, C, Z commands) by dx, dy."""
    out, axis = [], 0
    for token in re.findall(r"[A-Za-z]|-?\d+(?:\.\d+)?", d):
        if token.isalpha():
            out.append(token)
            axis = 0
            continue
        out.append(f"{float(token) + (dx if axis % 2 == 0 else dy):.1f}")
        axis += 1
    return " ".join(out)


# ---------------------------------------------------------------- parts

# Starting points; the spec's own values always win. "blob" is the classic bean.
ARCHETYPES = {
    "blob": {},
    "human": {"body": {"shape": "tall", "width": 0.44, "height": 0.5},
              "head": {"shape": "circle", "size": 0.5, "overlap": 0.06},
              "palette": {"body": "#4C7BD9", "skin": "#F2C7A5", "limb": "#4C7BD9", "hair": "#3B2A20",
                          "accent": "#2E3A59"},
              "arms": {"length": 0.36, "width": 0.08}, "legs": {"length": 0.26, "width": 0.1},
              "eyes": {"size": 0.12, "spacing": 0.24, "y": 0.5}, "mouth": {"width": 0.15, "y": 0.74},
              "hair": "bob", "nose": "button", "belly": False},
    "cat": {"ears": "pointy", "nose": "cat", "tail": "cat", "palette": {"body": "#F4A259"}},
    "dog": {"ears": "floppy", "nose": "snout", "tail": "wag", "palette": {"body": "#C98B5B"},
            "mouth": {"width": 0.15, "y": 0.66}},
    "bird": {"nose": "beak", "tail": "feather", "arms": {"length": 0.2, "width": 0.11},
             "legs": {"length": 0.12, "width": 0.045}, "palette": {"body": "#6CC3F0", "accent": "#F6A623"}},
    "robot": {"body": {"shape": "box", "width": 0.6, "height": 0.62}, "antenna": True,
              "eyes": {"style": "oval"}, "cheeks": False, "belly": False, "outfit": "panel",
              "palette": {"body": "#9FB4C7", "limb": "#7E93A6", "accent": "#FF6B6B"}},
}


def _deep(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep(target[key], value)
        else:
            target[key] = json.loads(json.dumps(value))
    return target


def _merge(spec):
    merged = json.loads(json.dumps(DEFAULT))
    archetype = spec.get("archetype", "blob")
    if archetype not in ARCHETYPES:
        raise ValueError(f"Unknown archetype {archetype}. Available: {', '.join(sorted(ARCHETYPES))}")
    _deep(merged, ARCHETYPES[archetype])
    _deep(merged, spec)
    palette = merged["palette"]
    palette.setdefault("limb", palette.get("body"))
    palette.setdefault("belly", light(palette["body"], 0.45))
    palette.setdefault("hair", "#3B2A20")
    palette.setdefault("outfit", shade(palette["body"], 0.35))
    return merged


def outfit_paint(spec, pad, w, h):
    """Clothing painted inside the body outline (clipped by the caller)."""
    style, colour, line = spec.get("outfit"), spec["palette"]["outfit"], spec["palette"]["line"]
    lw = spec["line_width"]
    if style == "shirt":
        return (f'<rect x="{pad - w:.1f}" y="{pad + h * 0.62:.1f}" width="{w * 3:.1f}" height="{h:.1f}" fill="{colour}"/>'
                f'<path d="M{pad - w:.1f} {pad + h * 0.62:.1f} H{pad + w * 2:.1f}" stroke="{line}" stroke-width="{lw * 0.6:.1f}"/>')
    if style == "overalls":
        strap = w * 0.1
        return (f'<rect x="{pad + w * 0.22:.1f}" y="{pad + h * 0.52:.1f}" width="{w * 0.56:.1f}" height="{h:.1f}" '
                f'rx="{w * 0.06:.1f}" fill="{colour}" stroke="{line}" stroke-width="{lw * 0.6:.1f}"/>'
                + "".join(f'<rect x="{pad + w * x:.1f}" y="{pad:.1f}" width="{strap:.1f}" height="{h * 0.55:.1f}" '
                          f'fill="{colour}" stroke="{line}" stroke-width="{lw * 0.5:.1f}"/>' for x in (0.27, 0.63)))
    if style == "scarf":
        return (f'<rect x="{pad - w:.1f}" y="{pad + h * 0.04:.1f}" width="{w * 3:.1f}" height="{h * 0.13:.1f}" '
                f'fill="{colour}" stroke="{line}" stroke-width="{lw * 0.6:.1f}"/>'
                f'<rect x="{pad + w * 0.58:.1f}" y="{pad + h * 0.12:.1f}" width="{w * 0.12:.1f}" height="{h * 0.3:.1f}" '
                f'rx="{w * 0.03:.1f}" fill="{colour}" stroke="{line}" stroke-width="{lw * 0.6:.1f}"/>')
    if style == "panel":
        accent = spec["palette"]["accent"]
        return (f'<rect x="{pad + w * 0.28:.1f}" y="{pad + h * 0.5:.1f}" width="{w * 0.44:.1f}" height="{h * 0.3:.1f}" '
                f'rx="{w * 0.05:.1f}" fill="{shade(spec["palette"]["body"], 0.2)}" stroke="{line}" stroke-width="{lw * 0.6:.1f}"/>'
                + "".join(f'<circle cx="{pad + w * x:.1f}" cy="{pad + h * 0.65:.1f}" r="{w * 0.04:.1f}" fill="{c}" '
                          f'stroke="{line}" stroke-width="{lw * 0.4:.1f}"/>'
                          for x, c in ((0.38, accent), (0.5, "#FFE066"), (0.62, "#6EE7B7"))))
    return ""


def body_part(spec, name, shape_spec, top_y, role, colour=None):
    pad = spec["line_width"] * 2
    w = shape_spec["width"] * UNIT
    h = shape_spec["height"] * UNIT
    part = Part(name, w + pad * 2, h + pad * 2, None, role)
    shape = shape_spec.get("shape", "bean")
    points = superellipse(pad + w / 2, pad + h / 2, w, h, SHAPES.get(shape, 2.5), _warp(shape))
    d = smooth_path(points)
    finish = shaded_shape(part, d, (pad, pad, w, h), colour or spec["palette"]["body"], spec, name)
    extra = ""
    if spec.get("belly") and role == "body":
        extra += (f'<ellipse cx="{pad + w / 2:.1f}" cy="{pad + h * 0.78:.1f}" rx="{w * 0.3:.1f}" ry="{h * 0.2:.1f}" '
                  f'fill="{spec["palette"]["belly"]}" opacity="0.85"/>')
    if role == "body":
        extra += outfit_paint(spec, pad, w, h)
    finish(extra)
    part.extra = {"pad": pad, "w": w, "h": h}
    return part


def face_details(spec, face):
    """Cheeks are painted on the face part; eyes, brows and mouths are layers."""
    if not spec.get("cheeks"):
        return
    pad, w, h = face.extra["pad"], face.extra["w"], face.extra["h"]
    eyes = spec["eyes"]
    for side in (-1, 1):
        cx = pad + w / 2 + side * (eyes["spacing"] * UNIT * 0.5 + eyes["size"] * UNIT * 0.35)
        cy = pad + h * (eyes["y"] + 0.17)
        face.body.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{eyes["size"] * UNIT * 0.42:.1f}" '
                         f'ry="{eyes["size"] * UNIT * 0.22:.1f}" fill="{spec["palette"]["cheek"]}" opacity="0.45"/>')


def eye_parts(spec, face_name, face):
    eyes, line, lw = spec["eyes"], spec["palette"]["line"], spec["line_width"]
    size = eyes["size"] * UNIT
    ew, eh = (size, size * 1.25) if eyes["style"] != "sleepy" else (size, size * 0.8)
    if eyes["style"] == "oval":
        ew, eh = size * 0.85, size * 1.4
    pad = lw
    parts = []
    face_pivot_y = face.extra["pivot_y"]
    for side, label in ((-1, "l"), (1, "r")):
        eye = Part(f"eye-{label}", ew + pad * 2, eh + pad * 2, [0.5, 0.5], "eye", face_name)
        eye.body.append(f'<ellipse cx="{pad + ew / 2:.1f}" cy="{pad + eh / 2:.1f}" rx="{ew / 2:.1f}" ry="{eh / 2:.1f}" '
                        f'fill="{spec["palette"]["eye"]}" stroke="{line}" stroke-width="{lw * 0.8:.1f}"/>')
        if eyes["style"] == "sleepy":
            eye.body.append(f'<path d="M{pad:.1f} {pad + eh * 0.45:.1f} Q{pad + ew / 2:.1f} {pad - eh * 0.1:.1f} '
                            f'{pad + ew:.1f} {pad + eh * 0.45:.1f} L{pad + ew:.1f} {pad:.1f} L{pad:.1f} {pad:.1f} Z" '
                            f'fill="{spec["palette"]["body"]}" stroke="{line}" stroke-width="{lw * 0.7:.1f}"/>')
        ox = side * eyes["spacing"] * UNIT / 2
        oy = face.extra["pad"] + face.extra["h"] * eyes["y"] - face_pivot_y
        eye.offset = (ox, oy)
        parts.append(eye)
        p = ew * eyes["pupil"]
        pupil = Part(f"pupil-{label}", p + 4, p + 4, [0.5, 0.5], "pupil", eye.name, (0, eh * 0.08))
        c = (p + 4) / 2
        pupil.body.append(f'<circle cx="{c:.1f}" cy="{c:.1f}" r="{p / 2:.1f}" fill="{spec["palette"]["pupil"]}"/>'
                          f'<circle cx="{c + p * 0.18:.1f}" cy="{c - p * 0.2:.1f}" r="{p * 0.17:.1f}" fill="#FFFFFF"/>'
                          f'<circle cx="{c - p * 0.16:.1f}" cy="{c + p * 0.18:.1f}" r="{p * 0.07:.1f}" fill="#FFFFFF" opacity="0.8"/>')
        parts.append(pupil)
        if spec.get("brows"):
            bw = ew * 1.1
            brow = Part(f"brow-{label}", bw + lw * 2, lw * 4, [0.5, 0.5], "brow", face_name,
                        (ox, oy - eh * 0.72))
            lift = -side * lw * 0.6
            brow.body.append(f'<path d="M{lw:.1f} {lw * 2 + lift:.1f} Q{lw + bw / 2:.1f} {lw * 0.6:.1f} '
                             f'{lw + bw:.1f} {lw * 2 - lift:.1f}" fill="none" stroke="{line}" '
                             f'stroke-width="{lw * 1.1:.1f}" stroke-linecap="round"/>')
            parts.append(brow)
    return parts


# Expression mouths, then the lip-sync visemes (studio/lipsync.py: open stands in for "ai").
MOUTHS = ("rest", "open", "wide", "o", "smile", "frown", "flat", "mbp", "e", "u", "fv", "l", "etc")


def mouth_parts(spec, face_name, face):
    mouth, pal, lw = spec["mouth"], spec["palette"], spec["line_width"]
    mw = mouth["width"] * UNIT
    mh = mw * 0.75
    pad = lw
    w, h = mw + pad * 2, mh + pad * 2
    ox = 0
    oy = face.extra["pad"] + face.extra["h"] * mouth["y"] - face.extra["pivot_y"]
    l, r, top, mid, bot = pad, pad + mw, pad + mh * 0.25, pad + mh * 0.45, pad + mh
    stroke = f'stroke="{pal["line"]}" stroke-width="{lw * 0.9:.1f}" stroke-linecap="round" stroke-linejoin="round"'
    open_mouth = lambda depth, width=1.0: (
        f'<path d="M{l + mw * (1 - width) / 2:.1f} {top:.1f} Q{pad + mw / 2:.1f} {top + mh * depth * 1.4:.1f} '
        f'{r - mw * (1 - width) / 2:.1f} {top:.1f} Z" fill="{pal["mouth"]}" {stroke}/>'
        f'<ellipse cx="{pad + mw / 2:.1f}" cy="{top + mh * depth * 0.55:.1f}" rx="{mw * 0.18 * width:.1f}" '
        f'ry="{mh * depth * 0.18:.1f}" fill="{pal["tongue"]}"/>')
    shapes = {
        "rest": f'<path d="M{l + mw * 0.2:.1f} {top:.1f} Q{pad + mw / 2:.1f} {mid:.1f} {r - mw * 0.2:.1f} {top:.1f}" fill="none" {stroke}/>',
        "open": open_mouth(0.45, 0.8),
        "wide": open_mouth(0.7, 1.0),
        "o": f'<ellipse cx="{pad + mw / 2:.1f}" cy="{mid:.1f}" rx="{mw * 0.18:.1f}" ry="{mh * 0.26:.1f}" fill="{pal["mouth"]}" {stroke}/>',
        "smile": open_mouth(0.55, 1.0).replace(f' Z" fill="{pal["mouth"]}"', f' Z" fill="{pal["mouth"]}"'),
        "frown": f'<path d="M{l + mw * 0.2:.1f} {mid + mh * 0.1:.1f} Q{pad + mw / 2:.1f} {top - mh * 0.1:.1f} {r - mw * 0.2:.1f} {mid + mh * 0.1:.1f}" fill="none" {stroke}/>',
        "flat": f'<path d="M{l + mw * 0.25:.1f} {mid:.1f} L{r - mw * 0.25:.1f} {mid:.1f}" fill="none" {stroke}/>',
    }
    teeth = pal.get("teeth", "#FFFFFF")

    def toothy(depth, width, tongue_up=False):
        x0, x1 = l + mw * (1 - width) / 2, r - mw * (1 - width) / 2
        bottom = top + mh * depth
        clip = f'M{x0:.1f} {top:.1f} Q{pad + mw / 2:.1f} {top + mh * depth * 1.4:.1f} {x1:.1f} {top:.1f} Z'
        tongue = (f'<ellipse cx="{pad + mw / 2:.1f}" cy="{top + mh * depth * 0.28:.1f}" rx="{mw * 0.12 * width:.1f}" '
                  f'ry="{mh * depth * 0.2:.1f}" fill="{pal["tongue"]}"/>' if tongue_up else
                  f'<rect x="{x0 + mw * 0.08:.1f}" y="{top:.1f}" width="{x1 - x0 - mw * 0.16:.1f}" '
                  f'height="{max(1.0, (bottom - top) * 0.32):.1f}" rx="{lw * 0.3:.1f}" fill="{teeth}"/>')
        return (f'<path d="{clip}" fill="{pal["mouth"]}"/>{tongue}'
                f'<path d="{clip}" fill="none" {stroke}/>')
    shapes.update({
        "mbp": f'<path d="M{l + mw * 0.24:.1f} {mid:.1f} Q{pad + mw / 2:.1f} {mid + mh * 0.06:.1f} {r - mw * 0.24:.1f} {mid:.1f}" '
               f'fill="none" stroke="{pal["line"]}" stroke-width="{lw * 1.35:.1f}" stroke-linecap="round"/>',
        "e": toothy(0.42, 1.0),
        "u": f'<ellipse cx="{pad + mw / 2:.1f}" cy="{mid:.1f}" rx="{mw * 0.11:.1f}" ry="{mh * 0.15:.1f}" fill="{pal["mouth"]}" {stroke}/>',
        "fv": f'<rect x="{l + mw * 0.3:.1f}" y="{mid - mh * 0.12:.1f}" width="{mw * 0.4:.1f}" height="{mh * 0.12:.1f}" '
              f'rx="{lw * 0.3:.1f}" fill="{teeth}" {stroke}/>'
              f'<path d="M{l + mw * 0.22:.1f} {mid:.1f} Q{pad + mw / 2:.1f} {mid + mh * 0.12:.1f} {r - mw * 0.22:.1f} {mid:.1f}" fill="none" {stroke}/>',
        "l": toothy(0.5, 0.85, tongue_up=True),
        "etc": toothy(0.28, 0.85),
    })
    parts = []
    for name in MOUTHS:
        part = Part(f"mouth-{name}", w, h, [0.5, 0.3], "mouth", face_name, (ox, oy))
        part.body.append(shapes[name])
        part.extra = {"shape": name}
        parts.append(part)
    return parts


def limb(spec, name, role, parent, offset, length, width, foot=False):
    pal, lw = spec["palette"], spec["line_width"]
    end = width * (1.45 if not foot else 1.2)
    pad = lw * 1.5
    w = max(width, end * (2.2 if foot else 2)) + pad * 2
    h = length + end + pad * 2
    cx = w / 2
    part = Part(name, w, h, [0.5, (pad + width / 2) / h], role, parent, offset)
    part.tip = (0.0, length - width / 2)  # Hand or foot centre from the pivot, in design units.
    color = pal["limb"]
    part.body.append(f'<path d="M{cx:.1f} {pad + width / 2:.1f} L{cx:.1f} {pad + length:.1f}" stroke="{pal["line"]}" '
                     f'stroke-width="{width + lw * 2:.1f}" stroke-linecap="round"/>'
                     f'<path d="M{cx:.1f} {pad + width / 2:.1f} L{cx:.1f} {pad + length:.1f}" stroke="{color}" '
                     f'stroke-width="{width:.1f}" stroke-linecap="round"/>'
                     f'<path d="M{cx + width * 0.22:.1f} {pad + width * 0.8:.1f} L{cx + width * 0.22:.1f} {pad + length - width * 0.2:.1f}" '
                     f'stroke="{shade(color, 0.22)}" stroke-width="{width * 0.3:.1f}" stroke-linecap="round" opacity="0.8"/>')
    if foot:
        fx = cx + (end * 0.35 if offset[0] >= 0 else -end * 0.35)
        part.body.append(f'<ellipse cx="{fx:.1f}" cy="{pad + length + end * 0.35:.1f}" rx="{end:.1f}" ry="{end * 0.55:.1f}" '
                         f'fill="{pal.get("accent", color)}" stroke="{pal["line"]}" stroke-width="{lw:.1f}"/>')
    else:
        part.body.append(f'<circle cx="{cx:.1f}" cy="{pad + length:.1f}" r="{end * 0.62:.1f}" fill="{pal.get("skin", color)}" '
                         f'stroke="{pal["line"]}" stroke-width="{lw:.1f}"/>'
                         f'<circle cx="{cx - end * 0.2:.1f}" cy="{pad + length - end * 0.2:.1f}" r="{end * 0.16:.1f}" '
                         f'fill="#FFFFFF" opacity="0.35"/>')
    return part


def ear_parts(spec, face_name, face):
    kind = spec.get("ears", "none")
    parts = []
    if kind and kind != "none":
        pal, lw = spec["palette"], spec["line_width"]
        size = face.extra["w"] * (0.28 if kind != "bunny" else 0.22)
        height = size * {"round": 1.0, "pointy": 1.4, "bunny": 3.0, "floppy": 1.7}.get(kind, 1.0)
        pad = lw * 1.5
        for side, label in ((-1, "l"), (1, "r")):
            if kind == "floppy":
                # Hangs from the top of the head, pivot at the top so it swings.
                part = Part(f"ear-{label}", size + pad * 2, height + pad * 2, [0.5, 0.08], "ear", face_name)
                d = smooth_path(superellipse(pad + size / 2, pad + height / 2, size, height, 2.2,
                                             lambda t: 0.75 + 0.35 * t))
                finish = shaded_shape(part, d, (pad, pad, size, height), shade(pal["body"], 0.25), spec, part.name)
                finish()
                part.offset = (side * face.extra["w"] * 0.47,
                               face.extra["pad"] + face.extra["h"] * 0.1 - face.extra["pivot_y"])
                part.extra = {"tilt": side * 12}
                parts.append(part)
                continue
            part = Part(f"ear-{label}", size + pad * 2, height + pad * 2, [0.5, 0.92], "ear", face_name)
            cx, base = pad + size / 2, pad + height
            if kind == "round":
                d = smooth_path(superellipse(cx, pad + height / 2, size, height, 2.0))
            else:
                d = (f"M{pad:.1f} {base:.1f} Q{pad - size * 0.05:.1f} {pad + height * 0.3:.1f} {cx:.1f} {pad:.1f} "
                     f"Q{pad + size * 1.05:.1f} {pad + height * 0.3:.1f} {pad + size:.1f} {base:.1f} Z")
            finish = shaded_shape(part, d, (pad, pad, size, height), pal["body"], spec, part.name)
            finish(f'<ellipse cx="{cx:.1f}" cy="{pad + height * 0.6:.1f}" rx="{size * 0.22:.1f}" '
                   f'ry="{height * 0.3:.1f}" fill="{pal["cheek"]}" opacity="0.5"/>')
            angle = 0.62 if kind != "bunny" else 0.8
            part.offset = (side * face.extra["w"] * 0.5 * angle, face.extra["pad"] + face.extra["h"] * 0.12 - face.extra["pivot_y"])
            part.extra = {"tilt": side * 14}
            parts.append(part)
    if spec.get("antenna"):
        pal, lw = spec["palette"], spec["line_width"]
        stalk, ball = face.extra["h"] * 0.28, face.extra["w"] * 0.09
        pad = lw * 1.5
        part = Part("antenna", ball * 2 + pad * 2, stalk + ball * 2 + pad * 2, [0.5, 0.97], "antenna", face_name,
                    (0, face.extra["pad"] + face.extra["h"] * 0.02 - face.extra["pivot_y"]))
        cx = pad + ball
        part.body.append(f'<path d="M{cx:.1f} {pad + stalk + ball * 2:.1f} Q{cx + ball * 0.6:.1f} {pad + ball * 2 + stalk * 0.5:.1f} '
                         f'{cx:.1f} {pad + ball * 1.6:.1f}" fill="none" stroke="{pal["line"]}" stroke-width="{lw:.1f}" stroke-linecap="round"/>'
                         f'<circle cx="{cx:.1f}" cy="{pad + ball:.1f}" r="{ball:.1f}" fill="{pal["accent"]}" stroke="{pal["line"]}" stroke-width="{lw:.1f}"/>'
                         f'<circle cx="{cx - ball * 0.3:.1f}" cy="{pad + ball * 0.7:.1f}" r="{ball * 0.3:.1f}" fill="#FFFFFF" opacity="0.6"/>')
        parts.append(part)
    return parts


def hair_parts(spec, face_name, face):
    """(behind, in front) hair parts for ``hair``: tuft, spiky, bob, bun, curly."""
    style = spec.get("hair")
    if not style or style == "none":
        return [], []
    pal, lw = spec["palette"], spec["line_width"]
    w, h, pad0 = face.extra["w"], face.extra["h"], face.extra["pad"]
    top = pad0 - face.extra["pivot_y"]  # Head top relative to the face pivot.
    colour = pal["hair"]
    pad = lw * 2
    behind, front = [], []
    if style == "tuft":
        tw, th = w * 0.36, h * 0.26
        part = Part("hair", tw + pad * 2, th + pad * 2, [0.5, 0.92], "hair", face_name, (0, top + h * 0.05))
        base, cx = pad + th, pad + tw / 2
        strands = "".join(
            f'<path d="M{cx + dx * tw * 0.25:.1f} {base:.1f} Q{cx + dx * tw * 0.5:.1f} {pad + th * 0.4:.1f} '
            f'{cx + dx * tw * 0.42 + tw * 0.1:.1f} {pad + th * 0.05 * (1 + abs(dx)):.1f}" fill="none" stroke="{colour}" '
            f'stroke-width="{lw * 1.6:.1f}" stroke-linecap="round"/>' for dx in (-1, 0, 1))
        part.body.append(strands)
        front.append(part)
    elif style in ("spiky", "curly"):
        # A cap that follows the skull, with spikes or curls in its outline and a fringe along the forehead.
        cw, ch = w * 1.06, h * 0.62
        part = Part("hair", cw + pad * 2, ch + pad * 2, [0.5, 0.5], "hair", face_name, (0, top + ch * 0.36))
        cx, cy = pad + cw / 2, pad + ch * 0.62
        outline = []
        steps = 48
        for index in range(steps + 1):
            a = math.pi + math.pi * index / steps
            if style == "spiky":
                tri = 1 - abs(((a * 7 / math.pi) % 2) - 1)
                bump = 1 + 0.2 * tri ** 2
            else:
                bump = 1 + 0.07 * abs(math.sin(a * 9))
            outline.append((cx + cw / 2 * math.cos(a) * bump, cy + ch * 0.62 * math.sin(a) * bump))
        waves = 7
        for index in range(waves * 4, -1, -1):
            x = pad + cw * index / (waves * 4)
            phase = index / (waves * 4) * waves * math.tau
            depth = (0.5 + 0.5 * math.cos(phase)) if style == "curly" else abs(math.sin(phase / 2)) ** 0.5
            side = abs(2 * index / (waves * 4) - 1)
            # High fringe in the middle, longer at the temples so the hair frames the face.
            outline.append((x, cy - ch * 0.3 + ch * 0.42 * side ** 3 + ch * 0.08 * depth))
        d = ("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in outline) + " Z") if style == "spiky" \
            else smooth_path(outline)
        shaded_shape(part, d, (pad, pad, cw, ch), colour, spec, part.name)()
        front.append(part)
    elif style in ("bob", "bun"):
        cw, ch = w * 1.08, h * 0.62
        part = Part("hair", cw + pad * 2, ch + pad * 2, [0.5, 0.5], "hair", face_name, (0, top + ch * 0.42))
        cx = pad + cw / 2
        bangs = 5
        d = (f"M{pad:.1f} {pad + ch * 0.85:.1f} Q{pad - cw * 0.02:.1f} {pad:.1f} {cx:.1f} {pad:.1f} "
             f"Q{pad + cw * 1.02:.1f} {pad:.1f} {pad + cw:.1f} {pad + ch * 0.85:.1f} ")
        for index in range(bangs, 0, -1):
            x_mid = pad + cw * (index - 0.5) / bangs
            x_end = pad + cw * (index - 1) / bangs
            d += f"Q{x_mid:.1f} {pad + ch * (0.62 if index % 2 else 0.5):.1f} {x_end:.1f} {pad + ch * 0.55:.1f} "
        d += "Z"
        shaded_shape(part, d, (pad, pad, cw, ch), colour, spec, part.name)()
        front.append(part)
        if style == "bob":
            bw, bh = w * 1.16, h * 0.95
            back = Part("hair-back", bw + pad * 2, bh + pad * 2, [0.5, 0.5], "hair", face_name,
                        (0, top + bh * 0.5))
            d = smooth_path(superellipse(pad + bw / 2, pad + bh / 2, bw, bh, 2.6))
            shaded_shape(back, d, (pad, pad, bw, bh), shade(colour, 0.15), spec, back.name)()
            behind.append(back)
        if style == "bun":
            r = w * 0.2
            bun = Part("hair-bun", r * 2 + pad * 2, r * 2 + pad * 2, [0.5, 0.9], "hair", face_name,
                       (0, top + h * 0.06))
            d = smooth_path(superellipse(pad + r, pad + r, r * 2, r * 2, 2.0))
            shaded_shape(bun, d, (pad, pad, r * 2, r * 2), colour, spec, bun.name)()
            behind.append(bun)
    return behind, front


def nose_part(spec, face_name, face):
    style = spec.get("nose")
    if not style or style == "none":
        return []
    pal, lw = spec["palette"], spec["line_width"]
    w, h = face.extra["w"], face.extra["h"]
    eyes_y, mouth_y = spec["eyes"]["y"], spec["mouth"]["y"]
    y = face.extra["pad"] + h * (eyes_y + (mouth_y - eyes_y) * 0.55) - face.extra["pivot_y"]
    pad = lw * 1.5
    line = pal["line"]
    skin = pal.get("skin", pal["body"])
    if style == "dot":
        r = w * 0.03
        part = Part("nose", r * 2 + pad * 2, r * 2 + pad * 2, [0.5, 0.5], "nose", face_name, (0, y))
        part.body.append(f'<circle cx="{pad + r:.1f}" cy="{pad + r:.1f}" r="{r:.1f}" fill="{line}"/>')
    elif style == "button":
        nw, nh = w * 0.12, w * 0.09
        part = Part("nose", nw + pad * 2, nh + pad * 2, [0.5, 0.5], "nose", face_name, (0, y))
        part.body.append(f'<ellipse cx="{pad + nw / 2:.1f}" cy="{pad + nh / 2:.1f}" rx="{nw / 2:.1f}" ry="{nh / 2:.1f}" '
                         f'fill="{shade(skin, 0.18)}" stroke="{line}" stroke-width="{lw * 0.5:.1f}"/>')
    elif style == "snout":
        nw, nh = w * 0.36, h * 0.24
        part = Part("nose", nw + pad * 2, nh + pad * 2, [0.5, 0.35], "nose", face_name, (0, y))
        part.body.append(f'<ellipse cx="{pad + nw / 2:.1f}" cy="{pad + nh / 2:.1f}" rx="{nw / 2:.1f}" ry="{nh / 2:.1f}" '
                         f'fill="{light(pal["body"], 0.35)}" stroke="{line}" stroke-width="{lw * 0.6:.1f}"/>'
                         f'<ellipse cx="{pad + nw / 2:.1f}" cy="{pad + nh * 0.28:.1f}" rx="{nw * 0.16:.1f}" ry="{nh * 0.14:.1f}" '
                         f'fill="{line}"/>')
    elif style == "beak":
        nw, nh = w * 0.22, h * 0.17
        part = Part("nose", nw + pad * 2, nh + pad * 2, [0.5, 0.3], "nose", face_name, (0, y))
        part.body.append(f'<path d="M{pad:.1f} {pad:.1f} L{pad + nw:.1f} {pad:.1f} L{pad + nw / 2:.1f} {pad + nh:.1f} Z" '
                         f'fill="{pal["accent"]}" stroke="{line}" stroke-width="{lw * 0.7:.1f}" stroke-linejoin="round"/>'
                         f'<path d="M{pad + nw * 0.15:.1f} {pad + nh * 0.3:.1f} L{pad + nw * 0.85:.1f} {pad + nh * 0.3:.1f}" '
                         f'stroke="{line}" stroke-width="{lw * 0.4:.1f}"/>')
    elif style == "cat":
        nw, nh, span = w * 0.1, w * 0.07, w * 0.75
        part = Part("nose", span + pad * 2, nh * 3 + pad * 2, [0.5, 0.3], "nose", face_name, (0, y))
        cx = pad + span / 2
        whiskers = "".join(
            f'<path d="M{cx + side * nw * 0.9:.1f} {pad + nh * (1.2 + row * 0.5):.1f} L{cx + side * span / 2:.1f} '
            f'{pad + nh * (0.7 + row * 1.0):.1f}" stroke="{line}" stroke-width="{lw * 0.35:.1f}" stroke-linecap="round" '
            f'opacity="0.7"/>' for side in (-1, 1) for row in (0, 1))
        part.body.append(whiskers + f'<path d="M{cx - nw / 2:.1f} {pad:.1f} L{cx + nw / 2:.1f} {pad:.1f} '
                         f'L{cx:.1f} {pad + nh:.1f} Z" fill="{pal["cheek"]}" stroke="{line}" '
                         f'stroke-width="{lw * 0.5:.1f}" stroke-linejoin="round"/>')
    else:
        raise ValueError(f"Unknown nose {style}. Use dot, button, snout, beak or cat.")
    return [part]


def tail_part(spec, body):
    """A tail hanging from its pivot, rotated to stick out; it has a ``tip`` so ``bend`` and ik work."""
    style = spec.get("tail")
    if not style or style == "none":
        return []
    pal, lw = spec["palette"], spec["line_width"]
    bw, bh = body.extra["w"], body.extra["h"]
    sizes = {"cat": (0.09, 0.62), "wag": (0.14, 0.32), "fluffy": (0.34, 0.6), "feather": (0.3, 0.34),
             "dino": (0.26, 0.45)}
    if style not in sizes:
        raise ValueError(f"Unknown tail {style}. Use {', '.join(sizes)}.")
    tw, tl = sizes[style][0] * bw, sizes[style][1] * bh
    pad = lw * 2
    # Parented to the rig root (like legs) so it draws behind the body; children always draw over parents.
    part = Part("tail", tw + pad * 2, tl + pad * 2, [0.5, (pad + tw * 0.2) / (tl + pad * 2)], "tail", None,
                (body.offset[0] + bw * 0.32, body.offset[1] - bh * 0.22))
    cx = pad + tw / 2
    colour = pal.get("tail") or (pal["body"] if style != "feather" else pal["accent"])
    if style == "cat":
        part.body.append(f'<path d="M{cx:.1f} {pad + tw * 0.2:.1f} L{cx:.1f} {pad + tl - tw / 2:.1f}" stroke="{pal["line"]}" '
                         f'stroke-width="{tw + lw * 2:.1f}" stroke-linecap="round"/>'
                         f'<path d="M{cx:.1f} {pad + tw * 0.2:.1f} L{cx:.1f} {pad + tl - tw / 2:.1f}" stroke="{colour}" '
                         f'stroke-width="{tw:.1f}" stroke-linecap="round"/>')
    else:
        if style == "feather":
            d = (f"M{cx:.1f} {pad:.1f} L{pad + tw:.1f} {pad + tl:.1f} Q{cx:.1f} {pad + tl * 0.85:.1f} {pad:.1f} "
                 f"{pad + tl:.1f} Z")
        elif style == "dino":
            d = f"M{pad:.1f} {pad:.1f} L{pad + tw:.1f} {pad:.1f} L{cx:.1f} {pad + tl:.1f} Z"
        else:
            d = smooth_path(superellipse(cx, pad + tl / 2, tw, tl, 2.0 if style == "fluffy" else 2.4,
                                         (lambda t: 0.7 + 0.5 * t) if style == "fluffy" else None))
        shaded_shape(part, d, (pad, pad, tw, tl), colour, spec, part.name)()
    part.tip = (0.0, tl - tw * 0.2)
    part.extra = {"tilt": {"cat": 125, "wag": 140, "fluffy": 150, "feather": 120, "dino": 100}[style],
                  "bend": 45 if style == "cat" else 0}
    return [part]


def build_parts(spec):
    spec = _merge(spec)
    legs, arms = spec.get("legs"), spec.get("arms")
    leg_length = legs["length"] * UNIT if legs else 0
    hip = -leg_length * 0.85
    body = body_part(spec, "body", spec["body"], 0, "body")
    body.pivot = [0.5, (body.extra["pad"] + body.extra["h"] * 0.98) / body.height]
    body.offset = (0, hip)
    body.extra["pivot_y"] = body.pivot[1] * body.height
    parts = []
    shadow_w = spec["body"]["width"] * UNIT * 1.1
    shadow = Part("shadow", shadow_w, shadow_w * 0.22, [0.5, 0.5], "shadow", None, (0, 0))
    shadow.body.append(f'<ellipse cx="{shadow_w / 2:.1f}" cy="{shadow_w * 0.11:.1f}" rx="{shadow_w / 2:.1f}" '
                       f'ry="{shadow_w * 0.1:.1f}" fill="{spec["palette"]["line"]}" opacity="0.22"/>')
    parts.append(shadow)
    if legs:
        for side, label in ((-1, "l"), (1, "r")):
            parts.append(limb(spec, f"leg-{label}", "leg", None,
                              (side * spec["body"]["width"] * UNIT * 0.2, hip - legs["width"] * UNIT * 0.4),
                              leg_length * 0.95, legs["width"] * UNIT, foot=True))
    parts.append(body)
    face, face_name = body, "body"
    if spec.get("head"):
        head_spec = {"shape": "circle", "size": 0.45, "overlap": 0.12, **spec["head"]}
        size = head_spec["size"]
        face = body_part(spec, "head", {"shape": head_spec["shape"], "width": size * 1.05, "height": size}, 0, "head",
                         colour=spec["palette"].get("skin"))
        face.pivot = [0.5, (face.extra["pad"] + face.extra["h"] * 0.92) / face.height]
        face.extra["pivot_y"] = face.pivot[1] * face.height
        face.parent = "body"
        face.offset = (0, -(body.extra["h"] * (1 - head_spec["overlap"])))
        face_name = "head"
    arm_parts = []
    if arms:
        for side, label in ((-1, "l"), (1, "r")):
            arm = limb(spec, f"arm-{label}", "arm", "body",
                       (side * (half_width(spec["body"], 0.5) - arms["width"] * UNIT * 0.35),
                        -body.extra["h"] * 0.5),
                       arms["length"] * UNIT, arms["width"] * UNIT)
            arm.extra = {"rest_rotate": side * -18}
            arm_parts.append(arm)
    face_details(spec, face)
    ears = ear_parts(spec, face_name, face)
    hair_behind, hair_front = hair_parts(spec, face_name, face)
    floppy = [part for part in ears if part.name.startswith("ear") and part.pivot[1] < 0.5]
    behind = [part for part in ears if part.name != "antenna" and part not in floppy] + hair_behind
    # Children always draw over their parent, so hair behind the face hangs from the face's parent instead.
    for part in hair_behind:
        part.parent = None if face is body else "body"
        part.offset = (face.offset[0] + part.offset[0], face.offset[1] + part.offset[1])
    behind = [part for part in behind if part not in hair_behind]
    index = parts.index(body)
    parts[index:index] = tail_part(spec, body) + (hair_behind if face is body else [])
    if face is not body:
        behind = hair_behind + behind
    if face is body:
        index = parts.index(body)
        parts[index:index] = behind
    else:
        parts.extend(behind)
        parts.append(face)
    parts.extend(part for part in ears if part.name == "antenna")
    parts.extend(eye_parts(spec, face_name, face))
    parts.extend(nose_part(spec, face_name, face))
    parts.extend(mouth_parts(spec, face_name, face))
    parts.extend(hair_front)
    parts.extend(floppy)
    # Arms hang in front of the torso and face: a hand at the chin or a raised arm must cover
    # the eyes, ears and hair, never slide behind them.
    parts.extend(arm_parts)
    return spec, parts


# ---------------------------------------------------------------- output

# Starter acting poses. Arm rotation is degrees from hanging down; positive swings
# the left arm out and up, negative the right. Brow y is a canvas fraction.
# Angles follow the studio convention: positive rotate turns counter-clockwise on screen, so
# raising arm-r (screen right) outward is positive and arm-l (screen left) is negative.
POSES = {
    "idle": {},
    "wave": {"arm-r": {"rotate": 150}, "mouth": "smile"},
    "cheer": {"arm-l": {"rotate": -155}, "arm-r": {"rotate": 155}, "brow-l": {"y": -0.006}, "brow-r": {"y": -0.006},
              "mouth": "wide"},
    "point-left": {"arm-l": {"rotate": -95}},
    "point-right": {"arm-r": {"rotate": 95}},
    "shrug": {"arm-l": {"rotate": -62}, "arm-r": {"rotate": 62}, "brow-l": {"y": -0.005}, "brow-r": {"y": -0.005},
              "mouth": "flat"},
    "surprise": {"arm-l": {"rotate": -40}, "arm-r": {"rotate": 40}, "eye-l": {"scale": 1.18}, "eye-r": {"scale": 1.18},
                 "brow-l": {"y": -0.009}, "brow-r": {"y": -0.009}, "mouth": "o"},
    "sad": {"arm-l": {"rotate": -4}, "arm-r": {"rotate": 4}, "brow-l": {"rotate": 14}, "brow-r": {"rotate": -14},
            "mouth": "frown"},
    "angry": {"arm-l": {"rotate": -28}, "arm-r": {"rotate": 28}, "brow-l": {"rotate": -18, "y": 0.003},
              "brow-r": {"rotate": 18, "y": 0.003}, "mouth": "frown"},
    "think": {"arm-r": {"rotate": -118},  # Inward: hand to the chin.
              "pupil-l": {"y": -0.004}, "pupil-r": {"y": -0.004}, "mouth": "flat"},
}

# How far face features sit in front of the face, so a head turn slides them like a cartoon.
FEATURE_DEPTH = {"eye": 0.12, "brow": 0.12, "mouth": 0.12, "nose": 0.16}


def rig_layers(spec, parts, folder):
    canvas_w, canvas_h = spec["canvas"]
    s = spec["height"] * canvas_h / UNIT
    layers = []
    for part in parts:
        layer = {"id": part.name, "kind": "svg", "file": f"{folder}/{part.name}.svg", "asset_scope": "channel",
                 "x": round(part.offset[0] * s / canvas_w, 5), "y": round(part.offset[1] * s / canvas_h, 5),
                 "width": round(part.width * s / canvas_w, 5), "height": round(part.height * s / canvas_h, 5),
                 "pivot": [round(v, 4) for v in (part.pivot or [0.5, 0.5])], "role": part.role}
        if part.parent:
            layer["parent"] = part.parent
        if spec.get("boil") and part.role != "shadow":
            layer["boil"] = spec["boil"]
        if part.role in FEATURE_DEPTH:
            layer["turn_depth"] = FEATURE_DEPTH[part.role]
        if part.role == "mouth":
            layer["variant_group"] = "mouth"
            layer["mouth_shape"] = part.extra["shape"]
            if part.extra["shape"] != "rest":
                layer["visible"] = False
        if getattr(part, "tip", None):
            layer["tip"] = [round(part.tip[0] * s / canvas_w, 5), round(part.tip[1] * s / canvas_h, 5)]
        if part.extra.get("rest_rotate"):
            layer["rotate"] = part.extra["rest_rotate"]
        if part.extra.get("tilt"):
            layer["rotate"] = part.extra["tilt"]
        if part.extra.get("bend"):
            layer["bend"] = part.extra["bend"]
        layers.append(layer)
    return layers


def preview_svg(parts, spec):
    """Assemble the parts into one SVG for a quick look (rest pose)."""
    by_name = {part.name: part for part in parts}
    origin = {}

    def pivot_point(part):
        if part.name in origin:
            return origin[part.name]
        base = (0.0, 0.0) if not part.parent else pivot_point(by_name[part.parent])
        point = (base[0] + part.offset[0], base[1] + part.offset[1])
        origin[part.name] = point
        return point

    groups = []
    for part in parts:
        if part.role == "mouth" and part.extra.get("shape") != "rest":
            continue
        px, py = pivot_point(part)
        pv = part.pivot or [0.5, 0.5]
        left, top = px - pv[0] * part.width, py - pv[1] * part.height
        # Rest angles; SVG rotate is clockwise, the studio's rotate is counter-clockwise. Bend is not previewed.
        angle = part.extra.get("rest_rotate") or part.extra.get("tilt") or 0
        turn = f' rotate({-angle:.1f} {pv[0] * part.width:.1f} {pv[1] * part.height:.1f})' if angle else ""
        groups.append(f'<g transform="translate({left:.1f} {top:.1f}){turn}">{part.svg(standalone=False)}</g>')
    w = UNIT * 1.2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-w / 2:.0f} {-UNIT * 1.05:.0f} {w:.0f} {UNIT * 1.15:.0f}" '
            f'width="600" height="{600 * 1.15 / 1.2:.0f}"><rect x="{-w / 2:.0f}" y="{-UNIT * 1.05:.0f}" width="{w:.0f}" '
            f'height="{UNIT * 1.15:.0f}" fill="#EEF1F7"/>{"".join(groups)}</svg>\n')


def world_pivots(parts):
    """Each part's pivot in character design units (feet at 0, y down)."""
    by_name = {part.name: part for part in parts}
    origin = {}

    def point(part):
        if part.name not in origin:
            base = (0.0, 0.0) if not part.parent else point(by_name[part.parent])
            origin[part.name] = (base[0] + part.offset[0], base[1] + part.offset[1])
        return origin[part.name]
    return {part.name: point(part) for part in parts}


def fit_poses(spec, parts, layers):
    """Starter poses for one rig.

    Pose values replace the rest value (``studio/poses.py``), so position offsets in
    ``POSES`` are added to each part's rest ``x``/``y`` here, and ``think`` aims the
    hand at this character's chin instead of using one angle for every body shape.
    """
    rest = {layer["id"]: layer for layer in layers}
    fitted = {}
    for name, pose in POSES.items():
        out = {}
        for part, props in pose.items():
            if part == "mouth":
                out[part] = props
                continue
            if part not in rest:
                continue
            out[part] = {prop: (round(float(rest[part].get(prop, 0)) + value, 5) if prop in ("x", "y") else value)
                         for prop, value in props.items()}
        fitted[name] = out
    pivots = world_pivots(parts)
    by_name = {part.name: part for part in parts}
    if "arm-r" in pivots and "mouth-rest" in pivots:
        shoulder, mouth = pivots["arm-r"], pivots["mouth-rest"]
        width = spec["mouth"]["width"] * UNIT
        target = (mouth[0] + width * 0.45, mouth[1] + width * 0.6)
        dx, dy = target[0] - shoulder[0], target[1] - shoulder[1]
        reach = getattr(by_name["arm-r"], "tip", (0, 1))[1] or 1
        angle = math.degrees(math.atan2(dx, dy))
        if math.hypot(dx, dy) < reach * 0.6:
            angle *= 0.85  # A short reach would push the hand over the face; keep it lower.
        fitted["think"] = {**fitted.get("think", {}), "arm-r": {"rotate": round(angle, 1)}}
    return fitted


def generate(channel_dir, spec_path, *, rig_library=None):
    channel_dir = Path(channel_dir).resolve()
    spec_file = (channel_dir / spec_path) if not Path(spec_path).is_absolute() else Path(spec_path)
    raw = json.loads(spec_file.read_text(encoding="utf-8"))
    if not raw.get("id"):
        raise ValueError("Character spec needs an id")
    spec, parts = build_parts(raw)
    folder = f"art/characters/{raw['id']}"
    out = channel_dir / folder
    out.mkdir(parents=True, exist_ok=True)
    for part in parts:
        (out / f"{part.name}.svg").write_text(part.svg(), encoding="utf-8")
    (out / "preview.svg").write_text(preview_svg(parts, spec), encoding="utf-8")
    channel_path = channel_dir / "channel.json"
    channel = json.loads(channel_path.read_text(encoding="utf-8"))
    rig_name = rig_library or channel.get("rig_library") or "rigs.json"
    rig_path = channel_dir / rig_name
    library = json.loads(rig_path.read_text(encoding="utf-8")) if rig_path.is_file() else {"version": 1, "rigs": {}}
    library["rigs"][raw["id"]] = rig_layers(spec, parts, folder)
    library.setdefault("poses", {})[raw["id"]] = fit_poses(spec, parts, library["rigs"][raw["id"]])
    rig_path.write_text(json.dumps(library, indent=2) + "\n", encoding="utf-8")
    linked = False
    if channel.get("rig_library") != rig_name:
        channel["rig_library"] = rig_name
        channel_path.write_text(json.dumps(channel, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        linked = True
    return {"character": raw["id"], "parts": len(parts), "folder": folder, "rig_library": rig_name,
            "linked_rig_library": linked, "preview": f"{folder}/preview.svg",
            "poses": sorted(POSES),
            "use": {"id": raw["id"], "kind": "use", "ref": raw["id"], "x": 0.5, "y": 0.85,
                    "alive": {"talk": "<speaker>"}, "pose_keys": [{"t": 0.5, "pose": "wave"}]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("channel", type=Path, help="channel folder")
    parser.add_argument("--spec", required=True, help="character spec JSON, relative to the channel or absolute")
    parser.add_argument("--rig-library", help="rig library JSON relative to the channel")
    args = parser.parse_args()
    try:
        print(json.dumps(generate(args.channel, args.spec, rig_library=args.rig_library), indent=2))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"studio: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
