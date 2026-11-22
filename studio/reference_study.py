"""Collect YouTube references and prepare timecoded evidence for an editorial pass."""

import argparse
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlsplit

import numpy as np
from PIL import Image

from . import music
from .core import MAX_SECONDS, new_package, run, write_json
from .project import ROOT
from .narration import decode, whisper_segments
from .reference import reference

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
CHANNEL_PATH = re.compile(r"/(?:@[^/]+|(?:channel|c|user)/[^/]+)(?:/shorts)?/?")
DEFAULT_SUBS = r".*-orig,en,pt,pt-BR"
CAPTION_TYPES = {".vtt", ".srt", ".ttml", ".srv1", ".srv2", ".srv3", ".json3"}
PUBLIC_METADATA = ("title", "description", "channel", "channel_id", "upload_date", "duration",
                   "view_count", "like_count", "tags", "language")


def watch(ident):
    return f"https://www.youtube.com/watch?v={ident}"


def source_url(value, *, channel=False):
    url = urlsplit(value)
    if url.scheme not in ("http", "https") or url.netloc not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
    }:
        raise ValueError(f"Use a public YouTube URL: {value}")
    path = url.path.rstrip("/")
    if channel:
        if url.netloc == "youtu.be" or not CHANNEL_PATH.fullmatch(path):
            raise ValueError("TOP requires a YouTube channel URL, for example https://www.youtube.com/@handle.")
        return "https://www.youtube.com" + path.removesuffix("/shorts") + "/shorts"
    ident = ""
    if path == "/watch" and url.netloc != "youtu.be":
        ident = parse_qs(url.query).get("v", [""])[0]
    elif url.netloc == "youtu.be" or path.startswith("/shorts/"):
        ident = path.split("/")[-1]
    if not VIDEO_ID.fullmatch(ident):
        raise ValueError(f"Expected a direct YouTube video or Short URL: {value}")
    return ident


def ytdlp(*args):
    return run(sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-progress", "--socket-timeout", "20",
               "--js-runtimes", "node", *args)


def top_shorts(url, limit, fetch=ytdlp):
    index = json.loads(fetch("--flat-playlist", "--dump-single-json", "--", url))
    entries = {row["id"]: row for row in index.get("entries", []) if row and VIDEO_ID.fullmatch(row.get("id", ""))}
    ranked = []
    for ident, row in entries.items():
        views = row.get("view_count")
        if views is None:
            try:
                views = json.loads(fetch("--no-playlist", "--skip-download", "--dump-single-json",
                                         "--", watch(ident))).get("view_count")
            except ValueError:
                pass
        if isinstance(views, int) and views >= 0:
            ranked.append((views, ident))
    if not ranked:
        raise ValueError("The channel’s Shorts tab returned no videos with public view counts.")
    ranked.sort(key=lambda item: (-item[0], item[1]))
    records = [{"id": ident, "views": views} for views, ident in ranked[:limit]]
    return records, {"source": url, "indexed": len(entries), "with_views": len(ranked), "requested": limit}


def download(ident, folder, subtitles, fetch):
    if not folder.exists():
        with new_package(folder) as staging:
            # Media and metadata first, captions on their own: a refused caption track (YouTube answers
            # 429 to auto-translated ones at times) must not cost the video.
            fetch("--no-playlist", "--no-mtime", "--write-info-json",
                  "--match-filter", f"duration <= {MAX_SECONDS} & !is_live", "-f",
                  "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
                  "-o", str(staging / "source.%(ext)s"), "--", watch(ident))
            info = staging / "source.info.json"
            if not info.is_file():
                raise ValueError(f"No public metadata downloaded for {watch(ident)}.")
            raw = json.loads(info.read_text(encoding="utf-8"))
            info.unlink()
            media = [path for path in staging.glob("source.*") if path.name.count(".") == 1]
            if len(media) != 1:
                raise ValueError(f"Expected one video for {watch(ident)}.")
            caption_error = None
            try:
                fetch("--no-playlist", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs",
                      subtitles, "--sub-format", "vtt/best", "-o", str(staging / "source.%(ext)s"), "--", watch(ident))
            except ValueError as error:
                caption_error = str(error).strip().splitlines()[-1][:300]
            captions = [path.name for path in sorted(staging.glob("source.*.*"))
                        if path.suffix in CAPTION_TYPES and path.name.count(".") == 2]
            write_json(staging / "metadata.json", {
                **{key: raw.get(key) for key in PUBLIC_METADATA}, "url": watch(ident),
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "file": media[0].name, "captions": captions,
                **({"captions_error": caption_error} if caption_error else {}),
            })
    return json.loads((folder / "metadata.json").read_text(encoding="utf-8"))


