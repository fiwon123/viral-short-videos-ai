# Direct the voices and design the sound

## Cast once, direct each scene

Create an audio library next to the approved channel files and set `audio_library` in `channel.json` to its relative path. Use exact character names as keys. Give each recurring speaker a distinct pacing, register, attitude, and pronunciation guide. Audition the cast together on a neutral line, a reaction, and a quiet beat. Have the user approve the voice identities once, then reuse the same library version across episodes. Keep the approved reference WAVs beside the channel library and create a new version for any deliberate recast.

Open the approved character art or a neutral and reaction render before choosing the voice. Read the silhouette, proportions, expression range, and movement alongside the character brief. Translate those observations into a playable direction such as clipped precision, an unhurried dry read, or a quick breath before a warning. For stylized animals, match the acting to the character's body and comic role. An adult register can fit a small body. Let the character's timing and texture carry the design.

Use `character_design.reference` to link the visual anchor from a cast profile. Record the observable design in `traits` and the performance rationale in `voice_fit`. Once approved, link a short `approved_take` for future comparisons. Paths are relative to the audio library. Show the look alongside the voice shortlist, then audition the finalists over the same brief acted shot so the user can judge face, mouth timing, and voice together. If voice blends still read as an everyday narrator against the design, try a directed actor or a deliberately designed voice and import the best take.

