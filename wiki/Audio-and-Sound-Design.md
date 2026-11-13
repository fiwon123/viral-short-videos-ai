# 🎧 Audio and Sound Design

Audio is half the film. The studio mixes in stereo, masters to a platform-safe level, and gives every cue a place in space.

## 🗣️ Cast and voice direction

Create a channel audio library and point `channel.json` at it:

```json
{"audio_library": "audio/cast-v2.json"}
```

```json
{
  "version": 2,
  "voices": {
    "Narrator": {
      "engine": "kokoro",
      "blend": {"af_sky": 65, "af_heart": 35},
      "language": "en-us",
      "speed": 1.02,
      "direction": "Warm, unhurried. Let the last word land."
    }
  },
  "sounds": {"thud": ["sfx/thud-1.wav", "sfx/thud-2.wav"]}
}
```

Use `recorded` profiles with approved WAVs when you need a specific performance. Audition the cast together on a neutral line, a reaction and a quiet beat before locking a series.

## 🎼 Music

```json
{"music": {"preset": "pulse", "gain": 0.06, "fade_in": 0.4, "fade_out": 0.6,
           "duck": {"amount": 0.58, "attack": 0.04, "release": 0.16}}}
```

Use `file` for licensed or original music. The mixer ducks under speech and applies fades.

## 🔊 Foley and layers

```json
{
  "at": 1.2,
  "layers": [
    {"sound": "thud", "gain": 0.65, "pan": 0},
    {"sound": "debris", "gain": 0.4, "offset": 0.02, "pan": 0.25, "pitch_variance": 0.06},
    {"sound": "clink", "gain": 0.25, "offset": 0.06, "pan": -0.3, "reverb": 0.18}
  ]
}
```

- `pan` places the cue left/right.
- `reverb` adds a wet tail.
- `pitch_variance` stops repeated cues stacking identically.
- `fade_in`, `fade_out`, `loop`, `duration` shape ambience.
- `offset` staggers layers inside a stack.

## 🎛️ Master

```json
{
  "audio": {
    "master": {"enabled": true, "loudness": -14, "true_peak": -1.5, "compress": true},
    "reverb": {"mix": 0.08, "size": 0.3},
    "room_tone": {"sound": "wind", "gain": 0.03}
  }
}
```

The mixer writes stereo, then applies a high-pass, gentle bus compression, two-pass loudness normalisation, a limiter, and a true-peak correction. Read the measured report in `audio-qa.json` or `timeline.json`.

> [!TIP]
> Review on headphones and a phone speaker. Keep dialogue forward and leave a little room around impacts.

## 🧪 Sound Lab

Create a JSON recipe:

```json
{
  "id": "custom-impact",
  "layers": [
    {"type": "tone", "start": 120, "end": 42, "duration": 0.22, "gain": 0.8,
     "attack": 0.002, "decay": 3.2},
    {"type": "noise", "duration": 0.08, "gain": 0.5,
     "filter": {"type": "bandpass", "low": 900, "high": 4800}},
    {"type": "grain", "count": 12, "duration": 0.4, "gain": 0.3}
  ],
  "reverb": {"mix": 0.15, "size": 0.3},
  "variants": 3
}
```

Render it:

```sh
python video.py sound workspace/my-channel/channel --recipe audio/custom-impact.json
```

The WAVs land in `audio/sfx/` and the library is updated automatically.

Supported layer types: `tone`, `sweep`, `noise`, `grain`.

## 🎚️ Built-in Foley

`make sfx CHANNEL=...` writes 32 families, including impact, liquid, destruction, comedy, wind, heartbeat, footsteps, glass, metal and sparkle.

## Next

- [Motion, Camera and Rigs](Motion-Camera-and-Rigs)
- [Captions and Typography](Captions-and-Typography)
- [QA, Export and Publishing](QA-Export-and-Publishing)
