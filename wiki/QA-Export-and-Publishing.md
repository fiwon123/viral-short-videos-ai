# ✅ QA, Export and Publishing

A render is not finished when the MP4 appears. It is finished when the picture, sound, captions and copy are all checked.

## 🔍 Validate

```sh
python video.py validate workspace/my-channel/episodes/episode/episode.json \
  --channel workspace/my-channel/channel/channel.json
```

Checks schema, duplicate IDs, parent cycles, camera keys, asset paths, SVG safety, runtime and thumbnail references.

## 🧱 Visual QA

```sh
python video.py check-visual workspace/my-channel/episodes/episode/episode.json \
  --channel workspace/my-channel/channel/channel.json
```

Runs the declared checks:

- `keep_in_frame`
- `avoid_2d`
- `avoid_3d`
- `floor`
- `contacts`
- `continuity`

Use them on the frames that matter: contacts, pose swaps, cuts and camera moves.

## 🔊 Audio QA

```sh
make audio EPISODE=workspace/my-channel/episodes/episode/episode.json
```

Listen to `mix.wav`, read `timeline.json` and `audio-qa.json`. Check:

- Speakers are distinct.
- The same performer carries across cuts.
- Contacts land on the visible contact.
- Loudness is near the target.
- The mix survives a phone speaker.

## 📦 Package

```sh
make render EPISODE=workspace/my-channel/episodes/episode/episode.json
```

| File | Use |
| --- | --- |
| `video.mp4` | Upload |
| `thumbnail.png` | Cover |
| `captions.srt` | Upload or review |
| `publishing.md` | Copy/paste guide |
| `publishing.json` | Machine-readable copy |
| `timed-script.md` | Per-shot record |
| `timeline.json` | Resolved timeline |
| `qa.json` | Codecs, runtime, loudness, captions |
| `visual-qa.json` | Visual check report |

## 🏷️ Channel copy

`channel/channel.md` is generated from `channel.json`:

```sh
python video.py channel-doc workspace/my-channel/channel/channel.json
```

It contains the channel description, tags and TikTok bio, ready to paste.

## 📺 Platform fields

| Platform | Field | Source |
| --- | --- | --- |
| YouTube | Title | episode `title` |
| YouTube | Description | episode `description` |
| YouTube | Tags | episode `tags` |
| YouTube | Shorts | vertical upload + `#Shorts` where relevant |
| TikTok | Caption | `publishing.md` TikTok block |
| TikTok | Hashtags | inline in the caption |
| Both | Channel identity | `channel.md` |

> [!WARNING]
> `publishing.md` flags fields over the platform limit. Fix those before uploading.

## 🧹 Housekeeping

```sh
make clean-cache
make clean-previews
make prune-casting
make prune-brand
make prune-legacy
```

Prune commands are dry runs. Add `APPLY=1` only after reading the list. Never prune an asset a manifest still points at.

## Next

- [Troubleshooting](Troubleshooting)
- [Contributing](Contributing)
