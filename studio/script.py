"""The production script: what a voice app and a visual AI need before anything is animated.

``make script EPISODE=...`` writes two files beside the episode:

- ``script.md``: the voices, then shot by shot the time, the picture, the sounds, every line (ID, time,
  speaker, words, delivery) and a prompt for a visual AI built from the shot direction and the channel's
  style lock.
- ``voice-script.txt``: each speaker's lines ready to paste into ElevenLabs or any voice app, and the command
  that brings the recording back (``make voice-import``).

Times are estimated from the manifest (shot durations, ``at``, words per second) until an audio pass exists;
then they are the measured ones.
"""

import argparse
import json
import sys
from pathlib import Path

WORDS_PER_SECOND = 2.6  # a clear Shorts read; only used until the voice exists
GAP = 0.18  # the pause the mixer leaves between lines without ``at``


def clock(seconds):
    seconds = max(0.0, float(seconds))
    return f"{int(seconds // 60):02d}:{seconds % 60:04.1f}"


def flat(text):
    return " ".join(str(text or "").split())


def shown_path(path):
    try:
        return str(Path(path).relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def spoken(line):
    return line.get("spoken_text", line["text"]).replace("*", "")


def line_id(shot, number):
    return f"{shot['id']}.{number}"


def planned(episode):
    """Shots and lines with estimated times, in reading order."""
    shots, cursor = [], 0.0
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            lines, previous_end = [], -GAP
            for number, line in enumerate(shot.get("speech", []), 1):
                start = float(line["at"]) if "at" in line else previous_end + GAP
                start += float(line.get("lead", 0) or 0)
                words = max(1, len(spoken(line).split()))
                length = words / WORDS_PER_SECOND / float(line.get("pace", 1) or 1)
                lines.append({"id": line_id(shot, number), "line": line, "start": cursor + start,
                              "end": cursor + start + length})
                previous_end = start + length + float(line.get("pause_after", 0) or 0)
            duration = max(float(shot.get("duration", 0)), previous_end + 0.14 if lines else 0)
            shots.append({"scene": scene, "shot": shot, "start": cursor, "end": cursor + duration, "lines": lines})
            cursor += duration
    return shots, "estimated"


def measured(shots, timeline):
    """The same shots with the times of an audio pass, when the timeline matches the manifest."""
    fps = float(timeline.get("fps", 24))
    resolved = [shot for scene in timeline.get("scenes", []) for shot in scene.get("shots", [])]
    if [item["shot"]["id"] for item in shots] != [shot.get("id") for shot in resolved]:
        return None
    out = []
    for item, timing in zip(shots, resolved):
        speech = timing.get("speech", [])
        if len(speech) != len(item["lines"]):
            return None
        lines = [{**line, "start": entry["start"] / fps, "end": entry["end"] / fps}
                 for line, entry in zip(item["lines"], speech)]
        out.append({**item, "start": timing["start"] / fps, "end": timing["end"] / fps, "lines": lines})
    return out


def newest_timeline(episode_path):
    from .episode_state import paths
    where = paths(episode_path)
    if not where["renders"].is_dir():
        return None, None
    edited = where["episode"].stat().st_mtime
    found = sorted((path for path in where["renders"].glob(f"{where['slug']}-*/timeline.json")
                    if path.stat().st_mtime >= edited), key=lambda path: path.stat().st_mtime, reverse=True)
    if not found:
        return None, None
    return json.loads(found[0].read_text(encoding="utf-8")), found[0].parent.name


def sounds(shot, start):
    rows = []
    for cue in shot.get("sfx", []):
        name = cue.get("sound") or cue.get("preset") or (Path(cue["file"]).stem if "file" in cue else "sound")
        rows.append(f"{name} at {clock(start + float(cue.get('at', 0)))}")
    return rows


def visual_prompt(shot, episode, lock):
    parts = ["Vertical 9:16 frame for a Short."]
    if lock and lock.get("summary"):
        parts.append(f"Look: {lock['summary']}")
    parts.append(f"Shot: {flat(shot.get('direction')) or 'see the episode treatment'}")
    if str(shot.get("background", "")).startswith("#"):
        parts.append(f"Background {shot['background']}.")
    if lock and lock.get("never"):
        never = lock["never"] if isinstance(lock["never"], list) else [lock["never"]]
        parts.append("Avoid: " + "; ".join(str(item) for item in never) + ".")
    parts.append("Original characters and setting; no logos, no text, no real people.")
    return " ".join(parts)


def tag(line):
    """Delivery as a leading audio tag (ElevenLabs v3 and similar read it as direction, not words)."""
    delivery = flat(line.get("delivery")).rstrip(".")
    return f"[{delivery.lower()}] " if delivery else ""


def write(episode_path, out_dir=None):
    episode_path = Path(episode_path).resolve()
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    from .episode_state import paths
    where = paths(episode_path)
    channel_dir = where["channel"].parent if where["channel"] else None
    voices, lock = {}, None
    if channel_dir:
        channel = json.loads(where["channel"].read_text(encoding="utf-8"))
        if channel.get("audio_library"):
            library = channel_dir / channel["audio_library"]
            if library.is_file():
                voices = json.loads(library.read_text(encoding="utf-8")).get("voices", {})
        if (channel_dir / "style-lock.json").is_file():
            lock = json.loads((channel_dir / "style-lock.json").read_text(encoding="utf-8"))

    shots, source = planned(episode)
    timeline, render = newest_timeline(episode_path)
    if timeline and (resolved := measured(shots, timeline)):
        shots, source = resolved, f"measured from {render}"
    lines = [item for shot in shots for item in shot["lines"]]
    speakers = list(dict.fromkeys(item["line"]["speaker"] for item in lines))
    runtime = shots[-1]["end"] if shots else 0

    rows = [f"# {episode.get('title', where['slug'])}: production script", "",
            f"Runtime {clock(runtime)} · {len(shots)} shots · {len(lines)} spoken lines · times {source}.", ""]
    if speakers:
        rows += ["## Voices", "", "| Speaker | Engine | Direction | Identity |", "| --- | --- | --- | --- |"]
        for name in speakers:
            profile = voices.get(name, {})
            rows.append(f"| {name} | {profile.get('engine', 'default')} | {flat(profile.get('direction'))} "
                        f"| {flat(profile.get('identity'))} |")
        rows += ["", "Record with `voice-script.txt`, then bring the audio back with "
                     f"`make voice-import EPISODE={shown_path(episode_path)} FILE=<recording>`.", ""]
    else:
        rows += ["Wordless: no spoken lines. Picture and sound carry the story.", ""]
    rows += ["## Shots", ""]
    for item in shots:
        shot = item["shot"]
        rows += [f"### {shot['id']} · {clock(item['start'])}–{clock(item['end'])}", "",
                 f"**Picture:** {flat(shot.get('direction') or item['scene'].get('purpose', ''))}", ""]
        if cues := sounds(shot, item["start"]):
            rows += ["**Sound:** " + ", ".join(cues) + ".", ""]
        if item["lines"]:
            rows += ["| ID | Time | Speaker | Line | Delivery |", "| --- | --- | --- | --- | --- |"]
            for entry in item["lines"]:
                line = entry["line"]
                said = flat(line["text"]) + (f" (say: {spoken(line)})" if line.get("spoken_text") else "")
                rows.append(f"| {entry['id']} | {clock(entry['start'])}–{clock(entry['end'])} | {line['speaker']} "
                            f"| {said.replace('|', '/')} | {flat(line.get('delivery'))} |")
            rows.append("")
        rows += ["**Visual AI prompt:**", "", "```text", visual_prompt(shot, episode, lock), "```", ""]

    voice = [f"{episode.get('title', where['slug'])}: voice script", "=" * 40, ""]
    if not speakers:
        voice += ["No spoken lines in this episode."]
    else:
        voice += ["Record every line below in order. One file for the whole episode is fine (leave a short",
                  "pause between lines), or one file per speaker. Then run:", "",
                  f"  make voice-import EPISODE={shown_path(episode_path)} FILE=<your recording> [SPEAKER=<name>]", "",
                  "Lines marked (written: ...) are respelled so the voice says them right. If your voice",
                  "already pronounces the written form correctly, you may read that instead.", ""]
        for name in speakers:
            profile = voices.get(name, {})
            voice += ["-" * 40, f"{name}" + (f": {flat(profile['direction'])}" if profile.get("direction") else ""), "-" * 40, "",
                      "Paste (any voice model):", ""]
            own = [entry for entry in lines if entry["line"]["speaker"] == name]
            voice += [spoken(entry["line"]) + "\n" for entry in own]
            if any(entry["line"].get("delivery") for entry in own):
                voice += ["With delivery tags (ElevenLabs v3 and other models that read [tags] as direction):", ""]
                voice += [tag(entry["line"]) + spoken(entry["line"]) + "\n" for entry in own]
            voice += ["Line by line, with timing:", ""]
            voice += [f"  {entry['id']:<10} {clock(entry['start'])}  {spoken(entry['line'])}"
                      + (f"  (written: {flat(entry['line']['text'])})" if entry["line"].get("spoken_text") else "")
                      for entry in own]
            voice.append("")

    out = Path(out_dir) if out_dir else episode_path.parent
    (out / "script.md").write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")
    (out / "voice-script.txt").write_text("\n".join(voice).rstrip() + "\n", encoding="utf-8")
    return {"script": str(out / "script.md"), "voice_script": str(out / "voice-script.txt"), "times": source,
            "shots": len(shots), "lines": len(lines), "speakers": speakers}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode", type=Path)
    args = parser.parse_args()
    try:
        report = write(args.episode)
    except (OSError, ValueError, KeyError) as error:
        print(f"studio: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
