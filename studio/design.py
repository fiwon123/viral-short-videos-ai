"""Data-driven 2D animation and channel publishing graphics."""

from functools import lru_cache
import math

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .core import asset


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
             "rotate": layer.get("rotate", 0), "opacity": layer.get("opacity", 1)}
    points = [(0, state, "linear")]
    for key in layer.get("keyframes", []):
        state = {name: key.get(name, value) for name, value in state.items()}
        if key["at"] == 0:
            points.pop()
        points.append((key["at"], state, key.get("ease", "linear")))
    return points


def ease(t, mode):
    if mode == "in":
        return t * t
    if mode == "out":
        return 1 - (1 - t) ** 2
    if mode == "smooth":
        return t * t * (3 - 2 * t)
    return t


def pose_at(points, progress):
    for (a, start, _), (b, end, mode) in zip(points, points[1:]):
        if progress <= b:
            t = ease((progress - a) / (b - a), mode)
            return {name: value + (end[name] - value) * t for name, value in start.items()}
    return points[-1][1]


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


class Composition:
    def __init__(self, shot, canvas, channel, font, base):
        self.canvas = canvas
        palette = channel["palette"]
        self.background = shot.get("background", palette["background"])
        self.layers = [(layer["id"], sprite(layer, canvas, palette, font, base), poses(layer), layer.get("mouth_for"))
                       for layer in shot["layers"]]

    def frame(self, progress, speaking, hidden=()):
        image = Image.new("RGB", self.canvas, self.background)
        cw, ch = self.canvas
        for layer_id, tile, points, mouth_for in self.layers:
            if layer_id in hidden:
                continue
            state = pose_at(points, progress)
            alpha = state["opacity"]
            if alpha <= 0:
                continue
            scale = state["scale"]
            mouth = 0.18 + 0.82 * speaking.get(mouth_for, 0) if mouth_for else 1
            size = max(1, round(tile.width * scale)), max(1, round(tile.height * scale * mouth))
            layer = tile if size == tile.size else tile.resize(size, Image.Resampling.BILINEAR)
            if state["rotate"]:
                layer = layer.rotate(state["rotate"], resample=Image.Resampling.BICUBIC, expand=True)
            if alpha < 1:
                layer = layer.copy()
                layer.putalpha(layer.getchannel("A").point(lambda value: round(value * alpha)))
            x = round(state["x"] * cw - layer.width / 2)
            y = round(state["y"] * ch - layer.height / 2)
            image.paste(layer, (x, y), layer)
        return image


def transition_frame(previous, current, mode, progress):
    if mode == "dissolve":
        return Image.blend(previous, current, ease(progress, "smooth"))
    split = math.floor(current.width * progress)
    image = previous.copy()
    image.paste(current.crop((0, 0, split, current.height)), (0, 0))
    return image


def draw_caption(image, text, channel, font):
    w, h = image.size
    rows = wrapped_text(text, get_font(font, max(14, round(min(w, h) * 0.056))), w * 0.8).count("\n") + 1
    height = min(round(h * 0.27), max(round(h * 0.065), round(min(w, h) * 0.067 * rows + h * 0.023)))
    left, bottom, right = round(w * 0.06), round(h * 0.88), round(w * 0.94)
    ImageDraw.Draw(image).rounded_rectangle((left, bottom - height, right, bottom),
                                            radius=max(2, height // 5), fill=channel["palette"]["background"])
    inset = max(2, height // 10)
    text_in_box(image, (left + inset, bottom - height + inset, right - inset, bottom - inset),
                text, channel["palette"]["foreground"], font, max(14, round(min(w, h) * 0.056)))


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
