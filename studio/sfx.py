"""Synthesize an original Foley bank for a channel.

Every sound is built from layered oscillators and filtered noise, so the bank is
license-free, deterministic, and tunable in place. Episodes reference it by name
through the channel audio library: {"sound": "thud", "variant": 2, "rate": 0.9}.

    python -m studio.sfx channels/<slug> --library audio/cast-v2.json \\
        --voices audio/cast-candidate-v1.json
"""

import argparse
import json
from pathlib import Path
import wave

import numpy as np

from hashlib import sha256

from .core import SAMPLE_RATE

SR = SAMPLE_RATE


def rng(seed):
    return np.random.default_rng(seed)


def noise(seconds, seed):
    return rng(seed).uniform(-1, 1, max(1, round(seconds * SR))).astype(np.float32)


def sweep(seconds, start, end, *, curve=1.0, phase=0.0):
    """Sine whose frequency glides from start to end."""
    n = max(1, round(seconds * SR))
    t = np.arange(n) / SR
    shape = (t / seconds) ** curve
    frequency = start + (end - start) * shape
    points = 2 * np.pi * np.cumsum(frequency) / SR + phase
    return np.sin(points).astype(np.float32)


def envelope(seconds, attack=0.004, curve=3.0, hold=0.0):
    n = max(1, round(seconds * SR))
    t = np.arange(n) / SR
    rise = np.minimum(1, t / max(attack, 1e-4))
    fall = np.maximum(0, 1 - np.clip((t - hold) / max(seconds - hold, 1e-4), 0, 1)) ** curve
    return (rise * fall).astype(np.float32)


def lowpass(signal, cutoff, order=1):
    a = 1 - np.exp(-2 * np.pi * cutoff / SR)
    out = np.empty_like(signal)
    state = 0.0
    for i, value in enumerate(signal):
        state += a * (value - state)
        out[i] = state
    return out if order == 1 else lowpass(out, cutoff, order - 1)


def highpass(signal, cutoff, order=1):
    return signal - lowpass(signal, cutoff, order)


def bandpass(signal, low, high, order=1):
    return highpass(lowpass(signal, high, order), low, order)


def sweep_filter(signal, start, end, resonance=1.0):
    """One-pole lowpass whose cutoff glides, for wind, splashes and blasts."""
    n = len(signal)
    cutoff = np.geomspace(max(start, 20), max(end, 20), n)
    a = 1 - np.exp(-2 * np.pi * cutoff / SR)
    out = np.empty(n, dtype=np.float32)
    state = 0.0
    for i in range(n):
        state += a[i] * (signal[i] - state)
        out[i] = state
    if resonance > 1:
        out = out + resonance * (signal - out) * 0.35
    return out


def room(signal, mix=0.22, seed=7):
    """Three short taps instead of a convolver: cheap, readable room tone."""
    out = signal.copy()
    for delay, gain in ((0.017, 0.5), (0.023, 0.33), (0.031, 0.22)):
        shift = round(delay * SR)
        if shift >= len(out):
            continue
        tail = np.zeros_like(out)
        tail[shift:] = lowpass(signal[:-shift], 2600) * gain
        out = out + tail * mix * (0.9 + 0.2 * rng(seed).random())
    return out


def grains(count, seconds, seed, *, low=400, high=5200, decay=2.4, spread=1.0):
    """Cluster of tiny noise+tone grains: debris, crackle, rattle."""
    r = rng(seed)
    out = np.zeros(round(seconds * SR), dtype=np.float32)
    for i in range(count):
        length = r.uniform(0.010, 0.045)
        start = round(r.uniform(0, 1) ** spread * seconds * 0.75 * SR)
        size = round(length * SR)
        if start + size > len(out):
            continue
        grain = bandpass(noise(length, seed + i), low, high)
        tone = sweep(length, r.uniform(high * 0.6, high), r.uniform(low, low * 2))
        amp = r.uniform(0.25, 1.0) * (1 - start / len(out)) ** decay
        out[start:start + size] += (grain * 0.7 + tone * 0.3) * envelope(length, 0.001, 4) * amp
    return out