Use the `audio_library` definition in the [manifest schema](../../../../studio/schema.json). Kokoro profiles lock a voice blend, language, and speed. Weights are relative. A single voice with weight 1 also works. Write distinct line rhythms and short playable beats. A profile's `direction` and a line's `delivery` are notes for the assistant or actor. Give Kokoro natural spoken phrasing and punctuation in `spoken_text` when it differs from the displayed `text` or `caption`. [Kokoro voice blending](https://github.com/thewh1teagle/kokoro-onnx/blob/main/examples/with_blending.py)

For richer acting or an original recorded identity, use a `recorded` profile with a stable `identity` and supply dry takes in each speech line's `file`. A file can also override the synthesis for one line in a Kokoro profile. Reuse the same performer or approved provider voice ID and settings. If using an external voice design or recording service, audition it and bring the resulting audio files into the project.

```json
{
  "version": 1,
  "voices": {
    "Mechanic": {
      "engine": "kokoro",
      "blend": {"am_michael": 70, "am_puck": 30},
      "language": "en-us",
      "speed": 1.04,
      "direction": "Quick and assured. Let the last word give away the doubt."
    },
    "Guide": {
      "engine": "recorded",
      "identity": "Guide approved take set v1",
      "direction": "Warm and patient. Pause before the correction."
    }
  },
  "sounds": {
    "wood-latch": ["foley/latch-light.wav", "foley/latch-firm.wav", "foley/latch-rattle.wav"]
  }
}
```

## Give each action a sound

Spot the episode by action, material, scale, perspective, and frame. Choose which moments benefit from silence. Record or create a specific sound for the signature reveal. For generated Foley, specify the action, materials, distance, and decay, then choose a dry take with a clear contact sound. For recurring physical actions, group several meaningfully different takes under a shared ID. For instance, record a wood latch with a gentle close, a firm snap, and a loose rattle. Keep source, creator, and license notes next to each imported asset. A recognizable brand sting can deliberately keep one fixed take.

Use `"sound": "wood-latch"` in a shot's SFX cue to select from the channel library. The starting variant depends on the episode folder, then variants rotate for repeated uses. Set `variant` with a one-based index to lock a take. Use a shot-local `file` for a new hero effect. Combine a contact transient and a short tail with two cues when the action needs both. Set gain per cue. An optional `rate` changes pitch and duration together, so recheck timing after changing it.

Place sounds in space and depth with `pan` (−1 left to 1 right) and `reverb` (0 dry to 1 wet). `pitch_variance` adds a deterministic small pitch change so repeated cues do not stack identically. `fade_in`, `fade_out`, `loop` and `duration` shape ambience and tails. For a compound impact, use `layers` with an `offset` per layer instead of hand-placing several cues:

```json
{
  "at": 1.2,
  "gain": 0.7,
  "layers": [
    {"sound": "thud", "gain": 0.65, "pan": 0},
    {"sound": "debris", "gain": 0.4, "offset": 0.02, "pan": 0.25, "pitch_variance": 0.06},
    {"sound": "clink", "gain": 0.25, "offset": 0.06, "pan": -0.3, "reverb": 0.18}
  ]
}
```

Set channel or episode `audio.reverb` for a shared room, and `audio.room_tone` with a library `sound` or a `file` plus gain. Use low room tone where it helps continuity. Leave the legacy synth presets for scratch work.

## Generate fresh Foley

When a channel needs a starting bank, synthesize one instead of shipping silence or borrowed samples:

```sh
python -m studio.sfx channels/my-channel --library audio/cast-v2.json \
  --voices audio/cast-candidate-v1.json
```

Every sound is layered from a transient, a body, and a tail, then filtered and peak-normalised with a 0.4 ms edge fade, so a cue's gain carries the size of the event. Three variants differ in pitch and texture so repeated uses do not phase together. Keep names behavioural (`thud`, `bonk`, `splash`, `burst`) rather than literal recordings, and point `audio_library` at the written JSON. Regenerating rewrites the WAVs and keeps the voice profiles, so recast voices separately.

Split the bank into impact, liquid, destruction, and comedy families and layer two or three cues per beat: contact, then debris, then settle. Put the contact on the exact frame. Keep music 6–12 dB under speech. If a real recording matters for a hero moment, import it as a shot-local `file` and leave the generated bank as the consistent bed.


## Master for the platform

The mixer writes stereo and then masters the episode by default: a high-pass, gentle bus compression, a two-pass loudness normalisation to −14 LUFS, and a true-peak limiter at −1.5 dBTP. Override it when a platform or a musical delivery needs a different target:

```json
{
  "audio": {
    "master": {"enabled": true, "loudness": -14, "true_peak": -1.5, "compress": true},
    "reverb": {"mix": 0.10, "size": 0.35},
    "room_tone": {"sound": "wind", "gain": 0.03}
  }
}
```

Read the measured `loudness` block in `audio-qa.json` or `timeline.json` before delivery. Keep dialogue forward, leave the limiter room for impacts, and check the result on headphones and a phone speaker. Use `master.enabled: false` only for a deliberate raw master.

## Approve audio before animation

Run the audio-only mix with the same episode manifest used for the final video.

```sh
python video.py audio episodes/my-episode/episode.json \
  --channel channels/my-channel/channel.json
```

Listen to `mix.wav` and review `timeline.json` and `audio-qa.json`. Check that the speakers sound distinct, breaths and pauses serve the line, the same performer carries across cuts, and the material and contact frame match the sound. Listen on headphones and a phone speaker. The QA report counts eSpeak lines and stock preset effects, which are useful to flag in a review. Keep the dialogue forward and give impacts space around key words.

Synthesis runs locally. The studio caches each generated WAV in the episode's `.audio-takes/` folder using the model files, voice blend, language, speed, runtime version, and exact spoken text. To lock a take for archiving or handoff, copy the approved WAV into the episode's voice assets and set the speech line's `file` to that path. Measure the final take before locking captions, mouth motion, and reaction timing. Use a fresh output folder for each review.

## Set up local Kokoro

Use Python 3.10–3.13 for the optional Kokoro runtime and install `requirements.txt` and `requirements-voice.txt` in that environment. Download the official `kokoro-v1.0.int8.onnx` and `voices-v1.0.bin` files into the local `audio-models/` folder. Set `STUDIO_KOKORO_MODEL` and `STUDIO_KOKORO_VOICES` to use a different local model pair. Run `video.py doctor` with the same Python interpreter used for rendering. [Model files](https://github.com/thewh1teagle/kokoro-onnx/releases/expanded_assets/model-files-v1.1) · [Runtime package](https://pypi.org/project/kokoro-onnx/)

Existing channels can still render with the original eSpeak scratch path. Once a cast is configured, use its speaker names and remove old per-line `voice` overrides before rendering. A missing cast profile or required recorded take raises an error.
