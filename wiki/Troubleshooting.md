# 🧰 Troubleshooting

Start with `python video.py doctor` for environment issues and `make status` for channel or episode selection.

| What you see | What to check first |
| --- | --- |
| ❌ Several channels or episodes found | Pass explicit `CHANNEL=` and `EPISODE=` paths. |
| ❌ SVG or Three.js renderer error | Choose HyperFrames or Remotion and check Chrome. |
| ⚠️ Missing voice or sound | Check the speaker or cue in the channel’s audio library. |
| ❌ Output already exists | Pick a new output path for the next version. |

## Several channels or episodes found

Discovery stops when more than one candidate exists. Pass the path explicitly:

```sh
make status
make render CHANNEL=workspace/my-channel/channel/channel.json \
  EPISODE=workspace/my-channel/episodes/my-episode/episode.json
```

Or pin them in `.env`.

## `Three.js shots require --renderer remotion or hyperframes`

Use a browser renderer:

```sh
--renderer hyperframes
```

## `SVG layers require --renderer hyperframes or remotion`

The Python renderer only handles raster shapes. Switch to HyperFrames or Remotion, or use PNG layers.

## Chrome or Node missing

```sh
python video.py doctor
npm ci --ignore-scripts
```

Set `STUDIO_CHROME=/path/to/chrome` if Chrome is not in a standard location.

## Kokoro missing

- Use Python 3.10–3.13.
- Install `requirements-voice.txt`.
- Put `kokoro-v1.0.int8.onnx` and `voices-v1.0.bin` in `audio-models/`.
- Or set `STUDIO_KOKORO_MODEL` and `STUDIO_KOKORO_VOICES`.

## `A has no cast profile for Narrator`

The channel has an `audio_library`, but the speaker is not in it. Add the profile or use a channel without an audio library for scratch work.

## `unknown sound or variant`

The cue references a sound not in the channel library. Run `make sfx`, add the sound, or use a local `file`.

## Parent cycle or unknown parent

A layer’s `parent` must exist in the same shot and share its plane. Check the IDs.

## Camera keys not moving

Camera keyframe `at` values must increase. A `preset` is ignored when explicit `keyframes` are present.

## Audio too quiet or too loud

Read `audio-qa.json`. Set:

```json
{"audio": {"master": {"loudness": -14, "true_peak": -1.5}}}
```

Use `master.enabled: false` only for a deliberate raw master.

## Captions missing

- `render.captions` must not be `false`.
- There must be speech or caption cues.
- `--no-captions` disables both burn and SRT.
- `--no-burn` keeps SRT only.

## `Output already exists`

Use a new `OUT` path. The studio never overwrites a package.

## `make assets` fails on a channel without a scene library

The inventory path now supports channels without 3D. If you see this on an old checkout, update the repository.

## Wiki page is missing

The GitHub Wiki is edited in the repository's Wiki tab. The `wiki/` folder is a versioned mirror; copy the page there when the live wiki changes.

## 🔗 Related guides

- [Quick Start](Quick-Start)
- [Workspace Layout](Workspace-Layout)
- [Contributing](Contributing)
