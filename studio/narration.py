"""Narration check: hear every spoken line back and compare it with the script.

    python -m studio.narration EPISODE [--video renders/<ep>-vN/video.mp4 | renders/<ep>-audio] [--model base]

A TTS take can drop a word, repeat one, misread a number or a name, or come out
mushy, and every other check stays green: word timing only places the script's
own words. This transcribes each line's take (``take`` in the render's
``timeline.json``; the mix around the line when the take is gone) with
faster-whisper's multilingual model, in the line's language and with no script
prompt, then compares what was heard with what was meant.

Both sides are normalised (case, punctuation, ``*emphasis*``, number words to
digits for en/pt/es/fr/it, characters for ja/zh) and the heard words are scored
against the best of the line's ``text``, ``caption`` and ``spoken_text`` (a
respelling for the voice counts as correct). Per line: the word error rate, the
missing, extra and repeated words, and numbers that differ.

* unheard   nothing intelligible, or most words wrong (high)
* misread   a quarter of the words wrong, or a long word (a name, a key term) missing (medium)
* number    a number in the script is not the number heard (medium)
* repeat    a word said twice that the script says once (medium)

faster-whisper is optional (``pip install faster-whisper``); the model is
downloaded once into ``audio-models/whisper/``. Without it, or with
``STUDIO_ASR=off``, the verdict is ``unchecked``: a check that did not run is
not a pass. ``STUDIO_ASR_MODEL`` picks another size (``small`` hears better,
``tiny`` is faster). A line with ``"narration": false`` is left out (a stylised
voice no recogniser hears).

Adapted from lanshu-create-ai-presenter-video's ASR pass over the locked
narration (MIT); the comparison is our own.
"""

import argparse
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RATE = 16000
MISREAD = 0.25     # word error rate that reads as a different line
UNHEARD = 0.5      # most of the line wrong
LONG_WORD = 6      # a missing word this long is usually a name or the key term
PAD = 0.3          # seconds around a line when it is cut from the mix

