"""Measure spoken takes, design the mix, and master it on the frame clock."""

from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import textwrap
import wave

import numpy as np

from .core import MAX_SECONDS, SAMPLE_RATE, asset, ffmpeg, require, run
from .voices import KokoroTakes


def read_audio(path, channels=1):
    flags = ["-ac", str(channels)] if channels else []
    pcm = ffmpeg("-protocol_whitelist", "file,pipe", "-i", str(path), "-vn", "-t", str(MAX_SECONDS + 1),
                 *flags, "-ar", str(SAMPLE_RATE), "-f", "s16le", "-")
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    if not 0 < len(samples) <= SAMPLE_RATE * MAX_SECONDS * max(1, channels):
        raise ValueError(f"Expected nonempty audio up to 12 minutes: {path.name}")
    if channels and channels > 1:
        return samples.reshape(-1, channels)
    return samples


def spoken_take(line, voice, base, temp, profile, takes):
    text = line.get("spoken_text", line["text"])
    if "file" in line:
        raw = read_audio(asset(base, line["file"]))
        source = line["file"]
        detail = {"engine": "recorded"}
    elif profile:
        path, detail = takes.take(text, profile)
        raw = read_audio(path)
        source = "Kokoro (" + " + ".join(sorted(profile["blend"])) + ")"
    else:
        require("espeak-ng")
        name = line.get("voice", voice.get("name", "en-us"))
        path = temp / "take.wav"
        run("espeak-ng", "-b", "1", "-z", "-v", name, "-s", str(voice.get("speed", 155)), "-w", str(path),
            "--stdin", data=text.encode("utf-8"))
        raw = read_audio(path)
        source = f"eSpeak NG ({name})"
        detail = {"engine": "espeak"}
    peak = float(np.max(np.abs(raw)))
    if peak < 0.002:
        raise ValueError(f"Voice take is silent: {source}")
    audible = np.flatnonzero(np.abs(raw) > max(0.001, peak * (0.010 if profile else 0.022)))
    start = max(0, int(audible[0]) - SAMPLE_RATE // (20 if profile else 40))
    end = min(len(raw), int(audible[-1]) + SAMPLE_RATE // (10 if profile else 16))
    clip = raw[start:end]
    gain = 0.73 / peak
    if profile:
        # Match dialogue energy with a peak ceiling. Retain the take's internal dynamics.
        rms = float(np.sqrt(np.mean(clip ** 2)))
        gain = min(0.65 / peak, 0.105 / rms, 4.0)
        fade = min(SAMPLE_RATE // 200, len(clip) // 2)
        if fade:
            ramp = np.linspace(0, 1, fade)
            clip[:fade] *= ramp
            clip[-fade:] *= ramp[::-1]
        detail["cast_direction"] = profile["direction"]
        if "identity" in profile:
            detail["cast_identity"] = profile["identity"]
        if "character_design" in profile:
            detail["character_design"] = profile["character_design"]
    return clip * gain, source, detail


class SoundBank:
    def __init__(self, sounds, base, episode_key):
        self.sounds = sounds
        self.base = base
        self.episode_key = episode_key
        self.next_variant = {}
        self.cue_index = 0

    def cue(self, spec, episode_base):
        if "sound" in spec:
            name = spec["sound"]
            variants = self.sounds[name]
            seed = sha256(f"{self.episode_key}\0{name}".encode()).digest()
            index = spec["variant"] - 1 if "variant" in spec else self.next_variant.get(
                name, int.from_bytes(seed[:8], "big") % len(variants))
            self.next_variant[name] = (index + 1) % len(variants)
            file = variants[index]
            clip = read_audio(asset(self.base, file))
            detail = {"kind": "library", "sound": name, "variant": index + 1, "source": file}
        elif "file" in spec:
            clip = read_audio(asset(episode_base, spec["file"]))
            detail = {"kind": "file", "source": spec["file"]}
        else:
            clip = effect(spec["cue"])
            detail = {"kind": "preset", "source": spec["cue"]}
        self.cue_index += 1
        rate = float(spec.get("rate", 1))
        variance = float(spec.get("pitch_variance", 0) or 0)
        if variance:
            seed = int.from_bytes(sha256(f"{self.episode_key}\0{self.cue_index}\0pitch".encode()).digest()[:4], "big")
            random = np.random.default_rng(seed).uniform(-1, 1)
            rate *= 1 + variance * random
        if abs(rate - 1) > 1e-6:
            count = max(1, round(len(clip) / rate))
            clip = np.interp(np.arange(count) * rate, np.arange(len(clip)), clip).astype(np.float32)
            detail["rate"] = round(rate, 4)
        return apply_cue_shape(clip, spec), detail


def oscillator(length, frequency, fade):
    t = np.arange(round(length * SAMPLE_RATE), dtype=np.float32) / SAMPLE_RATE
    envelope = np.minimum(1, t / 0.012) * np.maximum(0, 1 - t / length) ** fade
    return t, envelope, np.sin(2 * np.pi * frequency * t)


def effect(name):
    if name == "pop":
        _, env, tone = oscillator(0.15, 440, 3)
        return env * tone
    if name == "whoosh":
        t, env, _ = oscillator(0.36, 1, 0.9)
        noise = np.random.default_rng(25).uniform(-1, 1, len(t)).astype(np.float32)
        return env * (0.58 * np.sin(2 * np.pi * (110 * t + 530 * t * t)) + 0.35 * noise)
    t, env, tone = oscillator(0.5, 659.25, 2.5)
    return env * (tone * 0.6 + np.sin(2 * np.pi * 987.77 * t) * 0.4)


def music_bed(spec, base):
    if "file" in spec:
        return read_audio(asset(base, spec["file"]), channels=2)
    notes = []
    for pitch in [130.81, 196, 164.81, 196, 110, 164.81, 146.83, 164.81]:
        t, env, tone = oscillator(0.5, pitch, 1.7)
        notes.append(env * (0.7 * tone + 0.3 * np.sin(2 * np.pi * pitch * 2 * t)))
    return np.concatenate(notes)


def frame_count(seconds, fps):
    return max(1, math.ceil(seconds * fps - 1e-9))


def caption_lines(text):
    return "\n".join(row for line in text.splitlines() if line.strip() for row in textwrap.wrap(line, width=38))


def caption_words(text, start, end, fps):
    """Allocate word timings by visible length, with a beat after punctuation."""
    words = [word for word in text.split() if word]
    if not words:
        return []
    weights = [max(1, len(word.strip(".,!?;:"))) + (2 if word[-1:] in ".!?" else 0) for word in words]
    total = max(1, end - start)
    span = sum(weights)
    cursor = start
    result = []
    for word, weight in zip(words, weights):
        length = max(1, round(total * weight / span))
        result.append({"text": word, "start": cursor, "end": min(end, cursor + length)})
        cursor += length
    result[-1]["end"] = end
    return result


def flatten_cue(spec):
    if "layers" not in spec:
        return [spec]
    base = {key: value for key, value in spec.items() if key != "layers"}
    cues = []
    for layer in spec["layers"]:
        cues.extend(flatten_cue({**base, **layer}))
    return cues


def pan_gains(pan):
    angle = (max(-1.0, min(1.0, float(pan))) + 1) * math.pi / 4
    return math.cos(angle), math.sin(angle)


def _lowpass(signal, cutoff, order=1):
    a = 1 - np.exp(-2 * np.pi * cutoff / SAMPLE_RATE)
    out = np.empty_like(signal)
    state = 0.0
    for index, value in enumerate(signal):
        state += a * (value - state)
        out[index] = state
    return out if order == 1 else _lowpass(out, cutoff, order - 1)


def reverb(clip, amount=0.0, size=0.3, seed=7):
    """Cheap convolution reverb with a deterministic, channel-matched tail."""
    amount = max(0.0, min(1.0, float(amount or 0)))
    if amount <= 0:
        return np.zeros(0, dtype=np.float32)
    size = max(0.0, min(1.0, float(size if size is not None else 0.3)))
    seconds = 0.18 + 1.15 * size
    count = max(1, round(seconds * SAMPLE_RATE))
    random = np.random.default_rng(seed)
    t = np.arange(count) / SAMPLE_RATE
    decay = 0.12 + 0.7 * size
    impulse = random.normal(0, 1, count).astype(np.float32) * np.exp(-t / decay)
    impulse = _lowpass(impulse, 6200)
    impulse[0] = 1.0
    impulse /= max(1e-6, float(np.sqrt(np.sum(impulse ** 2))))
    length = len(clip) + count - 1
    size_fft = 1 << (length - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(clip, size_fft) * np.fft.rfft(impulse, size_fft), size_fft)[:length]
    return (wet * amount).astype(np.float32)


def apply_cue_shape(clip, spec):
    duration = spec.get("duration")
    if duration:
        target = max(1, round(float(duration) * SAMPLE_RATE))
        if len(clip) < target:
            clip = np.tile(clip, math.ceil(target / len(clip)))[:target]
        else:
            clip = clip[:target]
    elif spec.get("loop"):
        clip = np.tile(clip, 2)
    fade_in = float(spec.get("fade_in", 0) or 0)
    fade_out = float(spec.get("fade_out", 0) or 0)
    if fade_in:
        edge = min(len(clip), max(1, round(fade_in * SAMPLE_RATE)))
        clip = clip.copy()
        clip[:edge] *= np.linspace(0, 1, edge, dtype=np.float32)
    if fade_out:
        edge = min(len(clip), max(1, round(fade_out * SAMPLE_RATE)))
        clip = clip.copy()
        clip[-edge:] *= np.linspace(1, 0, edge, dtype=np.float32)
    return clip


def add_clip(mixed, clip, offset, gain, pan=0.0, reverb_amount=0.0, reverb_size=0.3, seed=7):
    if clip.ndim == 1:
        left, right = pan_gains(pan)
        dry = np.stack([clip * left, clip * right], axis=1)
    else:
        balance = float(pan)
        dry = clip.copy()
        dry[:, 0] *= max(0.0, 1 - balance)
        dry[:, 1] *= max(0.0, 1 + balance)
    wet = reverb(clip.mean(axis=1) if clip.ndim > 1 else clip,
                 amount=reverb_amount, size=reverb_size, seed=seed)
    if wet.size:
        left, right = pan_gains(pan)
        wet = np.stack([wet * left * 0.85, wet * right * 0.85], axis=1)
        if wet.shape[0] > dry.shape[0]:
            dry = np.pad(dry, ((0, wet.shape[0] - dry.shape[0]), (0, 0)))
        else:
            wet = np.pad(wet, ((0, dry.shape[0] - wet.shape[0]), (0, 0)))
        dry = dry + wet
    dry = dry * float(gain)
    start = max(0, int(offset))
    end = min(len(mixed), start + len(dry))
    if end > start:
        mixed[start:end] += dry[:end - start]


def write_stereo_wav(path, samples):
    peak = float(np.max(np.abs(samples))) if len(samples) else 0
    if peak > 0.99:
        samples = samples * (0.99 / peak)
    pcm = np.rint(np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setparams((2, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        stream.writeframes(pcm.tobytes())


def ambience_clip(cue, base, audio_library, seconds):
    if "file" in cue:
        clip = read_audio(asset(base, cue["file"]))
    elif audio_library and cue.get("sound") in audio_library[0].get("sounds", {}):
        variants = audio_library[0]["sounds"][cue["sound"]]
        clip = read_audio(asset(audio_library[1].parent, variants[0]))
    else:
        raise ValueError(f"Unknown ambience sound: {cue.get('sound')}")
    target = max(1, round(seconds * SAMPLE_RATE))
    if cue.get("loop", True) and len(clip) < target:
        clip = np.tile(clip, math.ceil(target / len(clip)))[:target]
    else:
        clip = clip[:target]
    fade_in = float(cue.get("fade_in", 0.2) or 0)
    fade_out = float(cue.get("fade_out", 0.2) or 0)
    if fade_in:
        edge = min(len(clip), max(1, round(fade_in * SAMPLE_RATE)))
        clip = clip.copy()
        clip[:edge] *= np.linspace(0, 1, edge, dtype=np.float32)
    if fade_out:
        edge = min(len(clip), max(1, round(fade_out * SAMPLE_RATE)))
        clip = clip.copy()
        clip[-edge:] *= np.linspace(1, 0, edge, dtype=np.float32)
    return clip


def _duck_abs(intervals, length, config):
    amount = float((config or {}).get("amount", 0.58))
    attack = max(1, round(float((config or {}).get("attack", 0.045)) * SAMPLE_RATE))
    release = max(1, round(float((config or {}).get("release", 0.16)) * SAMPLE_RATE))
    envelope = np.ones(length, dtype=np.float32)
    for start, end in intervals:
        a, b = max(0, start), min(length, end)
        if b <= a:
            continue
        floor = max(0.0, 1 - amount)
        envelope[a:b] = np.minimum(envelope[a:b], floor)
        pre, post = min(a, attack), min(length - b, release)
        if pre:
            envelope[a - pre:a] = np.minimum(envelope[a - pre:a], np.linspace(1, floor, pre, endpoint=False))
        if post:
            envelope[b:b + post] = np.minimum(envelope[b:b + post], np.linspace(floor, 1, post, endpoint=False))
    return envelope


def mix_global(path, total_frames, fps, dialogue, sfx, bed, music_config, ambience,
               room_tone, audio_library, base, *, stems=False):
    step = SAMPLE_RATE // fps
    length = total_frames * step
    tracks = {name: np.zeros((length, 2), dtype=np.float32)
              for name in ("dialogue", "music", "ambience", "sfx")}
    intervals = []
    for offset, clip, line, seed in dialogue:
        add_clip(tracks["dialogue"], clip, offset, line.get("gain", 1),
                 pan=line.get("pan", 0), reverb_amount=line.get("reverb", 0),
                 reverb_size=(music_config or {}).get("reverb_size", 0.3), seed=seed)
        intervals.append((offset, offset + len(clip)))
    for offset, clip, cue, seed in sfx:
        add_clip(tracks["sfx"], clip, offset, cue.get("gain", 0.24),
                 pan=cue.get("pan", 0), reverb_amount=cue.get("reverb", 0),
                 reverb_size=(music_config or {}).get("reverb_size", 0.3), seed=seed)
    if bed is not None and music_config.get("gain", 0):
        stereo = bed if bed.ndim > 1 else np.stack([bed, bed], axis=1)
        absolute = np.arange(length, dtype=np.int64)
        indices = absolute % len(stereo)
        music = stereo[indices] * float(music_config.get("gain", 0.1))
        if not music_config.get("loop", True):
            music = music.copy()
            music[absolute >= len(stereo)] = 0
        music *= _duck_abs(intervals, length, music_config.get("duck"))[:, None]
        fade_in = float(music_config.get("fade_in", 0) or 0)
        fade_out = float(music_config.get("fade_out", 0) or 0)
        fade = np.ones(length, dtype=np.float32)
        if fade_in:
            fade *= np.clip(np.arange(length) / max(1.0, fade_in * SAMPLE_RATE), 0, 1)
        if fade_out:
            fade *= np.clip((length - np.arange(length)) / max(1.0, fade_out * SAMPLE_RATE), 0, 1)
        tracks["music"] += music * fade[:, None]
    for cue in ambience:
        start = max(0, round(float(cue.get("start", 0)) * SAMPLE_RATE))
        end = min(length, round(float(cue.get("end", total_frames / fps)) * SAMPLE_RATE))
        if end <= start:
            continue
        clip = ambience_clip(cue, base, audio_library, (end - start) / SAMPLE_RATE)
        add_clip(tracks["ambience"], clip, start, cue.get("gain", 0.05),
                 pan=cue.get("pan", 0), reverb_amount=cue.get("reverb", 0),
                 reverb_size=(music_config or {}).get("reverb_size", 0.3), seed=7)
    if room_tone is not None and room_tone.size:
        indices = np.arange(length, dtype=np.int64) % len(room_tone)
        tracks["ambience"] += np.stack([room_tone[indices], room_tone[indices]], axis=1)
    mixed = sum(tracks.values())
    peak = float(np.max(np.abs(mixed)))
    if peak:
        mixed = mixed * min(1.0, 0.95 / peak)
    write_stereo_wav(path, mixed)
    if stems:
        for name, track in tracks.items():
            write_stereo_wav(path.parent / f"stem-{name}.wav", track)
    return mixed


def plan_shot(shot, fps, voice, base, temp, profiles, takes, sound_bank):
    step = SAMPLE_RATE // fps
    frames = frame_count(shot["duration"], fps)
    voices, effects = [], []
    previous_end = -round(0.18 * fps)
    for line in shot.get("speech", []):
        at = round(line["at"] * fps) if "at" in line else previous_end + round(0.18 * fps)
        lead = round(float(line.get("lead", 0) or 0) * fps)
        at += lead
        if "lead" not in line and at < previous_end:
            raise ValueError(f"{shot['id']} has overlapping speech. Move the line by {previous_end - at} frames or omit at.")
        clip, source, detail = spoken_take(line, voice, base, temp, profiles.get(line["speaker"]), takes)
        end = at + math.ceil(len(clip) / step)
        # Add a brief visual hold when speech extends beyond the requested shot.
        frames = max(frames, end + math.ceil(0.14 * fps))
        voices.append((at, end, line, clip, source, detail))
        previous_end = end
    for cue in shot.get("sfx", []):
        for layer in flatten_cue(cue):
            at = round((float(cue["at"]) + float(layer.get("offset", 0) or 0)
                        + float(cue.get("lead", 0) or 0)) * fps)
            clip, detail = sound_bank.cue(layer, base)
            end = at + math.ceil(len(clip) / step)
            frames = max(frames, end)
            effects.append((at, end, {**cue, **layer}, clip, detail))
    if frames > MAX_SECONDS * fps:
        raise ValueError(f"{shot['id']} exceeds the 12-minute limit after audio alignment")
    return frames, voices, effects


def mouth_levels(clip, step):
    padded = np.pad(clip, (0, -len(clip) % step))
    rms = np.sqrt(np.mean(padded.reshape(-1, step) ** 2, axis=1))
    return np.clip(rms * 3.2, 0, 1)


def _duck_envelope(voices, frames, step, config):
    amount = float((config or {}).get("amount", 0.58))
    attack = max(1, round(float((config or {}).get("attack", 0.045)) * SAMPLE_RATE))
    release = max(1, round(float((config or {}).get("release", 0.16)) * SAMPLE_RATE))
    envelope = np.ones(frames * step, dtype=np.float32)
    for start, end, *_ in voices:
        a, b = max(0, start * step), min(len(envelope), end * step)
        if b <= a:
            continue
        floor = max(0.0, 1 - amount)
        envelope[a:b] = np.minimum(envelope[a:b], floor)
        pre, post = min(a, attack), min(len(envelope) - b, release)
        if pre:
            envelope[a - pre:a] = np.minimum(envelope[a - pre:a], np.linspace(1, floor, pre, endpoint=False))
        if post:
            envelope[b:b + post] = np.minimum(envelope[b:b + post], np.linspace(floor, 1, post, endpoint=False))
    return envelope


def mix_shot(writer, frames, cursor, fps, voices, effects, bed, gain, *, preserve_dynamics,
             music_config=None, room_tone=None, total_frames=0):
    step = SAMPLE_RATE // fps
    length = frames * step
    mixed = np.zeros((length, 2), dtype=np.float32)
    default_reverb = float((music_config or {}).get("reverb_mix", 0) or 0)
    for start, _, cue, clip, _ in effects:
        add_clip(mixed, clip, start * step, cue.get("gain", 0.24),
                 pan=cue.get("pan", 0), reverb_amount=cue.get("reverb", default_reverb),
                 reverb_size=(music_config or {}).get("reverb_size", 0.3),
                 seed=int.from_bytes(sha256(f"{cue.get('sound', cue.get('file', cue.get('cue', 'fx')))}:{start}".encode()).digest()[:4], "big"))
    for start, _, line, clip, *_ in voices:
        add_clip(mixed, clip, start * step, line.get("gain", 1),
                 pan=line.get("pan", 0), reverb_amount=line.get("reverb", default_reverb),
                 reverb_size=(music_config or {}).get("reverb_size", 0.3),
                 seed=int.from_bytes(sha256(f"{line['speaker']}:{start}".encode()).digest()[:4], "big"))
    if room_tone is not None and room_tone.size:
        tone = room_tone
        indices = (np.arange(length, dtype=np.int64) + cursor * step) % len(tone)
        mixed += np.stack([tone[indices], tone[indices]], axis=1)
    if bed is not None and gain:
        stereo = bed if bed.ndim > 1 else np.stack([bed, bed], axis=1)
        absolute = np.arange(cursor * step, (cursor + frames) * step, dtype=np.int64)
        indices = absolute % len(stereo)
        music = stereo[indices] * float(gain)
        if not (music_config or {}).get("loop", True):
            music = music.copy()
            music[absolute >= len(stereo)] = 0
        music *= _duck_envelope(voices, frames, step, (music_config or {}).get("duck"))[:, None]
        if total_frames:
            fade_in = float((music_config or {}).get("fade_in", 0) or 0)
            fade_out = float((music_config or {}).get("fade_out", 0) or 0)
            sample = np.arange(length, dtype=np.float32)
            absolute = cursor * step + sample
            fade = np.ones(length, dtype=np.float32)
            if fade_in:
                fade *= np.clip(absolute / max(1.0, fade_in * SAMPLE_RATE), 0, 1)
            if fade_out:
                fade *= np.clip((total_frames / fps * SAMPLE_RATE - absolute) /
                               max(1.0, fade_out * SAMPLE_RATE), 0, 1)
            music *= fade[:, None]
        mixed += music
    peak = float(np.max(np.abs(mixed)))
    if preserve_dynamics or peak > 0.94:
        mixed *= min(1.0, 0.95 / peak) if peak else 1
        pcm = np.rint(mixed * 32767)
    else:
        pcm = np.tanh(mixed * 1.1) * 30000
    writer.writeframesraw(np.asarray(pcm, dtype="<i2").tobytes())


def prepare_audio(episode, base, path, temp, audio_library=None, channel=None):
    fps = episode["fps"]
    limit = episode.get("max_seconds", MAX_SECONDS)
    config = merge_audio(channel, episode)
    master = dict(config.get("master") or {})
    render_options = {**((channel or {}).get("render") or {}), **(episode.get("render") or {})}
    if render_options.get("master") is False:
        master["enabled"] = False
    music = episode.get("music")
    bed = music_bed(music, base) if music else None
    room = None
    if tone := config.get("room_tone"):
        if "file" in tone:
            room = read_audio(asset(base, tone["file"]))
        elif audio_library and tone.get("sound") in audio_library[0].get("sounds", {}):
            sound = audio_library[0]["sounds"][tone["sound"]][0]
            room = read_audio(asset(audio_library[1].parent, sound))
        if room is not None:
            room = room * float(tone.get("gain", 0.04))
    timeline = {"fps": fps, "duration_frames": 0, "scenes": [], "captions": [], "audio": config}
    if music:
        timeline["music"] = {"kind": "file" if "file" in music else "preset",
                             "source": music.get("file", music.get("preset")), "gain": music.get("gain", 0.10)}
    library = audio_library[0] if audio_library else {}
    if audio_library:
        timeline["audio_library"] = {"file": audio_library[1].name, "version": library["version"]}
    profiles = library.get("voices", {})
    takes = KokoroTakes(base)
    sound_bank = SoundBank(library.get("sounds", {}), audio_library[1].parent if audio_library else base, base.resolve().name)
    plans = []
    total_frames = 0
    for scene in episode["scenes"]:
        scene_plan = []
        for shot in scene["shots"]:
            frames, voices, effects = plan_shot(shot, fps, episode.get("voice", {}), base, temp,
                                                 profiles, takes, sound_bank)
            transition = shot.get("transition")
            transition_frames = frame_count(transition["duration"], fps) if transition else 0
            if transition_frames >= frames:
                raise ValueError(f"{shot['id']} transition must be shorter than the shot")
            scene_plan.append((shot, frames, voices, effects, transition_frames))
            total_frames += frames
        plans.append((scene, scene_plan))
    if total_frames / fps > limit:
        raise ValueError(f"Audio extends the video beyond {limit:g} seconds")
    levels = {}
    dialogue, sfx_events = [], []
    step = SAMPLE_RATE // fps
    cursor = 0
    for scene, scene_plan in plans:
        scene_timing = {"id": scene["id"], "purpose": scene["purpose"], "start": cursor, "shots": []}
        for shot, frames, voices, effects, transition_frames in scene_plan:
            transition = shot.get("transition")
            timing = {"id": shot["id"], "start": cursor, "end": cursor + frames,
                      "speech": [], "sfx": []}
            if transition:
                timing["transition"] = {**transition, "start": cursor,
                                        "end": cursor + transition_frames}
            levels[shot["id"]] = []
            for start, end, line, clip, source, detail in voices:
                absolute_start = cursor + start
                entry = {"speaker": line["speaker"], "text": line["text"], "source": source,
                         "start": absolute_start, "end": cursor + end, **detail}
                for key in ("spoken_text", "delivery", "pan", "reverb", "gain", "lead"):
                    if key in line:
                        entry[key] = line[key]
                timing["speech"].append(entry)
                text = line.get("caption", line["text"])
                words = line.get("words")
                timeline["captions"].append({
                    "start": max(0, absolute_start), "end": cursor + end,
                    "speaker": line["speaker"],
                    "text": caption_lines(text),
                    "words": ([{"text": word["text"],
                                "start": max(0, absolute_start) + round(word["start"] * fps),
                                "end": max(0, absolute_start) + round(word["end"] * fps)}
                               for word in words] if words else
                              caption_words(text, max(0, absolute_start), cursor + end, fps)),
                    "visemes": ([{"at": max(0, absolute_start) + round(item["at"] * fps),
                                  "shape": item["shape"]} for item in line.get("visemes", [])]
                                if line.get("visemes") else []),
                })
                levels[shot["id"]].append((start, end, line["speaker"], mouth_levels(clip, SAMPLE_RATE // fps)))
                dialogue.append((absolute_start * step, clip, line,
                                 int.from_bytes(sha256(f"{line['speaker']}:{absolute_start}".encode()).digest()[:4], "big")))
            for start, end, cue, clip, detail in effects:
                absolute_start = cursor + start
                entry = {"start": absolute_start, "end": cursor + end,
                         "gain": cue.get("gain", 0.24), **detail}
                for key in ("pan", "reverb", "pitch_variance", "lead"):
                    if key in cue:
                        entry[key] = cue[key]
                timing["sfx"].append(entry)
                sfx_events.append((absolute_start * step, clip, cue, 7 + len(sfx_events)))
            cursor += frames
            scene_timing["shots"].append(timing)
        scene_timing["end"] = cursor
        timeline["scenes"].append(scene_timing)
    timeline["duration_frames"] = cursor
    music_config = {**(music or {}),
                    "gain": music.get("gain", 0.10) if music else 0,
                    "reverb_size": config.get("reverb", {}).get("size", 0.3),
                    "reverb_mix": config.get("reverb", {}).get("mix", 0)}
    mix_global(path, cursor, fps, dialogue, sfx_events, bed, music_config,
               episode.get("ambience", []), room, audio_library, base,
               stems=bool(render_options.get("stems", False)))
    master_audio(path, master)
    timeline["loudness"] = measure_loudness(path)
    timeline["stems"] = bool(render_options.get("stems", False))
    return timeline, levels


def merge_audio(channel, episode):
    config = {}
    for source in ((channel or {}).get("audio"), episode.get("audio")):
        for key, value in (source or {}).items():
            if isinstance(value, dict):
                config[key] = {**config.get(key, {}), **value}
            else:
                config[key] = value
    return config


def _run_ffmpeg(args):
    result = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", *args], capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def master_audio(path, config):
    """Loudness-normalise and limit the mix without crushing dialogue dynamics."""
    config = config or {}
    if config.get("enabled", True) is False:
        return
    gain = float(config.get("gain", 1.0))
    target = float(config.get("loudness", -14))
    true_peak = float(config.get("true_peak", -1.5))
    filters = ["highpass=f=24"]
    if config.get("compress", True):
        filters.append("acompressor=threshold=-20dB:ratio=2.5:attack=8:release=180:makeup=1.4")
    width = float(config.get("stereo_width", 1.0))
    if abs(width - 1.0) > 1e-3:
        filters.append(f"extrastereo=m={max(0.0, min(4.0, width))}")
    code, stdout, stderr = _run_ffmpeg([
        "-i", str(path), "-af",
        f"loudnorm=I={target}:TP={true_peak}:LRA=11:print_format=json",
        "-f", "null", "-",
    ])
    measured = {}
    if code == 0:
        for line in stderr.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    measured = json.loads(line)
                except json.JSONDecodeError:
                    pass
        if not measured:
            start, end = stderr.rfind("{"), stderr.rfind("}")
            if start >= 0 and end > start:
                try:
                    measured = json.loads(stderr[start:end + 1])
                except json.JSONDecodeError:
                    measured = {}
    if measured.get("input_i") not in (None, "-inf"):
        filters.append(
            f"loudnorm=I={target}:TP={true_peak}:LRA=11:"
            f"measured_I={measured.get('input_i')}:measured_LRA={measured.get('input_lra')}:"
            f"measured_TP={measured.get('input_tp')}:measured_thresh={measured.get('input_thresh')}:"
            f"offset={measured.get('target_offset', 0)}:linear=true:print_format=summary"
        )
    filters.append("alimiter=limit=0.84:level=false")
    if gain != 1:
        filters.insert(0, f"volume={gain}")
    staged = path.with_suffix(".master.wav")
    code, _, stderr = _run_ffmpeg([
        "-y", "-i", str(path), "-af", ",".join(filters),
        "-ar", str(SAMPLE_RATE), "-ac", "2", "-c:a", "pcm_s16le", str(staged),
    ])
    if code != 0:
        # Keep the unmastered mix rather than losing the whole render.
        staged.unlink(missing_ok=True)
        return
    staged.replace(path)
    # Inter-sample peaks can survive a linear limiter. Trim once more only when
    # the measured true peak still exceeds the requested ceiling.
    try:
        peak = float(measure_loudness(path).get("true_peak_db"))
    except (TypeError, ValueError):
        peak = None
    if peak is not None and peak > true_peak:
        correction = max(-12.0, true_peak - peak - 0.1)
        trimmed = path.with_suffix(".trim.wav")
        code, _, _ = _run_ffmpeg([
            "-y", "-i", str(path), "-af", f"volume={correction}dB,alimiter=limit=0.84:level=false",
            "-ar", str(SAMPLE_RATE), "-ac", "2", "-c:a", "pcm_s16le", str(trimmed),
        ])
        if code == 0:
            trimmed.replace(path)
        else:
            trimmed.unlink(missing_ok=True)


def measure_loudness(path):
    code, _, stderr = _run_ffmpeg([
        "-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-",
    ])
    if code:
        return {}
    start, end = stderr.rfind("{"), stderr.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(stderr[start:end + 1])
    except json.JSONDecodeError:
        return {}
    return {
        "integrated_lufs": data.get("input_i"),
        "true_peak_db": data.get("input_tp"),
        "loudness_range": data.get("input_lra"),
    }


def audio_summary(timeline):
    shots = [shot for scene in timeline["scenes"] for shot in scene["shots"]]
    captions = timeline["captions"]
    words = sum(len(cue.get("words", [])) for cue in captions)
    return {
        "voice_engines": sorted({line["engine"] for shot in shots for line in shot["speech"]}),
        "scratch_voice_lines": sum(line["engine"] == "espeak" for shot in shots for line in shot["speech"]),
        "preset_effects": sum(cue["kind"] == "preset" for shot in shots for cue in shot["sfx"]),
        "library_effects": sum(cue["kind"] == "library" for shot in shots for cue in shot["sfx"]),
        "caption_cues": len(captions),
        "caption_words": words,
        "loudness": timeline.get("loudness", {}),
        "music": timeline.get("music"),
    }
