# 🤖 AI Workflow and Prompt Cookbook

Open the project in an assistant that can read files and run commands. In a chat-only model, attach the studio skill and the relevant manifest, then ask for the next file or command.

## 🧭 Entry points

| File | Use |
| --- | --- |
| `AGENTS.md` | Project storage rules and tool entry points |
| `.agents/skills/viral-video-studio/SKILL.md` | End-to-end workflow |
| `studio/schema.json` | Exact data contract |
| `README.md` | Commands and quick links |
| `wiki/` | Deep dives |

**Creator path:** [Create a Channel](Create-a-Channel) → [Find Ideas](Find-Ideas) → [Create Videos with Prompts](Create-Videos-with-Prompts) → [Make Shorts Travel](Make-Shorts-Travel) → [Monetization](YouTube-and-TikTok-Monetization) → [Automate a Channel](Automate-a-Channel).

## 🎬 Concept prompt

```text
Give me three original animated Short concepts for [audience] on [platform].
For each, include the hook, the visible change, the payoff, a rough runtime,
the animation approach, and one camera or sound idea.
Keep the characters and world original.
```

## 🧱 Episode prompt

```text
Turn concept 2 into an episode manifest for workspace/<channel>/episodes/<episode>.
Use a 540x960 canvas, 24fps, under 12 seconds, and the channel's palette.
Write timed shots with layer IDs, poses, camera keys, speech, SFX and captions.
Use parent/pivot rigs for the character and a karaoke caption.
Validate it, render a preview, and tell me what to inspect.
```

## 🎚️ Audio prompt

```text
Design the soundtrack for this episode.
Keep dialogue forward, pan the action, add a short room tail, and use layered
Foley for the main impact. If the channel library has no suitable cue, write a
Sound Lab recipe and synthesize it into the channel.
```

## 🎥 Camera prompt

```text
Add camera language that supports the beats. Use one motivated move per shot,
not constant motion. Use a push-in for the reveal, a whip for the cut, and
parallax on the background. Check the first and last frame of every move.
```

## 🎨 Finish prompt

```text
Apply a restrained cinematic finish: light grain, a soft vignette, a little
bloom on the practical light, and a warm tint. Keep the character silhouette
clear at phone size. Compare a clean and finished frame.
```

## 🔍 Review prompt

```text
Read the film-QA report of the latest preview, then run make review-pack and
give each lens (director, sound, continuity) to a reviewer that did not build
the episode. Fix every P0 and the P1s that matter, re-render the preview, and
tell me which notes changed and which you left, with the reason.
```

When you want to give the notes yourself:

```text
Open make review for [episode]. I will leave notes on the frames. When I say
done, read them with make comments, look at each frame and close-up first,
change only what each note is about, re-render, and reply to each note.
```

## ✅ Delivery checklist

- [ ] `make deliver` passes and every amber item is answered in `delivery.md`.
- [ ] MP4, thumbnail, and `publishing.md` are present. Include SRT when the video uses captions.
- [ ] The phone preview passes with sound and muted.
- [ ] Spoken lines pass `make narration-check` (or the notes say why a line is exempt).
- [ ] Platform copy fits each field’s limit.
- [ ] Editable manifests and assets are saved in the channel workspace.

## 🔗 Related guides

- [Examples](Examples)
- [QA, Export and Publishing](QA-Export-and-Publishing)
- [Troubleshooting](Troubleshooting)