def normalize(signal, peak=0.89, fade_ms=0.4):
    if len(signal) == 0:
        return signal
    signal = signal - float(np.mean(signal))
    top = float(np.max(np.abs(signal))) or 1.0
    signal = (signal / top * peak).astype(np.float32)
    edge = max(1, round(fade_ms / 1000 * SR))
    if edge * 2 < len(signal):
        ramp = np.linspace(0, 1, edge, dtype=np.float32)
        signal[:edge] *= ramp
        signal[-edge:] *= ramp[::-1]
    return signal


def vary(signal, factor):
    """Resample by a small factor so variants differ in pitch as well as texture."""
    if abs(factor - 1) < 1e-6:
        return signal
    count = max(1, round(len(signal) / factor))
    return np.interp(np.arange(count) * factor, np.arange(len(signal)), signal).astype(np.float32)


def pad(signal, seconds):
    n = round(seconds * SR)
    return np.pad(signal, (0, max(0, n - len(signal)))) if len(signal) < n else signal


# --- recipes -----------------------------------------------------------------


def thud(seed):
    """Weight landing on cloth: sub body, soft click, short air."""
    body = sweep(0.20, 96, 42, curve=0.6) * envelope(0.20, 0.003, 3.4)
    click = bandpass(noise(0.02, seed), 900, 4800) * envelope(0.02, 0.0005, 6)
    air = lowpass(noise(0.16, seed + 1), 700) * envelope(0.16, 0.002, 4.5) * 0.5
    out = np.zeros(round(0.28 * SR), dtype=np.float32)
    out[:len(body)] += body
    out[:len(click)] += click * 0.8
    out[:len(air)] += air
    return normalize(room(out, 0.10, seed))


def bonk(seed):
    """Hollow wooden head-hit."""
    tone = sweep(0.22, 340, 190, curve=0.5) * envelope(0.22, 0.002, 4)
    hollow = bandpass(noise(0.12, seed), 380, 1500, 2) * envelope(0.12, 0.001, 5) * 0.8
    out = np.zeros(round(0.26 * SR), dtype=np.float32)
    out[:len(tone)] += tone
    out[:len(hollow)] += hollow
    return normalize(room(out, 0.16, seed))


def thwack(seed):
    """Cartoon swat: bright attack, pitch drop, small tail."""
    crack = highpass(noise(0.05, seed), 1800) * envelope(0.05, 0.0004, 5)
    body = sweep(0.18, 240, 70, curve=0.45) * envelope(0.18, 0.001, 3.6)
    out = np.zeros(round(0.26 * SR), dtype=np.float32)
    out[:len(crack)] += crack * 0.9
    out[:len(body)] += body
    return normalize(room(out, 0.18, seed + 2))


def boing(seed):
    """Spring wobble for takes, squash and stretch."""
    n = round(0.55 * SR)
    t = np.arange(n) / SR
    wobble = 26 + 16 * np.sin(2 * np.pi * 11 * t) * np.exp(-3 * t)
    frequency = 330 * np.exp(-1.6 * t) * (1 + 0.35 * np.exp(-8 * t))
    phase = 2 * np.pi * np.cumsum(frequency * (1 + 0.06 * wobble / 42)) / SR
    tone = (np.sin(phase) * 0.8 + np.sin(phase * 2) * 0.16).astype(np.float32)
    tone *= envelope(0.55, 0.004, 2.2)
    return normalize(room(tone, 0.06, seed))


def pop(seed):
    """Small burst: cork, bubble, kernel."""
    click = highpass(noise(0.014, seed), 2500) * envelope(0.014, 0.0003, 5)
    body = sweep(0.13, 780, 260, curve=0.4) * envelope(0.13, 0.001, 3.2)
    out = np.zeros(round(0.20 * SR), dtype=np.float32)
    out[:len(click)] += click
    out[:len(body)] += body * 0.9
    return normalize(room(out, 0.12, seed + 3))


