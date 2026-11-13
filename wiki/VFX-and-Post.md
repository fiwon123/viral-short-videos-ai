# ✨ VFX and Post

Effects should explain an action, not decorate it. The studio gives you reusable vector effects, palette-matched generation, compositing modes and a finishing pass.

## 🎨 Built-in kit

`make vfx CHANNEL=workspace/my-channel/channel` writes:

- flash
- shockwave
- impact stars
- dust
- smoke
- splash
- ripple
- speed lines
- sparkle
- glow
- light leak
- halftone
- confetti
- impact frame
- spark
- bubble
- slash
- ring

Reference them as channel-scoped SVG layers:

```json
{"id": "dust", "kind": "svg", "file": "vfx/dust.svg", "asset_scope": "channel",
 "x": 0.5, "y": 0.7, "width": 0.4, "height": 0.28, "opacity": 0,
 "keyframes": [{"at": 0.31, "opacity": 0.9, "scale": 0.8},
                {"at": 0.54, "opacity": 0, "scale": 1.2}]}
```

Start every effect at `opacity: 0`. Pop in over one or two frames, hold, then fade.

## 🧪 Effect Lab

Generate a new SVG from a recipe:

```json
{"id": "custom-burst", "base": "burst", "points": 18, "outer": 48,
 "inner": 10, "color": "accent", "variants": 2}
```

```sh
python video.py effect workspace/my-channel/channel --recipe vfx/custom-burst.json
```

Bases: `ring`, `burst`, `glow`, `light-leak`, `dust`, `speed-lines`, `stars`, `confetti`, `slash`.

## 🧬 Blend modes

```json
{"blend": "screen", "blur": 0.02}
```

| Mode | Use |
| --- | --- |
| `normal` | Standard alpha |
| `add` | Light, sparks, glow |
| `screen` | Light without clipping |
| `multiply` | Shadows, colour washes |
| `overlay` | Contrast and texture |
| `soft-light` | Subtle grade layers |

## 🎞️ Transitions

| Family | Types |
| --- | --- |
| Soft | `dissolve`, `luma-wipe` |
| Directional | `wipe-left/right/up/down`, `slide-left/right/up/down` |
| Energy | `whip-left/right`, `zoom-in/out` |
| Graphic | `iris`, `flash`, `dip-to-black` |

Use `ease` for the transition curve. Keep it shorter than the incoming shot.

## 🎨 Post

```json
{
  "post": {
    "brightness": 1.0,
    "contrast": 1.05,
    "saturation": 1.02,
    "hue": 0,
    "tint": "#ffd6a5",
    "bloom": 0.25,
    "blur": 0,
    "chromatic": 0.04,
    "grain": 0.12,
    "vignette": 0.18,
    "letterbox": 0
  }
}
```

Post can be set on the channel, episode or shot. Shot values win.

> [!TIP]
> Review a clean frame and a finished frame at the same moment. Grain and bloom should support the silhouette, not hide it.

## 🔗 Related guides

- [Captions and Typography](Captions-and-Typography)
- [3D and Renderers](3D-and-Renderers)
- [Manifest Reference](Manifest-Reference)
