# 🧠 Core Concepts

The studio is a small data pipeline. Every creative choice becomes a field in a manifest, an imported asset, or a generated file.

## 🏷️ Channel

A channel is the reusable identity:

- Name, handle, tagline and description
- Tags and hashtags
- Palette and mark
- Font, logo and banner
- Optional scene library, audio library, caption style, audio defaults and render defaults

Machine-readable file: `channel/channel.json`. Human copy/paste file: `channel/channel.md`.

## 🎞️ Episode

An episode is one video. It contains:

- Title, description, tags and TikTok caption
- Canvas size, FPS and maximum runtime
- Scenes and shots
- Speech, sound effects, music, captions and thumbnail
- Optional camera, post, motion blur, render settings and style preset

Machine-readable file: `workspace/<channel>/episodes/<episode>/episode.json`.

## 🎬 Scene

A scene groups shots by story purpose:

```json
{"id": "S1", "purpose": "Hook and setup", "shots": []}
```

Scenes are for humans and for the timed script. They do not affect rendering directly.

## 🎥 Shot

A shot is the unit of animation and timing:

- `duration` in seconds
- `layers`
- `three` for a 3D scene
- `camera`
- `speech` and `sfx`
- `transition`
- `post` and `motion_blur`
- `checks` for visual QA

A shot is resolved to an integer frame count. Speech and sound can extend the shot if a take is longer than requested.

## 🧱 Layer

A 2D layer has an ID, kind, position, size, style and keyframes.

Supported kinds:

| Kind | Use |
| --- | --- |
| `rect` | Panels, cards, simple characters, props |
| `ellipse` | Heads, eyes, dots, light pools |
| `polygon` | Hills, wings, arrows, custom shapes |
| `text` | Titles, labels, on-screen copy |
| `image` | PNG/JPEG artwork |
| `svg` | Reusable vector art with per-layer motion |

Key layer features:

- `parent` and `pivot` for rigs
- `visible` and `variant_group` for expression/pose swaps
- `blend` for `add`, `screen`, `multiply`, `overlay`, `soft-light`
- `blur` and `parallax`
- `keyframes` with 13 easings

## 🧭 Coordinates

- `x` and `y` are fractions of the canvas, origin at the top-left.
- Positions refer to the layer centre, or to the pivot when `pivot` is set.
- `width` and `height` are fractions of the canvas.
- A child layer with `parent` uses `x` and `y` as offsets from the parent pivot.
- Background layers draw before the 3D stage; foreground layers draw above it.

## 🎚️ Keyframes

```json
{"at": 0.4, "x": 0.6, "scale": 1.1, "ease": "back"}
```

`at` is normalized over the resolved shot. The easing describes motion arriving at that pose.

Available easings: `linear`, `in`, `out`, `smooth`, `sine`, `expo`, `circ`, `quint`, `back`, `elastic`, `bounce`, `spring`, `hold`.

## ⏱️ Timeline

The audio pass resolves every shot to frames, measures speech, places SFX, writes captions and builds the frame timeline. The visual pass reads that timeline.

The package contains `timeline.json` with:

- Shot start and end frames
- Speech and SFX cues
- Caption cues and word timings
- Transition windows
- Loudness report
- Scene library version

## 📦 Package

Every render writes a self-contained package:

| File | Purpose |
| --- | --- |
| `video.mp4` | Upload this |
| `thumbnail.png` | Cover frame |
| `captions.srt` | Upload or review subtitles |
| `publishing.md` | YouTube and TikTok copy |
| `publishing.json` | Machine-readable copy |
| `timed-script.md` | Per-shot direction, speech and sound |
| `timeline.json` | Resolved frame timeline |
| `qa.json` | Runtime, codecs, loudness and caption checks |
| `visual-qa.json` | Layer, contact and continuity checks |

## 🔗 Related guides

- [Manifest Reference](Manifest-Reference)
- [Motion, Camera and Rigs](Motion-Camera-and-Rigs)
- [QA, Export and Publishing](QA-Export-and-Publishing)