def burst(seed):
    """Container letting go: sub thump, blast, crackle tail."""
    sub = sweep(0.60, 70, 38, curve=0.8) * envelope(0.60, 0.006, 2.6)
    blast = sweep_filter(noise(0.55, seed), 7000, 240, 1.2) * envelope(0.55, 0.002, 2.2)
    crackle = lowpass(grains(28, 0.55, seed + 5, low=1400, high=7000, decay=2.0), 10000)
    out = np.zeros(round(1.05 * SR), dtype=np.float32)
    for part, gain in ((sub, 1.0), (blast, 0.95), (crackle, 0.45)):
        segment = pad(part * gain, len(out) / SR)[:len(out)]
        out[:len(segment)] += segment
    return normalize(room(out, 0.20, seed))


def debris(seed):
    """Small pieces landing over half a second."""
    cluster = lowpass(grains(22, 0.62, seed, low=900, high=4600, decay=1.6, spread=0.8), 10000)
    return normalize(room(cluster, 0.26, seed))


def whoosh(seed):
    """Movement past camera: bandpass noise swelling and fading."""
    air = noise(0.46, seed)
    shaped = sweep_filter(air, 320, 3000, 1.1)
    shaped = lowpass(shaped, 3400) * envelope(0.46, 0.09, 2.0, hold=0.14)
    low = sweep(0.46, 180, 90, curve=0.7) * envelope(0.46, 0.12, 2.4) * 0.18
    out = shaped.astype(np.float32)
    out[:len(low)] += low
    return normalize(room(out, 0.10, seed))


def swish(seed):
    """Cloth or fur brush: softer and shorter than whoosh."""
    air = bandpass(noise(0.30, seed), 500, 2400) * envelope(0.30, 0.06, 2.2, hold=0.08)
    return normalize(room(air, 0.08, seed + 1), 0.55)


def splash(seed):
    """Crown splash: broad hit, sweep down, droplet spray."""
    r = rng(seed)
    hit = sweep_filter(noise(0.42, seed), 5000, 650, 0.9) * envelope(0.42, 0.004, 2.4)
    hit = lowpass(hit, 9000)
    out = np.zeros(round(0.85 * SR), dtype=np.float32)
    out[:len(hit)] += hit
    for i in range(7):
        start = round(r.uniform(0.03, 0.30) * SR)
        length = r.uniform(0.05, 0.11)
        drop = sweep(length, r.uniform(900, 1500), r.uniform(1800, 2600), curve=0.6)
        drop *= envelope(length, 0.001, 3.4) * r.uniform(0.2, 0.5)
        size = len(drop)
        if start + size < len(out):
            out[start:start + size] += drop
    return normalize(room(out, 0.24, seed))


def drip(seed):
    """Single drop in a quiet room."""
    plink = sweep(0.10, 620, 1500, curve=0.5) * envelope(0.10, 0.001, 3.6)
    body = lowpass(noise(0.05, seed), 900) * envelope(0.05, 0.001, 5) * 0.25
    out = np.zeros(round(0.16 * SR), dtype=np.float32)
    out[:len(plink)] += plink
    out[:len(body)] += body
    return normalize(room(out, 0.30, seed + 2), 0.6)


def sip(seed):
    """Straw pull: rising filtered noise and a small close."""
    draw = lowpass(noise(0.32, seed), 6000)
    shaped = sweep_filter(draw, 420, 1600, 0.8)
    shaped *= envelope(0.32, 0.10, 1.6, hold=0.14) * 0.9
    close = sweep(0.09, 300, 150, curve=0.5) * envelope(0.09, 0.002, 3.4) * 0.5
    out = shaped.astype(np.float32)
    out = pad(out, 0.42)
    out[-len(close):] += close
    return normalize(room(out, 0.08, seed), 0.62)


