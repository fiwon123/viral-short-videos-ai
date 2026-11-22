# 🚀 Quick Start

Run a first local render, then open the MP4 and its publishing package.

> [!TIP]
> To build with an AI assistant, start with **[Create a Channel](Create-a-Channel)** and **[Create Videos with Prompts](Create-Videos-with-Prompts)**.

## 1. Install

**In Docker (recommended with an AI agent).** Install Docker, then:

```sh
git clone https://github.com/fiwon123/viral-short-videos-ai.git
cd viral-short-videos-ai
make models art-models   # voice files, plus depth and cut-out models (optional, about 280 MB)
make shell               # builds the image once, then opens a terminal in the sandbox
```

The image has Python, FFmpeg, eSpeak NG, Node, Chromium, and opencode, Claude Code and Codex. Run the commands below from that terminal, or start an agent directly with `make claude`, `make codex` or `make opencode`.

**On your computer.** Install Python 3.10–3.13, FFmpeg with FFprobe, eSpeak NG, Node.js 22+ and Chrome or Chromium, then:

```sh
git clone https://github.com/fiwon123/viral-short-videos-ai.git
cd viral-short-videos-ai
make setup-host   # venv in audio-models/venv, npm packages, Kokoro voice files
```

> [!NOTE]
> `make doctor` reports FFmpeg, Node, Chrome, Kokoro, and the H.264 encoder. Fix anything marked missing before rendering. `make hardware` shows what your PC can do (AI art, AI video, the 2.5D fallback) and the limits the studio will respect. See [Your PC and Performance](Your-PC-and-Performance).

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

Save this four-second episode as `workspace/my-channel/episodes/my-first-episode/episode.json`.

```json
{
  "title": "My First Episode",
  "description": "A four-second test.",
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
  --renderer python --preview
```

The package appears under `workspace/my-channel/renders/my-first-episode-preview/`.

## 5. Review and render

Open `video.mp4` on a phone, with sound and muted. Check the hook, caption timing, contact frames and the payoff. Then render the master:

```sh
python video.py render workspace/my-channel/episodes/my-first-episode/episode.json \
  --channel workspace/my-channel/channel/channel.json \
  --renderer python
```

## 🧰 Make shortcuts

If you use the same Python environment as above, add `PYTHON=python` to the Make commands. Run these in place of the equivalent CLI commands or pass a fresh `OUT=<dir>` when repeating a render.

```sh
make status
make assets
make audio EPISODE=workspace/my-channel/episodes/my-first-episode/episode.json
make preview RENDERER=python EPISODE=workspace/my-channel/episodes/my-first-episode/episode.json
make render RENDERER=python EPISODE=workspace/my-channel/episodes/my-first-episode/episode.json
```

> [!TIP]
> If discovery finds several channels or episodes, pass `CHANNEL=` and `EPISODE=` explicitly or pin them in `.env`.

### More commands

```sh
make help                                  # every shortcut
make hardware                              # machine profile and AI plans
make preview EPISODE=... HOOK=20           # only the opening 20 seconds
make still EPISODE=... SHOT=A PROGRESS=0.5 # one review frame (SHEET=6 for a contact sheet)
make viral-check EPISODE=... [VIDEO=...]   # hook, pacing, loop, loudness and packaging score
make film-qa VIDEO=... [EPISODE=...]      # energy curve, dead runs, frozen ending, framing (red exits 1)
make treatment-lint EPISODE=...           # the plan in treatment.md, before any shot is built
make state EPISODE=...                    # the stage the files prove, and the next command
make review-pack EPISODE=...              # packet and prompt for a cold director pass
make deliver EPISODE=...                  # gate the master, write sealed delivery.md
make art CHANNEL=... SPEC=... [IMAGE=...]  # a cast member, rigged
make hero EPISODE=... SHOT=A KEEP=title    # moving hook shot
make support                               # renderer support matrix
make parity                                # shared visual fixture across renderers
make presets                               # style presets
make motion MOTION=impact                  # manifest-ready motion recipes
make schema                                # schema wrappers for editor completion
make batch SEASON=workspace/<channel>/season.json
make editor EPISODE=...                    # local shot inspector
make published EPISODE=workspace/<channel>/episodes/<episode> [URL=...]
make archive                               # dry run: clears _old folders, caches, old versions; APPLY=1 to act
```

A finished episode goes to `workspace/<channel>/renders/<episode>-v1/` with the MP4, thumbnail, publishing guide, QA report and captions.

## 🔗 Related guides

- [Workspace Layout](Workspace-Layout)
- [Manifest Reference](Manifest-Reference)
- [AI Workflow and Prompt Cookbook](AI-Workflow-and-Prompt-Cookbook)
- [Examples](Examples)
