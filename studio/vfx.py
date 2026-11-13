"""Write a channel VFX kit: self-contained SVGs that episodes composite as layers.

Shapes are palette-driven, so every channel gets its own flash, dust, splash and
shockwave in the approved colours. Layers reference them with
{"kind": "svg", "file": "vfx/flash.svg", "asset_scope": "channel"}.

    python -m studio.vfx channels/<slug>
"""

import argparse
import json
from pathlib import Path

DEFAULT = {
    "background": "#131B30",
    "foreground": "#FFF3D8",
    "accent": "#FFBD54",
    "secondary": "#293F59",
}


def rgb(value):
    value = value.lstrip("#")
    return [int(value[i:i + 2], 16) for i in (0, 2, 4)]


def hexed(values):
    return "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in values)


def blend(first, second, amount):
    a, b = rgb(first), rgb(second)
    return hexed([a[i] + (b[i] - a[i]) * amount for i in range(3)])


def shade(color, amount):
    values = rgb(color)
    return hexed([v + (255 - v) * amount if amount > 0 else v * (1 + amount) for v in values])


def palette(channel):
    base = {**DEFAULT, **(channel.get("palette") or {})}
    return {
        "light": base["foreground"],
        "warm": base["accent"],
        "dark": base["background"],
        "mid": base["secondary"],
        "liquid": blend(base["foreground"], "#5f9c96", 0.42),
        "smoke": blend(base["secondary"], base["foreground"], 0.28),
        "outline": shade(base["background"], -0.35),
        "hot": shade(base["accent"], 0.65),
    }


