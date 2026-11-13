# 🎬 Complete examples

These are small, original channel workspaces that show the full studio flow:
channel identity → episode source → audio and visual checks → rendered package
→ publishing copy.

| Example | Renderer | What it shows |
| --- | --- | --- |
| [orbit-workshop](orbit-workshop) | Python | 2D/2.5D layers, karaoke captions, Foley and a finished package |
| [paper-crane](paper-crane) | Python | Parented rig, camera push-in, karaoke slide, whip transition and post |
| [tiny-signal](tiny-signal) | HyperFrames | Three.js scene library, PBR/emissive materials, camera move and mastered mix |

Each example contains:

```text
<example>/
├── channel/
│   ├── channel.json       # machine-readable identity
│   ├── channel.md         # generated copy/paste page
│   ├── brief.md
│   └── brand/
├── episodes/<episode>/
│   └── episode.json
├── research/
└── renders/<episode>-preview/
    ├── video.mp4
    ├── thumbnail.png
    ├── captions.srt
    └── publishing.md
```

Render one again:

```sh
python video.py render examples/orbit-workshop/episodes/the-robot-who-unplugged-the-moon/episode.json \
  --channel examples/orbit-workshop/channel/channel.json \
  --renderer python --preview --out output/example-previews/orbit-workshop
```

The `renders/` folders are small previews, not full-resolution masters. They
exist so a new user can see the expected package before spending render time.