def gulp(seed):
    """One swallow."""
    body = sweep(0.22, 210, 88, curve=0.55) * envelope(0.22, 0.006, 3.0)
    wet = bandpass(noise(0.10, seed), 200, 800, 3) * envelope(0.10, 0.004, 4) * 0.4
    out = np.zeros(round(0.30 * SR), dtype=np.float32)
    out[:len(body)] += body
    out[:len(wet)] += wet
    return normalize(room(out, 0.14, seed + 1), 0.68)


def slosh(seed):
    """Liquid rocking in a container."""
    n = round(0.75 * SR)
    t = np.arange(n) / SR
    motion = 0.55 + 0.45 * np.sin(2 * np.pi * 2.6 * t + 0.4)
    liquid = bandpass(noise(0.75, seed), 240, 900, 3) * motion
    liquid = liquid + sweep(0.75, 120, 96) * motion * 0.16
    liquid *= envelope(0.75, 0.12, 1.8, hold=0.18)
    return normalize(room(liquid.astype(np.float32), 0.12, seed), 0.55)


def pour(seed):
    """Steady pour with wobble and drops."""
    n = round(1.0 * SR)
    t = np.arange(n) / SR
    wobble = 0.7 + 0.3 * np.sin(2 * np.pi * 5.5 * t + 1.1)
    stream = bandpass(noise(1.0, seed), 420, 1900, 3) * wobble * envelope(1.0, 0.10, 1.3, hold=0.30)
    stream = stream + sweep(1.0, 150, 120) * envelope(1.0, 0.10, 1.4) * 0.12
    drops = grains(9, 0.95, seed + 9, low=1200, high=4200, decay=1.2) * 0.25
    out = stream.astype(np.float32)
    out[:len(drops)] += drops
    return normalize(room(out, 0.10, seed), 0.58)


def rattle(seed):
    """Loose pieces in a container."""
    cluster = grains(16, 0.34, seed, low=700, high=3800, decay=2.0, spread=0.9)
    tone = sweep(0.12, 420, 300) * envelope(0.12, 0.002, 4) * 0.2
    out = cluster
    out[:len(tone)] += tone
    return normalize(room(out, 0.14, seed), 0.6)


def clink(seed):
    """Metal or glass contact."""
    partials = [(1240, 0.5), (1870, 0.34), (2610, 0.22), (3410, 0.12)]
    out = np.zeros(round(0.30 * SR), dtype=np.float32)
    for frequency, gain in partials:
        tone = sweep(0.28, frequency, frequency * 0.985) * envelope(0.28, 0.0008, 4.2) * gain
        out[:len(tone)] += tone
    out[:len(out)] *= 0.9
    return normalize(room(out, 0.18, seed), 0.66)


def click(seed):
    """Button, latch, or switch."""
    body = bandpass(noise(0.020, seed), 1200, 6000) * envelope(0.020, 0.0003, 5)
    tick = sweep(0.030, 900, 500) * envelope(0.030, 0.0005, 4) * 0.5
    out = np.zeros(round(0.06 * SR), dtype=np.float32)
    out[:len(body)] += body
    out[:len(tick)] += tick
    return normalize(out, 0.78)


def tap(seed):
    """Finger on wood."""
    body = bandpass(noise(0.05, seed), 500, 2200) * envelope(0.05, 0.0006, 4.5)
    tone = sweep(0.07, 300, 180) * envelope(0.07, 0.001, 4) * 0.5
    out = np.zeros(round(0.10 * SR), dtype=np.float32)
    out[:len(body)] += body
    out[:len(tone)] += tone
    return normalize(room(out, 0.10, seed))


