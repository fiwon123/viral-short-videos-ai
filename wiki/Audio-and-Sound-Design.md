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

### Voices with their own timing

Any local TTS program can be a voice with `"engine": "command"` (Piper, XTTS, F5-TTS, Chatterbox). Hosted voices work too:

```json
{"narrator": {"engine": "elevenlabs", "voice_id": "<voice id>", "model": "eleven_multilingual_v2",
              "voice_settings": {"stability": 0.4, "similarity_boost": 0.8},
              "direction": "Warm, dry storyteller."}}
```

ElevenLabs returns when each word is spoken along with the audio, so captions and lip sync follow the voice exactly instead of estimating. Set `ELEVENLABS_API_KEY` in your environment on the host (never in a file the repository tracks). Each line is generated once and cached with its timings: later renders, and the Docker sandbox, which has no keys, reuse the take without calling the service.

Any other voice or aligner can do the same through a command: write the word timings as JSON (`[{"text": "Hello", "start": 0.12, "end": 0.48}]`, seconds in the take) to the `{words}` path.

> [!TIP]
> Before animating to a take, run `make narration-check EPISODE=...`. It hears every line back and flags dropped, repeated or misread words and numbers, so you re-voice while it is still cheap. See [QA, Export and Publishing](QA-Export-and-Publishing).

## 🎼 Music

```json
{"music": {"preset": "pulse", "gain": 0.06, "fade_in": 0.4, "fade_out": 0.6,
           "duck": {"amount": 0.58, "attack": 0.04, "release": 0.16}}}
```

Use `file` for licensed or original music, or ask the channel's music library for a mood (`"music": {"mood": "funny", "energy": "high"}`). The mixer ducks under speech and applies fades.

### Fitted to the episode

A track is not simply cut at the last frame. When it has a beat (a library track, a `file` with a `beat`, or a file whose pulse the studio can measure), it is arranged to the episode's exact length:

- the track's own opening plays, and its own ending lands on the last frame;
- whole bars come out of the middle (or repeat, for a track shorter than the episode), joined only on bar lines so the beat carries across;
- the join with the smallest loudness step is chosen, and film QA reports `music-join` if even that one jumps;
- `music.beat` follows the arrangement, so `at_beat` anchors and `snap` still land.

The plan is in the render's `timeline.json` (`music.arrangement`). Set `"fit": false` to play from the start and cut, and `"loop": false` to never repeat bars. A drone, a pad or an ambience has no beat to cut on and plays as before.

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

The mixer writes stereo, then masters it: a high-pass and gentle bus compression, then the loudness is measured on that result and raised to the target into a peak limiter that works at four times the sample rate, so the peaks between samples are caught too. It re-measures and corrects for what the limiter took. A sparse mix of short hits and creature sounds reaches the target like a dense one. Read the measured report in `audio-qa.json` or `timeline.json`; `make deliver` checks the delivered file again and flags loudness off target, a true peak over −1 dBTP or a sound cut off on the last frame.

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

## 🔗 Related guides

- [Motion, Camera and Rigs](Motion-Camera-and-Rigs)
- [Captions and Typography](Captions-and-Typography)
- [QA, Export and Publishing](QA-Export-and-Publishing)
