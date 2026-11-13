"""Expand a static text layer into timed word, line or character pieces.

Reveal is an authoring convenience: the renderer only sees ordinary text
layers with visibility keys, so Python and the browser stay identical.
"""

import copy

from .design import _fit_text, _tracked_length, resolve_font


def _clamp(value):
    return max(0.0, min(1.0, value))


def _pieces(text, font, tracking):
    """Characters and their advance widths, with spaces as advances."""
    return [(character, font.getlength(character) + tracking * font.size)
            for character in text]


def _piece(original, piece_id, text, x, y, width, height, at, opacity, fade):
    layer = copy.deepcopy(original)
    layer.pop("reveal", None)
    layer.pop("keyframes", None)
    layer["id"] = piece_id
    layer["text"] = text
    layer["x"], layer["y"] = x, y
    layer["width"], layer["height"] = max(0.0001, width), max(0.0001, height)
    layer["align"] = "center"
    layer["line_height"] = 1.0
    layer["letter_spacing"] = 0
    layer["max_lines"] = 1
    layer["uppercase"] = False
    layer["visible"] = False
    if fade:
        if at <= 0:
            keys = [{"at": 0, "visible": True, "opacity": 0},
                    {"at": 0.08, "opacity": opacity, "ease": "smooth"}]
        elif at >= 1:
            keys = [{"at": 0, "visible": False, "opacity": 0},
                    {"at": 1, "visible": True, "opacity": opacity}]
        else:
            keys = [{"at": 0, "visible": False, "opacity": 0},
                    {"at": at, "visible": True, "opacity": 0, "ease": "smooth"},
                    {"at": min(1.0, at + 0.08), "opacity": opacity, "ease": "smooth"}]
    else:
        keys = [{"at": 0, "visible": False}]
        if at > 0:
            keys.append({"at": at, "visible": True})
        else:
            keys = [{"at": 0, "visible": True}]
    layer["keyframes"] = keys
    return layer


def expand(episode, channel, channel_dir):
    width, height = episode["width"], episode["height"]
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            layers = []
            for layer in shot.get("layers", []):
                reveal = layer.get("reveal")
                if not reveal:
                    layers.append(layer)
                    continue
                if layer.get("kind") != "text":
                    raise ValueError(f"Reveal only supports text layers: {layer['id']}")
                if layer.get("parent") or layer.get("keyframes"):
                    raise ValueError(f"Reveal needs a static, unparented text layer: {layer['id']}")
                if any(float(layer.get(key, 0)) for key in ("rotate", "skew_x", "skew_y")):
                    raise ValueError(f"Reveal needs an unrotated text layer: {layer['id']}")
                if float(layer.get("scale", 1)) != 1 or float(layer.get("scale_x", 1)) != 1 \
                        or float(layer.get("scale_y", 1)) != 1:
                    raise ValueError(f"Reveal needs an unscaled text layer: {layer['id']}")
                text = layer["text"]
                uppercase = bool(layer.get("uppercase", False))
                content = text.upper() if uppercase else text
                font_path = resolve_font(channel, channel_dir, layer.get("font"))
                box_width = max(1, round(layer.get("width", 0.55) * width))
                box_height = max(1, round(layer.get("height", 0.2) * height))
                stroke = layer.get("stroke") or {}
                padding = 0.07 if (layer.get("shadow") or layer.get("glow") or stroke) else 0.0
                inset_x = round(box_width * padding)
                inset_y = round(box_height * padding)
                inner_width = max(1, box_width - inset_x * 2)
                inner_height = max(1, box_height - inset_y * 2)
                line_height = float(layer.get("line_height", 1.14))
                tracking = float(layer.get("letter_spacing", 0))
                font, lines, spacing, _ = _fit_text(
                    content, inner_width, inner_height, font_path, inner_height,
                    line_height=line_height, tracking=tracking,
                    max_lines=layer.get("max_lines"), uppercase=False,
                )
                total = len(lines) * font.size + (len(lines) - 1) * spacing
                left = layer["x"] * width - box_width / 2
                top = layer["y"] * height - box_height / 2
                y0 = top + inset_y + (inner_height - total) / 2
                align = layer.get("align", "center")
                mode = reveal["mode"]
                start = float(reveal.get("start", 0))
                stagger = float(reveal.get("stagger", 0.04))
                fade = bool(reveal.get("fade", True))
                opacity = float(layer.get("opacity", 1))
                index = 0
                layout = []
                for line_index, line in enumerate(lines):
                    line_width = _tracked_length(line, font, tracking)
                    if align == "left":
                        x0 = left + inset_x
                    elif align == "right":
                        x0 = left + box_width - inset_x - line_width
                    else:
                        x0 = left + inset_x + (inner_width - line_width) / 2
                    y = y0 + line_index * (font.size + spacing)
                    if mode == "line":
                        layout.append((line, x0, y, line_width))
                    elif mode == "word":
                        cursor = x0
                        for word in line.split(" "):
                            word_width = _tracked_length(word, font, tracking)
                            if word:
                                layout.append((word, cursor, y, word_width))
                            cursor += word_width + _tracked_length(" ", font, tracking)
                    else:
                        cursor = x0
                        for character, advance in _pieces(line, font, tracking):
                            if character.strip():
                                layout.append((character, cursor, y, advance))
                            cursor += advance
                for text_piece, px, py, piece_width in layout:
                    at = _clamp(start + index * stagger)
                    layers.append(_piece(
                        layer, f"{layer['id']}-reveal-{index}", text_piece,
                        (px + piece_width / 2) / width, (py + font.size / 2) / height,
                        piece_width / width, font.size / height, at, opacity, fade,
                    ))
                    index += 1
            shot["layers"] = layers
    return episode
