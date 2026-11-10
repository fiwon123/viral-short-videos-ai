"""Load and validate reusable Three.js scene assets."""

import json
import struct

from .core import asset, load


def check_glb(path):
    with path.open("rb") as source:
        header = source.read(20)
        if len(header) != 20:
            raise ValueError(f"Invalid GLB header: {path.name}")
        magic, version, length, chunk_size, chunk_type = struct.unpack("<4sIII4s", header)
        if (magic, version, chunk_type) != (b"glTF", 2, b"JSON") or not 0 < chunk_size <= length - 20:
            raise ValueError(f"Expected a binary glTF 2.0 model: {path.name}")
        if length != path.stat().st_size:
            raise ValueError(f"Incomplete GLB model: {path.name}")
        model = json.loads(source.read(chunk_size))
    if not isinstance(model, dict):
        raise ValueError(f"Invalid GLB scene description: {path.name}")
    for item in (*model.get("buffers", []), *model.get("images", [])):
        if "uri" in item and not item["uri"].startswith("data:"):
            raise ValueError(f"Embed textures and buffers inside the GLB: {path.name}")


def load_library(channel, base):
    name = channel.get("scene_library")
    if not name:
        return None
    path = asset(base, name)
    library = load(path, "library")
    for scene_id, scene in library["scenes"].items():
        camera = scene["camera"]
        if camera["position"] == camera["target"]:
            raise ValueError(f"{scene_id} camera position and target must differ")
        ids = set()
        for obj in scene["objects"]:
            if obj["id"] in ids:
                raise ValueError(f"{scene_id} has a duplicate 3D object ID: {obj['id']}")
            ids.add(obj["id"])
            if obj["kind"] == "glb":
                check_glb(asset(path.parent, obj["file"]))
    return library, path.parent


def validate_three(shot, library):
    if "three" not in shot:
        return
    spec = shot["three"]
    scenes = library[0]["scenes"] if library else {}
    scene = scenes.get(spec["scene"])
    if scene is None:
        raise ValueError(f"{shot['id']} references an unknown channel 3D scene: {spec['scene']}")
    paths = spec.get("objects", {})
    if unknown := paths.keys() - {obj["id"] for obj in scene["objects"]}:
        raise ValueError(f"{shot['id']} references unknown 3D objects: {', '.join(sorted(unknown))}")
    for keys in (spec.get("camera", []), *paths.values()):
        times = [key["at"] for key in keys]
        if times != sorted(set(times)):
            raise ValueError(f"{shot['id']} requires increasing 3D keyframe times")