def creak(seed):
    """Old hinge or plank for slow comedic tension."""
    n = round(0.65 * SR)
    t = np.arange(n) / SR
    frequency = 180 + 60 * np.sin(2 * np.pi * 1.4 * t) + 40 * t
    phase = 2 * np.pi * np.cumsum(frequency) / SR
    tone = (np.sin(phase) * 0.5 + np.sin(phase * 2.02) * 0.3) * envelope(0.65, 0.08, 1.6)
    grain = bandpass(noise(0.65, seed), 260, 1500) * envelope(0.65, 0.05, 1.8) * 0.5
    return normalize(room((tone + grain).astype(np.float32), 0.14, seed), 0.55)


def squeak(seed):
    """Tiny rubber or hinge squeak for a quick reaction."""
    n = round(0.24 * SR)
    t = np.arange(n) / SR
    frequency = 820 + 260 * np.sin(2 * np.pi * 7.5 * t) + 180 * t
    tone = np.sin(2 * np.pi * np.cumsum(frequency) / SR)
    tone *= envelope(0.24, 0.01, 2.6) * (0.8 + 0.2 * np.sin(2 * np.pi * 19 * t))
    return normalize(room(tone.astype(np.float32), 0.08, seed), 0.58)


def zap(seed):
    """Short descending electric zap with a bright noise edge."""
    tone = sweep(0.22, 1800, 180, curve=0.45) * envelope(0.22, 0.001, 3.2)
    edge = highpass(noise(0.06, seed), 2400) * envelope(0.06, 0.0004, 5) * 0.7
    out = np.zeros(round(0.3 * SR), dtype=np.float32)
    out[:len(tone)] += tone
    out[:len(edge)] += edge
    return normalize(room(out, 0.1, seed + 1), 0.6)


def bell(seed):
    """Small bell or notification with inharmonic partials."""
    partials = [(880, 0.5), (1320, 0.3), (1980, 0.2), (2640, 0.12)]
    out = np.zeros(round(0.9 * SR), dtype=np.float32)
    for frequency, gain in partials:
        tone = sweep(0.88, frequency, frequency * 0.998) * envelope(0.88, 0.001, 2.6) * gain
        out[:len(tone)] += tone
    return normalize(room(out, 0.2, seed), 0.62)


def bubble(seed):
    """A few rising water bubbles for liquid comedy."""
    r = rng(seed)
    out = np.zeros(round(0.65 * SR), dtype=np.float32)
    for index in range(6):
        start = round(r.uniform(0, 0.42) * SR)
        length = r.uniform(0.05, 0.11)
        tone = sweep(length, r.uniform(400, 650), r.uniform(900, 1500), curve=0.55)
        tone *= envelope(length, 0.001, 3.4) * r.uniform(0.25, 0.7)
        if start + len(tone) < len(out):
            out[start:start + len(tone)] += tone
    return normalize(room(out, 0.18, seed), 0.55)


def splat(seed):
    """Soft wet splat: low body, broad noise, tiny droplets."""
    body = sweep(0.24, 150, 58, curve=0.5) * envelope(0.24, 0.002, 3.2)
    wet = lowpass(noise(0.3, seed), 2600) * envelope(0.3, 0.003, 2.6) * 0.8
    drops = grains(6, 0.3, seed + 2, low=1300, high=4200, decay=1.8) * 0.3
    out = np.zeros(round(0.42 * SR), dtype=np.float32)
    for part in (body, wet, drops):
        out[:len(part)] += part
    return normalize(room(out, 0.18, seed + 3), 0.62)


def crumble(seed):
    """Dry crumble or cereal pieces collapsing."""
    cluster = grains(30, 0.8, seed, low=600, high=3600, decay=1.4, spread=0.7)
    body = lowpass(noise(0.55, seed + 4), 900) * envelope(0.55, 0.01, 2.2) * 0.4
    out = cluster
    out[:len(body)] += body
    return normalize(room(out, 0.2, seed + 2), 0.55)


