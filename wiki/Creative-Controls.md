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
