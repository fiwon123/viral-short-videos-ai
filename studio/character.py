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

def _merge(spec):
    merged = json.loads(json.dumps(DEFAULT))
    for key, value in spec.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    palette = merged["palette"]
    palette.setdefault("limb", palette.get("body"))
    palette.setdefault("belly", light(palette["body"], 0.45))
    return merged


def body_part(spec, name, shape_spec, top_y, role):
    pad = spec["line_width"] * 2
    w = shape_spec["width"] * UNIT
    h = shape_spec["height"] * UNIT
    part = Part(name, w + pad * 2, h + pad * 2, None, role)
    shape = shape_spec.get("shape", "bean")
    points = superellipse(pad + w / 2, pad + h / 2, w, h, SHAPES.get(shape, 2.5), _warp(shape))
    d = smooth_path(points)
    finish = shaded_shape(part, d, (pad, pad, w, h), spec["palette"]["body"], spec, name)
    extra = ""
    if spec.get("belly") and role == "body":
        extra += (f'<ellipse cx="{pad + w / 2:.1f}" cy="{pad + h * 0.78:.1f}" rx="{w * 0.3:.1f}" ry="{h * 0.2:.1f}" '
                  f'fill="{spec["palette"]["belly"]}" opacity="0.85"/>')
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


MOUTHS = ("rest", "open", "wide", "o", "smile", "frown", "flat")


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
        part.body.append(f'<circle cx="{cx:.1f}" cy="{pad + length:.1f}" r="{end * 0.62:.1f}" fill="{color}" '
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
        height = size * {"round": 1.0, "pointy": 1.4, "bunny": 3.0}.get(kind, 1.0)
        pad = lw * 1.5
        for side, label in ((-1, "l"), (1, "r")):
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
        face = body_part(spec, "head", {"shape": head_spec["shape"], "width": size * 1.05, "height": size}, 0, "head")
        face.pivot = [0.5, (face.extra["pad"] + face.extra["h"] * 0.92) / face.height]
        face.extra["pivot_y"] = face.pivot[1] * face.height
        face.parent = "body"
        face.offset = (0, -(body.extra["h"] * (1 - head_spec["overlap"])))
        face_name = "head"
    if arms:
        for side, label in ((-1, "l"), (1, "r")):
            arm = limb(spec, f"arm-{label}", "arm", "body",
                       (side * (half_width(spec["body"], 0.5) - arms["width"] * UNIT * 0.35),
                        -body.extra["h"] * 0.5),
                       arms["length"] * UNIT, arms["width"] * UNIT)
            arm.extra = {"rest_rotate": side * -18}
            parts.append(arm)
    face_details(spec, face)
    ears = ear_parts(spec, face_name, face)
    behind = [part for part in ears if part.name != "antenna"]
    if face is body:
        index = parts.index(body)
        parts[index:index] = behind
    else:
        parts.extend(behind)
        parts.append(face)
    parts.extend(part for part in ears if part.name == "antenna")
    parts.extend(eye_parts(spec, face_name, face))
    parts.extend(mouth_parts(spec, face_name, face))
    return spec, parts


# ---------------------------------------------------------------- output

# Starter acting poses. Arm rotation is degrees from hanging down; positive swings
# the left arm out and up, negative the right. Brow y is a canvas fraction.
POSES = {
    "idle": {},
    "wave": {"arm-r": {"rotate": -150}, "mouth": "smile"},
    "cheer": {"arm-l": {"rotate": 155}, "arm-r": {"rotate": -155}, "brow-l": {"y": -0.006}, "brow-r": {"y": -0.006},
              "mouth": "wide"},
    "point-left": {"arm-l": {"rotate": 95}},
    "point-right": {"arm-r": {"rotate": -95}},
    "shrug": {"arm-l": {"rotate": 62}, "arm-r": {"rotate": -62}, "brow-l": {"y": -0.005}, "brow-r": {"y": -0.005},
              "mouth": "flat"},
    "surprise": {"arm-l": {"rotate": 40}, "arm-r": {"rotate": -40}, "eye-l": {"scale": 1.18}, "eye-r": {"scale": 1.18},
                 "brow-l": {"y": -0.009}, "brow-r": {"y": -0.009}, "mouth": "o"},
    "sad": {"arm-l": {"rotate": 4}, "arm-r": {"rotate": -4}, "brow-l": {"rotate": -14}, "brow-r": {"rotate": 14},
            "mouth": "frown"},
    "angry": {"arm-l": {"rotate": 28}, "arm-r": {"rotate": -28}, "brow-l": {"rotate": 18, "y": 0.003},
              "brow-r": {"rotate": -18, "y": 0.003}, "mouth": "frown"},
    "think": {"arm-r": {"rotate": -140}, "pupil-l": {"y": -0.004}, "pupil-r": {"y": -0.004}, "mouth": "flat"},
}

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
        groups.append(f'<g transform="translate({left:.1f} {top:.1f})">{part.svg(standalone=False)}</g>')
    w = UNIT * 1.2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-w / 2:.0f} {-UNIT * 1.05:.0f} {w:.0f} {UNIT * 1.15:.0f}" '
            f'width="600" height="{600 * 1.15 / 1.2:.0f}"><rect x="{-w / 2:.0f}" y="{-UNIT * 1.05:.0f}" width="{w:.0f}" '
            f'height="{UNIT * 1.15:.0f}" fill="#EEF1F7"/>{"".join(groups)}</svg>\n')


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
    names = {part.name for part in parts}
    library.setdefault("poses", {})[raw["id"]] = {
        name: {part: props for part, props in pose.items() if part == "mouth" or part in names}
        for name, pose in POSES.items()}
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
