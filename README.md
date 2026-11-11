# 🎬 Viral Short Videos

[![Format: Animated Shorts](https://img.shields.io/badge/Format-Animated%20Shorts-6d4aff)](.agents/skills/viral-video-studio/references/shorts.md)
[![Animation: 2D, 2.5D, and 3D](https://img.shields.io/badge/Animation-2D%20%7C%202.5D%20%7C%203D-0f766e)](.agents/skills/viral-video-studio/references/renderers.md)
[![Workflow: Research to MP4](https://img.shields.io/badge/Workflow-Research%20to%20MP4-2563eb)](.agents/skills/viral-video-studio/SKILL.md)

A reusable template for turning a video idea into an original channel and a finished episode. The built-in studio focuses on **animated Shorts** and supports animated videos up to **12 minutes**. You can reuse the research, scripting, and publishing steps for other genres with your own production tools.

## ✨ What you can create

- **An original channel.** Get a name, description, tags, logo, banner, and a brief that keeps the look, characters, voices, and episode format consistent.
- **Animated episodes.** Make character comedy, visual gags, short stories, or animated explainers in 2D, 2.5D, or 3D. Get a timed script, a rough cut to review on your phone, and a finished MP4 with sound and captions where needed.
- **A publishing package.** Get a thumbnail, YouTube title, description, and tags, plus a TikTok caption with hashtags. The finished files and copy are ready for you to review and publish.

## 🚀 Start from zero

1. **Open the repository.** On GitHub, use **Code** to clone or download the repository. Open the folder in Codex, Claude Code, or an assistant that can access your workspace.
2. **Tell the assistant where to start.** Use one of the prompts below. Add your audience, language, platform, genre, preferred length, or a reference link if you have one.
3. **Pick a direction and a pilot.** The assistant builds the brand for your chosen direction and turns the episode into a rough cut. Review the opening and payoff on a phone before the full render.

| If you want to… | Ask the assistant |
| --- | --- |
| 🔎 **Find a direction** | “Use this repository’s workflow. Show me at least five relevant channels with strong Shorts from the last seven days, where reliable data is available. Then give me three original channel ideas.” |
| 🧭 **Start a channel** | “Help me start an original animated comedy channel. Give me three directions with an audience, a repeatable episode format, and a first video idea. Build the brand kit after I pick one.” |
| 🎞️ **Make a video** | “Use my channel brief. Give me three episode ideas with a hook and payoff. After I choose, make a rough cut and carry it through the final video and publishing package.” |

**Already have an idea?** Give it to the assistant and start there. Use references to study timing, staging, and payoff, then develop your own characters, settings, artwork, and dialogue. Use audience response after publishing to decide what to test next.

## 🤖 Use it with your assistant

- **Codex or Claude Code.** Open the repository and ask the assistant to follow the [production workflow](.agents/skills/viral-video-studio/SKILL.md). In Codex, you can also invoke `$viral-video-studio`.
- **ChatGPT.** Attach [SKILL.md](.agents/skills/viral-video-studio/SKILL.md). For channel ideas, also attach [discovery and branding](.agents/skills/viral-video-studio/references/discovery.md). For an episode, attach [production](.agents/skills/viral-video-studio/references/production.md), [Shorts planning](.agents/skills/viral-video-studio/references/shorts.md), and the [episode schema](studio/schema.json). If the chat can’t run the renderer, ask for the editable files and render locally.

## 🛠️ Render locally

Install Python 3.10+ and FFmpeg with FFprobe. From the repository folder, install the Python packages with `python -m pip install -r requirements.txt`, then run `python video.py doctor` to check your setup. For SVG or 3D projects, install Node.js 22+ and Chrome or Chromium, then run `npm ci --ignore-scripts`.

Once the assistant has saved the channel and episode files, use the export command it provides. The default animation workflow uses [HyperFrames with GSAP/SVG and optional Three.js](.agents/skills/viral-video-studio/references/renderers.md). Recorded dialogue and local voice options are covered in the [audio guide](.agents/skills/viral-video-studio/references/audio.md).

Channel assets, episodes, research, and exports stay in your local project folders. The repository carries the reusable workflow and tools into each new clone.
