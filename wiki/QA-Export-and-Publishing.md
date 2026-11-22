# ✅ QA, Export and Publishing

Every Short goes through the same checks, in the order you work. Each one measures something you would otherwise have to notice by eye, and each one tells you how to fix what it finds.

| ✅ Ready | ❌ Revise |
| --- | --- |
| Hook and payoff are clear on a phone, with the sound off. | The key action is hidden or only understandable with sound. |
| Something new lands every few seconds; the end moves. | The picture holds, drifts or ends on a frozen frame. |
| Every hit, click and pop lands on its frame. | A sound arrives before or after the action it belongs to. |
| `make deliver` is green or every amber item is explained. | Delivery is refused, or the notes do not say why an amber item is fine. |

## 🗺️ The checks at a glance

| Stage | Command | What it proves |
| --- | --- | --- |
| Plan | `make treatment-lint EPISODE=...` | The shot plan has a hook, varied shot sizes, a camera with a job and an energy curve with a peak and a landing. |
| Build | `make validate EPISODE=...` | The manifest is valid and nothing is authored that silently does less than it says: the camera leaving the set, a camera that drifts there and back, keys under a frame apart, 3D contacts. |
| Sound | `make audio` · `make narration-check` | The mix, and every spoken line heard back against the script. |
| Frames | `make still` · `check-visual` | Composition, contacts, captions and continuity on the frames that matter. |
| Render | `make preview` · `make render` | Every render measures its own picture and sound (`film-qa/`). |
| Review | `make review-pack` · `make review` | Cold reviewers get the evidence they need; you leave notes on the frame itself. |
| Deliver | `make deliver` | The master decodes, sounds right and passes every gate; the facts are sealed in `delivery.md`. |
| Resume | `make state` | The stage the files on disk prove, and the exact next command. |

> [!TIP]
> Run `make state EPISODE=...` whenever you come back to an episode. It reads the evidence, not a status line someone forgot to update.

## 🔍 Validate

```sh
make validate EPISODE=workspace/my-channel/episodes/episode/episode.json
```

Checks the schema, duplicate IDs, parent cycles, camera keys, asset paths, SVG safety, runtime, thumbnail references and the channel's style lock. It also warns about authoring that will not look the way it reads:

| Warning | Meaning | Fix |
| --- | --- | --- |
| The camera's view leaves this backdrop | A pan or pull-out shows empty canvas past the edge of the set. | Draw the set larger than the frame (or give the layer a larger `width`/`height`), or keep the camera inside it. |
| The camera pushes or pans one way and comes back | Inside one setup, the camera returns half of a move within a second: it reads as a wobble. | Let the move land and hold, or cut to the new framing with a `hold` key. |
| Keys under one frame apart | The change snaps instead of moving. | Space the keys or use a `hold` ease. |

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

Use them on the frames that matter: contacts, pose swaps, cuts and camera moves. Render the treatment's key stills with `make still` before the first preview.

## 🔊 Audio QA

```sh
make audio EPISODE=workspace/my-channel/episodes/episode/episode.json
make narration-check EPISODE=workspace/my-channel/episodes/episode/episode.json
```

Listen to `mix.wav`, read `timeline.json` and `audio-qa.json`. Check that speakers are distinct, the same performer carries across cuts, contacts land on the visible contact and the mix survives a phone speaker.

`make narration-check` transcribes each line's take and compares it with the script, counting a `spoken_text` respelling and numbers said as words as correct. It reports:

| Note | Meaning |
| --- | --- |
| `unheard` | Nothing intelligible, or most of the words wrong. |
| `misread` | A quarter of the words differ, or a long word (a name, a key term) is missing. |
| `number` | A number in the script is not the number heard. |
| `repeat` | A word is said twice that the script says once. |

Fix the take before animating to it: respell the word in `spoken_text`, slow the `pace`, or re-voice. Mark a line `"narration": false` when it is a stylised voice no recogniser can hear.

## 🎞️ Film QA

Every render writes `film-qa/` beside the MP4: `report.json`, `energy.png` (the motion curve with cuts and dead runs) and `sheet.png` (a contact sheet). Run it on any video with `make film-qa VIDEO=...`. It reads the pixels and the sound, not the manifest, so it catches what the plan promised but the picture did not deliver.