KIT = {
    "flash.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <radialGradient id="core" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="{hot}" stop-opacity=".95"/>
      <stop offset=".42" stop-color="{warm}" stop-opacity=".62"/>
      <stop offset="1" stop-color="{warm}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <circle cx="50" cy="50" r="48" fill="url(#core)"/>
  <g fill="{hot}" opacity=".85">
    <path d="M50 0 L54 38 L50 46 L46 38 Z"/>
    <path d="M50 100 L54 62 L50 54 L46 62 Z"/>
    <path d="M0 50 L38 46 L46 50 L38 54 Z"/>
    <path d="M100 50 L62 46 L54 50 L62 54 Z"/>
    <path d="M15 15 L42 40 L36 44 L30 42 Z" opacity=".55"/>
    <path d="M85 15 L58 40 L64 44 L70 42 Z" opacity=".55"/>
    <path d="M15 85 L42 60 L36 56 L30 58 Z" opacity=".55"/>
    <path d="M85 85 L58 60 L64 56 L70 58 Z" opacity=".55"/>
  </g>
</svg>
''',
    "shockwave.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="47" fill="none" stroke="{light}" stroke-width="2.6" opacity=".92"/>
  <circle cx="50" cy="50" r="40" fill="none" stroke="{warm}" stroke-width="1.4" opacity=".7"/>
  <circle cx="50" cy="50" r="33" fill="none" stroke="{light}" stroke-width=".8" opacity=".35"/>
</svg>
''',
    "impact-stars.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path d="M50 3 L58 34 L84 12 L66 40 L97 50 L66 60 L84 88 L58 66 L50 97 L42 66 L16 88 L34 60 L3 50 L34 40 L16 12 L42 34 Z"
        fill="{light}" stroke="{outline}" stroke-width="2.4" stroke-linejoin="round"/>
  <circle cx="50" cy="50" r="12" fill="{warm}"/>
</svg>
''',
    "dust.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <radialGradient id="puff">
      <stop offset="0" stop-color="{light}" stop-opacity=".85"/>
      <stop offset=".65" stop-color="{mid}" stop-opacity=".4"/>
      <stop offset="1" stop-color="{mid}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <g fill="url(#puff)">
    <ellipse cx="34" cy="62" rx="30" ry="20"/>
    <ellipse cx="62" cy="56" rx="26" ry="18"/>
    <ellipse cx="50" cy="44" rx="20" ry="15"/>
    <ellipse cx="26" cy="44" rx="14" ry="11" opacity=".8"/>
    <ellipse cx="72" cy="40" rx="13" ry="10" opacity=".8"/>
  </g>
</svg>
''',
    "smoke.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <radialGradient id="haze">
      <stop offset="0" stop-color="{smoke}" stop-opacity=".7"/>
      <stop offset=".7" stop-color="{mid}" stop-opacity=".3"/>
      <stop offset="1" stop-color="{mid}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <g fill="url(#haze)">
    <ellipse cx="40" cy="58" rx="28" ry="24"/>
    <ellipse cx="64" cy="50" rx="24" ry="21"/>
    <ellipse cx="50" cy="34" rx="19" ry="17"/>
  </g>
</svg>
''',
    "splash.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <ellipse cx="50" cy="86" rx="30" ry="7" fill="{light}" opacity=".3"/>
  <path d="M50 86 C44 68 45 54 50 38 C55 54 56 68 50 86 Z" fill="{light}" opacity=".92"/>
  <g fill="none" stroke="{light}" stroke-width="3.2" stroke-linecap="round" opacity=".9">
    <path d="M50 84 C38 74 34 58 40 42"/>
    <path d="M50 84 C62 74 66 58 60 42"/>
  </g>
  <g fill="{light}">
    <circle cx="24" cy="34" r="4.4"/>
    <circle cx="34" cy="20" r="3.2"/>
    <circle cx="50" cy="12" r="4"/>
    <circle cx="66" cy="20" r="3"/>
    <circle cx="77" cy="34" r="4.2"/>
    <circle cx="18" cy="54" r="2.6" opacity=".85"/>
    <circle cx="83" cy="54" r="2.4" opacity=".85"/>
  </g>
</svg>
''',
    "ripple.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <g fill="none" stroke="{liquid}">
    <ellipse cx="50" cy="50" rx="46" ry="17" stroke-width="2.2" opacity=".85"/>
    <ellipse cx="50" cy="50" rx="34" ry="12" stroke-width="1.6" opacity=".6"/>
    <ellipse cx="50" cy="50" rx="21" ry="7.4" stroke-width="1.2" opacity=".4"/>
  </g>
</svg>
''',
    "speed-lines.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <g stroke="{light}" stroke-linecap="round">
    <path d="M4 26 H46" stroke-width="2.4" opacity=".75"/>
    <path d="M10 40 H66" stroke-width="1.6" opacity=".5"/>
    <path d="M2 54 H38" stroke-width="2" opacity=".65"/>
    <path d="M14 68 H72" stroke-width="1.4" opacity=".42"/>
    <path d="M6 82 H52" stroke-width="1.8" opacity=".55"/>
  </g>
</svg>
''',
    "sparkle.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path d="M50 6 C53 34 66 47 94 50 C66 53 53 66 50 94 C47 66 34 53 6 50 C34 47 47 34 50 6 Z"
        fill="{light}" opacity=".95"/>
  <circle cx="50" cy="50" r="6" fill="{hot}" opacity=".9"/>
</svg>
''',
    "impact-frame.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <g fill="none" stroke="{light}" stroke-linejoin="round">
    <path d="M50 4 L59 30 L82 14 L70 40 L96 50 L70 60 L82 86 L59 70 L50 96 L41 70 L18 86 L30 60 L4 50 L30 40 L18 14 L41 30 Z"
          stroke-width="3.4" opacity=".92"/>
    <path d="M50 18 L56 37 L74 26 L65 44 L84 50 L65 56 L74 74 L56 63 L50 82 L44 63 L26 74 L35 56 L16 50 L35 44 L26 26 L44 37 Z"
          stroke="{warm}" stroke-width="1.8" opacity=".8"/>
  </g>
  <circle cx="50" cy="50" r="8" fill="{hot}" opacity=".9"/>
</svg>
''',
    "light-leak.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <radialGradient id="leak" cx="30%" cy="40%" r="70%">
      <stop offset="0" stop-color="{hot}" stop-opacity=".8"/>
      <stop offset=".45" stop-color="{warm}" stop-opacity=".32"/>
      <stop offset="1" stop-color="{warm}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="100" height="100" fill="url(#leak)"/>
</svg>
''',
    "halftone.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <pattern id="dots" width="8" height="8" patternUnits="userSpaceOnUse">
      <circle cx="2" cy="2" r="1.4" fill="{light}" opacity=".55"/>
      <circle cx="6" cy="6" r=".9" fill="{warm}" opacity=".4"/>
    </pattern>
  </defs>
  <rect width="100" height="100" fill="url(#dots)"/>
</svg>
''',
    "glow.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <radialGradient id="halo" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="{hot}" stop-opacity=".95"/>
      <stop offset=".35" stop-color="{warm}" stop-opacity=".5"/>
      <stop offset="1" stop-color="{warm}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <circle cx="50" cy="50" r="48" fill="url(#halo)"/>
</svg>
''',
    "spark.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path d="M50 4 C54 38 62 46 96 50 C62 54 54 62 50 96 C46 62 38 54 4 50 C38 46 46 38 50 4 Z"
        fill="{hot}" opacity=".96"/>
  <path d="M50 22 C52 42 58 48 78 50 C58 52 52 58 50 78 C48 58 42 52 22 50 C42 48 48 42 50 22 Z"
        fill="{light}" opacity=".85"/>
</svg>
''',
    "bubble.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <g fill="none" stroke="{light}" stroke-width="1.6" opacity=".9">
    <circle cx="30" cy="62" r="17"/>
    <circle cx="58" cy="42" r="11"/>
    <circle cx="72" cy="68" r="7"/>
    <circle cx="22" cy="34" r="4"/>
  </g>
  <g fill="{light}" opacity=".5">
    <circle cx="25" cy="56" r="2.4"/>
    <circle cx="54" cy="37" r="1.8"/>
    <circle cx="70" cy="65" r="1.2"/>
  </g>
</svg>
''',
    "confetti.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <g opacity=".95">
    <rect x="18" y="16" width="8" height="14" rx="1.5" fill="{warm}" transform="rotate(24 22 23)"/>
    <rect x="44" y="10" width="7" height="12" rx="1.5" fill="{light}" transform="rotate(-34 47 16)"/>
    <rect x="72" y="22" width="8" height="13" rx="1.5" fill="{hot}" transform="rotate(48 76 28)"/>
    <rect x="26" y="60" width="7" height="12" rx="1.5" fill="{light}" transform="rotate(-18 29 66)"/>
    <rect x="54" y="52" width="8" height="14" rx="1.5" fill="{warm}" transform="rotate(62 58 59)"/>
    <rect x="76" y="64" width="7" height="12" rx="1.5" fill="{light}" transform="rotate(-52 79 70)"/>
    <circle cx="34" cy="42" r="3" fill="{hot}"/>
    <circle cx="66" cy="44" r="2.4" fill="{light}"/>
    <circle cx="48" cy="78" r="2.8" fill="{warm}"/>
  </g>
</svg>
''',
    "slash.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <g stroke-linecap="round" fill="none">
    <path d="M8 86 L92 14" stroke="{light}" stroke-width="6" opacity=".92"/>
    <path d="M18 94 L96 30" stroke="{warm}" stroke-width="2.4" opacity=".72"/>
    <path d="M4 72 L72 6" stroke="{hot}" stroke-width="1.6" opacity=".6"/>
  </g>
</svg>
''',
    "ring.svg": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <ellipse cx="50" cy="50" rx="45" ry="18" fill="none" stroke="{light}" stroke-width="3" opacity=".9"/>
  <ellipse cx="50" cy="50" rx="34" ry="12" fill="none" stroke="{warm}" stroke-width="1.6" opacity=".62"/>
  <ellipse cx="50" cy="50" rx="20" ry="6" fill="none" stroke="{hot}" stroke-width="1" opacity=".45"/>
</svg>
''',
}


def build(channel, *, folder="vfx"):
    channel = Path(channel).resolve()
    manifest = channel / "channel.json"
    data = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    colors = palette(data)
    out = (channel / folder).resolve()
    if not out.is_relative_to(channel):
        raise ValueError("The VFX kit must live inside the channel folder")
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, template in KIT.items():
        path = out / name
        path.write_text(template.format(**colors), encoding="utf-8")
        written.append(name)
    return {"folder": str(out.relative_to(channel)), "files": written, "palette": colors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", type=Path, help="channel folder, for example channels/<slug>")
    parser.add_argument("--folder", default="vfx", help="folder inside the channel")
    args = parser.parse_args()
    try:
        report = build(args.channel, folder=args.folder)
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(f"studio: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