def wind(seed):
    """Loopable air bed for exteriors and quiet tension."""
    n = round(1.4 * SR)
    t = np.arange(n) / SR
    air = noise(1.4, seed)
    shaped = sweep_filter(air, 260, 900, 0.8)
    wobble = 0.55 + 0.45 * np.sin(2 * np.pi * 0.8 * t + 0.4)
    shaped *= envelope(1.4, 0.18, 1.2, hold=0.4) * wobble
    low = sweep(1.4, 90, 70) * envelope(1.4, 0.2, 1.4) * 0.08
    out = shaped.astype(np.float32)
    out[:len(low)] += low
    return normalize(room(out, 0.08, seed), 0.48)


def heartbeat(seed):
    """Two low thumps for tension or a comic pause."""
    out = np.zeros(round(0.85 * SR), dtype=np.float32)
    for start, gain in ((0.0, 1.0), (0.24, 0.72)):
        body = sweep(0.18, 86, 42, curve=0.5) * envelope(0.18, 0.004, 3.0) * gain
        click = bandpass(noise(0.03, seed + int(start * 10)), 500, 2200) * envelope(0.03, 0.0005, 5) * 0.3
        offset = round(start * SR)
        out[offset:offset + len(body)] += body
        out[offset:offset + len(click)] += click
    return normalize(room(out, 0.12, seed), 0.66)


def footstep(seed):
    """A soft footfall with a short scuff."""
    body = sweep(0.16, 110, 48, curve=0.55) * envelope(0.16, 0.003, 3.2)
    scuff = bandpass(noise(0.1, seed), 700, 2800) * envelope(0.1, 0.004, 3.4) * 0.4
    out = np.zeros(round(0.24 * SR), dtype=np.float32)
    out[:len(body)] += body
    out[:len(scuff)] += scuff
    return normalize(room(out, 0.12, seed + 1), 0.6)


def sparkle(seed):
    """High, glittery cascade for reveals and magic."""
    r = rng(seed)
    out = np.zeros(round(0.9 * SR), dtype=np.float32)
    for index in range(14):
        start = round(r.uniform(0, 0.55) * SR)
        length = r.uniform(0.04, 0.12)
        tone = sweep(length, r.uniform(1800, 3200), r.uniform(3200, 6200), curve=0.6)
        tone *= envelope(length, 0.001, 3.8) * r.uniform(0.12, 0.45)
        if start + len(tone) < len(out):
            out[start:start + len(tone)] += tone
    return normalize(room(out, 0.2, seed), 0.5)


def glass(seed):
    """Bright glass contact, slightly different from metal."""
    partials = [(1760, 0.4), (2630, 0.3), (3920, 0.2), (5400, 0.1)]
    out = np.zeros(round(0.45 * SR), dtype=np.float32)
    for frequency, gain in partials:
        tone = sweep(0.42, frequency, frequency * 0.997) * envelope(0.42, 0.0006, 4.4) * gain
        out[:len(tone)] += tone
    return normalize(room(out, 0.16, seed), 0.6)


def metal(seed):
    """Larger metal ring for props and machinery."""
    partials = [(620, 0.45), (940, 0.3), (1510, 0.2), (2380, 0.12)]
    out = np.zeros(round(0.55 * SR), dtype=np.float32)
    for frequency, gain in partials:
        tone = sweep(0.5, frequency, frequency * 0.994) * envelope(0.5, 0.0008, 3.8) * gain
        out[:len(tone)] += tone
    impact = lowpass(noise(0.08, seed), 1800) * envelope(0.08, 0.0006, 5) * 0.35
    out[:len(impact)] += impact
    return normalize(room(out, 0.2, seed + 1), 0.62)


