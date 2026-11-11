"""Report and prune the channel files that episodes actually read.

Episodes resolve voices, Foley and 3D models through the channel manifest they
are rendered with. This module lists that dependency set so you can tell the
identity kit apart from documentation, brand artwork, audition leftovers and
libraries kept for older looks.
"""

import argparse
import json
import shutil
from pathlib import Path

from .audio_library import load_audio_library
from .core import load
from .scenes import load_library

# Groups no episode render reads. Each entry is a path relative to the channel folder.
PRUNE = {
    "duplicates": ["channel-audition.json"],
    "casting": ["audio/character-references-v1"],
    "brand": ["logo.svg", "banner.svg"],
    "legacy-look": ["channel-pause-v2.json", "scene-library/pause-workbench-v2.json", "audio-library"],
}

NOTES = {
    "duplicates": "An older copy of the channel manifest pointing at the same libraries.",
    "casting": "Character sheets from the voice and design audition. No render reads them.",
    "brand": "Editable logo and banner artwork. Only used when setting up the channel.",
    "legacy-look": "The pause-workbench look. Only its own manifest needs these files.",
    "alternate-look": "A second channel manifest. Keep it if you still render that look.",
    "documentation": "Reference only.",
}


def size(path):
    if path.is_file():
        return path.stat().st_size
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


