"""Measure spoken takes, place cues, and mix audio on the frame clock."""

from hashlib import sha256
import math
from pathlib import Path
import textwrap
import wave

import numpy as np

from .core import MAX_SECONDS, SAMPLE_RATE, asset, ffmpeg, require, run
from .voices import KokoroTakes


def read_audio(path):
    pcm = ffmpeg("-protocol_whitelist", "file,pipe", "-i", str(path), "-vn", "-t", str(MAX_SECONDS + 1),
                 "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-")
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    if not 0 < len(samples) <= SAMPLE_RATE * MAX_SECONDS:
        raise ValueError(f"Expected nonempty audio up to 12 minutes: {path.name}")
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
        rate = spec.get("rate", 1)
        if rate != 1:
            count = max(1, round(len(clip) / rate))
            clip = np.interp(np.arange(count) * rate, np.arange(len(clip)), clip).astype(np.float32)
            detail["rate"] = rate
        return clip, detail


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
        return read_audio(asset(base, spec["file"]))
    notes = []
    for pitch in [130.81, 196, 164.81, 196, 110, 164.81, 146.83, 164.81]:
        t, env, tone = oscillator(0.5, pitch, 1.7)
        notes.append(env * (0.7 * tone + 0.3 * np.sin(2 * np.pi * pitch * 2 * t)))
    return np.concatenate(notes)


def frame_count(seconds, fps):
    return max(1, math.ceil(seconds * fps - 1e-9))


def caption_lines(text):
    return "\n".join(row for line in text.splitlines() if line.strip() for row in textwrap.wrap(line, width=38))


def plan_shot(shot, fps, voice, base, temp, profiles, takes, sound_bank):
    step = SAMPLE_RATE // fps
    frames = frame_count(shot["duration"], fps)
    voices, effects = [], []
    previous_end = -round(0.18 * fps)
    for line in shot.get("speech", []):
        at = round(line["at"] * fps) if "at" in line else previous_end + round(0.18 * fps)
        if at < previous_end:
            raise ValueError(f"{shot['id']} has overlapping speech. Move the line by {previous_end - at} frames or omit at.")
        clip, source, detail = spoken_take(line, voice, base, temp, profiles.get(line["speaker"]), takes)
        end = at + math.ceil(len(clip) / step)
        # Add a brief visual hold when speech extends beyond the requested shot.
        frames = max(frames, end + math.ceil(0.14 * fps))
        voices.append((at, end, line, clip, source, detail))
        previous_end = end
    for cue in shot.get("sfx", []):
        at = round(cue["at"] * fps)
        clip, detail = sound_bank.cue(cue, base)
        end = at + math.ceil(len(clip) / step)
        frames = max(frames, end)
        effects.append((at, end, cue, clip, detail))
    if frames > MAX_SECONDS * fps:
        raise ValueError(f"{shot['id']} exceeds the 12-minute limit after audio alignment")
    return frames, voices, effects


def mouth_levels(clip, step):
    padded = np.pad(clip, (0, -len(clip) % step))
    rms = np.sqrt(np.mean(padded.reshape(-1, step) ** 2, axis=1))
    return np.clip(rms * 3.2, 0, 1)


def mix_shot(writer, frames, cursor, fps, voices, effects, bed, gain, *, preserve_dynamics):
    step = SAMPLE_RATE // fps
    length = frames * step
    mixed = np.zeros(length, dtype=np.float32)
    for start, _, cue, clip, _ in effects:
        offset = start * step
        mixed[offset:offset + len(clip)] += clip * cue.get("gain", 0.24)
    for start, _, _, clip, *_ in voices:
        offset = start * step
        mixed[offset:offset + len(clip)] += clip
    if bed is not None and gain:
        indices = np.arange(cursor * step, (cursor + frames) * step, dtype=np.int64) % len(bed)
        music = bed[indices] * gain
        fade = SAMPLE_RATE // 14
        for start, end, *_ in voices:
            a, b = start * step, min(length, end * step)
            music[a:b] *= 0.30
            pre, post = min(a, fade), min(length - b, fade)
            music[a - pre:a] *= np.linspace(1, 0.30, pre, endpoint=False)
            music[b:b + post] *= np.linspace(0.30, 1, post, endpoint=False)
        mixed += music
    if preserve_dynamics:
        # Leave encoding headroom while avoiding saturation of the entire mix.
        peak = float(np.max(np.abs(mixed)))
        mixed *= min(1, 0.9 / peak) if peak else 1
        pcm = np.rint(mixed * 32767)
    else:
        pcm = np.tanh(mixed * 1.18) * 30000
    writer.writeframesraw(np.asarray(pcm, dtype="<i2").tobytes())


