"""Automatic lip sync: spoken text plus measured timing become mouth shapes.

The studio speaks a Preston Blair style set of nine visemes::

    rest  closed, relaxed             mbp  lips pressed (M, B, P)
    ai    open (A, I, father)         e    wide, teeth (E, EE, schwa)
    o     round (O, AW)               u    small pucker (OO, W, Q)
    fv    lip under teeth (F, V)      l    tongue up (L, TH)
    etc   teeth slightly apart (T D K G N S Z R CH J Y H ...)

Phonemes come from eSpeak NG (``espeak-ng --ipa``) in the voice's language, or
from English spelling rules when eSpeak is missing. Each word's phonemes are
spread over its measured start/end (vowels weigh more than consonants), the
mouth closes in pauses and silent gaps, shapes shorter than ``hold`` frames are
folded into a neighbour (lip closures win so plosives still read), and the
result leads the audio by one frame like hand animation.

A character does not need all nine shapes. ``resolve`` maps each canonical
shape to the closest one its mouth layers provide, through a fallback chain,
and also accepts Rhubarb Lip Sync letters (A-H, X) as layer ``viseme`` names.
"""

from functools import lru_cache
import re
import shutil
import subprocess

VISEMES = ("rest", "mbp", "ai", "e", "o", "u", "fv", "l", "etc")
RHUBARB = {"X": "rest", "A": "mbp", "B": "etc", "C": "e", "D": "ai", "E": "o", "F": "u", "G": "fv", "H": "l"}
FALLBACK = {
    "rest": ["rest", "X", "flat", "mbp", "A", "smile"],
    "mbp": ["mbp", "A", "rest", "X", "flat"],
    "ai": ["ai", "D", "open", "wide", "e", "C", "etc", "B"],
    "e": ["e", "C", "wide", "etc", "B", "open", "ai", "D"],
    "o": ["o", "E", "u", "F", "open", "ai", "D"],
    "u": ["u", "F", "o", "E", "etc", "B", "open"],
    "fv": ["fv", "G", "etc", "B", "flat", "mbp", "A", "rest"],
    "l": ["l", "H", "etc", "B", "open", "ai", "D"],
    "etc": ["etc", "B", "e", "C", "open", "wide", "ai", "D"],
}
PRIORITY = {"mbp": 3, "fv": 2, "ai": 2, "o": 2, "u": 2, "e": 2, "l": 1, "etc": 1, "rest": 0}
WEIGHT = {"ai": 2.0, "e": 1.6, "o": 2.0, "u": 1.7, "mbp": 1.0, "fv": 1.0, "l": 0.9, "etc": 0.8}

# IPA, longest symbols first so diphthongs win over their first letter.
IPA = [
    ("aɪ", ["ai", "e"]), ("aʊ", ["ai", "u"]), ("eɪ", ["e"]), ("oʊ", ["o", "u"]), ("əʊ", ["o", "u"]),
    ("ɔɪ", ["o", "e"]), ("tʃ", ["etc"]), ("dʒ", ["etc"]),
    ("m", ["mbp"]), ("b", ["mbp"]), ("p", ["mbp"]), ("ɱ", ["mbp"]),
    ("f", ["fv"]), ("v", ["fv"]), ("ʋ", ["fv"]),
    ("l", ["l"]), ("ɫ", ["l"]), ("ʎ", ["l"]), ("θ", ["l"]), ("ð", ["l"]),
    ("w", ["u"]), ("ʍ", ["u"]), ("u", ["u"]), ("ʊ", ["u"]), ("y", ["u"]), ("ʏ", ["u"]), ("ɥ", ["u"]),
    ("o", ["o"]), ("ɔ", ["o"]), ("ɒ", ["o"]), ("ø", ["o"]), ("œ", ["o"]),
    ("a", ["ai"]), ("ɑ", ["ai"]), ("æ", ["ai"]), ("ʌ", ["ai"]), ("ɐ", ["ai"]), ("ɶ", ["ai"]),
    ("e", ["e"]), ("ɛ", ["e"]), ("i", ["e"]), ("ɪ", ["e"]), ("ə", ["e"]), ("ɜ", ["e"]), ("ɚ", ["e"]),
    ("ɝ", ["e"]), ("ɨ", ["e"]), ("ɯ", ["e"]), ("ɤ", ["o"]),
]
VOWELS = {"ai", "e", "o", "u"}
IGNORE = set("ˈˌːˑ̩̯̃‿-_ |.,!?;:'\"()[]")

