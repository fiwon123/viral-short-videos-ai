# 💬 Captions and Typography

Captions are part of the edit. They should land on the beat, fit the phone safe area, and stay readable when the platform overlays UI.

## 🎚️ Styles

| Style | Look | Best for |
| --- | --- | --- |
| `box` | Rounded background behind the full line | Dialogue, narration |
| `karaoke` | Active word highlighted | Shorts, comedy, retention |
| `minimal` | Text with outline, no box | Cinematic, clean |

```json
{
  "captions": {
    "style": "karaoke",
    "position": "bottom",
    "highlight": "#FFD166",
    "uppercase": false,
    "max_words": 4,
    "animation": "pop"
  }
}
```

## 🎨 Type controls

| Field | Range | Meaning |
| --- | --- | --- |
| `foreground` | color | Text colour |
| `background` | color | Box colour |
| `highlight` | color | Active word background |
| `font` | path | Optional font file, relative to the channel |
| `font_size` | 0.5–2 | Scale factor |
| `stroke` | 0–1 | Outline width |
| `shadow` | boolean | Soft shadow |
| `radius` | 0–1 | Box corner radius |

## ⏱️ Word timing

The audio pass writes word timings into `timeline.json` and the caption cue. Karaoke uses those timings automatically. SRT remains line-level.

## ✨ Animation

| Animation | Effect |
| --- | --- |
| `none` | Static |
| `pop` | Scales up from 90% as the cue enters |
| `slide` | Slides up into place |

## 📐 Safe areas

Keep captions at `bottom`, `center` or `top`. The default bottom position leaves room for platform controls. Check the preview on a phone before the master.

## 🧪 Review

- Read every line at phone size.
- Check the active word lands on the spoken word.
- Watch muted.
- Check that no caption covers the payoff.
- Keep line length short. Prefer 3–5 words per line for Shorts.

## 🔗 Related guides

- [Audio and Sound Design](Audio-and-Sound-Design)
- [QA, Export and Publishing](QA-Export-and-Publishing)
