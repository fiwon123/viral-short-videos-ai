# 🎬 Viral Short Videos

An AI-assisted studio for making original animated videos from the first channel idea to a finished MP4. Choose the direction and the episode. The assistant researches, writes, and designs the video, then the local studio animates, mixes, captions, and exports it.

**Up to 12 minutes · Layered 2D animation · Editable production files · Offline rendering**

<img src="examples/thumbnail.png" alt="Demo thumbnail showing a mint-green robot beneath a golden moon and the words Wrong Button" width="240">

*The Robot Who Unplugged the Moon — a 14-second vertical demo rendered from the bundled [episode] and [channel] files.*

[episode]: examples/episode.json
[channel]: examples/channel.json

## 🧭 How a video gets made

| Stage | What you get |
| --- | --- |
| **Discover a direction** | A sourced comparison of at least five channels when enough recent data is available. See the last seven days of examples, public view counts, recurring formats, and likely performance drivers. |
| **Build the channel** | A consistent identity with a name, description, logo, banner, tags, and a brief for future episodes. |
| **Choose an episode** | A short list of original concepts with a hook, payoff, visual approach, and estimated runtime. The assistant can also break down a reference by timestamp. |
| **Produce the video** | A shot-by-shot script, animated layers, timed speech, sound effects, optional music, and captions aligned to the voice takes. |
| **Prepare for publishing** | A verified MP4, thumbnail, subtitle file when applicable, and ready-to-copy title, description, and tags. |

## 🤖 Start in ChatGPT

1. **Create a ChatGPT project** for the channel and add the [Viral Video Studio skill](.agents/skills/viral-video-studio/SKILL.md) as a source. Add the guide you need for [channel discovery and branding](.agents/skills/viral-video-studio/references/discovery.md), [reference analysis](.agents/skills/viral-video-studio/references/reference.md), or [episode production](.agents/skills/viral-video-studio/references/production.md). For production, also add the [JSON schema](studio/schema.json) and the sample [episode] and [channel] files. [ChatGPT project guide](https://learn.chatgpt.com/docs/projects)
2. **Start with a creative choice.** If you have an approved channel, add its brief and `channel.json` so the assistant can reuse the identity.
3. **Render where the media tools are available.** If the chat can access the repository and run the CLI, ask it to render and verify the export. Otherwise, ask for the editable `episode.json` and assets, then use the local commands below.

> Use the attached Viral Video Studio workflow. Compare five distinct channels with strong videos from the past seven days, then give me three original channel directions to choose from.

**Using Codex or Claude Code?** Open the repository and ask for the Viral Video Studio workflow. Both entry points use the shared [project instructions](AGENTS.md). In Codex, you can invoke `$viral-video-studio` directly. [OpenAI skills guide](https://learn.chatgpt.com/docs/build-skills)

## ⚙️ Render the demo locally

Use Python 3.10+ and FFmpeg with FFprobe, AAC, and either `libx264` or `libopenh264`. The demo uses eSpeak NG for synthetic dialogue. For your own episode, you can supply a recorded or generated audio file for each line.

Run these commands from the repository root on macOS or Linux.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python video.py doctor
```

```sh
python video.py brand examples/channel.json --out output/example-brand
python video.py validate examples/episode.json --channel examples/channel.json
python video.py render examples/episode.json --channel examples/channel.json --out output/example-render
python video.py analyze output/example-render/video.mp4 --out output/example-reference
```

Use a fresh output directory for each run. Add `--preview` to render at half resolution or `--no-burn` to keep captions in a separate SRT file.

## 📦 What the studio saves

| Output | Contents |
| --- | --- |
| **Episode package** | `video.mp4`, `thumbnail.png`, `captions.srt` when there are caption cues, and `publishing.json` with the title, description, and tags. |
| **Production record** | `timed-script.md`, frame-based `timeline.json`, and `qa.json` with the verified runtime, frame count, resolution, codecs, and caption count. |
| **Channel kit** | `logo.png`, `banner.png`, a banner safe-area preview, and channel publishing metadata. |
| **Reference breakdown** | Contact sheet, sampled frames, candidate cut timestamps, extracted audio, and supported embedded text captions when available. |

Keep approved channel files in `channels/<slug>/` and episode manifests and source assets in `episodes/<slug>/`. Any assistant can edit the JSON and pick up where the previous session left off.

## 🔎 Optional YouTube discovery

With the YouTube Data API enabled and `YOUTUBE_API_KEY` set in your environment, sample recent videos across several queries.

```sh
python video.py discover --region BR --language pt \
  --query "animação curta" --query "história animada"
```

The CLI ranks distinct channels within the sample by the strongest sampled video's public view count. The assistant checks the source pages for genres, formats, and likely performance drivers. Use browser research for other platforms or when working without a key. [YouTube search reference](https://developers.google.com/youtube/data/reference/rest/v3/search/list) · [Video statistics reference](https://developers.google.com/youtube/data/reference/rest/v3/videos/list)