# Spelling fallback (English-leaning), longest patterns first.
SPELLING = [
    ("tion", ["etc", "e", "etc"]), ("igh", ["ai", "e"]), ("ough", ["o"]), ("augh", ["o"]),
    ("th", ["l"]), ("sh", ["etc"]), ("ch", ["etc"]), ("ph", ["fv"]), ("wh", ["u"]), ("qu", ["u"]),
    ("oo", ["u"]), ("ee", ["e"]), ("ea", ["e"]), ("ou", ["ai", "u"]), ("ow", ["o", "u"]), ("oa", ["o"]),
    ("ai", ["e"]), ("ay", ["e"]), ("oi", ["o", "e"]), ("oy", ["o", "e"]), ("au", ["o"]), ("aw", ["o"]),
    ("ck", ["etc"]), ("ng", ["etc"]),
    ("a", ["ai"]), ("e", ["e"]), ("i", ["e"]), ("y", ["e"]), ("o", ["o"]), ("u", ["u"]), ("w", ["u"]),
    ("m", ["mbp"]), ("b", ["mbp"]), ("p", ["mbp"]), ("f", ["fv"]), ("v", ["fv"]), ("l", ["l"]),
]


def _parse(text, table):
    shapes, index = [], 0
    while index < len(text):
        if text[index] in IGNORE or text[index].isdigit():
            index += 1
            continue
        for symbol, mapped in table:
            if text.startswith(symbol, index):
                shapes.extend(mapped)
                index += len(symbol)
                break
        else:
            if text[index].isalpha():
                shapes.append("etc")
            index += 1
    return shapes


def spelling_shapes(word):
    word = re.sub(r"[^a-zà-ÿ]", "", word.lower())
    if len(word) > 2 and word.endswith("e") and word[-2] not in "aeiouy":
        word = word[:-1]  # Silent final e.
    plain = word.translate(str.maketrans("àáâãäåèéêëìíîïòóôõöùúûüýÿç", "aaaaaaeeeeiiiiooooouuuuyyc"))
    return _parse(plain, SPELLING)


def _espeak_voice(language):
    language = (language or "en-us").lower()
    aliases = {"en": "en-us", "a": "en-us", "b": "en-gb", "pt": "pt-br", "zh": "cmn", "fr-fr": "fr", "ja": "ja"}
    return aliases.get(language, language)


