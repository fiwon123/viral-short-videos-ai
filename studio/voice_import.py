"""Split a complete recording into episode takes with clip-relative word timings."""

import argparse
from bisect import bisect_left
from collections import Counter
from difflib import SequenceMatcher
from itertools import pairwise
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4
import wave

import numpy as np

from .audio import read_audio
from .core import MAX_SECONDS, SAMPLE_RATE, asset, new_package, require, write_json
from .narration import decode, tokens, whisper_segments
from .script import line_id, spoken
from .voices import words_file

PAD_BEFORE, PAD_AFTER = 0.06, 0.14


def word_transcriber(model=None):
    recognize = whisper_segments(model, word_timestamps=True)
    if recognize is None:
        raise ValueError("Voice import needs faster-whisper from requirements-voice.txt and STUDIO_ASR enabled.")

    def transcribe(audio, language):
        segments, info = recognize(audio, language)
        return ([{"word": word.word.strip(), "start": float(word.start), "end": float(word.end)}
                 for segment in segments for word in (segment.words or [])], info.language)

    transcribe.model = recognize.model
    return transcribe


def fill_word_timings(words, anchors):
    """Keep ASR anchors and distribute unmatched words across the gaps they bound."""
    timings = []
    for (left, before), (right, after) in pairwise(anchors.items()):
        timings.append(before)
        gap = max(after["start"] - before["end"], 0)
        for i in range(left + 1, right):
            start = before["end"] + gap * (i - left - 1) / (right - left - 1)
            end = before["end"] + gap * (i - left) / (right - left - 1)
            timings.append({"text": words[i][0], "start": start, "end": end})
    timings.append(next(reversed(anchors.values())))
    return timings


def align(lines, heard, language):
    """Align the script in order. Require anchors on both sides of every imported take."""
    expected, owners, script_tokens = [], [], []
    for index, (_, line) in enumerate(lines):
        words = [(word, tokens(word, language)) for word in spoken(line).split()]
        words = [(word, parts) for word, parts in words if parts]
        expected.append(words)
        for position, (_, parts) in enumerate(words):
            script_tokens.extend(parts)
            owners.extend([(index, position)] * len(parts))

    said, said_owners = [], []
    recognized = [(word, tokens(word["word"], language)) for word in sorted(heard, key=lambda item: item["start"])]
    recognized = [(word, parts) for word, parts in recognized if parts]
    for index, (_, parts) in enumerate(recognized):
        said.extend(parts)
        said_owners.extend([index] * len(parts))

    matches = [{} for _ in lines]
    for block in SequenceMatcher(None, script_tokens, said, autojunk=False).get_matching_blocks():
        for offset in range(block.size):
            index, position = owners[block.a + offset]
            matches[index].setdefault(position, []).append(said_owners[block.b + offset])

    phrases = [tuple(part for _, parts in words for part in parts) for words in expected]
    duplicates = {phrase: count for phrase, count in Counter(phrases).items() if phrase and count > 1}
    ambiguous = {phrase for phrase, count in duplicates.items()
                 if sum(tuple(said[i:i + len(phrase)]) == phrase for i in range(len(said))) < count}

    results, unmatched = [], []
    for index, (words, matched, phrase) in enumerate(zip(expected, matches, phrases)):
        matched = {position: spots for position, spots in matched.items()
                   if len(spots) == len(words[position][1])}
        coverage = len(matched) / max(1, len(words))
        result = {"status": "missing", "coverage": round(coverage, 2), "words": []}
        if phrase in ambiguous:
            result["warning"] = "Repeated script line has too few distinguishable matches."
        elif coverage >= 0.6 and 0 in matched and len(words) - 1 in matched:
            anchors = {index: {"text": words[index][0], "start": recognized[spots[0]][0]["start"],
                               "end": recognized[spots[-1]][0]["end"]} for index, spots in sorted(matched.items())}
            used = {spot for spots in matched.values() for spot in spots}
            clean = coverage == 1 and len(used) == max(used) - min(used) + 1
            timings = fill_word_timings(words, anchors)
            result.update(status="found" if clean else "partial", words=timings,
                          start=timings[0]["start"], end=timings[-1]["end"])
            if not clean:
                result["warning"] = "The recording differs from the script. Review the take and estimated timing."
        elif not matched:
            unmatched.append(index)
            result["warning"] = "No script words were matched."
        else:
            result["warning"] = "Could not place both edges of this line with enough matching words."
        results.append(result)
    previous = None
    for result in results:
        if not result["words"]:
            continue
        if previous and result["start"] < previous["end"]:
            result.update(status="missing", words=[], warning="This line shares audio with the previous match.")
        else:
            previous = result

    # Only assign an unmatched line when two confirmed neighbors enclose exactly
    # one heard span of the expected size. Never split a gap between several lines.
    starts = [word["start"] for word, _ in recognized]
    for index in unmatched:
        if not 0 < index < len(results) - 1 or not expected[index]:
            continue
        before, result, after = results[index - 1:index + 2]
        if before["status"] != "found" or after["status"] != "found":
            continue
        first = bisect_left(starts, before["end"])
        last = bisect_left(starts, after["start"])
        between = [word for word, _ in recognized[first:last] if word["end"] <= after["start"]]
        if len(between) == len(expected[index]):
            timings = [{"text": text, "start": word["start"], "end": word["end"]}
                       for (text, _), word in zip(expected[index], between)]
            result.update(status="inferred", words=timings, start=timings[0]["start"], end=timings[-1]["end"],
                          warning="Words were inferred from the gap between confirmed lines. Listen before using.")
    return results


