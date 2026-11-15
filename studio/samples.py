"""Import a folder of recorded SFX into a channel's audio library.

Synthesized Foley (``studio.sfx``) is a fallback. Recorded sounds from a pack
you own or that is CC0 (Kenney, Sonniss GDC bundles, freesound CC0 exports)
sound far more professional. This tool scans a folder, classifies files by
their path words into the studio's sound names (whoosh, thud, pop, riser...),
trims and normalises them, copies the best variants into the channel and
points the audio library at them. Episodes that already say
``{"sound": "whoosh"}`` pick up the real recordings with no other change.

    python -m studio.samples workspace/<slug>/channel --source ~/sfx-pack [--dry-run]

Provenance for every imported file is written to ``audio/samples/SOURCES.json``
so licences and credits can be checked before publishing.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

import numpy as np

from .core import SAMPLE_RATE
from .sfx import write_wav

EXTENSIONS = {".wav", ".ogg", ".flac", ".mp3", ".aif", ".aiff", ".m4a"}

# Ordered: the first matching rule wins, so specific words come before broad ones.
RULES = [
    ("footstep", ["footstep", "footsteps", "step", "walk", "run"]),
    ("heartbeat", ["heartbeat", "heart"]),
    ("riser", ["riser", "rise", "build", "uplifter", "tension"]),
    ("boom", ["boom", "sub", "cinematic hit", "trailer hit", "braam"]),
    ("whoosh", ["whoosh", "woosh", "swoosh", "whoompf", "pass by", "passby", "fly by", "flyby", "swipe"]),
    ("swish", ["swish", "swing", "cloth", "fabric"]),
    ("splash", ["splash", "water impact"]),
    ("splat", ["splat", "squish", "goo", "slime"]),
    ("drip", ["drip", "droplet"]),
    ("bubble", ["bubble", "blub"]),
    ("pour", ["pour"]),
    ("slosh", ["slosh"]),
    ("gulp", ["gulp", "swallow"]),
    ("sip", ["sip", "slurp"]),
    ("glass", ["glass", "shatter"]),
    ("metal", ["metal", "clang", "anvil"]),
    ("clink", ["clink", "ting", "cutlery", "coin"]),
    ("bell", ["bell", "chime", "ding"]),
    ("sparkle", ["sparkle", "magic", "twinkle", "shimmer", "glitter"]),
    ("zap", ["zap", "laser", "electric", "spark"]),
    ("boing", ["boing", "spring", "cartoon jump"]),
    ("pop", ["pop", "bubble pop", "cork", "appear"]),
    ("click", ["click", "button", "switch", "ui", "interface", "menu", "select"]),
    ("tap", ["tap", "knock", "keyboard", "typing", "type"]),
    ("creak", ["creak", "door"]),
    ("squeak", ["squeak", "rubber"]),
    ("rattle", ["rattle", "shake"]),
    ("crumble", ["crumble", "rubble", "rocks", "gravel"]),
    ("debris", ["debris", "break", "crash", "destruction"]),
    ("burst", ["burst", "explosion", "explode", "blast"]),
    ("thwack", ["thwack", "whack", "slap", "punch", "smack"]),
    ("bonk", ["bonk", "cartoon hit", "bop"]),
    ("thud", ["thud", "impact", "hit", "body fall", "land", "drop", "bump"]),
    ("wind", ["wind", "air", "breeze", "storm"]),
]
LIMITS = {"riser": 6.0, "wind": 8.0, "boom": 4.0, "footstep": 1.0, "click": 0.8, "tap": 0.8}


def classify(path):
    """Return the sound name for a file path, or None."""
    raw = str(path)[: -len(path.suffix)] if path.suffix else str(path)
    raw = re.sub(r"([a-z])([A-Z])", r"\1 \2", raw)  # impactWood -> impact Wood
    text = " " + re.sub(r"[^a-z]+", " ", raw.lower()) + " "
    for name, words in RULES:
        if any(f" {word} " in text or f" {word}s " in text or f" {word}es " in text for word in words):
            return name
    return None


def prepare(samples, limit):
    """Trim silence, cap length, fade the tail and match peaks like studio.sfx."""
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    if peak < 0.01:
        return None
    loud = np.flatnonzero(np.abs(samples) > peak * 0.004)
    start = max(0, int(loud[0]) - SAMPLE_RATE // 500)
    end = min(len(samples), int(loud[-1]) + SAMPLE_RATE // 50, start + int(limit * SAMPLE_RATE))
    clip = np.array(samples[start:end], dtype=np.float32)
    if len(clip) < SAMPLE_RATE * 0.03:
        return None
    fade = min(len(clip) // 4, int(SAMPLE_RATE * 0.03))
    if fade:
        clip[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    clip -= float(np.mean(clip))  # Remove DC so stacking layers stays clean.
    return clip * (0.89 / max(1e-6, float(np.max(np.abs(clip)))))


def scan(source):
    found = {}
    for path in sorted(Path(source).expanduser().rglob("*")):
        if path.suffix.lower() in EXTENSIONS and path.is_file():
            name = classify(path.relative_to(source))
            if name:
                found.setdefault(name, []).append(path)
    return found


def _spread(paths, count):
    """Pick variants spread across the list so one sub-folder doesn't dominate."""
    if len(paths) <= count:
        return paths
    step = len(paths) / count
    return [paths[int(index * step)] for index in range(count)]


