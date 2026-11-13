# 🧪 Examples

Three complete, original workspaces live in [`examples/`](https://github.com/fiwon123/viral-short-videos-ai/tree/main/examples). They are small public previews, not full-resolution masters.

## 🎬 Orbit Workshop

Path: [`examples/orbit-workshop`](https://github.com/fiwon123/viral-short-videos-ai/tree/main/examples/orbit-workshop)

- 2D/2.5D robot micro-story
- Karaoke captions
- Layered Foley and a mastered mix
- Preview rendered with the Python renderer

```sh
python video.py render examples/orbit-workshop/episodes/the-robot-who-unplugged-the-moon/episode.json \
  --channel examples/orbit-workshop/channel/channel.json --renderer python --preview
```

## 🕊️ Paper Crane Post

Path: [`examples/paper-crane`](https://github.com/fiwon123/viral-short-videos-ai/tree/main/examples/paper-crane)

- Parented paper-crane rig with a pivot
- Camera push-in
- Karaoke caption with slide animation
- Whip transition and post grain/vignette

```sh
python video.py render examples/paper-crane/episodes/one-letter-home/episode.json \
  --channel examples/paper-crane/channel/channel.json --renderer python --preview
```

## 📡 Tiny Signal

Path: [`examples/tiny-signal`](https://github.com/fiwon123/viral-short-videos-ai/tree/main/examples/tiny-signal)

- Three.js scene library
- PBR and emissive materials
- Camera move and expanding rings
- HyperFrames preview

```sh
python video.py render examples/tiny-signal/episodes/one-small-signal/episode.json \
  --channel examples/tiny-signal/channel/channel.json --renderer hyperframes --preview
```

## 🗂️ What each example contains

```text
<example>/
├── channel/
│   ├── channel.json
│   ├── channel.md
│   ├── brief.md
│   └── brand/
├── episodes/<episode>/episode.json
├── research/notes.md
└── renders/<episode>-preview/
    ├── video.mp4
    ├── thumbnail.png
    ├── captions.srt
    └── publishing.md
```

## 🧭 How to use an example

1. Open `channel/channel.md` to see what the channel is and where each block goes.
2. Open `episodes/<episode>/episode.json` to see the timed source.
3. Watch the preview.
4. Read `renders/<episode>-preview/publishing.md` to see the delivery copy.
5. Copy the structure into `workspace/<your-channel>/` and replace the story and assets.

> [!TIP]
> Do not copy the example characters or copy verbatim. Use the structure and build an original world.

## Next

- [Workspace Layout](Workspace-Layout)
- [Core Concepts](Core-Concepts)
- [QA, Export and Publishing](QA-Export-and-Publishing)