def write_clip(path, samples):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


def language_of(episode, speaker):
    from .episode_state import paths
    channel_path = paths(episode)["channel"]
    if not channel_path:
        return None
    channel = json.loads(channel_path.read_text(encoding="utf-8"))
    if "audio_library" not in channel:
        return None
    library = asset(channel_path.parent, channel["audio_library"])
    voices = json.loads(library.read_text(encoding="utf-8")).get("voices", {})
    profiles = [voices.get(speaker, {})] if speaker else voices.values()
    languages = {profile["language"] for profile in profiles if profile.get("language")}
    return next(iter(languages)) if len(languages) == 1 else None


def run(episode_path, recording, speaker=None, *, transcribe=None, language=None, model=None):
    episode_path, recording = Path(episode_path).resolve(), Path(recording).resolve()
    if not recording.is_file():
        raise ValueError(f"No recording at {recording}")
    original = episode_path.read_bytes()
    episode = json.loads(original)
    lines = [(line_id(shot, number), line) for scene in episode["scenes"] for shot in scene["shots"]
             for number, line in enumerate(shot.get("speech", []), 1) if speaker is None or line["speaker"] == speaker]
    if not lines:
        raise ValueError(f"No spoken lines{f' for {speaker}' if speaker else ''} in {episode_path.name}")

    require("ffmpeg")
    audio = read_audio(recording)
    duration = len(audio) / SAMPLE_RATE
    transcribe = transcribe or word_transcriber(model)
    heard, detected = transcribe(decode(recording, seconds=MAX_SECONDS), language)
    heard = [{"word": word["word"], "start": max(0.0, word["start"]), "end": min(duration, word["end"])}
             for word in heard if math.isfinite(word["start"]) and math.isfinite(word["end"])
             and max(0.0, word["start"]) < min(duration, word["end"])]
    results = align(lines, heard, language or detected)
    batches = episode_path.parent / "audio" / "voice"
    if not batches.resolve().is_relative_to(episode_path.parent):
        raise ValueError("The voice output directory must stay inside the episode.")
    batch = batches / uuid4().hex
    rows = [{"id": ident, "speaker": line["speaker"], "text": spoken(line),
             "status": result["status"], "coverage": result["coverage"],
             **({"warning": result["warning"]} if "warning" in result else {})}
            for (ident, line), result in zip(lines, results)]
    found = [(line, result, row) for (_, line), result, row in zip(lines, results, rows) if result["words"]]
    report = {"recording": recording.name, "speaker": speaker, "language": language or detected,
              "model": getattr(transcribe, "model", "custom"), "lines": rows}
    report.update({status: sum(row["status"] == status for row in rows)
                   for status in ("found", "partial", "inferred", "missing")})

    lock = episode_path.parent / ".voice-import.lock"
    try:
        handle = lock.open("x")
    except FileExistsError as error:
        raise ValueError(f"Another voice import is publishing results: {lock}") from error
    try:
        with handle, TemporaryDirectory(prefix=".voice-import-", dir=episode_path.parent) as tmp:
            if episode_path.read_bytes() != original:
                raise ValueError("The episode changed during recognition. Rerun voice import on the updated script.")
            if found:
                with new_package(batch) as staging:
                    for index, (line, result, row) in enumerate(found):
                        start, end = result["start"], result["end"]
                        previous = found[index - 1][1]["end"] if index else 0.0
                        following = found[index + 1][1]["start"] if index + 1 < len(found) else duration
                        first = round(max(0.0, start - PAD_BEFORE, (previous + start) / 2) * SAMPLE_RATE)
                        last = round(min(duration, end + PAD_AFTER, (end + following) / 2) * SAMPLE_RATE)
                        clip = audio[first:last]
                        name = f"{index + 1:03d}.wav"
                        write_clip(staging / name, clip)
                        offset = first / SAMPLE_RATE
                        timings = [{"text": word["text"], "start": round(max(0.0, word["start"] - offset), 4),
                                    "end": round(min(len(clip) / SAMPLE_RATE, word["end"] - offset), 4)}
                                   for word in result["words"]]
                        write_json(words_file(staging / name), timings)
                        if line.get("pace") not in (None, 1) or line.get("pitch") not in (None, 0):
                            warning = "The line’s pace or pitch setting will also change the imported recording."
                            row["warning"] = " ".join(filter(None, (row.get("warning"), warning)))
                        line["file"] = (batch / name).relative_to(episode_path.parent).as_posix()
                        line.pop("words", None)
                        row.update(file=line["file"], at=round(offset, 3), seconds=round(len(clip) / SAMPLE_RATE, 3),
                                   words=timings)
                manifest = Path(tmp) / "episode.json"
                write_json(manifest, episode)
                manifest.chmod(episode_path.stat().st_mode & 0o777)
                manifest.replace(episode_path)
            report_file = Path(tmp) / "voice-import.json"
            write_json(report_file, report)
            report_file.replace(episode_path.parent / report_file.name)
    finally:
        lock.unlink()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--speaker", help="import the lines of this speaker only")
    parser.add_argument("--language", help="recognizer language; defaults to the cast or auto-detection")
    parser.add_argument("--model", help="faster-whisper model (default: STUDIO_ASR_MODEL or base)")
    args = parser.parse_args()
    from .machine import apply
    apply()
    try:
        report = run(args.episode, args.recording, args.speaker, model=args.model,
                     language=args.language or language_of(args.episode, args.speaker))
    except (ValueError, OSError) as error:
        print(f"studio: {error}", file=sys.stderr)
        return 1
    for row in report["lines"]:
        print(f"{row['status']:7} {row['id']} {row['speaker']}: {row['text']}")
        if row.get("warning"):
            print(f"        {row['warning']}")
    print(f"{report['found']} found, {report['partial']} partial, {report['inferred']} inferred, "
          f"{report['missing']} missing.")
    print(f"Report: {args.episode.parent / 'voice-import.json'}")
    return int(bool(report["missing"] or report["partial"] or report["inferred"]))


if __name__ == "__main__":
    raise SystemExit(main())
