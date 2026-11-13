# 🤖 AI Workflow and Prompt Cookbook

The repository is written for an AI assistant that can read files and run commands. It is also usable from a chat-only model: attach the episode manifest and ask for the next file.

## 🧭 Entry points

| File | Use |
| --- | --- |
| `AGENTS.md` | Project storage rules and tool entry points |
| `.agents/skills/viral-video-studio/SKILL.md` | End-to-end workflow |
| `studio/schema.json` | Exact data contract |
| `README.md` | Commands and quick links |
| `wiki/` | Deep dives |

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
Watch the preview with sound and muted. Check the hook, caption sync, contact
frames, camera continuity and the payoff. List only issues that change the
story or readability, then fix them and re-render.
```

## ✅ Delivery checklist

- MP4, thumbnail, SRT, `publishing.md`
- `channel.md` updated
- Loudness report inside −14 LUFS target
- No over-limit platform copy
- Preview checked on a phone
- Editable manifests kept

## Next

- [Examples](Examples)
- [QA, Export and Publishing](QA-Export-and-Publishing)
- [Troubleshooting](Troubleshooting)
