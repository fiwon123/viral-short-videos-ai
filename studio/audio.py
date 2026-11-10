"""Measure spoken takes, place cues, and mix audio on the frame clock."""

import math
from pathlib import Path
import textwrap
import wave

import numpy as np

from .core import MAX_SECONDS, SAMPLE_RATE, asset, ffmpeg, require, run


def read_audio(path):
    pcm = ffmpeg("-protocol_whitelist", "file,pipe", "-i", str(path), "-vn", "-t", str(MAX_SECONDS + 1),
                 "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-")
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    if not 0 < len(samples) <= SAMPLE_RATE * MAX_SECONDS:
        raise ValueError(f"Expected nonempty audio up to 12 minutes: {path.name}")
    return samples


def spoken_take(line, voice, base, temp):
    if "file" in line:
        raw = read_audio(asset(base, line["file"]))
        source = line["file"]
    else:
        require("espeak-ng")
        name = line.get("voice", voice.get("name", "en-us"))
        path = temp / "take.wav"
        run("espeak-ng", "-b", "1", "-z", "-v", name, "-s", str(voice.get("speed", 155)), "-w", str(path),
            "--stdin", data=line["text"].encode("utf-8"))
        raw = read_audio(path)
        source = f"eSpeak NG ({name})"
    peak = float(np.max(np.abs(raw)))
    if peak < 0.002:
        raise ValueError(f"Voice take is silent: {source}")
    audible = np.flatnonzero(np.abs(raw) > max(0.001, peak * 0.022))
    start = max(0, int(audible[0]) - SAMPLE_RATE // 40)
    end = min(len(raw), int(audible[-1]) + SAMPLE_RATE // 16)
    return raw[start:end] * (0.73 / peak), source


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


def plan_shot(shot, fps, voice, base, temp):
    step = SAMPLE_RATE // fps
    frames = frame_count(shot["duration"], fps)
    voices, effects = [], []
    previous_end = -round(0.18 * fps)
    for line in shot.get("speech", []):
        at = round(line["at"] * fps) if "at" in line else previous_end + round(0.18 * fps)
        if at < previous_end:
            raise ValueError(f"{shot['id']} has overlapping speech. Move the line by {previous_end - at} frames or omit at.")
        clip, source = spoken_take(line, voice, base, temp)
        end = at + math.ceil(len(clip) / step)
        # Add a brief visual hold when speech extends beyond the requested shot.
        frames = max(frames, end + math.ceil(0.14 * fps))
        voices.append((at, end, line, clip, source))
        previous_end = end
    for cue in shot.get("sfx", []):
        at = round(cue["at"] * fps)
        clip = read_audio(asset(base, cue["file"])) if "file" in cue else effect(cue["cue"])
        end = at + math.ceil(len(clip) / step)
        frames = max(frames, end)
        effects.append((at, end, cue, clip))
    if frames > MAX_SECONDS * fps:
        raise ValueError(f"{shot['id']} exceeds the 12-minute limit after audio alignment")
    return frames, voices, effects


def mouth_levels(clip, step):
    padded = np.pad(clip, (0, -len(clip) % step))
    rms = np.sqrt(np.mean(padded.reshape(-1, step) ** 2, axis=1))
    return np.clip(rms * 3.2, 0, 1)


def mix_shot(writer, frames, cursor, fps, voices, effects, bed, gain):
    step = SAMPLE_RATE // fps
    length = frames * step
    mixed = np.zeros(length, dtype=np.float32)
    for start, _, cue, clip in effects:
        offset = start * step
        mixed[offset:offset + len(clip)] += clip * cue.get("gain", 0.24)
    for start, _, _, clip, _ in voices:
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
    # Leave headroom for AAC encoding and gently compress summed peaks.
    writer.writeframesraw(np.asarray(np.tanh(mixed * 1.18) * 30000, dtype="<i2").tobytes())


def prepare_audio(episode, base, path, temp):
    fps = episode["fps"]
    limit = episode.get("max_seconds", MAX_SECONDS)
    music = episode.get("music")
    bed = music_bed(music, base) if music else None
    timeline = {"fps": fps, "duration_frames": 0, "scenes": [], "captions": []}
    levels = {}
    cursor = 0
    with wave.open(str(path), "wb") as writer:
        writer.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        for scene in episode["scenes"]:
            scene_timing = {"id": scene["id"], "purpose": scene["purpose"], "start": cursor, "shots": []}
            for shot in scene["shots"]:
                frames, voices, effects = plan_shot(shot, fps, episode.get("voice", {}), base, temp)
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
                for start, end, line, clip, source in voices:
                    timing["speech"].append({"speaker": line["speaker"], "text": line["text"], "source": source,
                                             "start": cursor + start, "end": cursor + end})
                    timeline["captions"].append({"start": cursor + start, "end": cursor + end,
                                                 "text": caption_lines(line.get("caption", line["text"]))})
                    levels[shot["id"]].append((start, end, line["speaker"], mouth_levels(clip, SAMPLE_RATE // fps)))
                for start, end, cue, _ in effects:
                    timing["sfx"].append({"start": cursor + start, "end": cursor + end,
                                          "source": cue.get("cue", cue.get("file")), "gain": cue.get("gain", 0.24)})
                mix_shot(writer, frames, cursor, fps, voices, effects, bed, music.get("gain", 0.10) if music else 0)
                cursor += frames
                scene_timing["shots"].append(timing)
            scene_timing["end"] = cursor
            timeline["scenes"].append(scene_timing)
    timeline["duration_frames"] = cursor
    return timeline, levels
