<h1 align="center">🎬 Viral Short Videos AI</h1>

<p align="center">
  <a href=".agents/skills/viral-video-studio/references/shorts.md"><img alt="Format: Animated Shorts" src="https://img.shields.io/badge/Format-Animated%20Shorts-6d4aff"></a>
  <a href=".agents/skills/viral-video-studio/references/renderers.md"><img alt="Animation: 2D, 2.5D, and 3D" src="https://img.shields.io/badge/Animation-2D%20%7C%202.5D%20%7C%203D-0f766e"></a>
  <a href=".agents/skills/viral-video-studio/SKILL.md"><img alt="Workflow: Research to MP4" src="https://img.shields.io/badge/Workflow-Research%20to%20MP4-2563eb"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-22c55e"></a>
</p>

A reusable template for turning a video idea into an original channel and a finished episode. The built-in studio focuses on **animated Shorts**, including character comedy, visual gags, short stories, and explainers. It supports 2D, 2.5D, and 3D animation up to 12 minutes. You can reuse the research, scripting, and publishing steps for other genres with your own production tools.

## 🤖 Use any AI model

The workflow is written in Markdown and works with hosted or local models that can follow text instructions. Use ChatGPT, Claude, Codex, OpenCode, another coding assistant, or a model you run yourself. Model quality, available tools, and context size can affect the result and how much review it needs.

1. **If your assistant can access the repository**, open the folder and tell it to follow [SKILL.md](.agents/skills/viral-video-studio/SKILL.md). Run your assistant in the terminal if that is how you normally use it.
2. **If you use a standalone chat or text-only model**, attach or paste [SKILL.md](.agents/skills/viral-video-studio/SKILL.md). Add [discovery and branding](.agents/skills/viral-video-studio/references/discovery.md) for channel work or [production](.agents/skills/viral-video-studio/references/production.md), [Shorts planning](.agents/skills/viral-video-studio/references/shorts.md), and the [episode schema](studio/schema.json) for video work. If the model has limited context, share the guide for one stage at a time and carry the approved brief forward.
3. **Match the work to the tools available.** For live research, give a model without browsing your reference links and verified notes. For rendering, have a model without terminal access return the editable manifests, assets or asset list, and the export command so you can run it locally.

## 🚀 Start where you are

On GitHub, use **Code** to clone or download the repository. Open it in your assistant or share the files above.

**Copy a prompt.** Use the copy icon in the top-right corner of a prompt box on GitHub when it appears. In other viewers, select the text inside the box. Paste it into your assistant and replace the bracketed fields you know. Leave the others open for the assistant to propose. Add any other preferences that matter, such as genre, language, or time budget.

### 🔎 Find an original channel direction

```text
Help me choose a channel direction for [platform, country, audience].

Compare five relevant channels using their strongest Shorts from the last
seven days where reliable data is available. Include links, dates, views,
and one technique I can adapt from each example.

Give me three original directions. For each, show the audience promise,
repeatable video format, animation style, runtime range, and a pilot idea.
Let me choose a direction.
```

### 🎨 Build a channel from scratch

```text
Build an original channel around [idea or direction] for [platform] and
[audience]. Propose a name, handle, tagline, description, and keywords.

Design a logo that reads at avatar size and a banner that survives the
platform crop. Define the colors, fonts, characters, voices, video format,
and target runtime.

Save the approved brand kit and give me three pilot ideas with estimated
production effort for each.
```

### 🔄 Continue an existing channel

```text
Use my channel brief, assets, and recent videos [attach or link]. Keep the
approved brand, character designs, voices, and episode format unless I ask
for a change.

If I share analytics, compare similar uploads at the same age and show
what you can verify. Suggest three original episodes that fit the channel
and one change worth testing.
```

### 🎞️ Make one episode

```text
Turn [idea] into an original [2D, 2.5D, or 3D] video for [platform]. Use
[language], aim for [runtime], and follow my approved channel brief.

Write a timed shot plan with positions, poses, camera, dialogue, captions,
sound, and transitions. Make a phone-size rough cut. Check the opening and
payoff with sound and muted.

Deliver the MP4, editable source, timed script, SRT when needed, thumbnail,
title, description, and platform tags or hashtags. Tell me which files
are ready to use.
```

### 📅 Plan the first month

```text
Make a four-week posting plan for [platforms] in [country] with a budget
of [hours per week]. Give me a realistic number of videos per week,
posting days and times to test, and what to review each week. Use my
audience's time zone and any channel data I share.

Verify each platform's monetization rules and show my remaining milestones.
Estimate time to eligibility only from stated assumptions or my own data.
```

## 🎯 Keep episodes consistent

Save the approved identity, characters, voice references, subtitle style, thumbnail style, and repeatable episode format with the channel. Reuse those decisions while giving each episode a new premise, action, and payoff. Study references for staging, timing, and performance, then create your own characters, artwork, dialogue, and sound.

Channels can also carry a generated Foley bank and a palette-matched effects kit: `python -m studio.sfx channels/<slug>` writes layered, variant-based sound effects, `python -m studio.vfx channels/<slug>` draws flash, dust, splash and shockwave art, and `studio/physics.py` samples falling, bouncing, splashing and shaking motion instead of hand-placed keys.

