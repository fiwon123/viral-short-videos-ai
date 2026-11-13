"""Data-driven 2D animation, compositing, captions, and channel graphics."""

from functools import lru_cache
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from .camera import resolve_camera
from .core import asset
from .transform import apply as apply_matrix
from .transform import bbox as matrix_bbox
from .transform import camera_matrix, inverse, layer_matrix, multiply, translate


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


def wrapped_text(text, font, width):
    rows = []
    for paragraph in text.split("\n"):
        row = ""
        for word in paragraph.split():
            candidate = f"{row} {word}".strip()
            if row and font.getlength(candidate) > width:
                rows.append(row)
                row = word
            else:
                row = candidate
        rows.append(row)
    return "\n".join(rows)


def text_in_box(image, box, text, fill, font_path=None, max_size=None):
    left, top, right, bottom = box
    width, height = max(1, right - left), max(1, bottom - top)
    draw = ImageDraw.Draw(image)
    low, high = 1, max_size or height
    fitted = None
    while low <= high:
        size = (low + high) // 2
        font = get_font(font_path, size)
        content = wrapped_text(text, font, width)
        spacing = max(1, round(size * 0.14))
        bounds = draw.multiline_textbbox((0, 0), content, font=font, spacing=spacing, align="center")
        x0, y0, x1, y1 = bounds
        if x1 - x0 <= width and y1 - y0 <= height:
            fitted = (font, content, spacing, bounds)
            low = size + 1
        else:
            high = size - 1
    if fitted:
        font, content, spacing, (x0, y0, x1, y1) = fitted
        center = ((left + right - x0 - x1) / 2, (top + bottom - y0 - y1) / 2)
        draw.multiline_text(center, content, font=font, fill=fill, spacing=spacing, align="center")


def resolve_font(channel, base):
    return str(asset(base, channel["font"])) if "font" in channel else None


