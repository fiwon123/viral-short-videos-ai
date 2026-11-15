"""Measure word timings from a spoken take so captions land on the voice.

Two strategies, best first:

* ``whisper``: when ``faster-whisper`` is installed, transcribe the take with
  word timestamps and map the recognised words onto the script words.
* ``energy``: dependency-free. Find pauses in the take's loudness envelope,
  pin punctuation to the nearest real pause, then spread words over the
  voiced audio by syllable weight and snap boundaries to nearby gaps.

Both return ``[{"text", "start", "end"}]`` in seconds relative to the clip.
Results are cached next to Kokoro takes so re-renders stay deterministic.
"""

from difflib import SequenceMatcher
from hashlib import sha256
import json
import os
import re

import numpy as np

HOP = 0.01  # Envelope resolution in seconds.
PUNCTUATION = ".,!?;:—–…"
_VOWELS = re.compile(r"[aeiouy]+")


def syllables(word):
    """Rough syllable count that works well enough for timing weights."""
    clean = re.sub(r"[^a-z0-9]", "", word.lower())
    if not clean:
        return 1
    if clean.isdigit():
        return max(1, len(clean)) * 2
    count = len(_VOWELS.findall(clean))
    if clean.endswith("e") and count > 1 and not clean.endswith(("le", "ee")):
        count -= 1
    return max(1, count)


def envelope(clip, rate):
    hop = max(1, int(rate * HOP))
    frames = len(clip) // hop
    if frames == 0:
        return np.zeros(1)
    window = np.asarray(clip[:frames * hop], dtype=np.float64).reshape(frames, hop)
    rms = np.sqrt(np.mean(window ** 2, axis=1))
    kernel = np.ones(3) / 3
    return np.convolve(rms, kernel, mode="same")


def gaps(env, minimum=0.05):
    """Interior silent runs as (start, end) seconds, longest first."""
    if not len(env) or float(env.max()) <= 0:
        return []
    voiced = env > max(float(env.max()) * 0.07, float(np.percentile(env, 15)) * 1.4)
    found, start = [], None
    for index, flag in enumerate(voiced):
        if not flag and start is None:
            start = index
        elif flag and start is not None:
            if start > 0 and (index - start) * HOP >= minimum:
                found.append((start * HOP, index * HOP))
            start = None
    return sorted(found, key=lambda gap: gap[0] - gap[1])


def _voiced_map(env, start, end):
    """Cumulative voiced time between start and end seconds."""
    lo, hi = int(start / HOP), max(int(start / HOP) + 1, int(end / HOP))
    piece = env[lo:hi]
    if not len(piece) or float(piece.max()) <= 0:
        return np.linspace(start, end, 2), np.array([0.0, 1.0])
    weight = np.clip(piece / float(piece.max()), 0.08, 1.0)
    cumulative = np.concatenate([[0.0], np.cumsum(weight)])
    times = start + np.arange(len(cumulative)) * HOP
    return times, cumulative / cumulative[-1]


def energy(clip, rate, words):
    """Align words to a clip using pauses and syllable-weighted voiced time."""
    if not words:
        return []
    total = len(clip) / rate
    env = envelope(clip, rate)
    weights = [syllables(word) for word in words]
    span = sum(weights)
    found = gaps(env)
    # Pin each punctuation break to the closest unused real pause.
    boundaries = []
    used = set()
    cursor = 0
    for index, word in enumerate(words[:-1]):
        cursor += weights[index]
        if word[-1:] not in PUNCTUATION:
            continue
        expected = total * cursor / span
        best = None
        for gap_index, (gap_start, gap_end) in enumerate(found):
            if gap_index in used or abs((gap_start + gap_end) / 2 - expected) > total * 0.25:
                continue
            if best is None or abs((gap_start + gap_end) / 2 - expected) < abs(sum(found[best]) / 2 - expected):
                best = gap_index
        if best is not None:
            used.add(best)
            boundaries.append((index, *found[best]))
    boundaries.sort()
    result = []
    segment_start, first = 0.0, 0
    for last, gap_start, gap_end in [*boundaries, (len(words) - 1, total, total)]:
        if gap_start <= segment_start:
            continue
        times, fractions = _voiced_map(env, segment_start, gap_start)
        piece = weights[first:last + 1]
        cumulative = np.concatenate([[0.0], np.cumsum(piece)]) / max(1, sum(piece))
        edges = np.interp(cumulative, fractions, times)
        for offset, word in enumerate(words[first:last + 1]):
            result.append({"text": word, "start": float(edges[offset]), "end": float(edges[offset + 1])})
        segment_start, first = gap_end, last + 1
    for word in words[len(result):]:  # Degenerate clips: keep every word.
        result.append({"text": word, "start": total, "end": total})
    _snap(result, [gap for index, gap in enumerate(found) if index not in used])
    return _tidy(result, total)


