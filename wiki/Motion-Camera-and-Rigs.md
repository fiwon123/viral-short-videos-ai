# 🎥 Motion, Camera and Rigs

Smooth animation comes from pose contrast, good spacing, and a camera that supports the beat instead of fighting it.

## 🌀 Easings

| Easing | Feel |
| --- | --- |
| `linear` | Constant. Use for spins and mechanical motion |
| `in` | Accelerate into the pose |
| `out` | Decelerate into the pose |
| `smooth` | Smoothstep |
| `sine` | Gentle in/out |
| `expo` | Fast, decisive arrival |
| `circ` | Soft deceleration |
| `quint` | Long, controlled settle |
| `back` | Overshoot |
| `elastic` | Springy overshoot |
| `bounce` | Physical bounce |
| `spring` | Damped settle |
| `hold` | Step, no interpolation |

Use `back`/`spring` for takes, `expo` for whips and impacts, `hold` for switches.

## 🧍 Parent and pivot

```json
{"id": "body", "kind": "rect", "x": 0.5, "y": 0.62, "width": 0.3, "height": 0.28,
 "fill": "secondary", "radius": 0.5, "pivot": [0.5, 0.5]},
{"id": "head", "kind": "ellipse", "parent": "body", "x": 0, "y": -0.23,
 "width": 0.22, "height": 0.22, "fill": "foreground", "pivot": [0.5, 0.85]}
```

A child’s `x` and `y` are offsets from the parent pivot. The renderer inherits parent scale, rotation and opacity. Keep parent and child on the same plane.

## 👁️ Visible variants

```json
{"id": "eye-open", "parent": "head", "variant_group": "eyes"},
{"id": "eye-blink", "parent": "head", "variant_group": "eyes", "visible": false,
 "keyframes": [{"at": 0.6, "visible": true}, {"at": 0.7, "visible": false}]}
```

At most one layer in a `variant_group` draws. This is the fast path for blinks, expressions and prop states.

## 🎥 Camera

```json
{
  "camera": {
    "preset": "push-in",
    "shake": {"amplitude": 0.008, "frequency": 11, "decay": 0.35}
  }
}
```

Presets:

| Preset | Move |
| --- | --- |
| `push-in` | Gentle zoom toward the subject |
| `pull-out` | Reveal the wider scene |
| `crash-zoom` | Fast zoom that settles |
| `whip-pan` | Lateral snap |
| `dolly` | Slide and slight zoom |
| `float` | Slow vertical drift |
| `orbit` | Small circular drift |
| `handheld` | Procedural handheld noise |

Per-layer `parallax` scales the camera move: backgrounds move less, foregrounds more.

## 🌫️ Motion blur

```json
{"motion_blur": 0.3}
```

The Python renderer accumulates subframes. The browser renderer blends the previous frame. Start around `0.2–0.35`, preview, then lower it if contacts smear.

## 🧪 Physics helpers

`studio/physics.py` samples:

- `drop()` — fall, bounce, settle, squash
- `burst()` — debris and particles
- `splash()` — liquid crowns
- `shake()` — decaying camera jitter
- `spring()` — overshoot between positions
- `orbit()` — floating props
- `pendulum()` — swings and tails

## ✅ Review

- Step through every contact frame.
- Check planted feet and held props.
- Compare the first and last frame of a camera move.
- Watch muted: the action should still read.
- Watch with sound: the contact should land on the sound.

## Next

- [VFX and Post](VFX-and-Post)
- [Captions and Typography](Captions-and-Typography)
- [3D and Renderers](3D-and-Renderers)