Try a 15–30 second first cut for a single visual gag, then adjust the length to fit the beats and the platform. Review it on a phone. Check where the eye goes in the opening, whether the payoff reads when muted, and whether captions and effects line up in playback. Each render includes `publishing.md` with YouTube title, description, and tags, plus a TikTok caption with hashtags. [Shorts planning](.agents/skills/viral-video-studio/references/shorts.md)

## 📈 Posting and monetization

**Start with a schedule you can keep.** For a new animated channel, try **one Short per posting day on two or three days a week** for the first four weeks. That’s a starter experiment. Pick two time slots in your audience’s time zone, compare posts at the same age, and review watch time, completion, and shares where available. Move toward one a day only if your production time and quality can support it. Use your own audience activity to refine posting times as data comes in. [YouTube scheduling guidance](https://support.google.com/youtube/answer/13616979?co=YOUTUBE._YTVideoType%3Dshorts&hl=en) · [YouTube audience analytics](https://support.google.com/youtube/answer/9314416?hl=en)

**Plan for eligibility, review, and then earnings.** The 30- and 90-day windows measure recent performance. Time to qualify depends on the channel’s growth and the rules for its country and account. Check the platform dashboard before planning around revenue. Rules below were checked November 10, 2026.

| Platform | What to plan for |
| --- | --- |
| **YouTube Shorts** | Shorts can run up to **3 minutes**. The Shorts route to ad sharing requires **1,000 subscribers** and **10 million qualified public Shorts views in the last 90 days**. YouTube says Partner Program review typically takes about **one month after applying**. In eligible countries, some fan-funding and shopping features may be available at **500 subscribers**, plus **3 valid public uploads and 3 million qualified Shorts views in the last 90 days**. [Shorts format](https://support.google.com/youtube/answer/12921536) · [Partner Program](https://support.google.com/youtube/answer/72851?hl=en) · [Expanded program](https://support.google.com/youtube/answer/13429240?hl=en) |
| **TikTok Creator Rewards** | Where available, the program requires an eligible personal account with **10,000 followers** and **100,000 video views in the last 30 days**. TikTok gives **about three days** for an application response through TikTok Studio. An eligible original video must run **at least one minute**, be posted after joining, and reach **1,000 qualified For You feed views** to start earning. [TikTok Creator Rewards requirements](https://www.tiktok.com/support/faq_detail?id=7581821550694013452&category=web_account) |

YouTube also lists a **February 1, 2027** change that requires **10 million qualified Shorts views over its specified 90-day window** for monthly Shorts Creator Pool and Premium revenue. Check the policy when planning a Shorts-first channel. [YouTube Shorts monetization policies](https://support.google.com/youtube/answer/12504220?hl=en)

## 🛠️ Render locally

Install Python 3.10+ and FFmpeg with FFprobe. From the repository folder, run `python -m pip install -r requirements.txt` and `python video.py doctor`. For SVG or 3D projects, install Node.js 22+ and Chrome or Chromium, then run `npm ci --ignore-scripts`. Follow the export command your assistant provides. [Renderer options](.agents/skills/viral-video-studio/references/renderers.md) · [Voice and sound](.agents/skills/viral-video-studio/references/audio.md)

The `Makefile` wraps the same commands and ships **no channel or episode path** — it resolves what is on disk, then falls back to `.env`:

```sh
make status        # what channel, episode, and .env resolve to
make init          # write .env from what is already on disk
make assets        # what this channel needs, and what is optional
make doctor        # ffmpeg, node, Chrome, Kokoro

make validate EPISODE=episodes/my-episode/episode.json
make preview  EPISODE=episodes/my-episode/episode.json
make render   EPISODE=episodes/my-episode/episode.json
```

Resolution order for `CHANNEL` and `EPISODE`: command line, then `.env`, then discovery. Discovery picks the only channel folder that has a manifest, preferring `channel.json`; with several folders or several manifests it stops and tells you what to pass. Copy [.env.example](.env.example) to `.env` to pin a channel and episode to the machine — `.env` is ignored by git, so a fresh clone starts clean.

Episode packages go under `output/<channel-slug>/`, using the selected channel manifest’s folder name. For example, rendering `episodes/my-episode/episode.json` with `CHANNEL=channels/my-channel/channel.json` writes `output/my-channel/my-episode-v1/video.mp4` alongside its publishing guide and other exports. Preview and audio packages use the suffixes `-preview` and `-audio`. Pass `OUT=<dir>` with Make or `--out <dir>` with `video.py` to choose a different path, including for a new render of the same episode.

`make assets` prints the identity kit a render actually reads — cast models, scene libraries, voice profiles, Foley — and separates it from artwork, documentation, audition leftovers and older looks. Delete an optional group only when you mean it:

```sh
make prune-casting        # dry run
make prune-casting APPLY=1
```

`make clean-cache` clears failed render staging, audio takes and `__pycache__`; `make clean-previews` removes preview packages. Rendered packages are never deleted automatically.

Channel assets, episodes, research, and exports stay in your local project folders. Each new clone carries the reusable workflow and tools.
