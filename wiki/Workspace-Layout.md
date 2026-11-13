# 🗂️ Workspace Layout

The studio supports two layouts. **Workspace** is the preferred layout for new channels. **Legacy** remains readable so existing projects do not break.

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

## 🕰️ Legacy layout

```text
channels/<channel>/
episodes/<episode>/
research/
output/<channel>/<episode>-v1/
```

Discovery checks both layouts. `make status` labels each entry `[workspace]` or `[legacy]`.

## 🚚 Migrate one channel

Dry run:

```sh
make migrate CHANNEL=channels/my-channel/channel.json \
  EPISODE=episodes/my-episode/episode.json
```

Apply:

```sh
make migrate CHANNEL=channels/my-channel/channel.json \
  EPISODE=episodes/my-episode/episode.json APPLY=1
```

Research can be moved explicitly:

```sh
python -m studio.migrate channels/my-channel/channel.json \
  --episode episodes/my-episode/episode.json \
  --research research/my-channel-note.md --apply
```

> [!WARNING]
> The migration never guesses which episode belongs to which channel. Pass `--episode` for each episode. If the target already exists, the migration stops instead of overwriting.

## 🧾 What is tracked

| Path | Tracked? | Purpose |
| --- | --- | --- |
| `studio/`, `browser/`, `presets/`, `wiki/` | ✅ | Reusable studio, renderers and docs |
| `examples/` | ✅ | Public, original showcase workspaces |
| `workspace/`, `channels/`, `episodes/` | ❌ | Your private production data |
| `research/`, `reference-media/` | ❌ | Private notes and source videos |
| `output/` | ❌ | Legacy render packages |
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

## Next

- [Core Concepts](Core-Concepts)
- [QA, Export and Publishing](QA-Export-and-Publishing)
- [Troubleshooting](Troubleshooting)