RECIPES = {
    "thud": thud,
    "bonk": bonk,
    "thwack": thwack,
    "boing": boing,
    "pop": pop,
    "burst": burst,
    "debris": debris,
    "whoosh": whoosh,
    "swish": swish,
    "splash": splash,
    "drip": drip,
    "sip": sip,
    "gulp": gulp,
    "slosh": slosh,
    "pour": pour,
    "rattle": rattle,
    "clink": clink,
    "click": click,
    "tap": tap,
    "creak": creak,
    "squeak": squeak,
    "zap": zap,
    "bell": bell,
    "bubble": bubble,
    "splat": splat,
    "crumble": crumble,
    "wind": wind,
    "heartbeat": heartbeat,
    "footstep": footstep,
    "sparkle": sparkle,
    "glass": glass,
    "metal": metal,
}

# Peaks are matched per file, so the mix gain carries the size of the event.
SUGGESTED_GAIN = {
    "burst": 0.78, "debris": 0.52, "splash": 0.62, "thud": 0.55, "bonk": 0.5,
    "thwack": 0.58, "boing": 0.42, "pop": 0.46, "whoosh": 0.4, "swish": 0.3,
    "drip": 0.4, "sip": 0.4, "gulp": 0.4, "slosh": 0.36, "pour": 0.4,
    "rattle": 0.36, "clink": 0.38, "click": 0.34, "tap": 0.3, "creak": 0.32,
    "squeak": 0.38, "zap": 0.42, "bell": 0.4, "bubble": 0.34, "splat": 0.5,
    "crumble": 0.38, "wind": 0.22, "heartbeat": 0.42, "footstep": 0.34,
    "sparkle": 0.34, "glass": 0.4, "metal": 0.4,
}


def write_wav(path, samples):
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, SR, 0, "NONE", "not compressed"))
        stream.writeframes(pcm.tobytes())


def build(channel, *, library="audio/cast-v2.json", voices=None, variants=3, only=None):
    """Write WAVs and an audio library JSON into a channel folder."""
    channel = Path(channel).resolve()
    target = (channel / library).resolve()
    if not target.is_relative_to(channel):
        raise ValueError("The audio library must live inside the channel folder")
    folder = target.parent / "sfx"
    folder.mkdir(parents=True, exist_ok=True)
    names = [only] if only else list(RECIPES)
    sounds, report = {}, []
    for name in names:
        recipe = RECIPES[name]
        files = []
        for index in range(1, variants + 1):
            seed = int.from_bytes(sha256(f"{name}:{index}".encode()).digest()[:4], "big") % 100_000
            samples = recipe(seed=seed)
            samples = vary(samples, 1 + (index - (variants + 1) / 2) * 0.045)
            file = folder / f"{name}-{index}.wav"
            write_wav(file, samples)
            files.append(str(file.relative_to(target.parent)))
            report.append({"sound": name, "variant": index, "file": str(file.relative_to(channel)),
                           "seconds": round(len(samples) / SR, 3),
                           "peak": round(float(np.max(np.abs(samples))), 3)})
        sounds[name] = files
    data = {"version": 2, "voices": {}, "sounds": sounds}
    if voices:
        source = (channel / voices).resolve()
        data["voices"] = json.loads(source.read_text(encoding="utf-8")).get("voices", {})
        for name, files in json.loads(source.read_text(encoding="utf-8")).get("sounds", {}).items():
            data["sounds"].setdefault(name, files)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"library": str(target.relative_to(channel)), "sounds": len(sounds), "files": report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", type=Path, help="channel folder, for example channels/<slug>")
    parser.add_argument("--library", default="audio/cast-v2.json", help="library JSON relative to the channel")
    parser.add_argument("--voices", help="existing library to copy voice profiles from, relative to the channel")
    parser.add_argument("--variants", type=int, default=3)
    parser.add_argument("--only", choices=sorted(RECIPES), help="synthesize a single sound")
    args = parser.parse_args()
    try:
        report = build(args.channel, library=args.library, voices=args.voices,
                       variants=args.variants, only=args.only)
        print(json.dumps({"library": report["library"], "sounds": report["sounds"],
                          "files": len(report["files"])}, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(f"studio: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