def human(count):
    value = float(count)
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def manifests(base):
    """Every channel manifest in the folder, keyed by filename."""
    found = {}
    for path in sorted(base.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and {"name", "mark", "palette"} <= data.keys():
            found[path.name] = data
    return found


def report(channel_path):
    channel_path = channel_path.resolve()
    base = channel_path.parent
    channel = load(channel_path, "channel")
    library, library_base = load_library(channel, base)
    audio = load_audio_library(channel, base)
    scenes = library["scenes"]

    required = {channel_path, (base / channel["scene_library"]).resolve()}
    models = {}
    for scene_id, scene in scenes.items():
        for obj in scene["objects"]:
            if obj["kind"] != "glb":
                continue
            path = (library_base / obj["file"]).resolve()
            required.add(path)
            entry = models.setdefault(str(path.relative_to(base)),
                                      {"file": str(path.relative_to(base)),
                                       "bytes": path.stat().st_size, "objects": [], "scenes": []})
            if obj["id"] not in entry["objects"]:
                entry["objects"].append(obj["id"])
            if scene_id not in entry["scenes"]:
                entry["scenes"].append(scene_id)

    voices, sounds = [], []
    if audio:
        profile_set, sound_bank = audio[0], audio[0].get("sounds", {})
        audio_base = audio[1].parent.resolve()
        required.add(audio[1].resolve())
        for name, profile in profile_set.get("voices", {}).items():
            voices.append({"name": name, "engine": profile.get("engine"),
                           "blend": profile.get("blend", {}), "speed": profile.get("speed")})
            if design := profile.get("character_design"):
                for key in ("reference", "approved_take"):
                    if key in design:
                        required.add((audio_base / design[key]).resolve())
        for name, variants in sound_bank.items():
            files = [(audio_base / file).resolve() for file in variants]
            required.update(files)
            sounds.append({"name": name, "variants": len(variants),
                           "bytes": sum(file.stat().st_size for file in files)})

    # Models shared by two or more scene libraries keep the cast identical between looks.
    seen = {}
    for path in sorted((base / "scene-library").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for scene in data.get("scenes", {}).values():
            for obj in scene.get("objects", []):
                if obj.get("kind") == "glb":
                    seen.setdefault(obj["file"], set()).add(path.name)
    shared = sorted(file for file, users in seen.items() if len(users) > 1)

    optional = []
    for group, names in PRUNE.items():
        for name in names:
            path = base / name
            if path.exists():
                optional.append({"group": group, "file": name, "bytes": size(path)})

    referenced = {name for names in PRUNE.values() for name in names}
    alternates = [name for name in manifests(base) if name != channel_path.name and name not in referenced]
    for name in alternates:
        optional.append({"group": "alternate-look", "file": name, "bytes": size(base / name)})
    for name in ("brief.md", "scene-library/build.mjs"):
        if (base / name).exists():
            optional.append({"group": "documentation", "file": name, "bytes": size(base / name)})

    # A top-level entry counts as referenced when any required file lives inside it.
    def referenced_entry(path):
        return any(required_file == path.resolve() or required_file.is_relative_to(path.resolve())
                   for required_file in required)

    unreferenced = [{"file": path.name, "bytes": size(path)}
                    for path in sorted(base.iterdir())
                    if not referenced_entry(path)]

    return {
        "channel": channel.get("name"),
        "manifest": str(channel_path.relative_to(base)),
        "palette": channel["palette"],
        "font": channel.get("font", "default sans serif"),
        "scenes": {scene_id: len([obj for obj in scene["objects"] if obj["kind"] == "glb"])
                   for scene_id, scene in scenes.items()},
        "models": sorted(models.values(), key=lambda item: item["file"]),
        "voices": voices,
        "sounds": sounds,
        "shared_models": shared,
        "required_bytes": sum(path.stat().st_size for path in required if path.is_file()),
        "optional": optional,
        "unreferenced": unreferenced,
        "prune": {group: [str(base / name) for name in names if (base / name).exists()]
                  for group, names in PRUNE.items()},
    }


def format_report(data):
    rows = [f"{data['channel']} — {data['manifest']}",
            f"palette {data['palette']['background']} · {data['palette']['foreground']} · "
            f"{data['palette']['accent']} · {data['palette']['secondary']}",
            f"font {data['font']}",
            f"identity kit a render needs: {human(data['required_bytes'])}", ""]
    rows.append("Read by every episode rendered with this manifest")
    for scene_id, count in data["scenes"].items():
        rows.append(f"  scene {scene_id}: {count} objects")
    for model in data["models"]:
        used = ", ".join(model["objects"][:3]) + (", …" if len(model["objects"]) > 3 else "")
        rows.append(f"    {model['file']:<44} {human(model['bytes']):>8}  {used}")
    for voice in data["voices"]:
        blend = " + ".join(f"{name} {weight}%" for name, weight in voice["blend"].items())
        rows.append(f"  voice {voice['name']}: {voice['engine']} · {blend} · speed {voice['speed']}")
    for sound in data["sounds"]:
        rows.append(f"  sound {sound['name']}: {sound['variants']} variants {human(sound['bytes']):>8}")
    rows.extend(["", "Shared between scene libraries (cast and props reused across looks)"])
    for file in data["shared_models"]:
        rows.append(f"  {file}")
    rows.extend(["", "Not read by an episode render"])
    for item in data["optional"]:
        note = NOTES.get(item["group"], item["group"].replace("-", " "))
        rows.append(f"  {item['file']:<44} {human(item['bytes']):>8}  {note}")
    return "\n".join(rows)


def prune(channel_path, group, apply):
    base = channel_path.resolve().parent
    if group not in PRUNE:
        raise ValueError(f"Unknown prune group: {group}. Use one of {', '.join(PRUNE)}")
    targets = [base / name for name in PRUNE[group] if (base / name).exists()]
    if not targets:
        return {"group": group, "applied": apply, "files": [], "bytes": 0,
                "hint": "Nothing to remove."}
    total = sum(size(path) for path in targets)
    for path in targets:
        if not path.resolve().is_relative_to(base.resolve()):
            raise ValueError(f"Refusing to touch a path outside the channel folder: {path}")
        if apply:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    return {"group": group, "applied": apply,
            "files": [str(path.relative_to(base)) for path in targets], "bytes": total,
            "hint": "" if apply else "Dry run. Add --apply to delete."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", type=Path,
                        help="channel manifest, for example channels/<slug>/channel.json")
    parser.add_argument("--json", action="store_true", help="print the machine-readable report")
    parser.add_argument("--prune", choices=sorted(PRUNE), help="delete one optional group")
    parser.add_argument("--apply", action="store_true", help="actually delete; without it --prune is a dry run")
    args = parser.parse_args()
    try:
        if args.prune:
            result = prune(args.channel, args.prune, args.apply)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"{'Removed' if args.apply else 'Would remove'} {len(result['files'])} item(s), "
                      f"{human(result['bytes'])}:")
                for name in result["files"]:
                    print(f"  {name}")
                if result["hint"]:
                    print(result["hint"])
            return 0
        data = report(args.channel)
        print(json.dumps(data, indent=2) if args.json else format_report(data))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"studio: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
