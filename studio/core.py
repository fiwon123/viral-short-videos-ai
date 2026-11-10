"""Manifest loading, local asset resolution, and media commands."""

import json
import math
from pathlib import Path
import shutil
import subprocess
from contextlib import contextmanager
from tempfile import TemporaryDirectory

from jsonschema import Draft202012Validator

MAX_SECONDS = 720
SAMPLE_RATE = 48000
SCHEMA = json.loads(Path(__file__).with_name("schema.json").read_text(encoding="utf-8"))


def load(path, kind):
    def reject_constant(value):
        raise ValueError(f"Invalid JSON constant: {value}")

    data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    validator = Draft202012Validator({**SCHEMA, "$ref": f"#/$defs/{kind}"})
    errors = sorted(validator.iter_errors(data), key=lambda error: error.json_path)
    if errors:
        details = "\n".join(f"{error.json_path}: {error.message}" for error in errors[:8])
        raise ValueError(f"{path.name}\n{details}")
    return data


def asset(base, name):
    if Path(name).is_absolute():
        raise ValueError(f"Use a project-relative asset path: {name}")
    path = (base / name).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise ValueError(f"Asset must be an existing file under {base}: {name}")
    return path


def validate_channel(channel, base):
    if "font" in channel:
        asset(base, channel["font"])
    if banner := channel.get("banner"):
        if banner["safe_width"] > banner["width"] or banner["safe_height"] > banner["height"]:
            raise ValueError("Banner safe area must fit inside the banner")


def validate_episode(episode, base):
    fps = episode["fps"]
    limit = episode.get("max_seconds", MAX_SECONDS)
    ids, shots = set(), {}
    total_frames = 0
    for scene in episode["scenes"]:
        for entry in (scene, *scene["shots"]):
            item_id = entry["id"]
            if item_id in ids:
                raise ValueError(f"Duplicate scene or shot ID: {item_id}")
            ids.add(item_id)
        for shot in scene["shots"]:
            shot_id = shot["id"]
            if not shots and "transition" in shot:
                raise ValueError("The first shot has no preceding shot for its transition")
            total_frames += max(1, math.ceil(shot["duration"] * fps - 1e-9))
            layer_ids = [layer["id"] for layer in shot["layers"]]
            if len(set(layer_ids)) != len(layer_ids):
                raise ValueError(f"{shot_id} has duplicate layer IDs")
            shots[shot_id] = set(layer_ids)
            for layer in shot["layers"]:
                times = [point["at"] for point in layer.get("keyframes", [])]
                if times != sorted(set(times)):
                    raise ValueError(f"{shot_id}/{layer['id']} requires increasing keyframe times")
            for item in (*shot["layers"], *shot.get("speech", []), *shot.get("sfx", [])):
                if "file" in item:
                    asset(base, item["file"])
    if total_frames / fps > limit:
        raise ValueError(f"Planned runtime exceeds {limit:g} seconds")
    cover = episode["thumbnail"]
    if cover["shot"] not in shots:
        raise ValueError("Thumbnail must reference an existing shot")
    if unknown := set(cover.get("hide_layers", [])) - shots[cover["shot"]]:
        raise ValueError(f"Unknown thumbnail layers: {', '.join(sorted(unknown))}")
    if (music := episode.get("music")) and "file" in music:
        asset(base, music["file"])


def require(name):
    if not shutil.which(name):
        raise ValueError(f"Install {name} and add it to PATH")


def run(*args, data=None):
    result = subprocess.run(args, input=data, capture_output=True, check=False)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"{Path(args[0]).name} failed\n{detail[-2500:]}")
    return result.stdout


def probe(path, count_frames=False):
    flags = ["-count_frames"] if count_frames else []
    return json.loads(run("ffprobe", "-v", "error", *flags, "-show_format", "-show_streams", "-of", "json", str(path)))


def ffmpeg(*args):
    return run("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", *args)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


@contextmanager
def new_package(target):
    """Keep failed renders out of the named output directory."""
    target = target.absolute()
    if target.exists() or target.is_symlink():
        raise ValueError(f"Output already exists. Choose a new path: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".studio-", dir=target.parent) as tmp:
        staging = Path(tmp) / "package"
        staging.mkdir()
        yield staging
        target.mkdir()
        moved = []
        try:
            for entry in staging.iterdir():
                entry.rename(target / entry.name)
                moved.append(entry.name)
        except OSError:
            for name in moved:
                (target / name).rename(staging / name)
            if not any(target.iterdir()):
                target.rmdir()
            raise
