# 🎬 Viral Short Videos

An AI-assisted studio for making original animated videos from the first channel idea to a finished MP4. Choose the direction and the episode. The assistant researches, writes, and designs the video, then the local studio animates, mixes, captions, and exports it.

**Up to 12 minutes · 2D, 2.5D, and 3D · Editable production files · Offline rendering**

## 🧭 How a video gets made

| Stage | What you get |
| --- | --- |
| **Discover a direction** | A sourced comparison of at least five channels when enough recent data is available. See the last seven days of examples, public view counts, recurring formats, and likely performance drivers. |
| **Build the channel** | A consistent identity with a name, description, logo, banner, tags, and a brief for future episodes. |
| **Choose an episode** | A short list of original concepts with a hook, payoff, visual approach, and estimated runtime. The assistant can also break down a reference by timestamp. |
| **Produce the video** | A shot-by-shot script, animated layers, timed speech, sound effects, optional music, and captions aligned to the voice takes. |
| **Prepare for publishing** | A verified MP4, thumbnail, subtitle file when applicable, and ready-to-copy title, description, and tags. |

## 🤖 Start in ChatGPT

1. **Create a ChatGPT project** for the channel and add the [Viral Video Studio skill](.agents/skills/viral-video-studio/SKILL.md) as a source. Add the guide you need for [channel discovery and branding](.agents/skills/viral-video-studio/references/discovery.md), [reference analysis](.agents/skills/viral-video-studio/references/reference.md), or [episode production](.agents/skills/viral-video-studio/references/production.md). For production, also add the [JSON schema](studio/schema.json). [ChatGPT project guide](https://learn.chatgpt.com/docs/projects)
2. **Start with a creative choice.** If you have an approved channel, add its brief and `channel.json` so the assistant can reuse the identity.
3. **Render where the media tools are available.** If the chat can access the repository and run the CLI, ask it to render and verify the export. Otherwise, ask for the editable `episode.json` and assets, then use the local commands below.

> Use the attached Viral Video Studio workflow. Compare five distinct channels with strong videos from the past seven days, then give me three original channel directions to choose from.

**Using Codex or Claude Code?** Open the repository and ask for the Viral Video Studio workflow. Both entry points use the shared [project instructions](AGENTS.md). In Codex, you can invoke `$viral-video-studio` directly. [OpenAI skills guide](https://learn.chatgpt.com/docs/build-skills)

## ⚙️ Render an episode locally

Use Python 3.10+ and FFmpeg with FFprobe, AAC, and either `libx264` or `libopenh264`. Install eSpeak NG for synthetic dialogue or supply a recorded or generated audio file for each line.

Run these commands from the repository root on macOS or Linux.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python video.py doctor
```

Use the skill to create a `channel.json` and `episode.json` that follow the schema. Save them under `channels/<slug>/` and `episodes/<slug>/` and replace the slugs below with yours.

```sh
channel=channels/my-channel/channel.json
episode=episodes/my-episode/episode.json

python video.py brand "$channel" --out output/my-channel-brand
python video.py validate "$episode" --channel "$channel"
python video.py render "$episode" --channel "$channel" --out output/my-episode
```

Use a fresh output directory for each run. Add `--preview` to render at half resolution or `--no-burn` to keep captions in a separate SRT file.

## 🎥 Consistent visuals with Remotion, HyperFrames, and Three.js

Render a single episode manifest with either browser backend. Both consume the same resolved shot timings, audio, subtitle cues, channel graphics, and 3D assets. The existing Python renderer is still available for 2D projects.

| Tool | Role in the studio |
| --- | --- |
| **Remotion** | React composition and frame-by-frame rendering. [Remotion rendering docs](https://www.remotion.dev/docs/renderer/render-media) |
| **HyperFrames + GSAP + SVG** | Default workflow for vector-led 2D and 2.5D. Reuse SVG artwork and animate its layers on the episode clock. [HyperFrames composition docs](https://hyperframes.heygen.com/concepts/compositions) |
| **Three.js** | Optional 3D shots with reusable models, lighting, cameras, and frame-driven movement. [Three.js renderer docs](https://threejs.org/docs/pages/WebGLRenderer.html) |

Install Node.js 22 or later and Chrome or Chromium. Run `npm ci --ignore-scripts` from the repository root. Set `STUDIO_CHROME` if the browser lives outside the standard install paths. HyperFrames uses VP9 as an intermediate on FFmpeg builds without libx264. Follow the [Remotion license terms](https://www.remotion.dev/docs/terms) for your use case. Set `REMOTION_LICENSE_KEY` in your environment if your license uses a key.

```sh
npm ci --ignore-scripts

python video.py render episodes/my-episode/episode.json --channel channels/my-channel/channel.json \
  --renderer hyperframes --preview --out output/my-episode-preview
```

Use `kind: "svg"` for vector art, `asset_scope: "channel"` for shared channel SVGs, and `plane: "background"` to place flat art behind the Three.js stage. Foreground graphics and captions sit above the 3D scene. Use `--renderer remotion` for the same manifest in a React workflow. Add the [renderer guide](.agents/skills/viral-video-studio/references/renderers.md) as a project source when planning vector or mixed episodes in ChatGPT.

## 📦 What the studio saves

| Output | Contents |
| --- | --- |
| **Episode package** | `video.mp4`, `thumbnail.png`, `captions.srt` when there are caption cues, and `publishing.json` with the title, description, and tags. |
| **Production record** | `timed-script.md`, frame-based `timeline.json`, and `qa.json` with the verified runtime, frame count, resolution, codecs, and caption count. |
| **Channel kit** | `logo.png`, `banner.png`, a banner safe-area preview, and channel publishing metadata. |
| **Reference breakdown** | Contact sheet, sampled frames, candidate cut timestamps, extracted audio, and supported embedded text captions when available. |

## 🗂️ What belongs in the template

Git tracks the skill, shared instructions, schema, CLI, renderers, and dependency manifests. The `studio/` and `browser/` directories render whichever channel and episode you pass in.

Keep channel assets in `channels/`, episode sources in `episodes/`, discovery notes in `research/`, and source videos in `reference-media/`. Git ignores these directories, local demos in `examples/`, and rendered packages in `output/`.

## 🔎 Optional YouTube discovery

With the YouTube Data API enabled and `YOUTUBE_API_KEY` set in your environment, sample recent videos across several queries.

```sh
python video.py discover --region BR --language pt \
  --query "animação curta" --query "história animada"
```

The CLI ranks distinct channels within the sample by the strongest sampled video's public view count. The assistant checks the source pages for genres, formats, and likely performance drivers. Use browser research for other platforms or when working without a key. [YouTube search reference](https://developers.google.com/youtube/data/reference/rest/v3/search/list) · [Video statistics reference](https://developers.google.com/youtube/data/reference/rest/v3/videos/list)