@lru_cache(maxsize=4096)
def phoneme_shapes(word, language="en-us"):
    """Viseme list for one word, from eSpeak NG IPA when available."""
    clean = word.strip().strip(".,!?;:\"'()[]*")
    if not clean:
        return ()
    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if binary:
        for voice in (_espeak_voice(language), _espeak_voice(language).split("-")[0], "en-us"):
            try:
                result = subprocess.run([binary, "-q", "--ipa", "-v", voice, clean], capture_output=True,
                                        text=True, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                break
            ipa = result.stdout.strip()
            if result.returncode == 0 and ipa:
                shapes = _parse(ipa, IPA)
                if shapes:
                    return tuple(shapes)
    return tuple(spelling_shapes(clean))


def _spread(shapes, start, end):
    """Segments (shape, start, end) in seconds across one word."""
    merged = []
    for shape in shapes:
        if merged and merged[-1][0] == shape:
            merged[-1][1] += WEIGHT.get(shape, 1)
        else:
            merged.append([shape, WEIGHT.get(shape, 1)])
    total = sum(weight for _, weight in merged) or 1
    cursor, segments = start, []
    for shape, weight in merged:
        length = (end - start) * weight / total
        segments.append((shape, cursor, cursor + length))
        cursor += length
    return segments


def _words_timing(words, spoken, levels, fps):
    """Pair spoken words with measured spans; spread by length when counts differ."""
    spoken_words = [word for word in spoken.split() if word.strip(".,!?;:\"'()[]*")]
    if words and len(words) == len(spoken_words):
        return [(word, float(item["start"]), float(item["end"])) for word, item in zip(spoken_words, words)]
    if words:
        start, end = float(words[0]["start"]), float(words[-1]["end"])
    else:
        loud = [index for index, value in enumerate(levels if levels is not None else []) if value > 0.08]
        if not loud:
            return []
        start, end = loud[0] / fps, (loud[-1] + 1) / fps
    weights = [max(1, len(re.sub(r"\W", "", word))) for word in spoken_words] or [1]
    total, cursor, result = sum(weights), start, []
    for word, weight in zip(spoken_words, weights):
        length = (end - start) * weight / total
        result.append((word, cursor, cursor + length))
        cursor += length
    return result


def visemes(spoken, words=None, levels=None, fps=30, language="en-us", *, hold=None, lead=1, gap=0.12,
            silence=0.06):
    """Viseme keys ``[{"at": seconds, "shape": name}]`` relative to the start of the take.

    ``words`` are measured spans in seconds; ``levels`` the per-frame mouth level of
    the take (0-1), used to close the mouth in silent stretches inside a word span.
    """
    timed = _words_timing(words, spoken.replace("*", ""), levels, fps)
    if not timed:
        return []
    segments = []
    for index, (word, start, end) in enumerate(timed):
        segments.extend(_spread(phoneme_shapes(word, language), start, end))
        following = timed[index + 1][1] if index + 1 < len(timed) else None
        if following is None or following - end > gap:
            segments.append(("rest", end, following if following is not None else end + 0.25))
    # Frames, with a one-frame lead.
    frames = []
    for shape, start, end in segments:
        a, b = max(0, round(start * fps) - lead), max(0, round(end * fps) - lead)
        if b > a:
            frames.append([shape, a, b])
    if levels is not None and len(levels):
        quiet_run = max(2, round(fps * 0.1))
        closed, run_start = [], None
        for index, value in enumerate(list(levels) + [1.0]):
            if value < silence and run_start is None:
                run_start = index
            elif value >= silence and run_start is not None:
                if index - run_start >= quiet_run:
                    closed.append((max(0, run_start - lead), max(0, index - lead)))
                run_start = None
        for a, b in closed:
            cut = []
            for shape, start, end in frames:
                if end <= a or start >= b or shape == "rest":
                    cut.append([shape, start, end])
                    continue
                if start < a:
                    cut.append([shape, start, a])
                cut.append(["rest", max(start, a), min(end, b)])
                if end > b:
                    cut.append([shape, b, end])
            frames = cut
    frames = _merge(frames)
    frames = _enforce_hold(frames, hold or max(2, round(fps / 12)))
    return [{"at": round(start / fps, 4), "shape": shape} for shape, start, _ in _merge(frames)]


def _merge(frames):
    merged = []
    for shape, start, end in sorted(frames, key=lambda item: item[1]):
        if merged and merged[-1][0] == shape and start <= merged[-1][2]:
            merged[-1][2] = max(merged[-1][2], end)
        elif merged and start < merged[-1][2]:
            merged.append([shape, merged[-1][2], max(end, merged[-1][2])])
        else:
            merged.append([shape, start, end])
    return [item for item in merged if item[2] > item[1]]


def _enforce_hold(frames, hold):
    """Fold segments shorter than ``hold`` frames into a neighbour; lip closures steal time instead."""
    frames = [list(item) for item in frames]
    while len(frames) > 1:
        short = [i for i, item in enumerate(frames) if item[2] - item[1] < hold]
        if not short:
            break
        i = min(short, key=lambda k: (PRIORITY.get(frames[k][0], 1), frames[k][2] - frames[k][1]))
        shape, start, end = frames[i]
        need = hold - (end - start)
        neighbours = [k for k in (i - 1, i + 1) if 0 <= k < len(frames)]
        donor = max(neighbours, key=lambda k: frames[k][2] - frames[k][1])
        if (PRIORITY.get(shape, 1) > PRIORITY.get(frames[donor][0], 1)
                and frames[donor][2] - frames[donor][1] - need >= hold):
            if donor < i:
                frames[donor][2] -= need
                frames[i][1] -= need
            else:
                frames[donor][1] += need
                frames[i][2] += need
            continue
        if donor < i:
            frames[donor][2] = end
        else:
            frames[donor][1] = start
        del frames[i]
        frames = _merge(frames)
    return frames


def resolve(shape, available):
    """The closest shape a character provides for a canonical (or Rhubarb) viseme."""
    if not available:
        return shape
    shape = RHUBARB.get(shape, shape)
    for candidate in FALLBACK.get(shape, [shape]):
        if candidate in available:
            return candidate
    return shape if shape in available else sorted(available)[0]


def speaker_shapes(episode):
    """Viseme names provided by layers, per ``viseme_for`` speaker."""
    found = {}
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            for layer in shot.get("layers", []):
                if layer.get("viseme_for") and layer.get("viseme"):
                    found.setdefault(layer["viseme_for"], set()).add(layer["viseme"])
    return found
