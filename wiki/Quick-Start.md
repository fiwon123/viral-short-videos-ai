# 🚀 Quick Start

Get from a clean clone to a reviewed MP4 in five steps.

## 1. Install

```sh
git clone https://github.com/fiwon123/viral-short-videos-ai.git
cd viral-short-videos-ai
python -m pip install -r requirements.txt
npm ci --ignore-scripts
python video.py doctor
```

For SVG or 3D renders, install Node.js 22+ and Chrome or Chromium. For local neural voices, use Python 3.10–3.13 and install `requirements-voice.txt`, then add `kokoro-v1.0.int8.onnx` and `voices-v1.0.bin` under `audio-models/`.

> [!NOTE]
> `python video.py doctor` reports FFmpeg, Node, Chrome, Kokoro, and the H.264 encoder. Fix anything marked missing before rendering.

## 2. Create a workspace

```sh
mkdir -p workspace/my-channel/channel
```

Create `workspace/my-channel/channel/channel.json`:

```json
{
  "name": "My Channel",
  "handle": "@MyChannel",
  "tagline": "Small stories. Big turns.",
  "description": "Original animated micro-stories.",
  "tags": ["animated short", "micro story"],
  "mark": "MC",
  "palette": {
    "background": "#101820",
    "foreground": "#FFF4E1",
    "accent": "#FF9F68",
    "secondary": "#284B63"
  }
}
```

Then create the brand kit and copy/paste page:

```sh
python video.py brand workspace/my-channel/channel/channel.json --out workspace/my-channel/channel/brand
```

This writes `brand/logo.png`, `brand/banner.png`, `brand/banner-safe-preview.png` and `channel/channel.md`.

## 3. Create an episode

```sh
mkdir -p workspace/my-channel/episodes/my-first-episode
```

Start with a five-second episode:

```json
{
  "title": "My First Episode",
  "description": "A five-second test.",
  "tags": ["animated short"],
  "width": 540,
  "height": 960,
  "fps": 24,
  "max_seconds": 5,
  "thumbnail": {"shot": "A", "text": "FIRST TEST"},
  "scenes": [
    {"id": "S1", "purpose": "A single readable beat.", "shots": [
      {"id": "A", "duration": 4,
       "layers": [
         {"id": "bg", "kind": "rect", "x": 0.5, "y": 0.5, "width": 1.2, "height": 1.2, "fill": "background"},
         {"id": "ball", "kind": "ellipse", "x": 0.5, "y": 0.5, "width": 0.2, "height": 0.2, "fill": "accent",
          "keyframes": [{"at": 1, "y": 0.3, "ease": "spring"}]}
       ]}
    ]}
  ]
}
```

## 4. Validate and preview

```sh
python video.py validate workspace/my-channel/episodes/my-first-episode/episode.json \
  --channel workspace/my-channel/channel/channel.json

python video.py render workspace/my-channel/episodes/my-first-episode/episode.json \
  --channel workspace/my-channel/channel/channel.json \
  --renderer hyperframes --preview
```

The package appears under `workspace/my-channel/renders/my-first-episode-preview/`.

## 5. Review and render

Open `video.mp4` on a phone, with sound and muted. Check the hook, caption timing, contact frames and the payoff. Then render the master:

```sh
python video.py render workspace/my-channel/episodes/my-first-episode/episode.json \
  --channel workspace/my-channel/channel/channel.json \
  --renderer hyperframes
```

## 🧰 Shortcuts

```sh
make status
make assets
make audio EPISODE=workspace/my-channel/episodes/my-first-episode/episode.json
make preview EPISODE=workspace/my-channel/episodes/my-first-episode/episode.json
make render EPISODE=workspace/my-channel/episodes/my-first-episode/episode.json
```

> [!TIP]
> If discovery finds several channels or episodes, pass `CHANNEL=` and `EPISODE=` explicitly or pin them in `.env`.

## Next

- [Workspace Layout](Workspace-Layout)
- [Manifest Reference](Manifest-Reference)
- [AI Workflow and Prompt Cookbook](AI-Workflow-and-Prompt-Cookbook)
- [Examples](Examples)