def transcript(path, recognize, language):
    if recognize is None:
        return [], None
    segments, info = recognize(decode(path), language)
    phrases = [{"start": round(segment.start, 3), "end": round(segment.end, 3), "text": segment.text.strip(),
                "words": [{"text": word.word.strip(), "start": round(word.start, 3), "end": round(word.end, 3)}
                          for word in segment.words or []]} for segment in segments if segment.text.strip()]
    return phrases, info.language


def sound_candidates(path, words):
    samples = music.decode(path)
    onset = music.onsets(samples)
    if onset is None:
        return [], None
    bpm = music.tempo(samples) if len(samples) <= 180 * music.RATE else None
    clarity = music.pulse_clarity(samples, bpm)
    grid = {"bpm": bpm, "first_beat": music.first_beat(samples, bpm), "clarity": round(clarity, 3),
            "alternatives": music.tempo_alternatives(samples, bpm)} if bpm and clarity >= music.PULSE else None
    threshold = max(0.30, float(np.quantile(onset, 0.97)))
    points = []
    hop = music.HOP / music.RATE
    speech = sorted((item["start"], item["end"]) for item in words)
    spoken = 0
    for index in np.flatnonzero(onset >= threshold):
        at = float((index + 1) * hop)
        while spoken < len(speech) and speech[spoken][1] + 0.09 < at:
            spoken += 1
        if spoken < len(speech) and speech[spoken][0] - 0.07 <= at:
            continue
        if points and at - points[-1][0] < 0.12:
            if onset[index] > points[-1][1]:
                points[-1] = (at, onset[index])
        else:
            points.append((at, onset[index]))
    return [round(at, 3) for at, _ in points], grid


def display(value):
    return escape(" ".join(str(value or "").split()), quote=False).replace("|", "&#124;").replace("[", "&#91;").replace("]", "&#93;")


def timestamp(value):
    return f"{int(value // 60):02d}:{value % 60:06.3f}"


def frame_delta(root, frames):
    if len(frames) < 2:
        return None
    with Image.open(root / frames[0]["file"]) as first, Image.open(root / frames[-1]["file"]) as last:
        a, b = (np.asarray(image.convert("RGB").resize((32, 32)), dtype=float) for image in (first, last))
    return round(float(np.mean(np.abs(a - b)) / 255), 3)


