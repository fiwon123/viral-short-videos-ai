"""Data-driven 2D animation, compositing, captions, and channel graphics."""

from functools import lru_cache
import math

import numpy as np
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

from .camera import resolve_camera
from .core import asset, scoped_asset
from .easing import catmull_rom, ease
from .transform import depth_fade, apply as apply_matrix
from .transform import bbox as matrix_bbox
from .transform import camera_matrix, inverse, layer_matrix, multiply, translate

DEFAULT_PALETTE = {
    "background": "#131B30",
    "foreground": "#FFF3D8",
    "accent": "#FFBD54",
    "secondary": "#293F59",
}


@lru_cache(maxsize=128)
def get_font(path, size):
    if path:
        return ImageFont.truetype(path, size)
    for name in ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def resolve_color(value, palette, default=None):
    """Resolve a hex value or a named palette role to a PIL colour."""
    if value is None:
        return default
    if isinstance(value, str) and value.startswith("#"):
        return value
    if isinstance(value, str) and value in (palette or {}):
        return palette[value]
    if default is not None:
        return default
    raise ValueError(f"Unknown colour or palette role: {value}")


def color_alpha(value, palette, opacity=1.0):
    red, green, blue = ImageColor.getrgb(resolve_color(value, palette))[:3]
    return red, green, blue, max(0, min(255, round(255 * opacity)))


def resolve_font(channel, base, name=None):
    """Resolve a font role, an explicit path, or the channel default."""
    fonts = (channel or {}).get("fonts") or {}
    if name and name in fonts:
        name = fonts[name]
    elif name is None:
        name = (channel or {}).get("font") or fonts.get("body") or fonts.get("display")
        if name is None and fonts:
            name = next(iter(fonts.values()))
    if not name:
        return None
    return str(asset(base, name))


def _tracked_length(value, font, tracking):
    if not value:
        return 0
    base = sum(font.getlength(character) for character in value)
    return base + tracking * font.size * max(0, len(value) - 1)


def _draw_tracked(draw, position, text, font, fill, tracking, *, stroke_width=0, stroke_fill=None):
    x, y = position
    if not tracking:
        draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_width,
                  stroke_fill=stroke_fill or fill)
        return
    for character in text:
        draw.text((x, y), character, font=font, fill=fill, stroke_width=stroke_width,
                  stroke_fill=stroke_fill or fill)
        x += font.getlength(character) + tracking * font.size


def wrapped_text(text, font, width, tracking=0.0):
    rows = []
    for paragraph in text.split("\n"):
        row = ""
        for word in paragraph.split():
            candidate = f"{row} {word}".strip()
            if row and _tracked_length(candidate, font, tracking) > width:
                rows.append(row)
                row = word
            else:
                row = candidate
        rows.append(row)
    return "\n".join(rows)


def _fit_text(text, width, height, font_path, max_size, *, line_height=1.14,
              tracking=0.0, max_lines=None, uppercase=False):
    content = text.upper() if uppercase else text
    low, high = 1, max(1, max_size or height)
    fitted = None
    while low <= high:
        size = (low + high) // 2
        font = get_font(font_path, size)
        wrapped = wrapped_text(content, font, width, tracking)
        lines = wrapped.split("\n") if wrapped else [""]
        spacing = max(1, round(size * (line_height - 1)))
        total = len(lines) * font.size + (len(lines) - 1) * spacing
        widest = max((_tracked_length(line, font, tracking) for line in lines), default=0)
        if widest <= width and total <= height and (max_lines is None or len(lines) <= max_lines):
            fitted = (font, lines, spacing, size)
            low = size + 1
        else:
            high = size - 1
    if fitted is None:
        size = max(8, min(high, max_size or height))
        font = get_font(font_path, size)
        wrapped = wrapped_text(content, font, width, tracking)
        lines = wrapped.split("\n") if wrapped else [""]
        if max_lines:
            lines = lines[:max_lines]
        fitted = (font, lines, max(1, round(size * (line_height - 1))), size)
    return fitted


def gradient_image(size, gradient, palette):
    """Render a linear or radial gradient as RGBA."""
    width, height = max(1, size[0]), max(1, size[1])
    stops = sorted((float(stop["at"]), resolve_color(stop["color"], palette))
                   for stop in gradient["stops"])
    pixel = np.zeros((height, width, 3), dtype=np.float32)
    ys, xs = np.mgrid[0:height, 0:width]
    u = xs / max(1, width - 1)
    v = ys / max(1, height - 1)
    if gradient.get("type", "linear") == "radial":
        center = gradient.get("center") or [0.5, 0.5]
        radius = float(gradient.get("radius", 0.7))
        progress = np.sqrt((u - center[0]) ** 2 + (v - center[1]) ** 2) / max(radius, 1e-6)
    else:
        angle = math.radians(float(gradient.get("angle", 90)))
        cos, sin = math.cos(angle), math.sin(angle)
        # Start from the corner the gradient points away from, so 90-360 degrees aren't clipped flat.
        progress = u * cos + v * sin - min(0.0, cos, sin, cos + sin)
    progress = np.clip(progress, 0, 1)
    positions = np.array([item[0] for item in stops], dtype=np.float32)
    colors = np.array([ImageColor.getrgb(item[1])[:3] for item in stops], dtype=np.float32)
    for channel in range(3):
        pixel[..., channel] = np.interp(progress, positions, colors[:, channel])
    return Image.fromarray(np.uint8(np.clip(pixel, 0, 255))).convert("RGBA")


def paint_tile(mask, fill, palette):
    """Colour a single-channel mask with a solid paint or gradient."""
    if isinstance(fill, dict):
        tile = gradient_image(mask.size, fill, palette)
    else:
        tile = Image.new("RGBA", mask.size, color_alpha(fill, palette, 1))
    tile.putalpha(mask)
    return tile


def text_tile(text, size, fill, font_path, *, palette=None, align="center", line_height=1.14,
              tracking=0.0, max_lines=None, uppercase=False, stroke=0.0, stroke_color=None,
              padding=0.0, max_size=None):
    palette = palette or DEFAULT_PALETTE
    width, height = max(1, size[0]), max(1, size[1])
    inset_x = round(width * float(padding or 0))
    inset_y = round(height * float(padding or 0))
    inner_width = max(1, width - inset_x * 2)
    inner_height = max(1, height - inset_y * 2)
    font, lines, spacing, point = _fit_text(text, inner_width, inner_height, font_path,
                                            min(inner_height, max_size) if max_size else inner_height,
                                            line_height=line_height, tracking=tracking,
                                            max_lines=max_lines, uppercase=uppercase)
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    outline = max(0, round(point * float(stroke or 0)))
    total = len(lines) * font.size + (len(lines) - 1) * spacing
    y = inset_y + (inner_height - total) / 2
    for line in lines:
        line_width = _tracked_length(line, font, tracking)
        if align == "left":
            x = inset_x
        elif align == "right":
            x = width - inset_x - line_width
        else:
            x = inset_x + (inner_width - line_width) / 2
        _draw_tracked(draw, (x, y), line, font, 255, tracking)
        y += font.size + spacing
    tile = paint_tile(mask, fill, palette)
    if outline and stroke_color is not None:
        outline_mask = Image.new("L", (width, height), 0)
        outline_draw = ImageDraw.Draw(outline_mask)
        y = inset_y + (inner_height - total) / 2
        for line in lines:
            line_width = _tracked_length(line, font, tracking)
            if align == "left":
                x = inset_x
            elif align == "right":
                x = width - inset_x - line_width
            else:
                x = inset_x + (inner_width - line_width) / 2
            _draw_tracked(outline_draw, (x, y), line, font, 255, tracking,
                          stroke_width=outline, stroke_fill=255)
            y += font.size + spacing
        outline_tile = Image.new("RGBA", (width, height), color_alpha(stroke_color, palette, 1))
        outline_tile.putalpha(outline_mask)
        tile = Image.alpha_composite(outline_tile, tile)
    return tile


def shape_mask(kind, size, points=None, radius=0.0):
    width, height = max(1, size[0]), max(1, size[1])
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    bounds = (0, 0, width - 1, height - 1)
    if kind == "ellipse":
        draw.ellipse(bounds, fill=255)
    elif kind == "polygon":
        draw.polygon([(round(x * (width - 1)), round(y * (height - 1))) for x, y in points or []], fill=255)
    else:
        draw.rounded_rectangle(bounds, radius=round(min(width, height) * float(radius or 0) / 2), fill=255)
    return mask


