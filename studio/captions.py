"""Kinetic short-form captions: short pages, per-word motion, emphasis.

The ``kinetic`` caption style breaks each spoken cue into pages of 1–3 words,
reveals words as they are spoken, bumps the active word, and gives emphasised
words an accent colour, a larger size and a short shake. Mark emphasis with
``*word*`` in the caption text or list keywords in ``captions.emphasis``.

Layout and sprites live here. The per-frame motion maths is ``word_state``,
mirrored line for line by ``wordState`` in ``browser/captions.mjs`` so the
Python and browser renderers agree.
"""

from functools import lru_cache
import json
import math
import re

from PIL import Image, ImageDraw, ImageFilter

PRESETS = {
    "hormozi-pop": {"words_per_page": 3, "word_in": "pop", "active": "color+scale", "uppercase": True,
                    "font_size": 1.0, "stroke": 0.16, "shadow": 0.6, "position": "center", "offset": 0.12},
    "clean-karaoke": {"words_per_page": 4, "word_in": "fade", "active": "pill", "reveal": "page",
                      "font_size": 0.8, "stroke": 0.0, "shadow": 0.4, "position": "bottom"},
    "kinetic-big": {"words_per_page": 2, "word_in": "bounce", "active": "scale", "uppercase": True,
                    "font_size": 1.25, "stroke": 0.18, "shadow": 0.7, "position": "center", "offset": 0.05},
    "documentary-lower": {"words_per_page": 5, "word_in": "slide", "active": "color", "reveal": "page",
                          "font_size": 0.62, "stroke": 0.0, "shadow": 0.5, "position": "bottom",
                          "offset": 0.04, "uppercase": False},
    "typewriter": {"words_per_page": 4, "word_in": "typewriter", "active": "color", "font_size": 0.8,
                   "stroke": 0.12, "shadow": 0.5, "position": "bottom"},
}

DEFAULTS = {"words_per_page": 3, "word_in": "pop", "active": "color+scale", "reveal": "page",
            "font_size": 1.0, "stroke": 0.14, "shadow": 0.55, "position": "center", "offset": 0.12,
            "foreground": "#FFFFFF", "outline": "#0B0B12", "highlight": "accent",
            "highlight_text": "#0B0B12", "emphasis_color": "accent", "emphasis_scale": 1.22,
            "active_scale": 1.1, "max_width": 0.84, "uppercase": True, "wave": 0.0}

_MARK = re.compile(r"^\*(.+)\*([.,!?;:]*)$")


def settings(config):
    """Merge preset → defaults → explicit caption config."""
    config = dict(config or {})
    preset = PRESETS.get(config.get("preset"), {})
    merged = {**DEFAULTS, **preset, **{k: v for k, v in config.items() if k != "style"}}
    if "uppercase" not in config and "uppercase" in preset:
        merged["uppercase"] = preset["uppercase"]
    if isinstance(merged["shadow"], bool):
        merged["shadow"] = DEFAULTS["shadow"] if merged["shadow"] else 0.0
    if merged["active"] == "none":
        merged["active"] = ""
    if merged["word_in"] == "typewriter":
        merged["word_in"] = "none"
    return merged


def clean(text):
    """Remove emphasis markers for display, SRT and speech."""
    return re.sub(r"\*([^*\s][^*]*?)\*", r"\1", text)


def split_word(raw, keywords):
    match = _MARK.match(raw)
    if match:
        return match.group(1) + match.group(2), True
    bare = re.sub(r"[^\w']", "", raw.lower())
    return raw, bool(bare and bare in keywords)


