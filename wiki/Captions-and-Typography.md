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
| `foreground` | paint | Text colour or palette role |
| `background` | paint | Box colour or palette role |
| `highlight` | paint | Active word background or palette role |
| `highlight_text` | paint | Active word text colour |
| `font` | role or path | Font role from `channel.fonts`, or a channel-relative file |
| `font_size` | 0.5–2 | Scale factor |
| `stroke` | 0–1 | Outline width |
| `shadow` | boolean | Soft shadow |
| `shadow_color` | paint | Shadow colour |
| `radius` | 0–1 | Box corner radius |
| `max_lines` | 1–8 | Maximum wrapped lines |
| `align` | left/center/right | Text alignment |
| `line_height` | 0.8–2.5 | Line spacing multiplier |
| `letter_spacing` | -0.2–0.5 | Tracking as a fraction of font size |
| `offset` | -0.5–0.5 | Extra vertical offset as a canvas fraction |
| `padding_x` / `padding_y` | 0–0.25 | Box padding as a canvas fraction |
| `background_opacity` | 0–1 | Box opacity |
| `animation` | none/pop/slide/fade/rise | Cue entrance |

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
