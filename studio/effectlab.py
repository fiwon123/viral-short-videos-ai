"""Generate a palette-matched SVG effect from a small JSON recipe.

    python -m studio.effectlab workspace/my-channel/channel \\
        --recipe vfx/custom-ring.json

The recipe chooses a base shape and a few parameters. The output is a static,
self-contained SVG, so it can be referenced directly by a layer.
"""

import argparse
import json
import math
from pathlib import Path
import random


DEFAULT = {
    "background": "#131B30",
    "foreground": "#FFF3D8",
    "accent": "#FFBD54",
    "secondary": "#293F59",
}


def _color(value, palette):
    if not value:
        return palette["accent"]
    return palette.get(value, value)


def _ring(recipe, palette, seed):
    rings = int(recipe.get("rings", 3))
    color = _color(recipe.get("color"), palette)
    second = _color(recipe.get("secondary"), palette)
    parts = []
    for index in range(rings):
        radius = 46 - index * (38 / max(1, rings))
        width = max(0.8, 3.4 - index * 0.7)
        color_value = color if index % 2 == 0 else second
        parts.append(f'<circle cx="50" cy="50" r="{radius:.2f}" fill="none" '
                     f'stroke="{color_value}" stroke-width="{width:.2f}" opacity="{0.95 - index * 0.18:.2f}"/>')
    return "".join(parts)


def _burst(recipe, palette, seed):
    random.seed(seed)
    count = int(recipe.get("points", 14))
    outer = float(recipe.get("outer", 47))
    inner = float(recipe.get("inner", 12))
    color = _color(recipe.get("color"), palette)
    parts = []
    for index in range(count):
        angle = index / count * math.tau
        jitter = random.uniform(0.78, 1.0)
        x, y = 50 + math.cos(angle) * outer * jitter, 50 + math.sin(angle) * outer * jitter
        x2, y2 = 50 + math.cos(angle + 0.08) * inner, 50 + math.sin(angle + 0.08) * inner
        parts.append(f'<path d="M50 50 L{x:.2f} {y:.2f} L{x2:.2f} {y2:.2f} Z" fill="{color}" opacity="{random.uniform(0.55, 0.95):.2f}"/>')
    return "".join(parts)


def _glow(recipe, palette, seed):
    color = _color(recipe.get("color"), palette)
    return (f'<defs><radialGradient id="glow"><stop offset="0" stop-color="{color}" stop-opacity=".95"/>'
            f'<stop offset=".42" stop-color="{color}" stop-opacity=".45"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient></defs>'
            '<circle cx="50" cy="50" r="48" fill="url(#glow)"/>')


def _light_leak(recipe, palette, seed):
    color = _color(recipe.get("color"), palette)
    second = _color(recipe.get("secondary"), palette)
    return (f'<defs><radialGradient id="leak" cx="{recipe.get("cx", 30)}%" cy="{recipe.get("cy", 40)}%" r="72%">'
            f'<stop offset="0" stop-color="{color}" stop-opacity=".85"/>'
            f'<stop offset=".48" stop-color="{second}" stop-opacity=".32"/>'
            f'<stop offset="1" stop-color="{second}" stop-opacity="0"/></radialGradient></defs>'
            '<rect width="100" height="100" fill="url(#leak)"/>')


def _dust(recipe, palette, seed):
    random.seed(seed)
    color = _color(recipe.get("color"), palette)
    second = _color(recipe.get("secondary"), palette)
    parts = []
    for index in range(int(recipe.get("puffs", 6))):
        cx = random.uniform(18, 82)
        cy = random.uniform(34, 74)
        rx = random.uniform(10, 30)
        ry = random.uniform(7, 20)
        parts.append(f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" '
                     f'fill="{color if index % 2 == 0 else second}" opacity="{random.uniform(0.25, 0.7):.2f}"/>')
    return "".join(parts)


def _speed_lines(recipe, palette, seed):
    random.seed(seed)
    color = _color(recipe.get("color"), palette)
    parts = []
    for index in range(int(recipe.get("lines", 8))):
        y = 12 + index * (76 / max(1, int(recipe.get("lines", 8))))
        length = random.uniform(20, 72)
        parts.append(f'<path d="M{random.uniform(0, 18):.2f} {y:.2f} H{length + 18:.2f}" '
                     f'stroke="{color}" stroke-width="{random.uniform(0.8, 2.6):.2f}" '
                     f'opacity="{random.uniform(0.35, 0.85):.2f}" stroke-linecap="round"/>')
    return "".join(parts)