def pages(cue, config):
    """Group a cue's timed words into short pages that break at punctuation."""
    config = settings(config)
    limit = max(1, int(config["words_per_page"]))
    keywords = {str(word).lower() for word in config.get("emphasis", [])}
    words = cue.get("words") or [{"text": word, "start": cue["start"], "end": cue["end"]}
                                 for word in cue.get("text", "").split()]
    items = []
    for word in words:
        text, emphasis = split_word(word["text"], keywords)
        if config.get("uppercase"):
            text = text.upper()
        items.append({"text": text, "start": int(word["start"]), "end": int(word["end"]),
                      "emphasis": emphasis})
    groups, current = [], []
    for index, item in enumerate(items):
        current.append(item)
        remaining = len(items) - index - 1
        boundary = item["text"][-1:] in ".!?;:," and remaining != 1
        if len(current) >= limit or boundary:
            # Never leave a lone trailing word: pull it into this page instead.
            if remaining == 1 and len(current) < limit + 1:
                continue
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    result = []
    for index, group in enumerate(groups):
        start = group[0]["start"]
        end = groups[index + 1][0]["start"] if index + 1 < len(groups) else cue["end"]
        result.append({"start": start, "end": max(start + 1, end), "words": group})
    return result


def _ease_back(t):
    c1 = 1.70158
    return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _ease_out(t):
    return 1 - (1 - t) ** 3


def _ease_bounce(t):
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


def word_state(word, index, page, frame, fps, size, config):
    """Per-frame transform for one word. Mirrors ``wordState`` in captions.mjs."""
    appear = page["start"] if config["reveal"] == "page" else word["start"]
    if frame < appear:
        return None
    t = min(1.0, max(0.0, (frame - appear) / max(1.0, 0.13 * fps)))
    scale, dx, dy, rotate, alpha = 1.0, 0.0, 0.0, 0.0, 1.0
    mode = config["word_in"]
    if mode == "pop":
        scale, alpha = 0.55 + 0.45 * _ease_back(t), min(1.0, t * 3)
    elif mode == "bounce":
        scale, alpha = 0.3 + 0.7 * _ease_bounce(t), min(1.0, t * 4)
    elif mode == "slide":
        dy, alpha = (1 - _ease_out(t)) * size * 0.45, t
    elif mode == "fade":
        alpha = _ease_out(t)
    active = word["start"] <= frame < word["end"]
    emphasis = word.get("emphasis", False)
    if active and "scale" in config["active"]:
        rise = min(1.0, (frame - word["start"]) / max(1.0, 0.06 * fps))
        scale *= 1 + (float(config["active_scale"]) - 1) * _ease_out(rise)
    if emphasis:
        scale *= float(config["emphasis_scale"])
        since = (frame - word["start"]) / fps
        if 0 <= since < 0.35:
            decay = 1 - since / 0.35
            rotate = math.sin(since * 55) * 5 * decay
            dx = math.sin(since * 70 + 1.3) * size * 0.04 * decay
    if config.get("wave"):
        dy += math.sin(frame / fps * 2 * math.pi * 1.1 + index * 0.9) * size * 0.05 * float(config["wave"])
    tinted = "color" in config["active"] or "pill" in config["active"]
    state = "emphasis" if emphasis else ("active" if active and tinted else "normal")
    return {"scale": scale, "dx": dx, "dy": dy, "rotate": rotate, "alpha": alpha, "state": state}


def _font(path, size):
    from .design import get_font
    return get_font(path, size)


def layout(page, canvas, font_path, config):
    """Word centres for a page, wrapped to the safe width and positioned on screen."""
    from .design import _tracked_length
    width, height = canvas
    size = max(14, round(min(width, height) * 0.085 * float(config["font_size"])))
    max_width = width * float(config["max_width"])
    tracking = float(config.get("letter_spacing", 0))
    for _ in range(12):
        font = _font(font_path, size)
        space = font.getlength(" ") + size * 0.08
        rows, row, row_width = [], [], 0.0
        for word in page["words"]:
            # Reserve room for the emphasis scale so big words never clip.
            grow = float(config["emphasis_scale"]) if word["emphasis"] else 1.0
            w = _tracked_length(word["text"], font, tracking) * grow
            if row and row_width + space + w > max_width:
                rows.append((row, row_width))
                row, row_width = [], 0.0
            row_width += (space if row else 0) + w
            row.append((word, w))
        if row:
            rows.append((row, row_width))
        if all(w <= max_width for _, w in rows) and len(rows) <= 3:
            break
        size = round(size * 0.9)
    line = size * 1.3
    base = {"top": 0.13, "center": 0.5, "bottom": 0.76}.get(config["position"], 0.5)
    centre_y = height * (base + float(config.get("offset", 0)))
    top = centre_y - line * len(rows) / 2
    placed = []
    for row_index, (row, row_width) in enumerate(rows):
        x = (width - row_width) / 2
        y = top + line * (row_index + 0.5)
        for word, w in row:
            placed.append({"cx": x + w / 2, "cy": y})
            x += w + space
    return placed, size