def breakdown(metadata, evidence, media_link, report, phrases):
    frames = evidence["frames"]
    frame_times = [frame["seek_seconds"] for frame in frames]
    selected = defaultdict(list)
    for at in evidence["candidate_cuts_seconds"]:
        selected[round(at, 3)].append("Candidate cut")
    for at in report["sound_onsets"]:
        selected[at].append("Audio onset outside timed words" if report["timed_words"] else "Audio onset")
    for phrase in phrases:
        selected[phrase["start"]].append("Phrase starts")
    selected[0.0].append("Opening")
    selected[round(evidence["duration_seconds"], 3)].append("Ending")
    rows = [
        f"# {display(metadata['title']) or 'Reference breakdown'}", "",
        f"[YouTube source]({metadata['url']}) · [Local media]({media_link}) · "
        "[Metadata](metadata.json) · [Contact sheet](evidence/contact-sheet.jpg) · [Measurements](study.json)",
        "", "## Pacing and sound", "",
        f"- Duration {report['seconds']:.3f}s · {report['cuts_per_second']:.2f} candidate cuts/s.",
    ]
    wps = report["words_per_second"]
    rows.append(f"- {wps:.2f} transcribed words/s across the clip." if wps is not None else "- Word pacing unavailable.")
    if report["first_phrase_end"] is not None:
        rows.append(f"- First phrase ends at {timestamp(report['first_phrase_end'])}. Verify the hook boundary in playback.")
    if report["edge_frame_delta"] is not None:
        rows.append(f"- Opening/closing sample difference {report['edge_frame_delta']:.3f} on a 0–1 scale. Inspect the loop in playback.")
    grid = report["pulse_candidate"]
    if grid:
        other = grid.get("alternatives") or []
        also = (f" A {' or '.join(f'{value:.1f}' for value in other)} BPM reading fits almost as well "
                "(a syncopated figure can repeat every one and a half beats); confirm the beat by ear.") if other else ""
        rows.append(f"- Mixed-audio pulse candidate {grid['bpm']:.1f} BPM, first beat {timestamp(grid['first_beat'])}.{also}")
    else:
        rows.append("- No reliable regular pulse measured in the mixed audio.")
    rows.extend(["- Music presence and sound labels need listening. Sudden rises can come from music, effects or untimed speech.",
                 f"- Transcript status {report['transcript_status']}. " + (
                     "Platform caption files are in the local media folder." if metadata.get("captions") else
                     "No platform caption files" + (f" (download refused: {display(metadata['captions_error'])})."
                                                    if metadata.get("captions_error") else ".")),
                 "", "## Timecoded evidence", "",
                 "| Time | Phrase and timed words | Shot sample | Candidate event | Editorial observation and original application |",
                 "| --- | --- | --- | --- | --- |"])
    starts = [phrase["start"] for phrase in phrases]
    for at, events in sorted(selected.items()):
        index = bisect_right(starts, at) - 1
        phrase = phrases[index] if index >= 0 and at < phrases[index]["end"] else None
        spoken = display(phrase["text"]) if phrase else ""
        if phrase and at == phrase["start"]:
            spoken += "<br>" + "; ".join(f"{display(word['text'])} {timestamp(word['start'])}–{timestamp(word['end'])}"
                                         for word in phrase["words"])
        nearest = bisect_right(frame_times, at) - 1
        frame = f"[Frame](evidence/{frames[nearest]['file']})" if nearest >= 0 else "—"
        rows.append(f"| {timestamp(at)} | {spoken} | {frame} | {', '.join(events)} | |")
    rows.extend(["", "## Playback review", "", "- Hook boundary and opening device", "- Setup, escalation and payoff",
                 "- Music presence and changes, beat confirmation, and effects with labels and times",
                 "- Ending image and sound, and how the cut loops", "- Technique to test in an original animatic", ""])
    return "\n".join(rows)


def study_video(ident, research, raw, subtitles, fetch, recognize):
    target, source = research / ident, raw / ident
    metadata = download(ident, source, subtitles, fetch)
    if (target / "breakdown.md").is_file():
        return target
    media = source / metadata["file"]
    with new_package(target) as staging:
        reference(media, staging / "evidence", 0.34, focus_shorts=True, all_cuts=True)
        evidence_dir = staging / "evidence"
        evidence = json.loads((evidence_dir / "reference.json").read_text(encoding="utf-8"))
        audio_path = evidence_dir / "audio.wav"
        seconds = evidence["duration_seconds"]
        phrases, language = transcript(audio_path, recognize, metadata.get("language")) if audio_path.is_file() else ([], None)
        words = [word for phrase in phrases for word in phrase["words"]]
        onsets, pulse = sound_candidates(audio_path, words) if audio_path.is_file() else ([], None)
        report = {"seconds": seconds, "cuts_per_second": len(evidence["candidate_cuts_seconds"]) / seconds,
                  "words_per_second": len(words) / seconds if words else None, "timed_words": len(words),
                  "first_phrase_end": phrases[0]["end"] if phrases else None,
                  "edge_frame_delta": frame_delta(evidence_dir, evidence["frames"]),
                  "transcript_status": ("no audio" if not audio_path.is_file() else "recognizer unavailable" if not recognize
                                        else "word timings available" if words else "no timed speech recognized"),
                  "language": language, "sound_onsets": onsets, "pulse_candidate": pulse, "phrases": phrases}
        write_json(staging / "study.json", report)
        write_json(staging / "metadata.json", metadata)
        relative_media = Path(os.path.relpath(media, target)).as_posix()
        (staging / "breakdown.md").write_text(breakdown(metadata, evidence, relative_media, report, phrases), encoding="utf-8")
    return target