def prepare_audio(episode, base, path, temp, audio_library=None):
    fps = episode["fps"]
    limit = episode.get("max_seconds", MAX_SECONDS)
    music = episode.get("music")
    bed = music_bed(music, base) if music else None
    timeline = {"fps": fps, "duration_frames": 0, "scenes": [], "captions": []}
    if music:
        timeline["music"] = {"kind": "file" if "file" in music else "preset",
                             "source": music.get("file", music.get("preset")), "gain": music.get("gain", 0.10)}
    library = audio_library[0] if audio_library else {}
    if audio_library:
        timeline["audio_library"] = {"file": audio_library[1].name, "version": library["version"]}
    profiles = library.get("voices", {})
    takes = KokoroTakes(base)
    sound_bank = SoundBank(library.get("sounds", {}), audio_library[1].parent if audio_library else base, base.resolve().name)
    levels = {}
    cursor = 0
    with wave.open(str(path), "wb") as writer:
        writer.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        for scene in episode["scenes"]:
            scene_timing = {"id": scene["id"], "purpose": scene["purpose"], "start": cursor, "shots": []}
            for shot in scene["shots"]:
                frames, voices, effects = plan_shot(shot, fps, episode.get("voice", {}), base, temp,
                                                     profiles, takes, sound_bank)
                if (cursor + frames) / fps > limit:
                    raise ValueError(f"Audio extends the video beyond {limit:g} seconds at shot {shot['id']}")
                transition = shot.get("transition")
                transition_frames = frame_count(transition["duration"], fps) if transition else 0
                if transition_frames >= frames:
                    raise ValueError(f"{shot['id']} transition must be shorter than the shot")
                timing = {"id": shot["id"], "start": cursor, "end": cursor + frames,
                          "speech": [], "sfx": []}
                if transition:
                    timing["transition"] = {"type": transition["type"], "start": cursor,
                                            "end": cursor + transition_frames}
                levels[shot["id"]] = []
                for start, end, line, clip, source, detail in voices:
                    entry = {"speaker": line["speaker"], "text": line["text"], "source": source,
                             "start": cursor + start, "end": cursor + end, **detail}
                    for key in ("spoken_text", "delivery"):
                        if key in line:
                            entry[key] = line[key]
                    timing["speech"].append(entry)
                    timeline["captions"].append({"start": cursor + start, "end": cursor + end,
                                                 "text": caption_lines(line.get("caption", line["text"]))})
                    levels[shot["id"]].append((start, end, line["speaker"], mouth_levels(clip, SAMPLE_RATE // fps)))
                for start, end, cue, _, detail in effects:
                    timing["sfx"].append({"start": cursor + start, "end": cursor + end,
                                          "gain": cue.get("gain", 0.24), **detail})
                mix_shot(writer, frames, cursor, fps, voices, effects, bed, music.get("gain", 0.10) if music else 0,
                         preserve_dynamics=audio_library is not None)
                cursor += frames
                scene_timing["shots"].append(timing)
            scene_timing["end"] = cursor
            timeline["scenes"].append(scene_timing)
    timeline["duration_frames"] = cursor
    return timeline, levels


def audio_summary(timeline):
    shots = [shot for scene in timeline["scenes"] for shot in scene["shots"]]
    return {
        "voice_engines": sorted({line["engine"] for shot in shots for line in shot["speech"]}),
        "scratch_voice_lines": sum(line["engine"] == "espeak" for shot in shots for line in shot["speech"]),
        "preset_effects": sum(cue["kind"] == "preset" for shot in shots for cue in shot["sfx"]),
        "library_effects": sum(cue["kind"] == "library" for shot in shots for cue in shot["sfx"]),
        "music": timeline.get("music"),
    }
