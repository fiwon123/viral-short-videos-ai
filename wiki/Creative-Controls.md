# 🎛️ Creative Controls

The studio is designed so an AI can make a strong first cut without touching Python, then refine with precise overrides.

## 🎬 Style presets

Set one preset on the channel or episode:

```json
{"style": {"preset": "cinematic"}}
```

| Preset | Direction |
| --- | --- |
| `cinematic` | Push-in camera, film grade, grain, vignette, minimal captions |
| `slapstick` | Crash zoom, saturated colour, karaoke pop, more motion blur |
| `cozy` | Floating camera, warm tint, soft grain, box captions |
| `minimal` | No camera move, flat grade, minimal captions, fast encode |

A preset fills only fields the episode does not already declare. Explicit values always win.

Preset source: [`presets/styles/`](https://github.com/fiwon123/viral-short-videos-ai/tree/main/presets/styles).

## 🎚️ Feature matrix

| Feature | Default | How to disable |
| --- | --- | --- |
| Audio mastering | On | `audio.master.enabled: false` or `render.master: false` |
| Captions | Burned | `render.captions: false` or `--no-captions` |
| SRT | Written | `render.captions: false` |
| Thumbnail | Written | `render.thumbnail: false` or `--no-thumbnail` |
| Publishing files | Written | `render.publishing: false` or `--no-publishing` |
| Motion blur | Off | Leave `motion_blur` at 0 |
| Supersampling | 1× | Set `supersample: 2` to enable |
| Post effects | Off | Omit `post` |
| Camera move | None | Omit `camera` |
| Transition | Cut | Omit `transition` |

## 🎥 Camera

```json
{
  "camera": {
    "preset": "push-in",
    "shake": {"amplitude": 0.01, "frequency": 12, "decay": 0.4}
  }
}
```

Presets: `push-in`, `pull-out`, `crash-zoom`, `whip-pan`, `dolly`, `float`, `orbit`, `handheld`.

Use explicit `keyframes` when the preset is not enough. Use `parallax` per layer for depth.

## 🔁 Transitions

```json
{"transition": {"type": "whip-left", "duration": 0.28, "ease": "expo"}}
```

17 types: dissolve, four wipes, four slides, two whips, two zooms, iris, flash, dip-to-black, luma-wipe.

## 🧱 Layers

- `visible` switches a layer on and off.
- `variant_group` keeps at most one visible layer in a group. Useful for blinks, expressions and prop states.
- `parent` + `pivot` build cutout rigs.
- `blend` supports screen/add/multiply/overlay/soft-light.
- `blur` and `parallax` add depth.

```json
{"id": "eye-blink", "parent": "head", "variant_group": "eyes", "visible": false,
 "keyframes": [{"at": 0.6, "visible": true}, {"at": 0.7, "visible": false}]}
```

## 🖼️ Captions

```json
{
  "captions": {
    "style": "karaoke",
    "position": "bottom",
    "animation": "pop",
    "font_size": 1.05,
    "stroke": 0.04,
    "shadow": true,
    "radius": 0.4
  }
}
```

## 🎚️ Render

```json
{"render": {"crf": 16, "preset": "slow", "tune": "film", "audio_bitrate": 256,
            "captions": true, "thumbnail": true, "publishing": true}}
```

CLI overrides: `--crf`, `--preset`, `--audio-bitrate`, `--no-captions`, `--no-thumbnail`, `--no-publishing`.

## 👁️ Fast review

Render one frame instead of a full video while composing:

```sh
make still EPISODE=workspace/my-channel/episodes/my-episode/episode.json \
  SHOT=A PROGRESS=0.5
```

Add `SHEET=4` for a contact sheet, `SCALE=0.5` for a faster review,
`NOAUDIO=1` while composing the picture, and `RENDERER=hyperframes` for SVG or
3D shots. `make presets`, `make templates`,
and `make motion MOTION=impact` list the available building blocks.

## 🔤 Typography

Give the channel named fonts, then use them per layer:

```json
{
  "fonts": {"display": "fonts/display.otf", "body": "fonts/body.otf"}
}
```

```json
{"kind": "text", "text": "BIG TYPE", "font": "display",
 "align": "left", "line_height": 1.05, "letter_spacing": 0.02,
 "max_lines": 2, "uppercase": true,
 "stroke": {"width": 0.04, "color": "background"},
 "shadow": {"color": "accent", "blur": 0.22, "opacity": 0.45}}
```

Text still fits its box automatically. Use `align`, `line_height`,
`letter_spacing`, `max_lines`, `stroke`, and `shadow` for a professional title
without baking it into an image.

## 🎨 Colour and shape finish

The palette can carry extra named roles:

```json
{"palette": {"background": "#0B1020", "foreground": "#F8FAFC",
             "accent": "#22D3EE", "secondary": "#334155", "warm": "#F59E0B"}}
```

`fill` accepts a hex colour, a palette role, or a gradient:

```json
{"fill": {"type": "linear", "angle": 90,
          "stops": [{"at": 0, "color": "foreground"}, {"at": 1, "color": "accent"}]},
 "stroke": {"width": 0.05, "color": "background"},
 "glow": {"color": "accent", "size": 0.28, "opacity": 0.6}}
```

`shadow` and `glow` work on shapes, text, images, and SVG layers. Captions and
thumbnail colours can use the same palette roles.

Add a colour wash with an animatable amount:

```json
{"tint": "warm", "tint_opacity": 0,
 "keyframes": [{"at": 0, "tint_opacity": 0},
               {"at": 0.5, "tint_opacity": 0.8, "ease": "sine"},
               {"at": 1, "tint_opacity": 0.2}]}
```

The tint multiplies the layer colour while preserving its alpha, so it works on
shapes, text, images and SVG art.

## ✍️ Word, line and character reveal

Reveal a static text layer without hand-keying every piece:

```json
{"kind": "text", "x": 0.5, "y": 0.42, "width": 0.8, "height": 0.18,
 "text": "ONE SMALL GUST", "reveal": {"mode": "word", "start": 0.1, "stagger": 0.12}}
```

Modes are `word`, `line`, and `character`. `start` and `stagger` use the 0..1
shot clock. With `fade: false` each piece pops in; the default fades it in.
Reveal needs a static, unparented, unrotated text layer; animate the pieces or
the whole shot after expanding.

## 🎞️ Sprite-sheet animation

Use a `sheet` layer for flipbook animation, hand-drawn effects or a character
with frame-by-frame poses:

```json
{"kind": "sheet", "file": "art/flipbook.png", "asset_scope": "channel",
 "columns": 4, "rows": 3, "count": 12,
 "x": 0.5, "y": 0.5, "width": 0.4, "height": 0.4,
 "keyframes": [{"at": 0, "frame": 0}, {"at": 0.5, "frame": 6}, {"at": 1, "frame": 11}]}
```

`frame` steps instead of interpolating, so each cell holds until the next key.
The sheet is sliced once and both Python and browser renderers choose the same
cell. Keep cell sizes equal and the count within `columns * rows`.

## 🧩 Reusable rigs with `defs`

Define a character part, prop, or set once, then instance it:

```json
{
  "defs": {
    "badge": [
      {"id": "plate", "kind": "rect", "x": 0, "y": 0, "width": 0.22, "height": 0.06, "radius": 0.4, "fill": "secondary"},
      {"id": "label", "kind": "text", "x": 0, "y": 0, "width": 0.2, "height": 0.04, "fill": "accent", "text": "BADGE"}
    ]
  },
  "scenes": [{"id": "S1", "purpose": "Reuse", "shots": [
    {"id": "A", "duration": 3, "layers": [
      {"id": "badge-1", "kind": "use", "ref": "badge", "x": 0.5, "y": 0.86},
      {"id": "badge-2", "kind": "use", "ref": "badge", "x": 0.5, "y": 0.12, "scale": 0.7}
    ]}
  ]}]
}
```

The studio prefixes layer IDs, rewrites local parents and masks, and namespaces
`variant_group`s. A `use` can carry its own pose and keyframes to move the whole
rig. Parts in one definition share that instance's `plane`; keep a rig on one
plane, or split it into two definitions.

## 🏛️ Channel rig library

Keep recurring cast and props across episodes in `channel/rigs.json`:

```json
{"version": 1, "rigs": {"hero": [
  {"id": "body", "kind": "ellipse", "x": 0, "y": 0, "width": 0.2, "height": 0.2},
  {"id": "head", "kind": "ellipse", "x": 0, "y": -0.14, "width": 0.12, "height": 0.12, "parent": "body"}
]}}
```

```json
{"rig_library": "rigs.json"}
```

Then instance it from any episode:

```json
{"id": "hero-1", "kind": "use", "ref": "hero", "x": 0.5, "y": 0.6}
```

Episode `defs` override channel rigs with the same name, so a one-off variation
does not fork the whole series.

## 🏃 Motion polish

Use `scale_x` and `scale_y` for squash and stretch, and `skew_x` / `skew_y`
for lean and smears:

```json
{"at": 0.55, "scale_x": 1.15, "scale_y": 0.85, "ease": "back"}
```

Easing accepts the named modes, a cubic-bezier object, or a spring. Add
`ease_props` when one property needs a different curve. `auto` smooths a
multi-key move through its neighbours:

```json
{"at": 1, "x": 0.7, "ease": "auto",
 "ease_props": {"scale_x": "linear"}}
```

`trail` adds delayed echoes without new renderer code:

```json
{"trail": {"count": 3, "spacing": 0.05, "opacity": 0.55, "scale_falloff": 0.85}}
```

`make motion MOTION=pop|impact|anticipate|settle|float|breathe|enter|exit`
emits keyframes you can paste into a layer.

## 🖼️ Thumbnail variants

`thumbnail` controls the primary cover. Add named `thumbnails` for A/B tests:

```json
{"thumbnail": {"shot": "A", "text": "MISSED THE WIND", "style": "banner"},
 "thumbnails": [
   {"name": "alt", "shot": "A", "text": "ONE SMALL GUST", "style": "lower-third"},
   {"name": "min", "shot": "A", "text": "A VERY IMPORTANT LETTER", "style": "minimal"}
 ]}
```

Styles are `banner`, `lower-third`, `center`, `minimal`, and `split`. Variants
share the primary shot and time so every renderer writes the same set of files.

## 📅 Batch a season

Keep a season file beside the channel:

```json
{
  "title": "Season 1",
  "channel": "channel/channel.json",
  "defaults": {"renderer": "hyperframes", "preview": true},
  "episodes": [
    {"id": "ep-01", "path": "episodes/ep-01/episode.json", "status": "approved"},
    {"id": "ep-02", "path": "episodes/ep-02/episode.json", "status": "planned"}
  ]
}
```

```sh
make batch SEASON=workspace/my-channel/season.json
make batch SEASON=... VALIDATE_ONLY=1
make batch SEASON=... STATUS=approved PREVIEW=1
make batch SEASON=... ONLY=ep-01 JOBS=2
```

`DRY_RUN=1` shows the exact commands and output packages without rendering.

## 🧪 Sound and Effect Labs

Generate a new cue:

```sh
make sound CHANNEL=workspace/my-channel/channel/channel.json RECIPE=audio/custom-impact.json
```

Generate a new SVG:

```sh
make effect CHANNEL=workspace/my-channel/channel/channel.json RECIPE=vfx/custom-ring.json
```

## 🔗 Related guides

- [Manifest Reference](Manifest-Reference)
- [Audio and Sound Design](Audio-and-Sound-Design)
- [Motion, Camera and Rigs](Motion-Camera-and-Rigs)
