"""Platform safe-area guide images for 9:16 review."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PLATFORMS = {
    "youtube-shorts": {
        "size": (1080, 1920),
        "safe": (0.06, 0.10, 0.94, 0.82),
        "right_rail": (0.84, 0.38, 1.0, 0.82),
        "bottom_ui": (0.04, 0.82, 1.0, 1.0),
        "label": "YouTube Shorts",
    },
    "tiktok": {
        "size": (1080, 1920),
        "safe": (0.06, 0.10, 0.84, 0.80),
        "right_rail": (0.82, 0.36, 1.0, 0.84),
        "bottom_ui": (0.04, 0.80, 1.0, 1.0),
        "label": "TikTok",
    },
    "generic": {
        "size": (1080, 1920),
        "safe": (0.05, 0.08, 0.95, 0.85),
        "right_rail": (0.86, 0.35, 1.0, 0.85),
        "bottom_ui": (0.05, 0.85, 1.0, 1.0),
        "label": "Generic 9:16",
    },
}


def _font(size):
    for name in ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def build(platform, target):
    spec = PLATFORMS[platform]
    width, height = spec["size"]
    image = Image.new("RGBA", (width, height), (12, 18, 32, 255))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    def rect(box, color):
        left, top, right, bottom = box
        draw.rectangle((round(left * width), round(top * height),
                        round(right * width), round(bottom * height)), fill=color)

    rect((0, 0, 1, 0.10), (239, 68, 68, 46))
    rect((0, 0.82, 1, 1), (239, 68, 68, 54))
    rect((0.84, 0.38, 1, 0.82), (245, 158, 11, 46))
    left, top, right, bottom = spec["safe"]
    draw.rectangle((round(left * width), round(top * height), round(right * width),
                    round(bottom * height)), outline=(110, 231, 183, 220), width=5)
    draw.text((round(left * width), round(top * height) - 46), spec["label"],
              fill=(248, 250, 252, 255), font=_font(34))
    draw.text((round(left * width), round(bottom * height) + 18),
              "Keep faces, captions and the payoff inside the green box.",
              fill=(203, 213, 225, 255), font=_font(26))
    image = Image.alpha_composite(image, overlay)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(target)
    return {"platform": platform, "file": str(Path(target).resolve()), "size": [width, height]}