| Note | Level | Meaning |
| --- | --- | --- |
| `first-frame` | 🔴 | Frame 0 is a different picture from the opening, so the feed shows the wrong poster. |
| `frozen-end` | 🔴 | The film ends on a still frame. |
| `dead` | 🟠 / 🔴 | Nothing moves for 0.8 s or more outside a planned stop (1.5 s or more is red). |
| `nothing-new` | 🟠 | Things move, but no cut, sound, caption change or action lands for over 4 s. |
| `one-framing` | 🟠 / 🔴 | One framing holds for over 6 s (12 s is red). |
| `flat` · `no-burst` · `slow-open` | 🟠 / 🔴 | The energy curve has no shape: no peak, or a slow first second. |
| `pop` · `ghost-cut` | 🔴 | A single frame jumps away and back, or a frame blends the shots on both sides of a cut. |
| `blank` | 🔴 | Empty frames mid-film. |
| `sound-early` · `sound-late` | 🟠 | A hit, click or pop lands before or after the frame its action starts or stops on. |
| `music-join` | 🟠 | The music was fitted to length with a join that jumps in loudness. |
| `off-beat` | ⚪ | In a montage, most cuts miss the beat. |

Declare planned stillness in the episode's `treatment.md` with `Stop: 8.1-8.4`, and a film that is one travelling camera with `Route: continuous`.

## 🧑‍⚖️ Review

```sh
make review-pack EPISODE=workspace/my-channel/episodes/episode/episode.json
```

Prepares a folder for reviewers who did not make the film, one prompt per lens:

| Lens | Evidence | Looks for |
| --- | --- | --- |
| Director | Contact sheet, energy chart, film-QA report, treatment, key stills | What happens in each beat with the words covered, where the film starts to lose you, the three notes that matter most. |
| Sound | The soundtrack drawn as a level curve with every cue and cut marked, the cue table with its sync status | A sound on frame one, hits on their frames, a visible cause for every sound, restraint on the payoff, the music's joins, the end. |
| Continuity | The frames on both sides of every cut, the key stills | Feet on the floor, props in the right hands, direction and scale across cuts, layering, set edges, one style. |

Each reviewer starts their notes with a `Reviewed:` line naming the render and its fingerprint, so the delivery can tell which file every review judged. Use `LENS=sound` (or `continuity`, `director`) for one lens only.

To give notes yourself, open the render and point at the frame:

```sh
make review EPISODE=workspace/my-channel/episodes/episode/episode.json
```

Pause on the moment, click the spot, write what should change. Your assistant reads the notes with `make comments EPISODE=...`, which also writes the frame with the spot circled and a close-up of it, changes only what each note is about, and answers with `make comments EPISODE=... DONE=c1 REPLY="what changed"`. The page shows the reply.

## 📬 Deliver

```sh
make deliver EPISODE=workspace/my-channel/episodes/episode/episode.json
```

Runs every gate on the master and writes `delivery.md` beside it:

- film QA, the treatment and the viral check;
- a full decode of the file (a damaged file is refused);
- the delivered sound: loudness against the channel's target, a true peak over −1 dBTP, a sound cut off on the last frame, a silent mix;
- the narration check;
- the review notes, with the render each one judged.

A red verdict or a damaged file is refused. Amber items are listed for you to answer in the maker's notes below the facts. The facts section is sealed: `make deliver VERIFY=.../delivery.md` tells you whether anyone edited it or the MP4 since.

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
| `timeline.json` | Resolved timeline, sound cues and music plan |
| `qa.json` | Codecs, runtime, loudness, captions, film-QA verdict |
| `visual-qa.json` | Visual check report |
| `film-qa/` | Energy chart, contact sheet and the full film-QA report |
| `delivery.md` | Sealed delivery facts and your notes, after `make deliver` |

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

After uploading, `make published EPISODE=...` marks the episode and archives its upload files.

## 🧹 Housekeeping

```sh
make clean-cache
make clean-previews
make prune-casting
make prune-brand
```

Prune commands are dry runs. Add `APPLY=1` only after reading the list. Never prune an asset a manifest still points at.

## 🔗 Related guides

- [Audio and sound design](Audio-and-Sound-Design)
- [Motion, camera and rigs](Motion-Camera-and-Rigs)
- [Troubleshooting](Troubleshooting)
- [Contributing](Contributing)
