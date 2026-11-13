<h1 align="center">🎬 Viral Short Videos AI</h1>

<p align="center">
  <strong>An AI-first studio for original animated Shorts.</strong><br>
  Research a niche, build a channel, generate ideas, write timed episodes,<br>
  create audio and VFX, render a verified MP4, and package the upload.
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/fiwon123/viral-short-videos-ai/main/docs/assets/ai-channel-flow.svg" alt="From idea to AI-run channel" width="920">
</p>

<p align="center">
  <img alt="Workflow" src="https://img.shields.io/badge/Workflow-Research%20to%20MP4-2563eb?style=flat-square">
  <img alt="2D 2.5D 3D" src="https://img.shields.io/badge/Animation-2D%20%7C%202.5D%20%7C%203D-0f766e?style=flat-square">
  <img alt="Audio" src="https://img.shields.io/badge/Audio-Mastered%20Stereo-8b5cf6?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-22c55e?style=flat-square">
</p>

> [!TIP]
> New here? Start with **[Quick Start](Quick-Start)**, then open the **[Examples](Examples)** folder and render one.

## 🛤️ Choose your path

| 🎬 Creator path | 🧰 Technical reference |
| --- | --- |
| [Create a Channel](Create-a-Channel) | [Manifest Reference](Manifest-Reference) |
| [Find Ideas](Find-Ideas) | [Audio and Sound Design](Audio-and-Sound-Design) |
| [Create Videos with Prompts](Create-Videos-with-Prompts) | [Motion, Camera and Rigs](Motion-Camera-and-Rigs) |
| [Make Shorts Travel](Make-Shorts-Travel) | [VFX and Post](VFX-and-Post) |
| [YouTube and TikTok Monetization](YouTube-and-TikTok-Monetization) | [Captions and Typography](Captions-and-Typography) |
| [Automate a Channel](Automate-a-Channel) | [3D and Renderers](3D-and-Renderers) |

## 🚦 Start here

| I want to… | Go to |
| --- | --- |
| Make my first video in 5 minutes | [Quick Start](Quick-Start) |
| Create and fill a channel | [Create a Channel](Create-a-Channel) |
| Get ideas that fit a series | [Find Ideas](Find-Ideas) |
| Make a video with prompts | [Create Videos with Prompts](Create-Videos-with-Prompts) |
| Understand why Shorts travel | [Make Shorts Travel](Make-Shorts-Travel) |
| Plan YouTube and TikTok income | [YouTube and TikTok Monetization](YouTube-and-TikTok-Monetization) |
| Turn one video into a system | [Automate a Channel](Automate-a-Channel) |
| Understand the folder layout | [Workspace Layout](Workspace-Layout) |
| Learn the manifest model | [Core Concepts](Core-Concepts) |
| Look up a field | [Manifest Reference](Manifest-Reference) |
| Control camera, motion and rigs | [Motion, Camera and Rigs](Motion-Camera-and-Rigs) |
| Create audio and sound design | [Audio and Sound Design](Audio-and-Sound-Design) |
| Create VFX and transitions | [VFX and Post](VFX-and-Post) |
| Style captions | [Captions and Typography](Captions-and-Typography) |
| Build 3D scenes | [3D and Renderers](3D-and-Renderers) |
| Use AI to make the video | [AI Workflow and Prompt Cookbook](AI-Workflow-and-Prompt-Cookbook) |
| Publish the package | [QA, Export and Publishing](QA-Export-and-Publishing) |
| Fix an error | [Troubleshooting](Troubleshooting) |
| Add a feature or preset | [Contributing](Contributing) |

## 🧭 The pipeline

```mermaid
flowchart LR
  A[Research] --> B[Channel]
  B --> C[Episode manifest]
  C --> D[Audio preview]
  D --> E[Visual preview]
  E --> F[Master render]
  F --> G[Publishing package]
```

## 🗂️ What is in the repo

| Path | Purpose |
| --- | --- |
| `studio/` | Python engine, schema and renderers |
| `browser/` | HyperFrames and Remotion painters |
| `presets/` | Style, camera and finishing presets |
| `examples/` | Three complete public example workspaces |
| `docs/assets/` | Diagrams used by the README and wiki |
| `wiki/` | Source for this wiki |
| `workspace/<channel>/` | Your private channel, episodes, research and renders |
| `channels/`, `episodes/`, `output/` | Legacy local layout, still supported |
| `reference-media/` | Local source videos for study |

## 🎨 What the studio can do

| Area | Controls |
| --- | --- |
| **Motion** | 13 easings, parent/pivot rigs, visible variants, camera presets and shake, motion blur, 2× supersampling |
| **Picture** | Post grade, bloom, blur, grain, vignette, chromatic split, letterbox, blend modes, 17 transitions |
| **Audio** | Kokoro or recorded voices, 32 Foley recipes, layered SFX, pan, reverb, pitch variance, room tone, −14 LUFS master |
| **Captions** | Box, karaoke and minimal styles, word timing, highlight, animation, font and colour controls |
| **VFX** | 18 palette-matched SVGs plus a parameterized Effect Lab |
| **3D** | Three.js scene libraries, PBR materials, emissive objects, GLB clips, ACES tone mapping |
| **Output** | MP4, SRT, thumbnail, timed script, QA report and platform-ready publishing copy |

## 🧪 Examples

| Example | Renderer | Shows |
| --- | --- | --- |
| [Orbit Workshop](Examples#orbit-workshop) | Python | 2D/2.5D layers, karaoke and Foley |
| [Paper Crane Post](Examples#paper-crane-post) | Python | Parented rig, camera push-in, slide caption, whip transition |
| [Tiny Signal](Examples#tiny-signal) | HyperFrames | 3D scene, PBR/emissive materials, camera move |

## 📄 License

MIT. See the repository [LICENSE](https://github.com/fiwon123/viral-short-videos-ai/blob/main/LICENSE).
