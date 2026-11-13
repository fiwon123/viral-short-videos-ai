# 🧪 Advanced Controls

These are the power features for AI-directed episodes. They are optional and fit the same workspace manifests.

## 🎭 Masks, mattes and groups

```json
{
  "id": "window-mask",
  "kind": "ellipse",
  "x": 0.5, "y": 0.5, "width": 0.5, "height": 0.5,
  "fill": "foreground", "visible": false
}
```

```json
{
  "id": "character-group",
  "kind": "group",
  "x": 0.5, "y": 0.6, "width": 0.6, "height": 0.6,
  "mask": {"source": "layer:window-mask", "mode": "alpha", "feather": 0.02}
}
```

- A group renders its children but not itself.
- A child’s `x` and `y` are offsets from the group pivot.
- A group mask is inherited by its children.
- `mode` is `alpha` or `luma`.
- `invert` and `feather` are optional.
- A mask file uses `scope: "episode"` or `"channel"`.

```json
{"mask": {"source": "masks/window.png", "scope": "channel", "mode": "luma"}}
```

Custom transition matte:

```json
{"transition": {"type": "mask", "mask": "masks/wipe.png",
                 "mask_scope": "channel", "mask_mode": "luma",
                 "softness": 0.06, "invert": false, "duration": 0.4}}
```

`luma-wipe` is a true procedural luma matte, not a left wipe.

## 📍 Named markers

```json
{
  "id": "impact-1",
  "shot": "A",
  "at": 0.72,
  "events": [
    {"kind": "sfx", "sound": "thud", "gain": 0.7},
    {"kind": "camera_shake", "amplitude": 0.02, "frequency": 14, "duration": 0.3},
    {"kind": "effect", "template": "dust-burst", "x": 0.5, "y": 0.7}
  ]
}
```

Moving `impact-1` moves the sound, camera shake and dust together.

Effect templates live in `presets/effects/`:

- `dust-burst`
- `impact-flash`
- `spark-burst`

Inspect resolved markers:

```sh
python video.py resolve EPISODE --channel CHANNEL --json
```

## 🎬 Shot templates

```sh
python video.py shot-template reaction \
  --set id=R1 --set duration=1.2 --set prop_x=0.7 --set prop_y=0.55 \
  --out /tmp/reaction-shot.json
```

Templates live in `presets/shots/`:

- `reaction`
- `title-card`
- `reveal`

They are authoring helpers. Paste the result into an episode and edit the layers.

## 🎥 Camera tracking and focus

```json
{
  "camera": {
    "track": {"layer": "crane", "x": 0.5, "y": 0.42},
    "shakes": [
      {"at": 0.72, "duration": 0.35, "amplitude": 0.02, "frequency": 14}
    ]
  }
}
```

- `track` keeps a layer at a chosen screen point while the background parallaxes.
- `shakes` are timed, decaying camera jitters.
- 3D camera keys can animate `fov`.
- 3D shots can focus-pull:

```json
{"three": {"focus": [
  {"at": 0, "distance": 2.5, "aperture": 1},
  {"at": 1, "distance": 0.8, "aperture": 2}
]}}
```

## ✨ Particles

```json
{
  "id": "sparks",
  "kind": "particles",
  "file": "vfx/spark.svg",
  "asset_scope": "channel",
  "x": 0.5, "y": 0.7,
  "count": 80,
  "life": 1.2,
  "velocity": [0.2, 1.4],
  "spread": 0.8,
  "gravity": [0, -2.4],
  "size": [0.01, 0.03],
  "area": [0.3, 0.1],
  "seed": 17
}
```

The emitter expands into deterministic image/SVG layers before rendering. The same seed gives the same motion in Python and the browser renderers.

## 🔊 Audio across cuts and stems

Dialogue can lead into a cut:

```json
{"speaker": "Narrator", "text": "A small delay.", "at": 0.2, "lead": -0.4}
```

Ambience can continue across shots:

```json
{"ambience": [
  {"sound": "wind", "start": 0, "end": 12, "gain": 0.04, "loop": true}
]}
```

Write stems:

```sh
python video.py render EPISODE --channel CHANNEL --stems
```

The package then contains `mix.wav`, `stem-dialogue.wav`, `stem-music.wav`, `stem-ambience.wav` and `stem-sfx.wav`.

## 💬 Measured words and visemes

```json
{
  "speaker": "Narrator",
  "text": "A small delay.",
  "words": [
    {"text": "A", "start": 0.0, "end": 0.06},
    {"text": "small", "start": 0.06, "end": 0.22}
  ],
  "visemes": [
    {"at": 0.06, "shape": "M"},
    {"at": 0.18, "shape": "AA"}
  ]
}
```

Import external alignment:

```sh
python video.py align EPISODE --json alignment.json
```

Alignment JSON shape:

```json
{"lines": [{"shot": "A", "index": 0, "words": [...], "visemes": [...]}]}
```

Mouth layers can use `viseme_for` and `viseme`:

```json
{"id": "mouth-AA", "viseme_for": "Narrator", "viseme": "AA", "variant_group": "mouth"}
```

Without visemes, the existing audio-level mouth motion remains the fallback.

## 🎞️ 3D clip blending

```json
{"animations": {"character": [
  {"clip": "idle", "at": 0, "weight": 0.4, "loop": true},
  {"clip": "talk", "at": 0, "weight": 0.6, "loop": true}
]}}
```

Weights blend multiple GLB clips.

## 🧪 Parity and support

```sh
python video.py support --markdown --out docs/RENDERER-SUPPORT.md
python video.py parity --renderers python,hyperframes
```

The parity fixture is `tests/parity/`. It writes renderer sheets, diff images and `parity.json`.

## 🖥️ Shot editor

```sh
python video.py editor EPISODE --channel CHANNEL
```

Opens a local-only storyboard, shot inspector, camera fields, marker list and safe-area guide. Save writes back to the same `episode.json`.

## Next

- [Renderer Support](Renderer-Support)
- [Manifest Reference](Manifest-Reference)
- [Motion, Camera and Rigs](Motion-Camera-and-Rigs)
- [Audio and Sound Design](Audio-and-Sound-Design)
