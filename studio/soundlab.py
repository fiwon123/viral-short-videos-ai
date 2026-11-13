"""Synthesize an original SFX from a JSON recipe.

The built-in bank in ``studio.sfx`` is a starting point. Sound Lab lets an
assistant design a new cue without editing Python::

    python -m studio.soundlab workspace/my-channel/channel \\
        --recipe audio/custom-impact.json

Recipe layers are deliberately small and deterministic: tone, noise, grain,
sweep, and a room/reverb tail.
"""

import argparse
import json
import math
from pathlib import Path
import wave

import numpy as np

from .core import SAMPLE_RATE
from .sfx import (bandpass, envelope, grains, highpass, lowpass, normalize, noise, pad,
                  room, sweep, sweep_filter, vary)


def _gain(value, default=1.0):
    return float(value if value is not None else default)


def _osc(kind, seconds, start, end, curve=1.0):
    if kind == "sine":
        return sweep(seconds, start, end, curve=curve)
    n = max(1, round(seconds * SAMPLE_RATE))
    t = np.arange(n) / SAMPLE_RATE
    shape = (t / max(seconds, 1e-6)) ** curve
    frequency = start + (end - start) * shape
    phase = 2 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
    if kind == "square":
        return np.sign(np.sin(phase)).astype(np.float32)
    if kind == "saw":
        return (2 * ((phase / (2 * np.pi)) % 1) - 1).astype(np.float32)
    if kind == "triangle":
        return (2 * np.abs(2 * ((phase / (2 * np.pi)) % 1) - 1) - 1).astype(np.float32)
    return np.sin(phase).astype(np.float32)


def _layer(layer, seed):
    kind = layer.get("type", "tone")
    offset = float(layer.get("offset", 0) or 0)
    gain = _gain(layer.get("gain"), 1.0)
    if kind in {"tone", "sweep"}:
        duration = float(layer.get("duration", 0.25))
        start = float(layer.get("start", layer.get("start_freq", 220)))
        end = float(layer.get("end", layer.get("end_freq", start)))
        wave_name = layer.get("wave", "sine")
        tone = _osc(wave_name, duration, start, end, curve=float(layer.get("curve", 1)))
        shape = envelope(duration, attack=float(layer.get("attack", 0.003)),
                         curve=float(layer.get("decay", 3.0)),
                         hold=float(layer.get("hold", 0)))
        return offset, tone * shape * gain
    if kind == "noise":
        duration = float(layer.get("duration", 0.2))
        source = noise(duration, seed)
        spec = layer.get("filter", {})
        if spec.get("type") == "lowpass":
            source = lowpass(source, float(spec.get("cutoff", 3000)))
        elif spec.get("type") == "highpass":
            source = highpass(source, float(spec.get("cutoff", 800)))
        elif spec.get("type") == "bandpass":
            source = bandpass(source, float(spec.get("low", 300)), float(spec.get("high", 5000)))
        elif spec.get("type") == "sweep":
            source = sweep_filter(source, float(spec.get("start", 400)), float(spec.get("end", 4000)))
        shape = envelope(duration, attack=float(layer.get("attack", 0.003)),
                         curve=float(layer.get("decay", 3.0)),
                         hold=float(layer.get("hold", 0)))
        return offset, source * shape * gain
    if kind == "grain":
        duration = float(layer.get("duration", 0.5))
        cluster = grains(int(layer.get("count", 18)), duration, seed,
                         low=float(layer.get("low", 500)), high=float(layer.get("high", 5000)),
                         decay=float(layer.get("decay", 2.0)), spread=float(layer.get("spread", 1.0)))
        return offset, cluster * gain
    raise ValueError(f"Unknown Sound Lab layer type: {kind}. Available: tone, sweep, noise, grain")


def render_recipe(recipe, seed=7):
    parts = []
    cursor = 0.0
    for index, layer in enumerate(recipe.get("layers", [])):
        offset, samples = _layer(layer, seed + index)
        parts.append((offset, samples))
        cursor = max(cursor, offset + len(samples) / SAMPLE_RATE)
    if not parts:
        raise ValueError("A Sound Lab recipe needs at least one layer")
    length = max(1, round(cursor * SAMPLE_RATE))
    mixed = np.zeros(length, dtype=np.float32)
    for offset, samples in parts:
        start = round(offset * SAMPLE_RATE)
        end = min(length, start + len(samples))
        if end > start:
            mixed[start:end] += samples[:end - start]
    reverb = recipe.get("reverb") or {}
    if reverb:
        mixed = room(mixed, float(reverb.get("mix", 0.18)), seed) if reverb.get("size", 0.3) < 0.7 else mixed
    return normalize(mixed, float(recipe.get("peak", 0.89)))


def write_wav(path, samples):
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        stream.writeframes(pcm.tobytes())


def build(channel, recipe_path, *, library="audio/cast-v2.json", variants=None):
    channel = Path(channel).resolve()
    recipe_file = Path(recipe_path)
    if not recipe_file.is_absolute():
        candidates = [channel / recipe_file, Path(__file__).resolve().parents[1] / recipe_file,
                      Path(__file__).resolve().parents[1] / "presets" / recipe_file]
        recipe_file = next((path.resolve() for path in candidates if path.is_file()),
                           (channel / recipe_file).resolve())
    recipe = json.loads(recipe_file.read_text(encoding="utf-8"))
    sound_id = recipe.get("id")
    if not sound_id:
        raise ValueError("Sound Lab recipe needs an id")
    count = int(variants or recipe.get("variants", 3))
    target = (channel / library).resolve()
    if not target.is_relative_to(channel):
        raise ValueError("The audio library must live inside the channel folder")
    folder = target.parent / "sfx"
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for index in range(1, count + 1):
        samples = render_recipe(recipe, seed=index * 17 + len(sound_id))
        samples = vary(samples, 1 + (index - (count + 1) / 2) * 0.035)
        path = folder / f"{sound_id}-{index}.wav"
        write_wav(path, samples)
        files.append(str(path.relative_to(target.parent)))
    data = {"version": 2, "voices": {}, "sounds": {}}
    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
    data.setdefault("sounds", {})[sound_id] = files
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"sound": sound_id, "library": str(target.relative_to(channel)), "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--library", default="audio/cast-v2.json")
    parser.add_argument("--variants", type=int)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.channel, args.recipe, library=args.library,
                               variants=args.variants), indent=2))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"studio: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
