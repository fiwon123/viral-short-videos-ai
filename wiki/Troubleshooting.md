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

Read `audio-qa.json`, or the "Delivered sound" line in `delivery.md` after `make deliver`. The master reaches the target on sparse and dense mixes alike; set another one with:

```json
{"audio": {"master": {"loudness": -14, "true_peak": -1.5}}}
```

If delivery still reports `loudness` with the true peak at the ceiling, a few very loud hits hold the mix down: lower their `gain` or `punch`, or raise the music or ambience under them. Use `master.enabled: false` only for a deliberate raw master.

## `make deliver` refuses the master

- **A red film-QA or treatment verdict:** read `film-qa/report.json` or run `make treatment-lint`; each note says how to fix it.
- **The file does not decode cleanly:** the MP4 is damaged. Render it again; never upload it.
- Amber items do not block delivery. Answer each one under "Maker's notes" in `delivery.md`.

## Narration check says `unchecked`

The speech recogniser is not available: faster-whisper is not installed (it ships in the studio image; on the host, `pip install -r requirements-voice.txt`) or `STUDIO_ASR=off` is set. An unchecked narration is not a pass.

## `make validate` warns that the camera leaves the backdrop

A pan or pull-out goes past the edge of a frame-size set, so empty canvas shows. Draw the set larger than the frame or keep the camera inside it. Do not pin the set with `parallax: 0` instead: the cast then slides off its floor when the camera zooms.

## `make review` opens on another port

Another studio page (usually `make editor`) holds port 8765, so the review page takes the next free one and prints it. Inside the Docker sandbox only 8765 reaches your browser: stop the other page, or pass `PORT=`.

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

The repository's `wiki/` folder is the source of the GitHub Wiki and is synced to it with each release. Edit the page there, in a pull request.

## 🔗 Related guides

- [Quick Start](Quick-Start)
- [Workspace Layout](Workspace-Layout)
- [Contributing](Contributing)

## Docker sandbox

| Message | Fix |
| --- | --- |
| `the dev image is out of date` | `make dev-build`. The Dockerfile, a requirements file or `package-lock.json` changed; agent logins are kept. |
| `host port 8765 (make editor) is already in use` | Free the port, or `HOST_PORT=8766 make dev-up`. |
| `has CRLF line endings, so bash cannot parse it` | A Windows checkout from before `.gitattributes`: `git rm --cached -r . && git reset --hard`. |
| `these files can hold secrets and would be readable inside the sandbox` | Only `./.env` is hidden from the agents. Move the listed files out of the repository. |
| `make discover` has no API key in the sandbox | Keys are not available there by design. Run `make discover` on the host. |
| `you are already inside the sandbox` | Run the studio commands directly there (`make test`, `make render ...`). |
| An agent asks to sign in again | Its login lives in a Docker volume; only `make reset` removes it. |

`make dev-doctor` checks Docker, the image, the studio inside the sandbox, and each agent's login.
