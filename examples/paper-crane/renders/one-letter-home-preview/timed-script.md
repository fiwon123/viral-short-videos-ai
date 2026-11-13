# The Letter That Missed the Wind

540 × 960 · 24 fps
Runtime 00:00:06.417

Layer coordinates and box sizes are canvas fractions with the origin at the top left. Positions refer to layer centers. Background layers sit behind the 3D stage and foreground layers sit above it. Layers within each plane are drawn back to front.

Music bed: pulse, gain 0.06, ducked under speech.

## S1 · 00:00:00.000–00:00:06.417

Introduce the crane waiting on a hill and its one important letter.

### A · 00:00:00.000–00:00:03.417

A paper crane waits on a hill while the sun rises. The letter flutters, but the crane holds it.

- Background #101820.
- Camera 0, 0, zoom 1, rotate 0.
- sky (rect, background) at (0.5, 0.5), box 1.3 × 1.3, scale 1, rotation 0°, opacity 1. Fill #101820.
- sun (ellipse, background) at (0.72, 0.24), box 0.22 × 0.12, scale 1, rotation 0°, opacity 0.9. Fill #FF9F68.
  - 00:00:03.375 · y=0.2, ease=sine
- hill-back (polygon, background) at (0.5, 0.72), box 1.2 × 0.5, scale 1, rotation 0°, opacity 1. Fill #284B63.
- hill-front (polygon, background) at (0.5, 0.82), box 1.2 × 0.38, scale 1, rotation 0°, opacity 1. Fill #1d3b4a.
- cloud-a (ellipse, background) at (0.24, 0.33), box 0.26 × 0.07, scale 1, rotation 0°, opacity 0.25. Fill #FFF4E1.
  - 00:00:03.375 · x=0.32, ease=sine
- cloud-b (ellipse, background) at (0.66, 0.42), box 0.18 × 0.05, scale 1, rotation 0°, opacity 0.18. Fill #FFF4E1.
  - 00:00:03.375 · x=0.58, ease=sine
- body (ellipse, foreground) at (0.42, 0.68), box 0.18 × 0.1, scale 1, rotation 0°, opacity 1. Fill #FFF4E1.
  - 00:00:01.667 · y=0.665, ease=spring
- wing-left (polygon, foreground) at (-0.002, -0.018), box 0.13 × 0.12, scale 1, rotation 0°, opacity 1. Fill #e8d8bc.
  - 00:00:01.417 · rotate=-8, ease=back
  - 00:00:02.417 · rotate=0, ease=smooth
- wing-right (polygon, foreground) at (0.002, -0.018), box 0.13 × 0.12, scale 1, rotation 0°, opacity 1. Fill #d9c7a7.
  - 00:00:01.417 · rotate=8, ease=back
  - 00:00:02.417 · rotate=0, ease=smooth
- head (ellipse, foreground) at (0.075, -0.035), box 0.09 × 0.07, scale 1, rotation 0°, opacity 1. Fill #FFF4E1.
  - 00:00:01.667 · rotate=5, ease=elastic
- eye-open (ellipse, foreground) at (0.02, -0.005), box 0.012 × 0.012, scale 1, rotation 0°, opacity 1. Fill #101820.
  - 00:00:02.083 · visible=False
  - 00:00:02.417 · visible=True
- eye-blink (rect, foreground) at (0.02, -0.005), box 0.016 × 0.004, scale 1, rotation 0°, opacity 1. Fill #101820.
  - 00:00:02.083 · visible=True
  - 00:00:02.417 · visible=False
- letter (rect, foreground) at (0.41, 0.635), box 0.065 × 0.045, scale 1, rotation -6°, opacity 1. Fill #f3dfc1.
  - 00:00:01.167 · rotate=-12, ease=sine
  - 00:00:02.708 · rotate=-4, ease=sine
- badge (rect, foreground) at (0.5, 0.075), box 0.46 × 0.035, scale 1, rotation 0°, opacity 1. Fill #284B63.
- badge-text (text, foreground) at (0.5, 0.075), box 0.4 × 0.021, scale 1, rotation 0°, opacity 1. Fill #FF9F68. Screen text: PAPER CRANE POST / 01
- 00:00:00.333–00:00:02.958 · Narrator: The letter was ready. The wind was not. [eSpeak NG (en-us)].
- 00:00:00.125–00:00:00.500 · SFX whoosh at gain 0.18.
- 00:00:00.125–00:00:00.292 · SFX pop at gain 0.12.

### B · 00:00:03.417–00:00:06.417

A gust finally arrives. The crane lifts, the letter catches the light, and the horizon opens.

- Background #101820.
- Camera 0, 0, zoom 1, rotate 0.
- whip-left from 00:00:03.417 to 00:00:03.708.
- sky (rect, background) at (0.5, 0.5), box 1.3 × 1.3, scale 1, rotation 0°, opacity 1. Fill #14212b.
- sun (ellipse, background) at (0.52, 0.28), box 0.3 × 0.16, scale 1, rotation 0°, opacity 0.95. Fill #FF9F68.
  - 00:00:06.375 · scale=1.2, ease=sine
- ring (ellipse, background) at (0.52, 0.28), box 0.46 × 0.24, scale 1, rotation 0°, opacity 0. Fill #FF9F68.
  - 00:00:04.750 · opacity=0.18, scale=1.1
  - 00:00:06.375 · opacity=0
- hill (polygon, background) at (0.5, 0.82), box 1.2 × 0.42, scale 1, rotation 0°, opacity 1. Fill #284B63.
- bird (polygon, foreground) at (0.4, 0.55), box 0.11 × 0.06, scale 1, rotation 0°, opacity 1. Fill #FFF4E1.
  - 00:00:04.167 · x=0.44, y=0.48, rotate=-8, ease=sine
  - 00:00:06.375 · x=0.72, y=0.3, rotate=12, ease=sine
- bird-wing (polygon, foreground) at (0, -0.01), box 0.09 × 0.05, scale 1, rotation 0°, opacity 1. Fill #e8d8bc.
  - 00:00:04.000 · rotate=-18, ease=sine
  - 00:00:04.750 · rotate=14, ease=sine
  - 00:00:05.500 · rotate=-12, ease=sine
  - 00:00:06.375 · rotate=8, ease=sine
- letter (rect, foreground) at (0.42, 0.56), box 0.05 × 0.035, scale 1, rotation 0°, opacity 1. Fill #f3dfc1.
  - 00:00:04.167 · x=0.45, y=0.5, rotate=20
  - 00:00:06.375 · x=0.73, y=0.32, rotate=90
- badge (rect, foreground) at (0.5, 0.075), box 0.46 × 0.035, scale 1, rotation 0°, opacity 1. Fill #284B63.
- badge-text (text, foreground) at (0.5, 0.075), box 0.4 × 0.021, scale 1, rotation 0°, opacity 1. Fill #FF9F68. Screen text: PAPER CRANE POST / 02
- 00:00:03.958–00:00:05.958 · Narrator: A small delay is still a delivery. [eSpeak NG (en-us)].
- 00:00:03.583–00:00:03.958 · SFX whoosh at gain 0.2.
- 00:00:03.792–00:00:04.292 · SFX chime at gain 0.12.

## Captions

- 00:00:00.333–00:00:02.958 · The letter was ready. The wind was / not.
- 00:00:03.958–00:00:05.958 · A small delay is still a delivery.