def import_pack(channel, source, *, library="audio/cast-v2.json", variants=6, keep_synth=False, dry_run=False):
    from .audio import read_audio

    channel, source = Path(channel).resolve(), Path(source).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Sample folder not found: {source}")
    target = (channel / library).resolve()
    folder = target.parent / "samples"
    found = scan(source)
    plan = {name: _spread(paths, variants) for name, paths in found.items()}
    if dry_run:
        return {"source": str(source), "sounds": {name: [str(p.relative_to(source)) for p in paths]
                                                  for name, paths in plan.items()},
                "unclassified_hint": "rename or move files so a folder or file name contains the sound word"}
    data = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {"version": 2, "voices": {}, "sounds": {}}
    folder.mkdir(parents=True, exist_ok=True)
    provenance_path = folder / "SOURCES.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.is_file() else {}
    report = {}
    for name, paths in plan.items():
        files = []
        for path in paths:
            try:
                clip = prepare(read_audio(path), LIMITS.get(name, 3.0))
            except (OSError, ValueError):
                continue
            if clip is None:
                continue
            digest = sha256(str(path).encode()).hexdigest()[:8]
            file = folder / f"{name}-{digest}.wav"
            write_wav(file, clip)
            relative = str(file.relative_to(target.parent))
            files.append(relative)
            provenance[relative] = {"source": str(path), "pack": source.name}
        if not files:
            continue
        previous = [item for item in data["sounds"].get(name, []) if not item.startswith("samples/")]
        data["sounds"][name] = files + (previous if keep_synth else [])
        report[name] = len(files)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"library": str(target.relative_to(channel)), "imported": report,
            "provenance": str(provenance_path.relative_to(channel))}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("channel", type=Path, help="channel folder")
    parser.add_argument("--source", type=Path, required=True, help="folder of recorded sound files")
    parser.add_argument("--library", default="audio/cast-v2.json", help="library JSON relative to the channel")
    parser.add_argument("--variants", type=int, default=6)
    parser.add_argument("--keep-synth", action="store_true", help="keep synthesized variants after the samples")
    parser.add_argument("--dry-run", action="store_true", help="only show how files would be classified")
    args = parser.parse_args()
    try:
        print(json.dumps(import_pack(args.channel, args.source, library=args.library, variants=args.variants,
                                     keep_synth=args.keep_synth, dry_run=args.dry_run), indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(f"studio: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
