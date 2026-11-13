<h1 align="center">🎬 Viral Short Videos AI</h1>

<p align="center">
  <a href=".agents/skills/viral-video-studio/SKILL.md"><img alt="Workflow: Research to MP4" src="https://img.shields.io/badge/Workflow-Research%20to%20MP4-2563eb?style=flat-square"></a>
  <a href="https://github.com/fiwon123/viral-short-videos-ai/wiki/Motion-Camera-and-Rigs"><img alt="Animation: 2D, 2.5D and 3D" src="https://img.shields.io/badge/Animation-2D%20%7C%202.5D%20%7C%203D-0f766e?style=flat-square"></a>
  <a href="https://github.com/fiwon123/viral-short-videos-ai/wiki/Audio-and-Sound-Design"><img alt="Audio: mastered stereo" src="https://img.shields.io/badge/Audio-Mastered%20Stereo-8b5cf6?style=flat-square"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-22c55e?style=flat-square"></a>
</p>

Turn a video idea into an original animated channel and a finished Short. The studio is manifest-driven: an AI or a person writes JSON, imports original assets, previews, and renders a verified MP4 with captions and publishing copy.

It supports 2D vector, 2.5D layered and 3D animation up to 12 minutes, with AI-controlled camera moves, transitions, sound design, captions, VFX and audio mastering.

## 🚀 Quick start

```sh
git clone https://github.com/fiwon123/viral-short-videos-ai.git
cd viral-short-videos-ai
python -m pip install -r requirements.txt
npm ci --ignore-scripts
python video.py doctor
```

For Kokoro voices, use Python 3.10–3.13 and install `requirements-voice.txt`, then add the local model files under `audio-models/`. See [Quick Start](https://github.com/fiwon123/viral-short-videos-ai/wiki/Quick-Start).

## 📁 One channel = one workspace

```text
workspace/<channel>/
├── channel/
│   ├── channel.json      # machine-readable identity
│   ├── channel.md        # generated copy/paste page
│   ├── brief.md
│   ├── brand/
│   ├── art/
│   ├── audio/
│   └── vfx/
├── episodes/<episode>/episode.json
├── research/
└── renders/<episode>-v1/
    ├── video.mp4
    ├── thumbnail.png
    ├── captions.srt
    └── publishing.md
```

The older `channels/`, `episodes/`, `research/` and `output/` layout still works. Migrate one channel when ready:

```sh
make migrate CHANNEL=channels/my-channel/channel.json EPISODE=episodes/my-episode/episode.json
make migrate CHANNEL=channels/my-channel/channel.json EPISODE=episodes/my-episode/episode.json APPLY=1
```

## ▶️ The five commands you need

```sh
make status       # resolved channel, episode and layout
make validate     # schema and asset checks
make audio        # listen to the mastered mix before animation
make preview      # fast review render
make render       # final package
```

Pass `EPISODE=...` and `CHANNEL=...` when discovery is ambiguous. `make help` lists the rest, including `sfx`, `vfx`, `sound`, `effect`, `channel-doc` and `assets`.

## 🎨 Creative controls

```json
{
  "style": {"preset": "cinematic"},
  "camera": {"preset": "push-in"},
  "motion_blur": 0.3,
  "post": {"grain": 0.12, "vignette": 0.2, "bloom": 0.24},
  "captions": {"style": "karaoke", "animation": "pop"},
  "audio": {"master": {"loudness": -14}, "reverb": {"mix": 0.08}}
}
```

Layer-level rigs, blend modes, camera shake, procedural transitions, Sound Lab recipes and Effect Lab SVGs are documented in the wiki.

## 🧪 Complete examples

Three complete, original examples show the full input-to-output flow:

| Example | Shows |
| --- | --- |
| [Orbit Workshop](examples/orbit-workshop) | 2D/2.5D layers, karaoke captions, Foley and a finished package |
| [Paper Crane Post](examples/paper-crane) | Parented rig, camera push-in, slide caption, whip transition and post |
| [Tiny Signal](examples/tiny-signal) | Three.js scene library, PBR/emissive materials, camera move and mastered mix |

Each example contains a channel identity, episode source, research note, generated `channel.md`, rendered preview and publishing package. See [examples/README.md](examples/README.md).

## 📚 Documentation

| I want to… | Read |
| --- | --- |
| Understand the big picture | [Core Concepts](https://github.com/fiwon123/viral-short-videos-ai/wiki/Core-Concepts) |
| Look up every field | [Manifest Reference](https://github.com/fiwon123/viral-short-videos-ai/wiki/Manifest-Reference) |
| Make audio and sound design | [Audio and Sound Design](https://github.com/fiwon123/viral-short-videos-ai/wiki/Audio-and-Sound-Design) |
| Move the camera and rig a character | [Motion, Camera and Rigs](https://github.com/fiwon123/viral-short-videos-ai/wiki/Motion-Camera-and-Rigs) |
| Make effects and transitions | [VFX and Post](https://github.com/fiwon123/viral-short-videos-ai/wiki/VFX-and-Post) |
| Style captions | [Captions and Typography](https://github.com/fiwon123/viral-short-videos-ai/wiki/Captions-and-Typography) |
| Build 3D scenes | [3D and Renderers](https://github.com/fiwon123/viral-short-videos-ai/wiki/3D-and-Renderers) |
| Use AI to make a video | [AI Workflow and Prompt Cookbook](https://github.com/fiwon123/viral-short-videos-ai/wiki/AI-Workflow-and-Prompt-Cookbook) |
| Publish and troubleshoot | [QA, Export and Publishing](https://github.com/fiwon123/viral-short-videos-ai/wiki/QA-Export-and-Publishing) · [Troubleshooting](https://github.com/fiwon123/viral-short-videos-ai/wiki/Troubleshooting) |
| Edit the docs source | [wiki/](wiki/) · publish with `make wiki` |

## 🛠️ Requirements

- Python 3.10+ with `requirements.txt`
- FFmpeg and FFprobe
- Node.js 22+ and Chrome or Chromium for SVG/3D renderers
- Optional Kokoro ONNX model files for local neural voices

## 📄 License

MIT. See [LICENSE](LICENSE).