def _snap(words, free_gaps):
    """Move the nearest word boundary onto each unclaimed pause."""
    for gap_start, gap_end in free_gaps:
        middle = (gap_start + gap_end) / 2
        best, distance = None, None
        for index in range(len(words) - 1):
            edge = words[index]["end"]
            reach = 0.45 * min(words[index]["end"] - words[index]["start"],
                               words[index + 1]["end"] - words[index + 1]["start"])
            if abs(edge - middle) <= max(reach, 0.04) and (distance is None or abs(edge - middle) < distance):
                best, distance = index, abs(edge - middle)
        if best is not None:
            if gap_start > words[best]["start"]:
                words[best]["end"] = gap_start
            if gap_end < words[best + 1]["end"]:
                words[best + 1]["start"] = gap_end


def _tidy(words, total):
    previous = 0.0
    for word in words:
        word["start"] = round(max(previous, min(word["start"], total)), 3)
        word["end"] = round(max(word["start"] + 0.02, min(word["end"], total)), 3)
        previous = word["start"]
    return words


def _normal(word):
    return re.sub(r"[^a-z0-9']", "", word.lower())


def map_recognised(script, heard):
    """Copy recognised timings onto script words; interpolate the misses."""
    matcher = SequenceMatcher(a=[_normal(word) for word in script],
                              b=[_normal(item["text"]) for item in heard], autojunk=False)
    timed = [None] * len(script)
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            item = heard[block.b + offset]
            timed[block.a + offset] = (item["start"], item["end"])
    known = [index for index, value in enumerate(timed) if value]
    if not known:
        return None
    result = []
    for index, word in enumerate(script):
        if timed[index]:
            start, end = timed[index]
        else:
            before = max((k for k in known if k < index), default=None)
            after = min((k for k in known if k > index), default=None)
            lo = timed[before][1] if before is not None else (timed[after][0] if after is not None else 0)
            hi = timed[after][0] if after is not None else lo + 0.25
            gap_words = (after if after is not None else len(script)) - (before if before is not None else -1) - 1
            step = (hi - lo) / max(1, gap_words)
            position = index - (before if before is not None else -1) - 1
            start, end = lo + step * position, lo + step * (position + 1)
        result.append({"text": word, "start": float(start), "end": float(end)})
    return result


def whisper(clip, rate, words):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model = _whisper_model(WhisperModel)
    audio = np.asarray(clip, dtype=np.float32)
    if rate != 16000:
        target = int(len(audio) * 16000 / rate)
        audio = np.interp(np.linspace(0, len(audio) - 1, target), np.arange(len(audio)), audio).astype(np.float32)
    segments, _ = model.transcribe(audio, word_timestamps=True, initial_prompt=" ".join(words),
                                   condition_on_previous_text=False, vad_filter=False)
    heard = [{"text": item.word.strip(), "start": item.start, "end": item.end}
             for segment in segments for item in (segment.words or [])]
    mapped = map_recognised(words, heard) if heard else None
    return _tidy(mapped, len(clip) / rate) if mapped else None


_MODEL = {}


def _whisper_model(factory):
    name = os.environ.get("STUDIO_WHISPER_MODEL", "base.en")
    if name not in _MODEL:
        _MODEL[name] = factory(name, device="cpu", compute_type="int8")
    return _MODEL[name]


def measure(clip, rate, text, cache=None, method=None):
    """Return (words, method) for a clip. ``method`` forces energy/whisper/auto."""
    words = [word for word in text.split() if word]
    if not words:
        return [], "none"
    method = method or os.environ.get("STUDIO_WORD_TIMING", "auto")
    key = None
    if cache is not None:
        digest = sha256(np.asarray(clip, dtype=np.float32).tobytes())
        digest.update(json.dumps([words, method, os.environ.get("STUDIO_WHISPER_MODEL", "base.en")]).encode())
        key = cache / f"words-{digest.hexdigest()[:24]}.json"
        if key.is_file():
            stored = json.loads(key.read_text(encoding="utf-8"))
            return stored["words"], stored["method"]
    result, used = None, "energy"
    if method in {"auto", "whisper"}:
        result = whisper(clip, rate, words)
        used = "whisper" if result else used
        if result is None and method == "whisper":
            raise ValueError("STUDIO_WORD_TIMING=whisper needs faster-whisper installed in the studio Python")
    if result is None:
        result = energy(clip, rate, words)
    if key is not None:
        cache.mkdir(parents=True, exist_ok=True)
        key.write_text(json.dumps({"words": result, "method": used}), encoding="utf-8")
    return result, used
