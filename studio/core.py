"""Manifest loading, local asset resolution, and media commands."""

import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

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


def scoped_asset(layer, base, channel_base=None):
    target = channel_base if layer.get("asset_scope") == "channel" else base
    if target is None:
        raise ValueError("A channel-scoped asset requires a channel manifest")
    return asset(target, layer["file"])


def svg_asset(layer, base, channel_base):
    if layer.get("asset_scope") == "channel":
        if channel_base is None:
            raise ValueError("A channel-scoped SVG requires a channel manifest")
        base = channel_base
    path = asset(base, layer["file"])
    if path.suffix.lower() != ".svg":
        raise ValueError(f"SVG layer requires a .svg file: {layer['file']}")
    return path


def validate_svg(path):
    try:
        root = ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, LookupError) as error:
        raise ValueError(f"Invalid SVG {path.name}: {error}") from error
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError(f"Expected an SVG root with the SVG namespace: {path.name}")
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag in {"animate", "animateColor", "animateMotion", "animateTransform", "set", "script", "foreignObject"}:
            raise ValueError(f"Use static SVG artwork and manifest keyframes: {path.name}")
        css = "".join(node.itertext()) if tag == "style" else node.get("style", "")
        if re.search(r"\b(?:animation|transition)(?:-[a-z-]+)?\s*:", css, re.IGNORECASE):
            raise ValueError(f"Use manifest keyframes for SVG animation: {path.name}")
        for name, value in node.attrib.items():
            if name.rsplit("}", 1)[-1] == "href" and not value.strip().startswith("#"):
                raise ValueError(f"SVG artwork must be self-contained: {path.name}")


def validate_channel(channel, base):
    if "font" in channel:
        asset(base, channel["font"])
    if banner := channel.get("banner"):
        if banner["safe_width"] > banner["width"] or banner["safe_height"] > banner["height"]:
            raise ValueError("Banner safe area must fit inside the banner")


def validate_episode(episode, base, channel_base=None, *, check_visual_assets=True):
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
            by_id = {layer["id"]: layer for layer in shot["layers"]}
            for layer in shot["layers"]:
                times = [point["at"] for point in layer.get("keyframes", [])]
                if times != sorted(set(times)):
                    raise ValueError(f"{shot_id}/{layer['id']} requires increasing keyframe times")
                parent = layer.get("parent")
                if parent and parent not in by_id:
                    raise ValueError(f"{shot_id}/{layer['id']} references unknown parent layer: {parent}")
                if parent == layer["id"]:
                    raise ValueError(f"{shot_id}/{layer['id']} cannot parent itself")
                if parent and (by_id[parent].get("plane", "foreground") != layer.get("plane", "foreground")):
                    raise ValueError(f"{shot_id}/{layer['id']} and its parent must share a plane")
                seen = {layer["id"]}
                walk = parent
                while walk:
                    if walk in seen:
                        raise ValueError(f"{shot_id} has a parent cycle at {walk}")
                    seen.add(walk)
                    walk = (by_id.get(walk) or {}).get("parent")
                if mask := layer.get("mask"):
                    source = mask.get("source", "")
                    if source.startswith("layer:"):
                        mask_layer = by_id.get(source.split(":", 1)[1])
                        if mask_layer is None:
                            raise ValueError(f"{shot_id}/{layer['id']} mask references an unknown layer")
                        if mask_layer.get("plane", "foreground") != layer.get("plane", "foreground"):
                            raise ValueError(f"{shot_id}/{layer['id']} and its mask must share a plane")
                    if source and not source.startswith("layer:"):
                        mask_base = channel_base if mask.get("scope") == "channel" else base
                        asset(mask_base, source)
            if transition := shot.get("transition", {}):
                if transition.get("type") == "mask" and transition.get("mask"):
                    mask_base = channel_base if transition.get("mask_scope") == "channel" else base
                    asset(mask_base, transition["mask"])
            for line in shot.get("speech", []):
                times = [word.get("start") for word in line.get("words", [])]
                if times and times != sorted(times):
                    raise ValueError(f"{shot_id}/{line['speaker']} requires increasing word times")
                viseme_times = [item.get("at") for item in line.get("visemes", [])]
                if viseme_times and viseme_times != sorted(viseme_times):
                    raise ValueError(f"{shot_id}/{line['speaker']} requires increasing viseme times")
            camera = shot.get("camera", {})
            camera_times = [key["at"] for key in camera.get("keyframes", [])]
            if camera_times != sorted(set(camera_times)):
                raise ValueError(f"{shot_id} requires increasing camera keyframe times")
            visual_assets = shot["layers"] if check_visual_assets else []
            for item in (*visual_assets, *shot.get("speech", []), *shot.get("sfx", [])):
                if item.get("kind") == "svg":
                    validate_svg(svg_asset(item, base, channel_base))
                elif "file" in item:
                    scoped_asset(item, base, channel_base)
    if total_frames / fps > limit:
        raise ValueError(f"Planned runtime exceeds {limit:g} seconds")
    cover = episode["thumbnail"]
    if cover["shot"] not in shots:
        raise ValueError("Thumbnail must reference an existing shot")
    if unknown := set(cover.get("hide_layers", [])) - shots[cover["shot"]]:
        raise ValueError(f"Unknown thumbnail layers: {', '.join(sorted(unknown))}")
    if (music := episode.get("music")) and "file" in music:
        asset(base, music["file"])
    marker_ids = set()
    for marker in episode.get("markers", []):
        if marker["id"] in marker_ids:
            raise ValueError(f"Duplicate marker ID: {marker['id']}")
        marker_ids.add(marker["id"])
        if marker["shot"] not in shots:
            raise ValueError(f"Marker {marker['id']} references an unknown shot: {marker['shot']}")
    for ambience in episode.get("ambience", []):
        if ambience.get("end", 0) <= ambience.get("start", 0):
            raise ValueError("Ambience end must be after start")
        if "file" in ambience:
            asset(base, ambience["file"])


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