_UNITS = {
    "en": "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
          "seventeen eighteen nineteen twenty",
    "pt": "zero um dois três quatro cinco seis sete oito nove dez onze doze treze catorze quinze dezesseis "
          "dezessete dezoito dezenove vinte",
    "es": "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciséis "
          "diecisiete dieciocho diecinueve veinte",
    "fr": "zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize "
          "dix-sept dix-huit dix-neuf vingt",
    "it": "zero uno due tre quattro cinque sei sette otto nove dieci undici dodici tredici quattordici quindici "
          "sedici diciassette diciotto diciannove venti",
}
_TENS = {
    "en": {"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
           "hundred": 100, "thousand": 1000},
    "pt": {"trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70, "oitenta": 80,
           "noventa": 90, "cem": 100, "mil": 1000, "uma": 1, "duas": 2, "catorze": 14, "quatorze": 14,
           "dezesseis": 16, "dezessete": 17, "dezenove": 19},
    "es": {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
           "noventa": 90, "cien": 100, "mil": 1000, "una": 1},
    "fr": {"trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60, "cent": 100, "mille": 1000, "une": 1},
    "it": {"trenta": 30, "quaranta": 40, "cinquanta": 50, "sessanta": 60, "settanta": 70, "ottanta": 80,
           "novanta": 90, "cento": 100, "mille": 1000, "una": 1},
}
NUMBERS = {lang: {**{word: value for value, word in enumerate(_UNITS[lang].split())}, **_TENS[lang]}
           for lang in _UNITS}
# Spoken contractions a recogniser writes out in full (or the reverse); both sides are expanded.
CONTRACTIONS = {
    "pt": {"pra": "para a", "pro": "para o", "pras": "para as", "pros": "para os", "tá": "está", "tô": "estou",
           "cê": "você", "né": "não é"},
    "en": {"gonna": "going to", "wanna": "want to", "gotta": "got to", "ok": "okay"},
}
CHARACTERS = ("ja", "zh")


def language_code(language):
    """``pt-br`` -> ``pt``; the code Whisper and the number tables use."""
    return str(language or "en").split("-")[0].lower()


def tokens(text, language="en"):
    """Comparable units: lower-case words (or characters for ja/zh), number words as digits."""
    lang = language_code(language)
    text = unicodedata.normalize("NFKC", str(text or "")).replace("*", "").lower()
    if lang in CHARACTERS:
        return [char for char in text if char.isalnum()]
    text = re.sub(r"(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])", " ", text)  # GTA6 -> gta 6
    contractions = CONTRACTIONS.get(lang, {})
    words = [part for word in re.findall(r"\w+(?:-\w+)*", text) for part in contractions.get(word, word).split()]
    table = NUMBERS.get(lang, {})
    out = []
    for word in words:
        if word in table:
            out.append(str(table[word]))
        elif "-" in word and all(part in table for part in word.split("-")):  # twenty-one
            out.append(str(sum(table[part] for part in word.split("-"))))
        else:
            out.extend(part for part in word.split("-") if part)
    return out


def compare(expected, heard):
    """How ``heard`` (tokens) differs from ``expected`` (tokens)."""
    matcher = SequenceMatcher(None, expected, heard, autojunk=False)
    missing, extra, errors = [], [], 0
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        errors += max(a2 - a1, b2 - b1)
        missing += expected[a1:a2]
        extra += heard[b1:b2]
    repeated = [word for index, word in enumerate(heard[1:], 1) if word == heard[index - 1]
                and not any(expected[i] == expected[i - 1] == word for i in range(1, len(expected)))]
    numbers = sorted({word for word in missing if word.isdigit() and word != "1"})  # "one" is also "a" (um, un, uno)
    return {"wer": round(errors / max(1, len(expected)), 3), "missing": missing, "extra": extra,
            "repeated": repeated, "numbers": numbers}


def judge(line, heard_text):
    """Notes and a row for one line, against the best of its written forms."""
    language = line.get("language") or "en"
    heard = tokens(heard_text, language)
    forms = [line.get(key) for key in ("text", "caption", "spoken_text") if line.get(key)]
    best = min((dict(compare(tokens(form, language), heard), meant=form) for form in forms),
               key=lambda result: result["wer"])
    row = {"speaker": line.get("speaker"), "at": line.get("at"), "meant": best["meant"], "heard": heard_text.strip(),
           **{key: best[key] for key in ("wer", "missing", "extra", "repeated", "numbers")}}
    where = f"{line.get('speaker', 'line')} at {line.get('at', 0):.2f} s"
    notes = []
    meant = tokens(best["meant"], language)
    # A short line reaches a high error rate on one slip: there, only silence or nearly every word wrong is unheard.
    if not heard or (best["wer"] >= UNHEARD and (len(meant) >= 4 or best["wer"] >= 0.99)):
        notes.append(_note("unheard", "high", f"{where}: heard \"{heard_text.strip()}\" for \"{best['meant']}\".",
                           "Listen to the take. Re-voice it: slow `pace`, respell hard words in `spoken_text`, or "
                           "pick another voice; a stylised creature voice may need `narration: false` on the line."))
    else:
        if best["numbers"]:
            notes.append(_note("number", "medium", f"{where}: the number {', '.join(best['numbers'])} was not heard "
                               f"(heard \"{heard_text.strip()}\").",
                               "Spell the number out in `spoken_text` the way it should be read."))
        if best["repeated"]:
            notes.append(_note("repeat", "medium", f"{where}: \"{' '.join(best['repeated'])}\" is said twice.",
                               "Re-voice the line (a new take) or split it at the repeat."))
        long_missing = [word for word in best["missing"] if len(word) >= LONG_WORD and not word.isdigit()]
        rate = best["wer"] - len(best["repeated"]) / max(1, len(meant))  # a repeat is reported once, as a repeat
        if rate >= MISREAD or long_missing:
            missing = ", ".join(long_missing or best["missing"][:4])
            notes.append(_note("misread", "medium", f"{where}: {best['wer']:.0%} of the words differ; missing: "
                               f"{missing or 'none'} (heard \"{heard_text.strip()}\").",
                               "Respell the missing words in `spoken_text`, slow the `pace`, or re-voice the take."))
    return notes, row


def _note(kind, severity, note, fix):
    return {"kind": kind, "severity": severity, "note": note, "fix": fix}


def decode(path, start=None, seconds=None):
    command = ["ffmpeg", "-nostdin", "-v", "error"]
    if start is not None:
        command += ["-ss", f"{max(0.0, start):.3f}"]
    command += ["-i", str(path)]
    if seconds is not None:
        command += ["-t", f"{seconds:.3f}"]
    data = subprocess.run(command + ["-vn", "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
                          capture_output=True, check=True).stdout
    return np.frombuffer(data, dtype="<f4").copy()


def whisper(model=None):
    """A transcriber ``(audio, language) -> text``, or None when faster-whisper is not installed."""
    if os.environ.get("STUDIO_ASR", "").lower() in ("0", "off", "false", "no"):
        return None
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    name = model or os.environ.get("STUDIO_ASR_MODEL", "base")
    loaded = WhisperModel(name, device="cpu", compute_type="int8", download_root=str(ROOT / "audio-models" / "whisper"))

    def transcribe(audio, language):
        segments, _ = loaded.transcribe(audio, language=language_code(language), beam_size=5,
                                        condition_on_previous_text=False)
        return " ".join(segment.text.strip() for segment in segments)
    transcribe.model = name
    return transcribe


def lines_from_timeline(timeline_path, episode_dir):
    """Each speech line with its audio: the cached take, or the render's mix around the line."""
    timeline = json.loads(Path(timeline_path).read_text(encoding="utf-8"))
    fps = float(timeline.get("fps", 24))
    mix = Path(timeline_path).parent / "mix.wav"
    if not mix.is_file():
        mix = Path(timeline_path).parent / "video.mp4"
    found = []
    for scene in timeline.get("scenes", []):
        for shot in scene.get("shots", []):
            for line in shot.get("speech", []):
                if line.get("narration") is False:
                    continue
                entry = {key: line.get(key) for key in ("speaker", "text", "caption", "spoken_text", "language")}
                entry.update(shot=shot["id"], at=round(line["start"] / fps, 3))
                take = Path(episode_dir) / line["take"] if line.get("take") else None
                if take is not None and take.is_file():
                    entry["source"], entry["clip"] = str(take), None
                elif mix.is_file():
                    start = line["start"] / fps - PAD
                    entry["source"], entry["clip"] = str(mix), (start, (line["end"] - line["start"]) / fps + 2 * PAD)
                else:
                    entry["source"], entry["clip"] = None, None
                found.append(entry)
    return found


def check(timeline_path, episode_dir, transcribe=None):
    """The narration report for one render: ``verdict`` green/amber/red, ``unchecked`` or ``no-speech``."""
    lines = lines_from_timeline(timeline_path, episode_dir)
    if not lines:
        return {"verdict": "no-speech", "lines": [], "notes": []}
    if transcribe is None:
        transcribe = whisper()
    if transcribe is None:
        return {"verdict": "unchecked", "lines": len(lines), "notes": [],
                "reason": "faster-whisper is not installed (pip install faster-whisper)"}
    notes, rows = [], []
    for line in lines:
        if not line["source"]:
            heard = ""
        else:
            clip = line["clip"]
            audio = decode(line["source"], *clip) if clip else decode(line["source"])
            heard = transcribe(audio, line.get("language") or "en") if len(audio) else ""
        line_notes, row = judge(line, heard)
        row["shot"] = line["shot"]
        notes += line_notes
        rows.append(row)
    severities = {note["severity"] for note in notes}
    verdict = "red" if "high" in severities else "amber" if "medium" in severities else "green"
    return {"verdict": verdict, "model": getattr(transcribe, "model", "custom"), "lines": rows, "notes": notes}


def run(episode, video=None, transcribe=None):
    """Check the newest render or audio pass of ``episode`` (or ``video``: a render's video.mp4, mix.wav or its
    folder) and write ``narration.json`` beside it."""
    from .episode_state import paths
    where = paths(episode)
    if video:
        folder = Path(video).resolve()
        folder = folder if folder.is_dir() else folder.parent
    else:
        found = sorted(where["renders"].glob(f"{where['slug']}-*/timeline.json"),
                       key=lambda path: path.stat().st_mtime, reverse=True) if where["renders"].is_dir() else []
        if not found:
            raise ValueError("No render or audio pass with a timeline.json; run make audio or make preview first.")
        folder = found[0].parent
    if not (folder / "timeline.json").is_file():
        raise ValueError(f"{folder} has no timeline.json.")
    report = check(folder / "timeline.json", where["folder"], transcribe)
    report["render"] = folder.name
    (folder / "narration.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--video", type=Path, help="a render's video.mp4, mix.wav or folder (default: the newest "
                                                   "render or audio pass with a timeline.json)")
    parser.add_argument("--model", help="faster-whisper model (default: STUDIO_ASR_MODEL or base)")
    args = parser.parse_args()
    try:
        report = run(args.episode, args.video, whisper(args.model) if args.model else None)
    except ValueError as error:
        print(f"studio: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["verdict"] == "red" else 0


if __name__ == "__main__":
    raise SystemExit(main())