def _stars(recipe, palette, seed):
    random.seed(seed)
    color = _color(recipe.get("color"), palette)
    parts = []
    for index in range(int(recipe.get("count", 7))):
        cx, cy = random.uniform(12, 88), random.uniform(12, 88)
        size = random.uniform(3, 9)
        parts.append(f'<path d="M{cx:.2f} {cy - size:.2f} L{cx + size * .25:.2f} {cy - size * .25:.2f} '
                     f'L{cx + size:.2f} {cy:.2f} L{cx + size * .25:.2f} {cy + size * .25:.2f} '
                     f'L{cx:.2f} {cy + size:.2f} L{cx - size * .25:.2f} {cy + size * .25:.2f} '
                     f'L{cx - size:.2f} {cy:.2f} L{cx - size * .25:.2f} {cy - size * .25:.2f} Z" '
                     f'fill="{color}" opacity="{random.uniform(0.45, 0.95):.2f}"/>')
    return "".join(parts)


def _confetti(recipe, palette, seed):
    random.seed(seed)
    colors = [_color(value, palette) for value in recipe.get("colors", ["accent", "foreground", "secondary"])]
    parts = []
    for index in range(int(recipe.get("count", 16))):
        cx, cy = random.uniform(8, 92), random.uniform(8, 92)
        width, height = random.uniform(2, 6), random.uniform(5, 12)
        angle = random.uniform(0, 180)
        parts.append(f'<rect x="{cx:.2f}" y="{cy:.2f}" width="{width:.2f}" height="{height:.2f}" '
                     f'rx="1" fill="{random.choice(colors)}" transform="rotate({angle:.1f} {cx:.2f} {cy:.2f})" '
                     f'opacity="{random.uniform(0.55, 0.95):.2f}"/>')
    return "".join(parts)


def _slash(recipe, palette, seed):
    color = _color(recipe.get("color"), palette)
    second = _color(recipe.get("secondary"), palette)
    return (f'<path d="M8 86 L92 14" stroke="{color}" stroke-width="{recipe.get("width", 6)}" '
            f'stroke-linecap="round" opacity=".92"/>'
            f'<path d="M18 94 L96 30" stroke="{second}" stroke-width="2.4" '
            f'stroke-linecap="round" opacity=".72"/>')


BASE = {
    "ring": _ring, "burst": _burst, "glow": _glow, "light-leak": _light_leak,
    "dust": _dust, "speed-lines": _speed_lines, "stars": _stars,
    "confetti": _confetti, "slash": _slash,
}


def build(channel, recipe_path, *, folder="vfx"):
    channel = Path(channel).resolve()
    recipe_file = Path(recipe_path)
    if not recipe_file.is_absolute():
        candidates = [channel / recipe_file, Path(__file__).resolve().parents[1] / recipe_file,
                      Path(__file__).resolve().parents[1] / "presets" / recipe_file]
        recipe_file = next((path.resolve() for path in candidates if path.is_file()),
                           (channel / recipe_file).resolve())
    recipe = json.loads(recipe_file.read_text(encoding="utf-8"))
    effect_id = recipe.get("id")
    base = recipe.get("base", "ring")
    if not effect_id:
        raise ValueError("Effect Lab recipe needs an id")
    if base not in BASE:
        raise ValueError(f"Unknown Effect Lab base: {base}. Available: {', '.join(sorted(BASE))}")
    manifest = channel / "channel.json"
    data = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    palette = {**DEFAULT, **(data.get("palette") or {})}
    target = (channel / folder).resolve()
    if not target.is_relative_to(channel):
        raise ValueError("The VFX folder must live inside the channel folder")
    target.mkdir(parents=True, exist_ok=True)
    count = int(recipe.get("variants", 1))
    files = []
    for index in range(1, count + 1):
        body = BASE[base](recipe, palette, int(recipe.get("seed", 7)) + index * 13)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
               f'{body}</svg>\n')
        name = f"{effect_id}{'' if count == 1 else '-' + str(index)}.svg"
        (target / name).write_text(svg, encoding="utf-8")
        files.append(f"{folder}/{name}")
    return {"effect": effect_id, "base": base, "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--folder", default="vfx")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.channel, args.recipe, folder=args.folder), indent=2))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"studio: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