def comparison(research, selected, ranking):
    lines = ["# Reference comparison", ""]
    if ranking:
        lines.append(f"Ranked by lifetime views across {ranking['with_views']} of {ranking['indexed']} Shorts indexed "
                     f"on the [channel’s Shorts tab]({ranking['source']}).")
        lines.append("")
        for i, item in enumerate(selected, 1):
            lines.append(f"{i}. [{item['id']}]({item['id']}/breakdown.md) · {item['views']:,} views at selection.")
        if len(selected) < ranking["requested"]:
            lines.append(f"Only {len(selected)} of {ranking['requested']} requested Shorts had usable data.")
        lines.append("")
    lines.extend(["| Reference | Duration | Words/s | Cut candidates/s | Pulse candidate |",
                  "| --- | ---: | ---: | ---: | ---: |"])
    for path in sorted(research.glob("*/study.json")):
        metrics = json.loads(path.read_text(encoding="utf-8"))
        metadata = json.loads(path.with_name("metadata.json").read_text(encoding="utf-8"))
        words, pulse = metrics["words_per_second"], metrics["pulse_candidate"]
        wps, bpm = (f"{words:.2f}" if words is not None else "—"), (f"{pulse['bpm']:.1f} BPM" if pulse else "—")
        lines.append(f"| [{display(metadata['title']) or path.parent.name}]({path.parent.name}/breakdown.md) | "
                     f"{metrics['seconds']:.2f}s | {wps} | {metrics['cuts_per_second']:.2f} | {bpm} |")
    (research / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        with (research / "patterns.md").open("x", encoding="utf-8") as output:
            output.write("# Reference patterns\n\nStart with the [measured comparisons](comparison.md).\n\n"
                         "| Recurring technique | Timecoded evidence from multiple references | Counterexample | Original test |\n"
                         "| --- | --- | --- | --- |\n| | | | |\n")
    except FileExistsError:
        pass


def research_path(root, channel):
    workspace = root / "workspace"
    candidate = Path(channel)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", channel):
        folder = (workspace / channel).resolve()
    else:
        manifest = (root / candidate).resolve()
        if manifest.name != "channel.json" or manifest.parent.name != "channel":
            raise ValueError("Use CHANNEL=<slug> or CHANNEL=workspace/<slug>/channel/channel.json.")
        folder = manifest.parent.parent
    if folder.parent != workspace.resolve():
        raise ValueError("Reference studies belong directly under workspace/<slug>.")
    return folder / "research" / "references"


def study(root, channel, urls, *, top=None, subtitles=DEFAULT_SUBS, fetch=ytdlp, recognizer=whisper_segments):
    if not 1 <= len(urls) <= 3 or (top is not None and (len(urls) != 1 or top not in (1, 2, 3))):
        raise ValueError("Provide one to three video URLs, or one channel URL with TOP=1, 2 or 3.")
    research = research_path(root, channel)
    raw = root / "reference-media" / "youtube"
    if not raw.resolve().is_relative_to(root.resolve()):
        raise ValueError("Reference media must stay inside the studio checkout.")
    if top is None:
        selected = [{"id": ident} for ident in dict.fromkeys(source_url(url) for url in urls)]
        ranking = None
    else:
        selected, ranking = top_shorts(source_url(urls[0], channel=True), top, fetch)
    recognize = None
    if any(not (research / item["id"] / "breakdown.md").is_file() for item in selected):
        recognize = recognizer(word_timestamps=True)
    results = [study_video(item["id"], research, raw, subtitles, fetch, recognize) for item in selected]
    comparison(research, selected, ranking)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*", default=os.environ.get("STUDIO_REFERENCE_URLS", "").split())
    parser.add_argument("--channel", default=os.environ.get("STUDIO_REFERENCE_CHANNEL"))
    parser.add_argument("--top", type=int, default=os.environ.get("STUDIO_REFERENCE_TOP") or None)
    parser.add_argument("--sub-langs", default=os.environ.get("STUDIO_REFERENCE_LANGS") or DEFAULT_SUBS)
    args = parser.parse_args()
    if not args.channel or not args.urls:
        parser.error("Set CHANNEL=<slug or manifest> and URL='https://www.youtube.com/... [other URL ...]'")
    from .machine import apply
    apply()
    try:
        if importlib.util.find_spec("yt_dlp") is None:
            raise ValueError("Install requirements-reference.txt on the host or rebuild the studio image (make dev-build).")
        for folder in study(ROOT, args.channel, args.urls, top=args.top, subtitles=args.sub_langs):
            print(folder / "breakdown.md")
    except (OSError, ValueError) as error:
        print(f"studio: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