def make_brand(channel, base, out):
    p = channel["palette"]
    font = resolve_font(channel, base)
    logo = Image.new("RGB", (800, 800), p["background"])
    draw = ImageDraw.Draw(logo)
    draw.ellipse((85, 85, 715, 715), fill=p["secondary"])
    draw.ellipse((118, 118, 682, 682), outline=p["accent"], width=12)
    text_in_box(logo, (185, 210, 615, 570), channel["mark"], p["foreground"], font, 245)
    draw.ellipse((610, 144, 660, 194), fill=p["accent"])
    logo.save(out / "logo.png")

    spec = channel.get("banner", {"width": 2560, "height": 1440, "safe_width": 1500, "safe_height": 380})
    w, h, sw, sh = (spec[k] for k in ("width", "height", "safe_width", "safe_height"))
    banner = Image.new("RGB", (w, h), p["background"])
    draw = ImageDraw.Draw(banner)
    for index in range(9):
        x = index * w // 8
        draw.line((x, 0, x - w // 3, h), fill=p["secondary"], width=max(1, w // 720))
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


def poses(layer):
    state = {"x": layer["x"], "y": layer["y"], "scale": layer.get("scale", 1),
             "rotate": layer.get("rotate", 0), "opacity": layer.get("opacity", 1),
             "visible": layer.get("visible", True)}
    points = [(0, state, "linear")]
    for key in layer.get("keyframes", []):
        state = {name: key.get(name, value) for name, value in state.items()}
        if key["at"] == 0:
            points.pop()
        points.append((key["at"], state, key.get("ease", "linear")))
    return points


def camera_points(shot):
    camera = shot.get("camera")
    if not camera:
        return None
    state = {"x": camera.get("x", 0), "y": camera.get("y", 0),
             "zoom": camera.get("zoom", 1), "rotate": camera.get("rotate", 0)}
    points = [(0, state, "linear")]
    for key in camera.get("keyframes", []):
        state = {name: key.get(name, value) for name, value in state.items()}
        if key["at"] == 0:
            points.pop()
        points.append((key["at"], state, key.get("ease", "linear")))
    return points


def ease(t, mode):
    t = max(0.0, min(1.0, t))
    if mode == "in":
        return t * t
    if mode == "out":
        return 1 - (1 - t) ** 2
    if mode == "smooth":
        return t * t * (3 - 2 * t)
    if mode == "sine":
        return 0.5 - 0.5 * math.cos(math.pi * t)
    if mode == "expo":
        return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)
    if mode == "circ":
        return math.sqrt(max(0.0, 1 - (1 - t) ** 2))
    if mode == "quint":
        return 1 - (1 - t) ** 5
    if mode == "back":
        c1, c3 = 1.70158, 2.70158
        return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
    if mode == "elastic":
        if t in (0.0, 1.0):
            return t
        return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1
    if mode == "bounce":
        n1, d1 = 7.5625, 2.75
        if t < 1 / d1:
            return n1 * t * t
        if t < 2 / d1:
            t -= 1.5 / d1
            return n1 * t * t + 0.75
        if t < 2.5 / d1:
            t -= 2.25 / d1
            return n1 * t * t + 0.9375
        t -= 2.625 / d1
        return n1 * t * t + 0.984375
    if mode == "spring":
        return 1 - math.exp(-6 * t) * math.cos(9 * t)
    if mode == "hold":
        return 0.0 if t < 1 else 1.0
    return t


def pose_at(points, progress):
    for (a, start, _), (b, end, mode) in zip(points, points[1:]):
        if progress <= b:
            t = ease((progress - a) / (b - a) if b > a else 1, mode)
            return {
                name: (end[name] if progress >= b else value) if isinstance(value, bool)
                else value + (end[name] - value) * t
                for name, value in start.items()
            }
    return points[-1][1]


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


def apply_post(image, config, *, seed=0):
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
        value = tint.lstrip("#")
        color = np.array([int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)
        data = np.clip(data * 0.88 + color * 0.12, 0, 1)
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
    def __init__(self, shot, canvas, channel, font, base, *, episode_post=None, motion_blur=0):
        self.canvas = canvas
        palette = channel["palette"]
        self.background = shot.get("background", palette["background"])
        self.post = _merge(channel.get("post"), episode_post, shot.get("post"))
        self.motion_blur = shot.get("motion_blur", motion_blur)
        self.camera_points = camera_points({**shot, "camera": resolve_camera(shot)}) if shot.get("camera") else None
        layers = sorted(layer_order(shot["layers"]), key=lambda item: item.get("plane") != "background")
        self.layers = [{
            "id": layer["id"],
            "tile": sprite(layer, canvas, palette, font, base),
            "points": poses(layer),
            "mouth_for": layer.get("mouth_for"),
            "parent": layer.get("parent"),
            "variant_group": layer.get("variant_group"),
            "pivot": layer.get("pivot", [0.5, 0.5]),
            "blend": layer.get("blend", "normal"),
            "blur": layer.get("blur", 0),
            "parallax": layer.get("parallax", 1),
            "plane": layer.get("plane", "foreground"),
        } for layer in layers]

    def frame(self, progress, speaking, hidden=(), *, post=True, seed=0):
        width, height = self.canvas
        image = Image.new("RGBA", self.canvas, self.background)
        camera = pose_at(self.camera_points, progress) if self.camera_points else None
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
            if layer["parent"] and not states[layer["parent"]]["visible"]:
                state["visible"] = False
        matrices, alphas, origins = {}, {}, {}
        for layer in self.layers:
            state = states[layer["id"]]
            if layer["id"] in hidden_ids or not state["visible"]:
                continue
            parent_matrix = matrices.get(layer["parent"])
            parent_alpha = alphas.get(layer["parent"], 1.0)
            alpha = state["opacity"] * parent_alpha
            tile = layer["tile"]
            if layer["mouth_for"]:
                level = speaking.get(layer["mouth_for"], 0) if speaking else 0
                mouth = 0.18 + 0.82 * level
                if mouth < 0.999:
                    tile = tile.resize((tile.width, max(1, round(tile.height * mouth))),
                                       Image.Resampling.BILINEAR)
            if layer["blur"]:
                tile = tile.filter(ImageFilter.GaussianBlur(max(0.5, min(width, height) * layer["blur"] * 0.02)))
            matrix = layer_matrix(state, width, height, layer["pivot"], parent=parent_matrix,
                                  parent_origin=origins.get(layer["parent"]),
                                  camera=camera, parallax=layer["parallax"],
                                  box=(tile.width, tile.height))
            matrices[layer["id"]], alphas[layer["id"]] = matrix, alpha
            origins[layer["id"]] = (float(layer["pivot"][0]) * tile.width,
                                    float(layer["pivot"][1]) * tile.height)
            if alpha <= 0:
                continue
            placed, left, top = _transformed(tile, matrix)
            if alpha < 1:
                placed = placed.copy()
                placed.putalpha(placed.getchannel("A").point(lambda value: round(value * alpha)))
            if layer["blend"] == "normal":
                image = Image.alpha_composite(image, placed) if placed.size == image.size else _paste(image, placed, left, top)
            else:
                image = _blend_at(image, placed, left, top, layer["blend"])
        if post:
            image = apply_post(image, self.post, seed=seed)
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


def sprite(layer, canvas, palette, font, base):
    cw, ch = canvas
    w = max(1, round(layer.get("width", 0.55) * cw))
    h = max(1, round(layer.get("height", 0.2) * ch))
    fill = layer.get("fill", "foreground")
    fill = palette.get(fill, fill)
    kind = layer["kind"]
    if kind == "image":
        with Image.open(asset(base, layer["file"])) as source:
            return ImageOps.contain(ImageOps.exif_transpose(source).convert("RGBA"), (w, h))
    tile = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(tile)
    bounds = (0, 0, w - 1, h - 1)
    if kind == "text":
        text_in_box(tile, (0, 0, w, h), layer["text"], fill, font)
    elif kind == "ellipse":
        draw.ellipse(bounds, fill=fill)
    elif kind == "polygon":
        draw.polygon([(round(x * (w - 1)), round(y * (h - 1))) for x, y in layer["points"]], fill=fill)
    else:
        draw.rounded_rectangle(bounds, radius=round(min(w, h) * layer.get("radius", 0) / 2), fill=fill)
    return tile


def transition_frame(previous, current, mode, progress, ease_mode="smooth"):
    t = ease(progress, ease_mode)
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
    max_width = width * 0.82
    size = max(12, round(min(width, height) * 0.058 * float(config.get("font_size", 1))))
    draw = ImageDraw.Draw(image)
    font, rows = get_font(font_path, size), []
    # Shrink rather than clip when a long line or a narrow phone needs it.
    for _ in range(8):
        font = get_font(font_path, size)
        lines, row = [], []
        for word in text.split():
            candidate = " ".join([*row, word])
            if row and (len(row) >= max_words or draw.textlength(candidate, font=font) > max_width):
                lines.append(" ".join(row))
                row = [word]
            else:
                row.append(word)
        if row:
            lines.append(" ".join(row))
        rows, y = [], 0
        for line in lines:
            line_width = draw.textlength(line, font=font)
            row_words, x = [], (width - line_width) / 2
            for word in line.split():
                word_width = draw.textlength(word + " ", font=font)
                box = draw.textbbox((x, y), word, font=font)
                row_words.append({"text": word, "box": box})
                x += word_width
            rows.append(row_words)
            y += font.size + round(font.size * 0.22)
        if lines and all(draw.textlength(line, font=font) <= max_width for line in lines) and len(lines) <= 5:
            break
        size = max(12, round(size * 0.9))
    return font, rows, size


def draw_caption(image, cue, channel, font, config=None, frame=None):
    if isinstance(cue, str):
        cue = {"text": cue}
    config = config or {}
    text = cue.get("text", "")
    if config.get("uppercase"):
        text = text.upper()
    style = config.get("style", "box")
    position = config.get("position", "bottom")
    font_obj, rows, size = caption_layout(image, text, font, config)
    width, height = image.size
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    foreground = config.get("foreground", channel["palette"]["foreground"])
    background = config.get("background", channel["palette"]["background"])
    highlight = config.get("highlight", channel["palette"]["accent"])
    top = rows[0][0]["box"][1] if rows else 0
    bottom = rows[-1][0]["box"][3] if rows else 0
    if position == "top":
        offset = round(height * 0.09) - top
    elif position == "center":
        offset = round(height * 0.46) - top
    else:
        offset = round(height * 0.80) - top
    radius = max(2, round(size * float(config.get("radius", 0.45))))
    if style in {"box", "karaoke"}:
        pad_x, pad_y = round(size * 0.65), round(size * 0.45)
        left = round(width / 2 - width * 0.43) - pad_x
        right = round(width / 2 + width * 0.43) + pad_x
        box = (left, offset + top - pad_y, right, offset + bottom + pad_y)
        draw.rounded_rectangle(box, radius=radius, fill=background)
    outline = max(0, round(size * float(config.get("stroke", 0))))
    shadow = bool(config.get("shadow", False))

    def write(word, x, y, fill):
        if shadow:
            draw.text((x + size * 0.05, y + size * 0.07), word, font=font_obj,
                      fill=(0, 0, 0, 120), stroke_width=outline, stroke_fill=(0, 0, 0, 90))
        draw.text((x, y), word, font=font_obj, fill=fill,
                  stroke_width=outline, stroke_fill=background if outline else fill)

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
                    draw.rounded_rectangle((box[0] - size * 0.18, box[1] - size * 0.13,
                                            box[2] + size * 0.18, box[3] + size * 0.19),
                                           radius=max(2, round(size * 0.25)), fill=highlight)
                write(word["text"], box[0], box[1], background if index == active else foreground)
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
        elif animation == "slide":
            shifted = Image.new("RGBA", image.size, (0, 0, 0, 0))
            shifted.alpha_composite(layer, (0, round((1 - t) * height * 0.035)))
            layer = shifted
    image.paste(layer, (0, 0), layer)


def thumbnail(frame, text, channel, font):
    image = frame.copy()
    w, h = image.size
    p = channel["palette"]
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = round(w * 0.06), round(h * 0.08), round(w * 0.94), round(h * 0.33)
    draw.rounded_rectangle((left, top, right, bottom), radius=round(min(w, h) * 0.045), fill=p["background"])
    y = top + round((bottom - top) * 0.13)
    draw.rounded_rectangle((round(w * 0.42), y, round(w * 0.58), y + max(3, h // 130)),
                           radius=max(2, h // 260), fill=p["accent"])
    text_in_box(image, (left + w // 20, top + (bottom - top) // 4, right - w // 20, bottom - h // 50),
                text, p["foreground"], font)
    return image