def stroke_shape(tile, kind, points=None, radius=0.0, stroke=None, palette=None):
    if not stroke:
        return tile
    palette = palette or DEFAULT_PALETTE
    width, height = tile.size
    draw = ImageDraw.Draw(tile)
    pixels = max(1, round(min(width, height) * float(stroke.get("width", 0.02))))
    color = color_alpha(stroke.get("color", "foreground"), palette, 1)
    bounds = (0, 0, width - 1, height - 1)
    if kind == "ellipse":
        draw.ellipse(bounds, outline=color, width=pixels)
    elif kind == "polygon":
        points = [(round(x * (width - 1)), round(y * (height - 1))) for x, y in points or []]
        if points:
            draw.line([*points, points[0]], fill=color, width=pixels, joint="curve")
    else:
        draw.rounded_rectangle(bounds, radius=round(min(width, height) * float(radius or 0) / 2),
                               outline=color, width=pixels)
    return tile


def text_in_box(image, box, text, fill, font_path=None, max_size=None, *, palette=None,
                align="center", line_height=1.14, tracking=0.0, max_lines=None,
                uppercase=False, stroke=0.0, stroke_color=None):
    left, top, right, bottom = box
    width, height = max(1, right - left), max(1, bottom - top)
    tile = text_tile(text, (width, height), fill, font_path, palette=palette, align=align,
                     line_height=line_height, tracking=tracking, max_lines=max_lines,
                     uppercase=uppercase, stroke=stroke, stroke_color=stroke_color,
                     max_size=max_size)
    image.alpha_composite(tile, (left, top)) if image.mode == "RGBA" else image.paste(tile, (left, top), tile)