@lru_cache(maxsize=512)
def _sprite(text, font_path, size, state, style_key):
    style = json.loads(style_key)
    font = _font(font_path, size)
    stroke = max(0, round(size * float(style["stroke"])))
    left, top, right, bottom = font.getbbox(text, stroke_width=stroke)
    pad = round(size * 0.35) + stroke
    w, h = right - left + pad * 2, bottom - top + pad * 2
    image = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(image)
    origin = (pad - left, pad - top)
    fill = {"normal": style["foreground"], "active": style["highlight"],
            "emphasis": style["emphasis_color"]}[state]
    text_fill = fill
    if state == "active" and "pill" in style["active"]:
        draw.rounded_rectangle((pad * 0.55, pad * 0.6, w - pad * 0.55, h - pad * 0.6),
                               radius=round(size * 0.22), fill=style["highlight"])
        text_fill = style["highlight_text"]
    if float(style["shadow"]) > 0:
        shadow = Image.new("RGBA", (w, h))
        ImageDraw.Draw(shadow).text((origin[0] + size * 0.04, origin[1] + size * 0.08), text, font=font,
                                    fill=(0, 0, 0, round(255 * float(style["shadow"]))),
                                    stroke_width=stroke, stroke_fill=(0, 0, 0, round(255 * float(style["shadow"]))))
        shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.06))
        image = Image.alpha_composite(shadow, image)
        draw = ImageDraw.Draw(image)
    draw.text(origin, text, font=font, fill=text_fill, stroke_width=stroke,
              stroke_fill=style["outline"] if stroke else text_fill)
    return image


def style_key(config, palette):
    from .design import resolve_color
    keys = ("foreground", "outline", "highlight", "highlight_text", "emphasis_color")
    style = {key: resolve_color(config[key], palette, config[key]) for key in keys}
    style.update({key: config[key] for key in ("stroke", "shadow", "active")})
    return json.dumps(style, sort_keys=True)


def word_sprite(text, font_path, size, state, config, palette):
    return _sprite(text, font_path, size, state, style_key(config, palette))


def draw_kinetic(image, cue, channel, font_path, config, frame, fps):
    """Composite the kinetic caption page that is live at ``frame``."""
    config = settings(config)
    palette = (channel or {}).get("palette", {})
    page = next((item for item in pages(cue, config) if item["start"] <= frame < item["end"]), None)
    if page is None:
        return
    placed, size = layout(page, image.size, font_path, config)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    for index, (word, spot) in enumerate(zip(page["words"], placed)):
        state = word_state(word, index, page, frame, fps, size, config)
        if not state or state["alpha"] <= 0.01:
            continue
        sprite = word_sprite(word["text"], font_path, size, state["state"], config, palette)
        if abs(state["scale"] - 1) > 1e-3:
            sprite = sprite.resize((max(1, round(sprite.width * state["scale"])),
                                    max(1, round(sprite.height * state["scale"]))), Image.Resampling.BICUBIC)
        if abs(state["rotate"]) > 0.05:
            sprite = sprite.rotate(-state["rotate"], resample=Image.Resampling.BICUBIC, expand=True)
        if state["alpha"] < 0.999:
            sprite = sprite.copy()
            sprite.putalpha(sprite.getchannel("A").point(lambda value, a=state["alpha"]: round(value * a)))
        x = round(spot["cx"] + state["dx"] - sprite.width / 2)
        y = round(spot["cy"] + state["dy"] - sprite.height / 2)
        layer.alpha_composite(sprite, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))
    image.paste(layer, (0, 0), layer)
