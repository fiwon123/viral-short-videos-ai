# 🗂️ Workspace Layout

Every channel lives in one workspace folder. Inputs, research and generated renders stay together.

## ✅ Workspace layout

```text
workspace/<channel>/
├── channel/
│   ├── channel.json      # machine-readable identity
│   ├── channel.md        # generated copy/paste page
│   ├── brief.md
│   ├── brand/
│   ├── art/
│   ├── audio/
│   ├── scene-library/
│   └── vfx/
├── episodes/
│   └── <episode>/
│       ├── episode.json
│       └── assets/
├── research/
│   └── notes.md
└── renders/
    └── <episode>-v1/
        ├── video.mp4
        ├── thumbnail.png
        ├── captions.srt
        ├── publishing.md
        ├── timeline.json
        └── qa.json
```

Why one folder per channel:

- Easy to zip, archive or share.
- Input and generated output stay together.
- The channel brief, research and renders are in one place.
- The public repo can show the same structure under `examples/` without exposing private work.

Shared research that applies to several channels lives in:

```text
workspace/_shared/research/
```

## 🧾 What is tracked

| Path | Tracked? | Purpose |
| --- | --- | --- |
| `studio/`, `browser/`, `presets/`, `wiki/` | ✅ | Reusable studio, renderers and docs |
| `examples/` | ✅ | Public, original showcase workspaces |
| `workspace/` | ❌ | Your private production data |
| `reference-media/` | ❌ | Private source videos |
| `.env`, `audio-models/` | ❌ | Machine-local defaults and models |

## 📝 Channel Markdown

Generate `channel.md` from `channel.json`:

```sh
python video.py channel-doc workspace/my-channel/channel/channel.json
```

It contains:

- Identity table
- Palette swatches
- YouTube channel description and tags
- TikTok bio with hashtags
- Brand asset links
- A “where to paste” table

> [!TIP]
> Keep `channel.json` as the source of truth. Regenerate `channel.md` after editing the JSON; do not maintain both by hand.

## 🔗 Related guides

- [Core Concepts](Core-Concepts)
- [QA, Export and Publishing](QA-Export-and-Publishing)
- [Troubleshooting](Troubleshooting)