def make_brand(channel, base, out):
    p = channel["palette"]
    brand = channel.get("brand") or {}
    font = resolve_font(channel, base)
    logo = Image.new("RGB", (800, 800), p["background"])
    draw = ImageDraw.Draw(logo)
    shape = brand.get("logo", "disc")
    if shape == "ring":
        draw.ellipse((85, 85, 715, 715), outline=p["secondary"], width=54)
        draw.ellipse((118, 118, 682, 682), outline=p["accent"], width=12)
    elif shape in {"rounded", "square"}:
        radius = 120 if shape == "rounded" else 0
        draw.rounded_rectangle((85, 85, 715, 715), radius=radius, fill=p["secondary"])
        draw.rounded_rectangle((118, 118, 682, 682), radius=max(0, radius - 30),
                               outline=p["accent"], width=12)
    else:
        draw.ellipse((85, 85, 715, 715), fill=p["secondary"])
        draw.ellipse((118, 118, 682, 682), outline=p["accent"], width=12)
    size = float(brand.get("mark_size", 1))
    inset = round(185 * size)
    text_in_box(logo, (inset, 210, 800 - inset, 570), channel["mark"], p["foreground"], font,
                round(245 * size))
    if brand.get("accent_dot", True):
        draw.ellipse((610, 144, 660, 194), fill=p["accent"])
    logo.save(out / "logo.png")

    spec = channel.get("banner", {"width": 2560, "height": 1440, "safe_width": 1500, "safe_height": 380})
    w, h, sw, sh = (spec[k] for k in ("width", "height", "safe_width", "safe_height"))
    banner = Image.new("RGB", (w, h), p["background"])
    draw = ImageDraw.Draw(banner)
    pattern = brand.get("banner", "lines")
    if pattern == "lines":
        for index in range(9):
            x = index * w // 8
            draw.line((x, 0, x - w // 3, h), fill=p["secondary"], width=max(1, w // 720))
    elif pattern == "grid":
        for index in range(9):
            x = index * w // 8
            draw.line((x, 0, x, h), fill=p["secondary"], width=max(1, w // 900))
        for index in range(6):
            y = index * h // 5
            draw.line((0, y, w, y), fill=p["secondary"], width=max(1, h // 900))
    elif pattern == "dots":
        radius = max(2, w // 240)
        for row in range(7):
            for column in range(13):
                draw.ellipse((column * w // 12 - radius, row * h // 6 - radius,
                              column * w // 12 + radius, row * h // 6 + radius), fill=p["secondary"])
    x, y = (w - sw) // 2, (h - sh) // 2
    draw.rounded_rectangle((x, y, x + sw - 1, y + sh - 1), radius=sh // 5, fill=p["secondary"])
    icon = min(round(sh * 0.64), sw // 4)
    banner.paste(logo.resize((icon, icon), Image.Resampling.LANCZOS), (x + sw // 16, y + (sh - icon) // 2))
    title_x = x + icon + sw // 9
    text_in_box(banner, (title_x, y + sh // 8, x + sw * 15 // 16, y + sh * 3 // 5),
                channel["name"], p["foreground"], font, sh // 3)
    text_in_box(banner, (title_x, y + sh * 3 // 5, x + sw * 15 // 16, y + sh * 7 // 8),
                channel["tagline"], p["accent"], font, sh // 6)
    banner.save(out / "banner.png")
    banner.crop((x, y, x + sw, y + sh)).save(out / "banner-safe-preview.png")


TALK_LEVEL = 0.08  # Mouth level above which a speaker counts as talking.
MOTION_SHUTTER = 0.08  # Seconds a layer's motion_blur of 1 smears across.


def _rgb_list(value):
    if isinstance(value, list):
        return value
    value = value.lstrip("#")
    return [int(value[i:i + 2], 16) for i in (0, 2, 4)]


def _mix(start, end, k):
    if isinstance(start, list):
        return [a + (b - a) * k for a, b in zip(start, end)]
    return start + (end - start) * k


def poses(layer):
    scale = layer.get("scale", 1)
    state = {
        "x": layer["x"], "y": layer["y"],
        "scale": scale,
        "scale_x": layer.get("scale_x", scale),
        "scale_y": layer.get("scale_y", scale),
        "skew_x": layer.get("skew_x", 0),
        "skew_y": layer.get("skew_y", 0),
        "frame": layer.get("frame", 0),
        "blur": layer.get("blur", 0),
        "tint_opacity": layer.get("tint_opacity", 0),
        "rotate": layer.get("rotate", 0),
        "opacity": layer.get("opacity", 1),
        "visible": layer.get("visible", True),
        "z": layer.get("z", 0),
        "wipe": layer.get("wipe", 1),
        "turn_x": layer.get("turn_x", 0),
        "turn_y": layer.get("turn_y", 0),
        "bend": layer.get("bend", 0),
    }
    colour = layer.get("tint_color") or next((key["tint_color"] for key in layer.get("keyframes", [])
                                               if "tint_color" in key), None)
    if colour:
        state["tint_color"] = _rgb_list(layer.get("tint_color", colour))
    points = [(0, state, "linear", {})]
    for key in layer.get("keyframes", []):
        if "tint_color" in key:
            key = {**key, "tint_color": _rgb_list(key["tint_color"])}
        state = {name: key.get(name, value) for name, value in state.items()}
        if "scale" in key:
            if "scale_x" not in key:
                state["scale_x"] = key["scale"]
            if "scale_y" not in key:
                state["scale_y"] = key["scale"]
        if key["at"] == 0:
            points.pop()
        points.append((key["at"], state, key.get("ease", "linear"), key.get("ease_props") or {}))
    return points


def camera_points(shot):
    camera = shot.get("camera")
    if not camera:
        return None
    state = {"x": camera.get("x", 0), "y": camera.get("y", 0),
             "zoom": camera.get("zoom", 1), "rotate": camera.get("rotate", 0),
             "z": camera.get("z", 0), "fov": camera.get("fov", 50)}
    points = [(0, state, "linear", {})]
    for key in camera.get("keyframes", []):
        state = {name: key.get(name, value) for name, value in state.items()}
        if key["at"] == 0:
            points.pop()
        points.append((key["at"], state, key.get("ease", "linear"), {}))
    return points


def pose_at(points, progress):
    for index in range(1, len(points)):
        a, start, _, _ = points[index - 1]
        b, end, mode, ease_props = points[index]
        if progress > b:
            continue
        t = (progress - a) / (b - a) if b > a else 1.0
        result = {}
        for name, value in start.items():
            if isinstance(value, bool) or name == "frame":
                result[name] = end[name] if progress >= b else value
                continue
            property_mode = ease_props.get(name, mode)
            if property_mode == "auto":
                p0 = points[index - 2][1].get(name, value) if index >= 2 else value
                p3 = points[index + 1][1].get(name, end[name]) if index + 1 < len(points) else end[name]
                if isinstance(value, list):
                    result[name] = [catmull_rom(a, b, c, d, t) for a, b, c, d in zip(p0, value, end[name], p3)]
                else:
                    result[name] = catmull_rom(p0, value, end[name], p3, t)
            else:
                result[name] = _mix(value, end[name], ease(t, "smooth" if property_mode == "auto" else property_mode))
        return result
    return points[-1][1]


TURN_FOCAL = 2.5  # Perspective distance for turn_x/turn_y, in multiples of the layer's longest side.


def turn_point(dx, dy, turn_x, turn_y, focal):
    """Project a point offset from the pivot after turning about Y then X. Mirrors painter.mjs."""
    ty, tx = math.radians(turn_y), math.radians(turn_x)
    x1, z1 = dx * math.cos(ty), -dx * math.sin(ty)
    y2, z2 = dy * math.cos(tx) - z1 * math.sin(tx), dy * math.sin(tx) + z1 * math.cos(tx)
    scale = focal / max(focal * 0.05, focal + z2)
    return x1 * scale, y2 * scale


def _perspective_coeffs(output, source):
    rows, values = [], []
    for (x, y), (u, v) in zip(output, source):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        values.extend([u, v])
    return np.linalg.solve(np.array(rows, dtype=np.float64), np.array(values, dtype=np.float64)).tolist()


def turn_tile(tile, turn_x, turn_y, pivot):
    """Perspective-turn a tile about its pivot; returns the padded tile and its new pivot."""
    w, h = tile.size
    focal = TURN_FOCAL * max(w, h)
    pad = round(0.3 * max(w, h))
    cx, cy = float(pivot[0]) * w, float(pivot[1]) * h
    corners = [(0, 0), (w, 0), (w, h), (0, h)]
    projected = []
    for x, y in corners:
        px, py = turn_point(x - cx, y - cy, turn_x, turn_y, focal)
        projected.append((pad + cx + px, pad + cy + py))
    size = (w + 2 * pad, h + 2 * pad)
    try:
        coeffs = _perspective_coeffs(projected, corners)
    except np.linalg.LinAlgError:  # Edge-on: nothing visible.
        return Image.new("RGBA", size, (0, 0, 0, 0)), [(pad + cx) / size[0], (pad + cy) / size[1]]
    turned = tile.transform(size, Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC)
    return turned, [(pad + cx) / size[0], (pad + cy) / size[1]]


def bend_point(u, d, curvature, length):
    """Forward bend of a point ``u`` across and ``d`` along a part's axis (pivot origin, +y down the part).

    The part curves as a circular arc from the pivot; above the pivot it stays rigid and past the end
    it continues straight along the final tangent. Returns ``(x, y, tangent_degrees)``.
    Positive bend turns counter-clockwise on screen, like ``rotate``. Mirrors painter.mjs bendPoint.
    """
    if d <= 0 or abs(curvature) < 1e-9:
        return u, d, 0.0
    along = min(d, length)
    phi = curvature * along
    sin, cos = math.sin(phi), math.cos(phi)
    x = (1 - cos) / curvature + u * cos + (d - along) * sin
    y = sin / curvature - u * sin + (d - along) * cos
    return x, y, math.degrees(phi)


def bend_tile(tile, degrees, pivot):
    """Curve a tile along its vertical axis from the pivot; returns the new tile and pivot."""
    w, h = tile.size
    px, py = float(pivot[0]) * w, float(pivot[1]) * h
    length = h - py
    if length < 2 or abs(degrees) < 0.05:
        return tile, pivot
    k = math.radians(degrees) / length
    corners = [bend_point(x - px, y - py, k, length)[:2]
               for x in np.linspace(0, w, 9) for y in np.linspace(0, h, 33)]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    left, top = math.floor(min(xs)) - 2, math.floor(min(ys)) - 2
    right, bottom = math.ceil(max(xs)) + 2, math.ceil(max(ys)) + 2
    out_w, out_h = right - left, bottom - top
    gx, gy = np.meshgrid(np.arange(out_w, dtype=np.float64) + left + 0.5, np.arange(out_h, dtype=np.float64) + top + 0.5)
    # Inverse of the arc: the curvature centre sits at (1/k, 0) from the pivot.
    radius = 1.0 / k
    vx, vy = gx - radius, gy
    sign = 1.0 if k > 0 else -1.0
    reach = np.hypot(vx, vy) * sign
    phi = np.arctan2(vy * sign, -vx * sign)
    su = radius - reach
    sd = phi / k
    bent = (sd >= 0) & (sd <= length)
    # Past the end: straight continuation along the final tangent.
    end_x, end_y, _ = bend_point(0.0, length, k, length)
    t_x, t_y = math.sin(k * length), math.cos(k * length)
    n_x, n_y = math.cos(k * length), -math.sin(k * length)
    rel_x, rel_y = gx - end_x, gy - end_y
    tail_d = rel_x * t_x + rel_y * t_y
    tail_u = rel_x * n_x + rel_y * n_y
    rigid = (~bent) & (gy <= 0) & (gx + px >= 0) & (gx + px <= w) & (gy + py >= 0)
    tail = (~bent) & (~rigid) & (tail_d > 0)
    src_u = np.where(bent, su, np.where(tail, tail_u, gx))
    src_d = np.where(bent, sd, np.where(tail, length + tail_d, gy))
    valid = bent | tail | rigid
    sx, sy = src_u + px - 0.5, src_d + py - 0.5
    source = np.asarray(tile.convert("RGBA"), dtype=np.float32)
    alpha = source[..., 3:4] / 255.0
    premultiplied = np.concatenate([source[..., :3] * alpha, source[..., 3:4]], axis=2)
    x0, y0 = np.floor(sx).astype(int), np.floor(sy).astype(int)
    fx, fy = (sx - x0)[..., None], (sy - y0)[..., None]
    result = np.zeros((out_h, out_w, 4), dtype=np.float32)
    for dx, dy, weight in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        inside = valid & (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        sample = np.zeros_like(result)
        sample[inside] = premultiplied[yi[inside], xi[inside]]
        result += sample * weight
    rgb = np.where(result[..., 3:4] > 0, result[..., :3] / np.maximum(result[..., 3:4], 1e-6) * 255.0, 0)
    pixels = np.clip(np.concatenate([rgb, result[..., 3:4]], axis=2), 0, 255).astype(np.uint8)
    return Image.fromarray(pixels, "RGBA"), [(-left) / out_w, (-top) / out_h]


def bend_child(state, bend, parent_size, parent_pivot, width, height):
    """Move a child's attach point and add the tangent turn when its parent is bent."""
    w, h = parent_size
    py = float(parent_pivot[1]) * h
    length = h - py
    if length < 2 or not bend:
        return state
    k = math.radians(bend) / length
    x, y, turn = bend_point(float(state["x"]) * width, float(state["y"]) * height, k, length)
    return {**state, "x": x / width, "y": y / height, "rotate": float(state.get("rotate", 0)) + turn}


def wipe_region(width, height, amount, start="left"):
    """Visible box of a tile revealed ``amount`` (0..1) from one edge or the centre."""
    amount = max(0.0, min(1.0, amount))
    if start == "right":
        return (width * (1 - amount), 0, width, height)
    if start == "top":
        return (0, 0, width, height * amount)
    if start == "bottom":
        return (0, height * (1 - amount), width, height)
    if start == "center":
        return (width * (1 - amount) / 2, 0, width * (1 + amount) / 2, height)
    return (0, 0, width * amount, height)


def wipe_tile(tile, amount, start="left"):
    """Draw-on reveal: keep only the revealed part of a tile. Mirrors painter.mjs."""
    left, top, right, bottom = (round(v) for v in wipe_region(tile.width, tile.height, amount, start))
    revealed = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    if right > left and bottom > top:
        revealed.paste(tile.crop((left, top, right, bottom)), (left, top))
    return revealed


def depth_order(layers):
    """Parent-first order, then far-to-near by each layer's root ``z`` (stable)."""
    ordered = layer_order(layers)
    by_id = {layer["id"]: layer for layer in ordered}

    def root_z(layer):
        while layer.get("parent") in by_id:
            layer = by_id[layer["parent"]]
        return float(layer.get("z", 0) or 0)
    return sorted(ordered, key=lambda layer: -root_z(layer))


def depth_blur(z, camera):
    """Extra blur for layers outside the camera's focus band (``camera.focus``)."""
    focus = (camera or {}).get("focus")
    if not focus:
        return 0.0
    distance = abs(float(z or 0) - float(focus.get("z", 0)))
    return float(focus.get("amount", 0.5)) * max(0.0, min(1.0, (distance - float(focus.get("range", 0.2))) / 1.0))


def layer_order(layers):
    """Stable parent-before-child order; cycle detection happens in core."""
    by_id = {layer["id"]: layer for layer in layers}
    ordered, seen = [], set()

    def visit(layer):
        if layer["id"] in seen:
            return
        parent = layer.get("parent")
        if parent and parent in by_id:
            visit(by_id[parent])
        seen.add(layer["id"])
        ordered.append(layer)

    for layer in layers:
        visit(layer)
    return ordered


def _blend(base, layer, mode):
    if mode == "normal":
        return Image.alpha_composite(base, layer)
    base_rgb, layer_rgb = base.convert("RGB"), layer.convert("RGB")
    operation = {
        "add": ImageChops.add,
        "screen": ImageChops.screen,
        "multiply": ImageChops.multiply,
        "overlay": ImageChops.overlay,
        "soft-light": getattr(ImageChops, "soft_light", ImageChops.overlay),
    }.get(mode, ImageChops.screen)
    blended = operation(base_rgb, layer_rgb).convert("RGBA")
    blended.putalpha(layer.getchannel("A"))
    return Image.alpha_composite(base, blended)


def _transformed(tile, matrix):
    left, top, width, height = matrix_bbox(matrix, tile.width, tile.height)
    # Image.transform maps output pixels back into the source image. PIL stores
    # the inverse affine row-major, while the project uses Canvas column order.
    mapping = multiply(inverse(matrix), translate(left, top))
    pil_mapping = (mapping[0], mapping[2], mapping[4], mapping[1], mapping[3], mapping[5])
    return tile.transform((width, height), Image.Transform.AFFINE, pil_mapping,
                          resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0)), left, top


def _merge(*configs):
    merged = {}
    for config in configs:
        for key, value in (config or {}).items():
            if isinstance(value, dict):
                merged[key] = {**merged.get(key, {}), **value}
            else:
                merged[key] = value
    return merged


_NOISE = {}


def _noise_tile(size, seed):
    """Deterministic grey noise, identical to noiseTile() in browser/painter.mjs."""
    if (size, seed) not in _NOISE:
        state, values = seed or 1, np.empty(size * size, dtype=np.uint8)
        for index in range(size * size):
            state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
            values[index] = (state >> 24) & 0xFF
        _NOISE[(size, seed)] = values.reshape(size, size)
    return _NOISE[(size, seed)]


def apply_post(image, config, *, seed=0, palette=None):
    """Film-style finishing: grade, bloom, vignette, grain, halation."""
    if not config:
        return image
    data = np.asarray(image.convert("RGB")).astype(np.float32) / 255
    height, width = data.shape[:2]
    brightness = float(config.get("brightness", 1))
    if brightness != 1:
        data *= brightness
    if (contrast := float(config.get("contrast", 1))) != 1:
        data = (data - 0.5) * contrast + 0.5
    if (saturation := float(config.get("saturation", 1))) != 1:
        gray = data @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        data = np.clip(gray[..., None] + (data - gray[..., None]) * saturation, 0, 1)
    if (hue := float(config.get("hue", 0))) % 360:
        angle = math.radians(hue)
        cosine, sine = math.cos(angle), math.sin(angle)
        matrix = np.array([
            [0.213 + cosine * 0.787 - sine * 0.213, 0.715 - cosine * 0.715 - sine * 0.715, 0.072 - cosine * 0.072 + sine * 0.928],
            [0.213 - cosine * 0.213 + sine * 0.143, 0.715 + cosine * 0.285 + sine * 0.140, 0.072 - cosine * 0.072 - sine * 0.283],
            [0.213 - cosine * 0.213 - sine * 0.787, 0.715 - cosine * 0.715 + sine * 0.715, 0.072 + cosine * 0.928 + sine * 0.072],
        ], dtype=np.float32)
        data = np.clip(data @ matrix.T, 0, 1)
    if tint := config.get("tint"):
        value = resolve_color(tint, palette or DEFAULT_PALETTE).lstrip("#")
        color = np.array([int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)
        data = np.clip(data * 0.88 + color * 0.12, 0, 1)
    if config.get("grade") or config.get("lut"):
        from .grade import apply as apply_lut, table
        size, lut = table(config)
        data = apply_lut(data, size, lut, float(config.get("grade_amount", 1)))
    if bloom := float(config.get("bloom", 0)):
        bright = np.clip(data - 0.72, 0, None) * (2.4 * bloom)
        glow = np.asarray(Image.fromarray(np.uint8(np.clip(bright, 0, 1) * 255)).filter(
            ImageFilter.GaussianBlur(max(1, round(min(width, height) * 0.035 * bloom)))))
        data = 1 - (1 - data) * (1 - glow.astype(np.float32) / 255 * 0.85)
    if blur := float(config.get("blur", 0)):
        radius = max(0.5, min(width, height) * 0.012 * blur)
        data = np.asarray(Image.fromarray(np.uint8(np.clip(data, 0, 1) * 255)).filter(
            ImageFilter.GaussianBlur(radius))).astype(np.float32) / 255
    if chromatic := float(config.get("chromatic", 0)):
        shift = max(1, round(min(width, height) * 0.006 * chromatic))
        data[..., 0] = np.roll(data[..., 0], shift, axis=1)
        data[..., 2] = np.roll(data[..., 2], -shift, axis=1)
    if grain := float(config.get("grain", 0)):
        random = np.random.default_rng(seed or 1)
        noise = random.normal(0, 1, (height, width, 1)).astype(np.float32)
        data = data + noise * (0.11 * grain)
    if paper := float(config.get("paper", 0)):
        # Same LCG tiles as browser/painter.mjs: soft blotches plus fine fibre, multiplied.
        blotch = np.asarray(Image.fromarray(_noise_tile(48, 11)).resize((width, height), Image.Resampling.BILINEAR),
                            dtype=np.float32) / 255
        fibre = np.tile(_noise_tile(256, 5), (height // 256 + 1, width // 256 + 1))[:height, :width].astype(np.float32) / 255
        data *= (1 - paper * 0.35 * (1 - blotch))[..., None]
        data *= (1 - paper * 0.15 * (1 - fibre))[..., None]
    if leak := float(config.get("leak", 0)):
        y, x = np.ogrid[:height, :width]
        reach = math.hypot(width, height) * 0.75
        falloff = np.clip(1 - np.sqrt((x - width) ** 2 + (y + height * 0.05) ** 2) / reach, 0, 1) ** 1.6
        pulse = 0.75 + 0.25 * math.sin(seed * 0.05)
        warm = np.array([1.0, 0.69, 0.44], dtype=np.float32)
        amount = (falloff * leak * 0.55 * pulse)[..., None]
        data = 1 - (1 - data) * (1 - warm * amount)
    if vignette := float(config.get("vignette", 0)):
        y, x = np.ogrid[:height, :width]
        cx, cy = width / 2, height / 2
        distance = np.sqrt(((x - cx) / cx) ** 2 + ((y - cy) / cy) ** 2) / math.sqrt(2)
        mask = np.clip(1 - vignette * np.clip(distance * 1.15, 0, 1) ** 1.8, 0, 1)
        data *= mask[..., None]
    if letterbox := float(config.get("letterbox", 0)):
        bar = round(height * letterbox / 2)
        data[:bar] = 0
        data[-bar:] = 0
    return Image.fromarray(np.uint8(np.clip(data, 0, 1) * 255))


class Composition:
    def __init__(self, shot, canvas, channel, font, base, *, episode_post=None, motion_blur=0,
                 channel_base=None):
        self.shot = shot
        self.canvas = canvas
        self.base = base
        self.channel_base = channel_base
        self.palette = channel["palette"]
        self.background = resolve_color(shot.get("background", "background"), self.palette)
        self.post = _merge(channel.get("post"), episode_post, shot.get("post"))
        self.camera = resolve_camera(shot) if shot.get("camera") else None
        self.camera_points = camera_points({**shot, "camera": self.camera}) if shot.get("camera") else None
        self.track = (self.camera or {}).get("track")
        layers = sorted(depth_order(shot["layers"]), key=lambda item: item.get("plane") != "background")
        self.layers = []
        for layer in layers:
            tiles = sheet_tiles(layer, canvas, base, channel_base) if layer["kind"] == "sheet" else None
            if layer.get("paint_frames"):
                tiles = [sprite({**layer, **look}, canvas, channel, font, base, channel_base)
                         for look in layer["paint_frames"]]
            self.layers.append({
                "id": layer["id"],
                "kind": layer["kind"],
                "tile": tiles[0] if tiles else sprite(layer, canvas, channel, font, base, channel_base),
                "tiles": tiles,
                "points": poses(layer),
                "mouth_for": layer.get("mouth_for"),
                "parent": layer.get("parent"),
                "variant_group": layer.get("variant_group"),
                "pivot": layer.get("pivot", [0.5, 0.5]),
                "blend": layer.get("blend", "normal"),
                "blur": layer.get("blur", 0),
                "motion_blur": layer.get("motion_blur", 0),
                "parallax": layer.get("parallax", 1),
                "plane": layer.get("plane", "foreground"),
                "mask": layer.get("mask"),
                "shadow": layer.get("shadow"),
                "glow": layer.get("glow"),
                "tint": layer.get("tint"),
                "viseme_for": layer.get("viseme_for"),
                "viseme": layer.get("viseme"),
                "spec": layer,
            })
        self.layer_map = {layer["id"]: layer for layer in self.layers}
        self.masks = {}
        for layer in self.layers:
            inherited = list(self.masks.get(layer["parent"], []))
            if layer.get("mask"):
                inherited.append(layer["mask"])
            self.masks[layer["id"]] = inherited

    def _world(self, layer_id, progress, camera, seen=None):
        seen = set(seen or ())
        if layer_id in seen:
            raise ValueError(f"Mask cycle at {layer_id}")
        seen.add(layer_id)
        layer = self.layer_map[layer_id]
        state = pose_at(layer["points"], progress)
        parent = layer["parent"]
        parent_matrix = None
        parent_origin = None
        if parent in self.layer_map:
            parent_matrix, parent_tile = self._world(parent, progress, camera, seen)
            parent_origin = (float(self.layer_map[parent]["pivot"][0]) * parent_tile.width,
                             float(self.layer_map[parent]["pivot"][1]) * parent_tile.height)
        tile = layer["tile"]
        matrix = layer_matrix(state, self.canvas[0], self.canvas[1], layer["pivot"],
                              parent=parent_matrix, parent_origin=parent_origin, camera=camera,
                              parallax=layer["parallax"], box=(tile.width, tile.height))
        return matrix, tile

    def _mask_buffer(self, spec, progress, camera, cache):
        source = spec.get("source", "")
        key = (source, spec.get("mode", "alpha"), bool(spec.get("invert", False)),
               float(spec.get("feather", 0)))
        if key in cache:
            return cache[key]
        width, height = self.canvas
        if source.startswith("layer:"):
            layer = self.layer_map.get(source.split(":", 1)[1])
            if layer is None:
                raise ValueError(f"Mask references unknown layer: {source}")
            matrix, tile = self._world(layer["id"], progress, camera)
            placed, left, top = _transformed(tile, matrix)
            if spec.get("mode") == "luma":
                channel = ImageChops.multiply(ImageOps.grayscale(placed.convert("RGB")),
                                              placed.getchannel("A"))
            else:
                channel = placed.getchannel("A")
            mask = Image.new("L", (width, height), 0)
            mask.paste(channel, (left, top))
        else:
            base = self.channel_base if spec.get("scope") == "channel" else self.base
            if base is None:
                raise ValueError("Channel-scoped masks require a channel path")
            with Image.open(asset(base, source)) as image:
                rgba = image.convert("RGBA")
                if spec.get("mode") == "alpha":
                    mask = rgba.getchannel("A")
                else:
                    mask = ImageChops.multiply(ImageOps.grayscale(rgba), rgba.getchannel("A"))
                mask = mask.resize((width, height), Image.Resampling.BILINEAR)
        if spec.get("invert"):
            mask = ImageOps.invert(mask)
        if feather := float(spec.get("feather", 0)):
            mask = mask.filter(ImageFilter.GaussianBlur(max(0.5, min(width, height) * feather * 0.08)))
        cache[key] = mask
        return mask

    def _apply_masks(self, placed, left, top, specs, progress, camera, cache):
        if not specs:
            return placed
        width, height = self.canvas
        alpha = placed.getchannel("A")
        for spec in specs:
            mask = self._mask_buffer(spec, progress, camera, cache)
            patch = Image.new("L", placed.size, 0)
            sx0, sy0 = max(0, left), max(0, top)
            sx1, sy1 = min(width, left + placed.width), min(height, top + placed.height)
            if sx1 > sx0 and sy1 > sy0:
                patch.paste(mask.crop((sx0, sy0, sx1, sy1)), (sx0 - left, sy0 - top))
            alpha = ImageChops.multiply(alpha, patch)
        placed = placed.copy()
        placed.putalpha(alpha)
        return placed

    def _tracked_camera(self, progress):
        width, height = self.canvas
        base = pose_at(self.camera_points, progress) if self.camera_points else {
            "x": 0, "y": 0, "zoom": 1, "rotate": 0}
        if not self.track:
            return base
        layer = self.layer_map.get(self.track.get("layer"))
        if layer is None:
            return base
        origins = {}

        def pre_matrix(item):
            state = pose_at(item["points"], progress)
            parent = item["parent"]
            parent_matrix = pre_matrix(self.layer_map[parent])[0] if parent in self.layer_map else None
            parent_origin = origins.get(parent)
            tile = item["tile"]
            matrix = layer_matrix(state, width, height, item["pivot"], parent=parent_matrix,
                                  parent_origin=parent_origin, camera=None,
                                  box=(tile.width, tile.height))
            origins[item["id"]] = (float(item["pivot"][0]) * tile.width,
                                   float(item["pivot"][1]) * tile.height)
            return matrix, tile

        matrix, tile = pre_matrix(layer)
        subject_x, subject_y = apply_matrix(matrix, tile.width / 2, tile.height / 2)
        desired = (float(self.track.get("x", 0.5)) * width,
                   float(self.track.get("y", 0.5)) * height)
        inverse_camera = inverse(camera_matrix({**base, "x": 0, "y": 0}, width, height))
        target_x, target_y = apply_matrix(inverse_camera, *desired)
        return {**base,
                "x": float(base.get("x", 0)) + (target_x - subject_x) / width,
                "y": float(base.get("y", 0)) + (target_y - subject_y) / height}

    def frame(self, progress, speaking, hidden=(), *, post=True, seed=0, visemes=None):
        width, height = self.canvas
        image = Image.new("RGBA", self.canvas, self.background)
        camera = self._tracked_camera(progress) if self.camera_points else None
        hidden_ids = set(hidden)
        for layer in self.layers:
            if layer["parent"] in hidden_ids:
                hidden_ids.add(layer["id"])
        states = {layer["id"]: pose_at(layer["points"], progress) for layer in self.layers}
        chosen = {}
        for layer in self.layers:
            group = layer.get("variant_group")
            if group and states[layer["id"]]["visible"]:
                chosen[group] = layer["id"]
        for layer in self.layers:
            state = states[layer["id"]]
            group = layer.get("variant_group")
            if group and chosen.get(group) != layer["id"]:
                state["visible"] = False
            if layer.get("viseme_for"):
                shape = (visemes or {}).get(layer["viseme_for"])
                if shape and layer.get("viseme") and layer["viseme"] != shape:
                    state["visible"] = False
            if layer["parent"] and not states[layer["parent"]]["visible"]:
                state["visible"] = False
        matrices, alphas, origins, mask_cache, depths, bends = {}, {}, {}, {}, {}, {}
        for layer in self.layers:
            state = states[layer["id"]]
            if layer["id"] in hidden_ids or not state["visible"]:
                continue
            parent_matrix = matrices.get(layer["parent"])
            parent_alpha = alphas.get(layer["parent"], 1.0)
            alpha = state["opacity"] * parent_alpha
            if layer["parent"] in depths:
                depths[layer["id"]] = depths[layer["parent"]]
            else:
                depths[layer["id"]] = float(state.get("z", 0) or 0)
                if camera is not None and (depths[layer["id"]] or camera.get("z")):
                    alpha *= depth_fade(depths[layer["id"]], camera)
            extra_blur = depth_blur(depths[layer["id"]], {**(camera or {}), "focus": (self.camera or {}).get("focus")})
            if extra_blur:
                state = {**state, "blur": float(state.get("blur", 0) or 0) + extra_blur}
            if layer.get("tiles"):
                frame_index = max(0, min(len(layer["tiles"]) - 1, int(round(state.get("frame", 0)))))
                tile = layer["tiles"][frame_index]
            else:
                tile = layer["tile"]
            quiet = layer["spec"].get("quiet_for")
            if quiet and speaking and speaking.get(quiet, 0) > TALK_LEVEL:
                continue
            if layer["mouth_for"] and layer["spec"].get("talk_only") and (
                    not speaking or speaking.get(layer["mouth_for"], 0) <= TALK_LEVEL):
                continue
            if layer["mouth_for"]:
                level = speaking.get(layer["mouth_for"], 0) if speaking else 0
                floor = 0.4 if layer["spec"].get("talk_only") else 0.18
                mouth = floor + (1 - floor) * level
                if mouth < 0.999:
                    tile = tile.resize((tile.width, max(1, round(tile.height * mouth))),
                                       Image.Resampling.BILINEAR)
            if float(state.get("wipe", 1)) < 1:
                tile = wipe_tile(tile, float(state["wipe"]), layer["spec"].get("wipe_from", "left"))
            if state.get("blur"):
                tile = tile.filter(ImageFilter.GaussianBlur(max(0.5, min(width, height) * float(state["blur"]) * 0.02)))
            pivot = layer["pivot"]
            if layer["parent"] in bends:
                state = bend_child(state, *bends[layer["parent"]], width, height)
            if state.get("bend") and layer["kind"] != "group":
                bends[layer["id"]] = (float(state["bend"]), tile.size, pivot)
                tile, pivot = bend_tile(tile, float(state["bend"]), pivot)
            if (state.get("turn_x") or state.get("turn_y")) and layer["kind"] != "group":
                tile, pivot = turn_tile(tile, float(state.get("turn_x", 0)), float(state.get("turn_y", 0)), pivot)
            matrix = layer_matrix(state, width, height, pivot, parent=parent_matrix,
                                  parent_origin=origins.get(layer["parent"]),
                                  camera=camera, parallax=layer["parallax"],
                                  box=(tile.width, tile.height))
            matrices[layer["id"]], alphas[layer["id"]] = matrix, alpha
            origins[layer["id"]] = (float(pivot[0]) * tile.width,
                                    float(pivot[1]) * tile.height)
            if layer["kind"] == "group" or alpha <= 0:
                continue
            placed, left, top = _transformed(tile, matrix)
            if alpha < 1:
                placed = placed.copy()
                placed.putalpha(placed.getchannel("A").point(lambda value: round(value * alpha)))
            placed = self._apply_masks(placed, left, top, self.masks.get(layer["id"], []),
                                       progress, camera, mask_cache)
            tint_opacity = max(0.0, min(1.0, float(state.get("tint_opacity", 0) or 0)))
            if (layer.get("tint") or state.get("tint_color")) and tint_opacity > 0:
                colour = (tuple(max(0, min(255, round(v))) for v in state["tint_color"]) if state.get("tint_color")
                          else resolve_color(layer["tint"], self.palette))
                tinted = ImageChops.multiply(
                    placed.convert("RGB"),
                    Image.new("RGB", placed.size, colour),
                ).convert("RGBA")
                tinted.putalpha(placed.getchannel("A"))
                placed = Image.blend(placed, tinted, tint_opacity)
            motion = float(layer.get("motion_blur", 0) or 0)
            if motion > 0 and (self.masks.get(layer["id"]) or ((layer.get("tint") or state.get("tint_color"))
                                                               and tint_opacity > 0)):
                # Masked or tinted layers keep the cheaper smear of the finished patch.
                future = pose_at(layer["points"], min(1.0, progress + motion * MOTION_SHUTTER
                                                      / max(0.1, float(self.shot.get("duration", 1)))))
                shift_x, shift_y = (future["x"] - state["x"]) * width, (future["y"] - state["y"]) * height
                samples = 5 if motion >= 0.5 else 3
                for index in range(samples):
                    factor = (index - (samples - 1) / 2) / max(1, samples - 1)
                    sample = placed.copy()
                    sample.putalpha(placed.getchannel("A").point(lambda value: round(value / samples)))
                    image = (_paste(image, sample, left + round(shift_x * factor), top + round(shift_y * factor))
                             if layer["blend"] == "normal" else
                             _blend_at(image, sample, left + round(shift_x * factor), top + round(shift_y * factor),
                                       layer["blend"]))
                continue
            if motion > 0:
                # Sample the full pose (move, turn, scale) over a fixed shutter in seconds,
                # mirrored in browser/painter.mjs.
                window = motion * MOTION_SHUTTER / max(0.1, float(self.shot.get("duration", 1)))
                samples = 5 if motion >= 0.5 else 3
                for index in range(samples):
                    factor = (index - (samples - 1) / 2) / max(1, samples - 1)
                    sample_state = {**state, **{key: value for key, value in pose_at(
                        layer["points"], max(0.0, min(1.0, progress + window * factor))).items()
                        if key in ("x", "y", "scale", "scale_x", "scale_y", "rotate", "skew_x", "skew_y")}}
                    sample_matrix = layer_matrix(sample_state, width, height, pivot, parent=parent_matrix,
                                                 parent_origin=origins.get(layer["parent"]), camera=camera,
                                                 parallax=layer["parallax"], box=(tile.width, tile.height))
                    sample, sample_left, sample_top = _transformed(tile, sample_matrix)
                    sample = sample.copy()
                    sample.putalpha(sample.getchannel("A").point(lambda value: round(value * alpha / samples)))
                    if layer["blend"] == "normal":
                        image = _paste(image, sample, sample_left, sample_top)
                    else:
                        image = _blend_at(image, sample, sample_left, sample_top, layer["blend"])
                continue
            if layer.get("shadow"):
                shadow, dx, dy = _effect_patch(placed, layer["shadow"], "background", self.palette,
                                               width, height, default_opacity=0.55)
                image = _paste(image, shadow, left + dx, top + dy)
            if layer.get("glow"):
                glow, dx, dy = _effect_patch(placed, layer["glow"], "accent", self.palette,
                                             width, height, default_opacity=0.6, glow=True)
                image = _blend_at(image, glow, left + dx, top + dy, "screen")
            if layer["blend"] == "normal":
                image = Image.alpha_composite(image, placed) if placed.size == image.size else _paste(image, placed, left, top)
            else:
                image = _blend_at(image, placed, left, top, layer["blend"])
        if post:
            image = apply_post(image, self.post, seed=seed, palette=self.palette)
        return image.convert("RGB")


def _paste(base, layer, left, top):
    canvas = base.copy()
    canvas.alpha_composite(layer, (left, top))
    return canvas


def _blend_at(base, layer, left, top, mode):
    # Composite the layer over a transparent canvas first so blend maths stays
    # inside the layer's own bounds, then blend that patch into the frame.
    patch = Image.new("RGBA", base.size, (0, 0, 0, 0))
    patch.alpha_composite(layer, (left, top))
    return _blend(base, patch, mode)


def _effect_patch(placed, spec, default_color, palette, width, height, *, default_opacity=0.6,
                  glow=False):
    opacity = float(spec.get("opacity", default_opacity))
    color = resolve_color(spec.get("color", default_color), palette)
    size = float(spec.get("size", 0.18) if glow else spec.get("blur", 0.18))
    radius = max(0.5, min(width, height) * size * 0.16)
    margin = max(2, round(radius * 3))
    alpha = Image.new("L", (placed.width + margin * 2, placed.height + margin * 2), 0)
    alpha.paste(placed.getchannel("A").filter(ImageFilter.GaussianBlur(radius)), (margin, margin))
    patch = Image.new("RGBA", alpha.size, color_alpha(color, palette, opacity))
    patch.putalpha(alpha)
    dx = round(float(spec.get("offset_x", 0)) * width) - margin
    dy = round(float(spec.get("offset_y", 0)) * height) - margin
    return patch, dx, dy


def sheet_tiles(layer, canvas, base, channel_base=None):
    """Slice a sprite sheet and fit each frame inside the layer box."""
    with Image.open(scoped_asset(layer, base, channel_base)) as source:
        sheet = source.convert("RGBA")
    columns, rows = int(layer["columns"]), int(layer["rows"])
    count = int(layer.get("count", columns * rows))
    if count > columns * rows:
        raise ValueError(f"Sprite sheet has {columns * rows} cells but count is {count}: {layer['id']}")
    cw, ch = canvas
    width = max(1, round(layer.get("width", 0.55) * cw))
    height = max(1, round(layer.get("height", 0.2) * ch))
    frame_width, frame_height = sheet.width / columns, sheet.height / rows
    tiles = []
    for index in range(count):
        column, row = index % columns, index // columns
        frame = sheet.crop((round(column * frame_width), round(row * frame_height),
                            round((column + 1) * frame_width), round((row + 1) * frame_height)))
        tiles.append(ImageOps.contain(frame, (width, height)))
    return tiles


def sprite(layer, canvas, channel, font, base, channel_base=None):
    cw, ch = canvas
    palette = channel["palette"]
    w = max(1, round(layer.get("width", 0.55) * cw))
    h = max(1, round(layer.get("height", 0.2) * ch))
    fill = layer.get("fill", "foreground")
    kind = layer["kind"]
    if kind == "group":
        if "width" not in layer or "height" not in layer:
            w, h = cw, ch
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if kind == "particles":
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if kind == "image":
        with Image.open(scoped_asset(layer, base, channel_base)) as source:
            return ImageOps.contain(ImageOps.exif_transpose(source).convert("RGBA"), (w, h))
    if kind == "text":
        font_path = resolve_font(channel, channel_base or base, layer["font"]) if "font" in layer else font
        stroke = layer.get("stroke") or {}
        effect_padding = 0.07 if (layer.get("shadow") or layer.get("glow") or stroke) else 0.0
        return text_tile(
            layer["text"], (w, h), fill, font_path, palette=palette,
            align=layer.get("align", "center"),
            line_height=layer.get("line_height", 1.14),
            tracking=layer.get("letter_spacing", 0),
            max_lines=layer.get("max_lines"),
            uppercase=layer.get("uppercase", False),
            stroke=stroke.get("width", 0),
            stroke_color=stroke.get("color"),
            padding=effect_padding,
        )
    mask = shape_mask(kind, (w, h), layer.get("points"), layer.get("radius", 0))
    tile = paint_tile(mask, fill, palette)
    return stroke_shape(tile, kind, layer.get("points"), layer.get("radius", 0),
                        layer.get("stroke"), palette)


def luma_mask(width, height, progress, *, softness=0.08, invert=False, seed=17):
    """Deterministic diagonal luma matte shared with the browser renderer."""
    x, y = np.meshgrid(np.linspace(0, 1, width, dtype=np.float32),
                       np.linspace(0, 1, height, dtype=np.float32))
    noise = 0.5 + 0.5 * np.sin(x * 17.3 + y * 9.7 + seed) * np.sin(x * 5.1 - y * 13.9 + seed * 0.7)
    ramp = x * 0.55 + (1 - y) * 0.25 + noise * 0.20
    threshold = -0.8 + progress * 2.2
    feather = max(0.015, softness)
    alpha = np.clip((ramp - threshold) / feather + 0.5, 0, 1)
    if invert:
        alpha = 1 - alpha
    return Image.fromarray(np.uint8(alpha * 255), mode="L")


def transition_frame(previous, current, mode, progress, ease_mode="smooth", *,
                     softness=0.08, invert=False, seed=17, mask_image=None, mask_mode="luma"):
    t = ease(progress, ease_mode)
    if mode == "luma-wipe":
        mask = luma_mask(max(4, current.width // 4), max(4, current.height // 4),
                         t, softness=softness, invert=invert, seed=seed)
        mask = mask.resize(current.size, Image.Resampling.BILINEAR)
        return Image.composite(current, previous, mask)
    if mode == "mask" and mask_image is not None:
        matte = mask_image.convert("L").resize(current.size, Image.Resampling.BILINEAR)
        if invert:
            matte = ImageOps.invert(matte)
        values = np.asarray(matte, dtype=np.float32) / 255
        if mask_mode == "alpha":
            alpha = values * t
        else:
            alpha = np.clip((values - (1 - t)) / max(0.015, softness) + 0.5, 0, 1)
        mask = Image.fromarray(np.uint8(alpha * 255), mode="L")
        return Image.composite(current, previous, mask)
    if mode == "dissolve":
        return Image.blend(previous, current, t)
    if mode in {"wipe-left", "wipe-right", "wipe-up", "wipe-down"}:
        return _wipe(previous, current, mode, t)
    if mode in {"slide-left", "slide-right", "slide-up", "slide-down"}:
        return _slide(previous, current, mode, t)
    if mode in {"whip-left", "whip-right"}:
        return _slide(previous, current, mode.replace("whip", "slide"), min(1, t * 1.1))
    if mode in {"zoom-in", "zoom-out"}:
        return _zoom(previous, current, mode, t)
    if mode == "iris":
        return _iris(previous, current, t)
    if mode == "flash":
        white = Image.new("RGB", current.size, "#ffffff")
        return Image.blend(previous, white, min(1, t * 2)) if t < 0.5 else Image.blend(white, current, (t - 0.5) * 2)
    if mode == "dip-to-black":
        black = Image.new("RGB", current.size, "#000000")
        return Image.blend(previous, black, t * 2) if t < 0.5 else Image.blend(black, current, (t - 0.5) * 2)
    if mode == "luma-wipe":
        return _wipe(previous, current, "wipe-left", t)
    return Image.blend(previous, current, t)


def _wipe(previous, current, mode, t):
    width, height = current.size
    if mode == "wipe-left":
        split = math.floor(width * t)
        image = previous.copy()
        image.paste(current.crop((0, 0, split, height)), (0, 0))
        return image
    if mode == "wipe-right":
        split = math.floor(width * t)
        image = previous.copy()
        image.paste(current.crop((width - split, 0, width, height)), (width - split, 0))
        return image
    if mode == "wipe-up":
        split = math.floor(height * t)
        image = previous.copy()
        image.paste(current.crop((0, 0, width, split)), (0, 0))
        return image
    split = math.floor(height * t)
    image = previous.copy()
    image.paste(current.crop((0, height - split, width, height)), (0, height - split))
    return image


def _slide(previous, current, mode, t):
    width, height = current.size
    image = previous.copy()
    if mode == "slide-left":
        offset = round(width * t)
        image.paste(current, (offset - width, 0))
        return image.crop((0, 0, width, height))
    if mode == "slide-right":
        offset = round(width * t)
        image.paste(current, (width - offset, 0))
        return image
    if mode == "slide-up":
        offset = round(height * t)
        image.paste(current, (0, offset - height))
        return image
    offset = round(height * t)
    image.paste(current, (0, height - offset))
    return image


def _zoom(previous, current, mode, t):
    width, height = current.size
    if mode == "zoom-in":
        scale = 0.84 + 0.16 * t
        layer = current.resize((max(1, round(width * scale)), max(1, round(height * scale))),
                               Image.Resampling.BICUBIC)
        image = previous.copy()
        image.paste(layer, ((width - layer.width) // 2, (height - layer.height) // 2))
        return Image.blend(image, current, t)
    scale = 1.0 + 0.2 * (1 - t)
    layer = previous.resize((max(1, round(width * scale)), max(1, round(height * scale))),
                            Image.Resampling.BICUBIC)
    image = current.copy()
    image.paste(layer, ((width - layer.width) // 2, (height - layer.height) // 2))
    return Image.blend(image, current, t)


def _iris(previous, current, t):
    width, height = current.size
    mask = Image.new("L", current.size, 0)
    draw = ImageDraw.Draw(mask)
    radius = round(math.hypot(width, height) / 2 * t)
    draw.ellipse((width / 2 - radius, height / 2 - radius,
                  width / 2 + radius, height / 2 + radius), fill=255)
    return Image.composite(current, previous, mask)


def _grade(color, value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def caption_layout(image, text, font_path, config=None):
    config = config or {}
    width, height = image.size
    max_words = int(config.get("max_words", 6))
    max_lines = int(config.get("max_lines", 5))
    padding_x = float(config.get("padding_x", 0.09))
    tracking = float(config.get("letter_spacing", 0))
    line_height = float(config.get("line_height", 1.22))
    max_width = max(10, width * (1 - 2 * padding_x))
    size = max(12, round(min(width, height) * 0.058 * float(config.get("font_size", 1))))
    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    font, rows = get_font(font_path, size), []
    # Shrink rather than clip when a long line or a narrow phone needs it.
    for _ in range(10):
        font = get_font(font_path, size)
        lines, row = [], []
        for word in text.split():
            candidate = " ".join([*row, word])
            if row and (len(row) >= max_words
                        or _tracked_length(candidate, font, tracking) > max_width):
                lines.append(" ".join(row))
                row = [word]
            else:
                row.append(word)
        if row:
            lines.append(" ".join(row))
        rows, y = [], 0
        for line in lines:
            line_width = _tracked_length(line, font, tracking)
            if config.get("align", "center") == "left":
                x = padding_x * width
            elif config.get("align", "center") == "right":
                x = width - padding_x * width - line_width
            else:
                x = (width - line_width) / 2
            row_words = []
            for word in line.split():
                word_width = _tracked_length(word, font, tracking)
                box = draw.textbbox((x, y), word, font=font)
                box = (box[0], box[1], box[0] + word_width, box[3])
                row_words.append({"text": word, "box": box})
                x += word_width + draw.textlength(" ", font=font) + tracking * font.size
            rows.append(row_words)
            y += font.size * line_height
        if (lines and all(_tracked_length(line, font, tracking) <= max_width for line in lines)
                and len(lines) <= max_lines):
            break
        size = max(10, round(size * 0.9))
    return font, rows, size


def draw_caption(image, cue, channel, font, config=None, frame=None):
    if isinstance(cue, str):
        cue = {"text": cue}
    config = config or {}
    if config.get("style") == "kinetic":
        from .captions import draw_kinetic
        if frame is None:
            frame = cue.get("start", 0) + max(0, (cue.get("end", 0) - cue.get("start", 0)) // 2)
        draw_kinetic(image, cue, channel, font, config, frame, float(config.get("fps", 30)))
        return
    text = cue.get("text", "")
    if config.get("uppercase"):
        text = text.upper()
    style = config.get("style", "box")
    position = config.get("position", "bottom")
    font_obj, rows, size = caption_layout(image, text, font, config)
    width, height = image.size
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    palette = channel["palette"]
    foreground = resolve_color(config.get("foreground", "foreground"), palette)
    background = resolve_color(config.get("background", "background"), palette)
    highlight = resolve_color(config.get("highlight", "accent"), palette)
    highlight_text = resolve_color(config.get("highlight_text", "background"), palette)
    shadow_color = resolve_color(config.get("shadow_color", "background"), palette)
    opacity = float(config.get("background_opacity", 1))
    box_color = color_alpha(background, palette, opacity)
    top = rows[0][0]["box"][1] if rows else 0
    bottom = rows[-1][0]["box"][3] if rows else 0
    base = {"top": 0.09, "center": 0.46, "bottom": 0.80}.get(position, 0.80)
    offset = round(height * (base + float(config.get("offset", 0)))) - top
    radius = max(2, round(size * float(config.get("radius", 0.45))))
    if style in {"box", "karaoke"}:
        pad_x = round(width * float(config.get("padding_x", 0.04)))
        pad_y = round(height * float(config.get("padding_y", 0.02)))
        left = round(width * float(config.get("padding_x", 0.09))) - pad_x
        right = width - left
        box = (left, offset + top - pad_y, right, offset + bottom + pad_y)
        draw.rounded_rectangle(box, radius=radius, fill=box_color)
    outline = max(0, round(size * float(config.get("stroke", 0))))
    shadow = bool(config.get("shadow", False))
    tracking = float(config.get("letter_spacing", 0))

    def write(word, x, y, fill):
        if shadow:
            _draw_tracked(draw, (x + size * 0.05, y + size * 0.07), word, font_obj,
                          color_alpha(shadow_color, palette, 0.5), tracking,
                          stroke_width=outline,
                          stroke_fill=color_alpha(shadow_color, palette, 0.35))
        _draw_tracked(draw, (x, y), word, font_obj, fill, tracking,
                      stroke_width=outline, stroke_fill=box_color if outline else fill)

    if style == "minimal":
        for row in rows:
            for word in row:
                box = (word["box"][0], word["box"][1] + offset,
                       word["box"][2], word["box"][3] + offset)
                write(word["text"], box[0], box[1], foreground)
    elif style == "karaoke" and cue.get("words"):
        active = None
        if frame is not None:
            active = next((index for index, word in enumerate(cue["words"])
                           if word.get("start", 0) <= frame < word.get("end", 0)), None)
        index = 0
        for row in rows:
            for word in row:
                box = (word["box"][0], word["box"][1] + offset,
                       word["box"][2], word["box"][3] + offset)
                if index == active:
                    draw.rounded_rectangle((box[0] - size * 0.04, box[1] - size * 0.06,
                                            box[2] + size * 0.04, box[3] + size * 0.10),
                                           radius=max(2, round(size * 0.20)), fill=highlight)
                write(word["text"], box[0], box[1],
                      highlight_text if index == active else foreground)
                index += 1
    else:
        for row in rows:
            for word in row:
                write(word["text"], word["box"][0], word["box"][1] + offset, foreground)

    animation = config.get("animation", "none")
    if animation != "none" and cue.get("start") is not None and cue.get("end") is not None:
        span = max(1, int((cue["end"] - cue["start"]) * 0.22))
        t = 1.0 if frame is None else max(0.0, min(1.0, (frame - cue["start"]) / span))
        if animation == "pop":
            scale = 0.9 + 0.1 * t
            resized = layer.resize((max(1, round(width * scale)), max(1, round(height * scale))),
                                   Image.Resampling.BICUBIC)
            layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
            layer.alpha_composite(resized, ((width - resized.width) // 2,
                                            (height - resized.height) // 2))
        elif animation in {"slide", "rise"}:
            distance = 0.035 if animation == "slide" else 0.06
            shifted = Image.new("RGBA", image.size, (0, 0, 0, 0))
            shifted.alpha_composite(layer, (0, round((1 - t) * height * distance)))
            layer = shifted
        elif animation == "fade":
            layer.putalpha(layer.getchannel("A").point(lambda value: round(value * t)))
    image.paste(layer, (0, 0), layer)


def thumbnail(frame, text, channel, font, config=None, base=None):
    config = config or {}
    image = frame.copy().convert("RGBA")
    w, h = image.size
    palette = channel["palette"]
    background = resolve_color(config.get("background", "background"), palette)
    foreground = resolve_color(config.get("foreground", "foreground"), palette)
    accent = resolve_color(config.get("accent", "accent"), palette)
    font_path = font
    if config.get("font"):
        font_path = resolve_font(channel, base, config["font"])
    style = config.get("style", "banner")
    padding = float(config.get("padding", 0.06))
    align = config.get("align", "center")
    position = config.get("position")
    draw = ImageDraw.Draw(image)

    if style == "minimal":
        left, top, right, bottom = round(w * padding), round(h * 0.60), round(w * (1 - padding)), round(h * 0.93)
        tile = text_tile(text, (max(1, right - left), max(1, bottom - top)), foreground, font_path,
                         palette=palette, align=align, line_height=1.05, max_lines=2)
        shadow = Image.new("RGBA", tile.size, color_alpha(background, palette, 0.65))
        shadow.putalpha(tile.getchannel("A").filter(ImageFilter.GaussianBlur(max(2, h * 0.01))))
        image.alpha_composite(shadow, (left + max(2, h // 180), top + max(2, h // 180)))
        image.alpha_composite(tile, (left, top))
        return image.convert("RGB")

    if style == "split":
        panel = round(w * 0.42)
        draw.rectangle((0, 0, panel, h), fill=color_alpha(background, palette, 0.94))
        draw.rectangle((0, 0, max(2, round(w * 0.012)), h), fill=accent)
        left, right = panel + round(w * padding), w - round(w * padding)
        top, bottom = round(h * 0.20), round(h * 0.80)
    elif style == "lower-third":
        left, right = round(w * padding), round(w * (1 - padding))
        top, bottom = round(h * 0.64), round(h * 0.90)
    elif style == "center":
        left, right = round(w * (padding + 0.02)), round(w * (1 - padding - 0.02))
        top, bottom = round(h * 0.28), round(h * 0.68)
    else:
        left, right = round(w * padding), round(w * (1 - padding))
        top, bottom = round(h * 0.08), round(h * 0.33)

    if position == "top":
        top, bottom = round(h * 0.08), round(h * 0.33)
    elif position == "center":
        top, bottom = round(h * 0.28), round(h * 0.68)
    elif position == "bottom":
        top, bottom = round(h * 0.64), round(h * 0.90)

    if style != "split":
        draw.rounded_rectangle((left, top, right, bottom), radius=round(min(w, h) * 0.045),
                               fill=color_alpha(background, palette, 0.96))
    bar_y = top + round((bottom - top) * 0.13)
    draw.rounded_rectangle((round(w * 0.42), bar_y, round(w * 0.58), bar_y + max(3, h // 130)),
                           radius=max(2, h // 260), fill=accent)
    text_top = top + round((bottom - top) * 0.28)
    size_scale = float(config.get("text_size", 1))
    text_height = max(1, round((bottom - text_top - h * 0.02) * size_scale))
    text_in_box(image, (left + round(w * 0.03), text_top, right - round(w * 0.03), text_top + text_height),
                text, foreground, font_path, palette=palette, align=align,
                line_height=1.05, max_lines=2)
    return image.convert("RGB")
