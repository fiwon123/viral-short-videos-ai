"""A local music library: import tracks once, then ask for a mood.

    python -m studio.music import workspace/<slug>/channel --source ~/music-pack [--dry-run]
    python -m studio.music list workspace/<slug>/channel

Import scans a folder of tracks you own or that are free to use (CC0 such as
FreePD, the YouTube Audio Library for YouTube uploads, Pixabay Music, or CC-BY
with credit). It measures tempo, loudness and energy, tags moods from folder
and file names (calm, happy, funny, epic, tense, sad, action, dreamy) with
the energy as a fallback, copies the tracks into ``audio/music/``, and writes
``audio/music/index.json`` with provenance. The channel's ``music_library``
points at it.

Episodes then ask for music by feel instead of by file::

    "music": {"mood": "funny", "energy": "high", "gain": 0.06}

The pick is deterministic per episode and favours tracks long enough for the
episode and close to the requested tempo (``bpm``: ``[min, max]``), so a channel
keeps a consistent sound without repeating one track on every upload.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np

EXTENSIONS = {".wav", ".ogg", ".flac", ".mp3", ".m4a", ".aac", ".opus"}
RATE = 22050
MOODS = {
    "calm": ["calm", "chill", "ambient", "lofi", "lo-fi", "soft", "peaceful", "relax", "piano", "gentle", "sleep"],
    "happy": ["happy", "upbeat", "cheerful", "bright", "sunny", "positive", "ukulele", "joy"],
    "funny": ["funny", "comedy", "quirky", "silly", "cartoon", "comic", "goofy", "bouncy"],
    "epic": ["epic", "cinematic", "trailer", "heroic", "orchestral", "inspiring", "triumph"],
    "tense": ["tense", "suspense", "dark", "mystery", "thriller", "horror", "creepy", "ominous"],
    "sad": ["sad", "melancholy", "emotional", "sentimental", "lonely", "tragic"],
    "action": ["action", "energetic", "drive", "driving", "fast", "rock", "electronic", "hype", "sport"],
    "dreamy": ["dreamy", "magic", "magical", "wonder", "fantasy", "whimsical", "fairy"],
}


def decode(path, seconds=None):
    command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(RATE)]
    if seconds:
        command += ["-t", str(seconds)]
    data = subprocess.run(command + ["-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(data, dtype="<f4").astype(np.float64)


HOP = 512


def onsets(samples):
    """Onset strength per hop: the rise in log energy (index i is the boundary at (i + 1) * HOP)."""
    frames = len(samples) // HOP
    if frames < 64:
        return None
    energy = np.sqrt(np.mean(samples[:frames * HOP].reshape(frames, HOP) ** 2, axis=1))
    return np.maximum(0, np.diff(np.log1p(energy * 100)))


def tempo(samples):
    """BPM from the autocorrelation of an onset-strength envelope (60-180)."""
    onset = onsets(samples)
    if onset is None:
        return None
    # Smooth over three hops: a beat period is rarely a whole number of hops (120 bpm is 21.5), and
    # unsmoothed clicks then line up better at two beats than at one, halving the tempo.
    onset = np.convolve(onset, [0.25, 0.5, 0.25], mode="same")
    onset = onset - onset.mean()
    corr = np.correlate(onset, onset, mode="full")[len(onset) - 1:]
    fps = RATE / HOP
    lags = np.arange(len(corr))
    valid = (lags >= fps * 60 / 180) & (lags <= fps * 60 / 60)
    if not valid.any() or corr[valid].max() <= 0:
        return None
    best = int(lags[valid][np.argmax(corr[valid])])
    half = round(best / 2)
    if half >= fps * 60 / 180 and corr[max(1, half - 1):half + 2].max() >= 0.6 * corr[best]:
        best = int(max(1, half - 1) + np.argmax(corr[max(1, half - 1):half + 2]))  # the faster pulse is there too
    left, middle, right = corr[best - 1], corr[best], corr[min(best + 1, len(corr) - 1)]
    curve = left - 2 * middle + right
    lag = best + (0.5 * (left - right) / curve if curve < 0 else 0.0)  # parabolic peak: a fractional lag
    bpm = 60 * fps / lag
    return round(float(bpm), 1)


def first_beat(samples, bpm):
    """Seconds to the first beat: the phase of the beat grid that collects the most onset strength."""
    onset = onsets(samples)
    if onset is None or not bpm:
        return None
    fps = RATE / HOP
    period = fps * 60.0 / float(bpm)
    best, phase = -1.0, 0.0
    for start in np.arange(0.0, period, 1.0):
        picks = np.round(np.arange(start, len(onset), period)).astype(int)
        score = float(onset[picks[picks < len(onset)]].sum())
        if score > best:
            best, phase = score, start
    return round(float((phase + 1) * HOP / RATE), 3)


def beat_grid(path):
    """{"bpm", "offset"} measured from an audio file, or None when it has no steady pulse."""
    samples = decode(path, seconds=120)
    bpm = tempo(samples)
    if not bpm:
        return None
    return {"bpm": bpm, "offset": first_beat(samples, bpm)}


def analyse(path):
    samples = decode(path, seconds=240)
    duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                     str(path)], capture_output=True, text=True).stdout.strip() or len(samples) / RATE)
    rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0.0
    loudness = round(20 * np.log10(max(rms, 1e-9)), 1)
    hop = RATE // 2
    blocks = len(samples) // hop
    levels = np.sqrt(np.mean(samples[:blocks * hop].reshape(blocks, hop) ** 2, axis=1)) if blocks else np.array([rms])
    dynamics = float(np.percentile(levels, 90) / max(np.percentile(levels, 30), 1e-6))
    bpm = tempo(samples)
    score = (loudness + 30) / 20 + ((bpm or 100) - 100) / 60 - min(dynamics, 6) / 12
    energy = "high" if score > 0.85 else "low" if score < 0.25 else "medium"
    return {"duration": round(duration, 2), "bpm": bpm, "first_beat": first_beat(samples, bpm),
            "loudness_db": loudness, "energy": energy}


def moods_for(path, energy, bpm):
    words = re.sub(r"[_\-./]+", " ", str(path).lower())
    found = [mood for mood, keys in MOODS.items() if any(re.search(rf"\b{re.escape(key)}\b", words) for key in keys)]
    if not found:
        found = ["action" if energy == "high" and (bpm or 0) >= 120 else "happy" if energy == "high"
                 else "calm" if energy == "low" else "dreamy" if (bpm or 100) < 95 else "happy"]
    return found


def import_music(channel_dir, source, dry_run=False):
    channel_dir, source = Path(channel_dir).resolve(), Path(source).expanduser().resolve()
    files = sorted(path for path in source.rglob("*") if path.suffix.lower() in EXTENSIONS and path.is_file())
    if not files:
        raise ValueError(f"No audio files under {source}")
    folder = channel_dir / "audio" / "music"
    index_path = folder / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {"version": 1, "tracks": []}
    known = {track["sha256"] for track in index["tracks"]}
    added = []
    for path in files:
        digest = sha256(path.read_bytes()).hexdigest()
        if digest in known:
            continue
        info = analyse(path)
        if info["duration"] < 5:
            continue
        relative = path.relative_to(source)
        name = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")[:48] or digest[:8]
        target = f"audio/music/{name}-{digest[:6]}{path.suffix.lower()}"
        track = {"file": target, "title": path.stem, "moods": moods_for(relative, info["energy"], info["bpm"]),
                 **info, "source": str(relative), "sha256": digest,
                 "license": "check the pack's licence; record the credit line here if CC-BY"}
        added.append(track)
        known.add(digest)
        if not dry_run:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, channel_dir / target)
    if not dry_run and added:
        index["tracks"].extend(added)
        index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        channel_path = channel_dir / "channel.json"
        if channel_path.is_file():
            channel = json.loads(channel_path.read_text(encoding="utf-8"))
            if channel.get("music_library") != "audio/music/index.json":
                channel["music_library"] = "audio/music/index.json"
                channel_path.write_text(json.dumps(channel, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"scanned": len(files), "added": [{key: track[key] for key in ("title", "moods", "energy", "bpm", "duration")}
                                             for track in added],
            "library": str(index_path), "dry_run": dry_run}


def pick(tracks, request, runtime, seed_text=""):
    """Best track for ``request`` ({mood, energy, bpm}); deterministic per ``seed_text``."""
    if not tracks:
        raise ValueError("The music library is empty. Run python -m studio.music import first.")
    mood, energy, bpm = request.get("mood"), request.get("energy"), request.get("bpm")

    def score(track):
        value = 0.0
        if mood:
            value += 4 if mood in track["moods"] else 0
        if energy:
            order = ["low", "medium", "high"]
            value += 2 - abs(order.index(energy) - order.index(track["energy"]))
        if bpm and track.get("bpm"):
            low, high = bpm
            value += 2 if low <= track["bpm"] <= high else max(0, 2 - min(abs(track["bpm"] - low), abs(track["bpm"] - high)) / 15)
        value += 1 if track["duration"] >= runtime else track["duration"] / max(runtime, 1)
        return value
    ranked = sorted(tracks, key=lambda track: (-score(track), track["file"]))
    best = score(ranked[0])
    shortlist = [track for track in ranked if score(track) >= best - 0.5][:4]
    salt = int(sha256(seed_text.encode()).hexdigest(), 16)
    return shortlist[salt % len(shortlist)]


def expand(episode, channel, channel_dir):
    """Turn ``music: {mood, energy, bpm}`` into a concrete library track file."""
    music = episode.get("music")
    if not music or "mood" not in music and "energy" not in music and "bpm" not in music:
        return episode
    library = (channel or {}).get("music_library")
    if not library:
        raise ValueError("music asks for a mood but the channel has no music_library. Import tracks with "
                         "python -m studio.music import <channel> --source <folder>.")
    base = Path(channel_dir)
    index = json.loads((base / library).read_text(encoding="utf-8"))
    runtime = sum(float(shot.get("duration", 0)) for scene in episode.get("scenes", []) for shot in scene.get("shots", []))
    track = pick(index["tracks"], music, runtime, episode.get("title", ""))
    episode["music"] = {**{key: value for key, value in music.items() if key not in ("mood", "energy", "bpm")},
                        "library_file": str((base / track["file"]).resolve()), "library_track": track["title"]}
    if track.get("bpm") and track.get("first_beat") is not None and "beat" not in music:
        episode["music"]["beat"] = {"bpm": track["bpm"], "offset": track["first_beat"]}  # for at_beat anchors
    return episode


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import")
    importer.add_argument("channel", type=Path)
    importer.add_argument("--source", type=Path, required=True)
    importer.add_argument("--dry-run", action="store_true")
    listing = commands.add_parser("list")
    listing.add_argument("channel", type=Path)
    args = parser.parse_args()
    if args.command == "import":
        print(json.dumps(import_music(args.channel, args.source, args.dry_run), indent=2))
    else:
        index = json.loads((args.channel / "audio" / "music" / "index.json").read_text(encoding="utf-8"))
        for track in index["tracks"]:
            print(f"{track['title'][:40]:<40} {','.join(track['moods']):<16} {track['energy']:<7} "
                  f"{track.get('bpm') or '-':>6} bpm {track['duration']:>6.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
