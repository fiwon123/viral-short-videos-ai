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
    return morph_names(model)


def morph_names(model):
    """Morph target names a glTF model exposes (mesh.extras.targetNames, else indices)."""
    names = set()
    for mesh in model.get("meshes", []):
        count = max((len(primitive.get("targets", [])) for primitive in mesh.get("primitives", [])), default=0)
        labels = (mesh.get("extras") or {}).get("targetNames") or []
        names |= set(labels[:count]) | {str(index) for index in range(count)}
    return names


def load_library(channel, base):
    name = channel.get("scene_library")
    if not name:
        return None
    path = asset(base, name)
    library = load(path, "library")
    for scene_id, scene in library["scenes"].items():
        if rig := scene.get("lighting_rig"):
            if rig not in library.get("lighting_rigs", {}):
                raise ValueError(f"{scene_id} references an unknown lighting rig: {rig}")
            scene["lighting"] = library["lighting_rigs"][rig]
        light = scene.get("lighting", {})
        if ("target" in light or light.get("shadows")) and light.get("position", [-3, 6, 5]) == light.get("target", [0, 0, 0]):
            raise ValueError(f"{scene_id} light position and target must differ")
        camera = scene["camera"]
        if camera["position"] == camera["target"]:
            raise ValueError(f"{scene_id} camera position and target must differ")
        ids = set()
        for obj in scene["objects"]:
            if obj["id"] in ids:
                raise ValueError(f"{scene_id} has a duplicate 3D object ID: {obj['id']}")
            ids.add(obj["id"])
            if obj["kind"] == "glb":
                obj["_morphs"] = sorted(check_glb(asset(path.parent, obj["file"])))
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
    object_ids = {obj["id"] for obj in scene["objects"]}
    if unknown := paths.keys() - object_ids:
        raise ValueError(f"{shot['id']} references unknown 3D objects: {', '.join(sorted(unknown))}")
    if unknown := spec.get("animations", {}).keys() - object_ids:
        raise ValueError(f"{shot['id']} animates unknown 3D objects: {', '.join(sorted(unknown))}")
    for keys in spec.get("animations", {}).values():
        if [key.get("at", 0) for key in keys] != sorted(key.get("at", 0) for key in keys):
            raise ValueError(f"{shot['id']} requires increasing animation offsets")
    for keys in (spec.get("camera", []), *paths.values()):
        times = [key["at"] for key in keys]
        if times != sorted(set(times)):
            raise ValueError(f"{shot['id']} requires increasing 3D keyframe times")
    morphs = {obj["id"]: set(obj.get("_morphs", [])) for obj in scene["objects"]}
    for object_id, keys in paths.items():
        used = {name for key in keys for name in (key.get("morph") or {})}
        if unknown := used - morphs.get(object_id, set()):
            known = ", ".join(sorted(morphs.get(object_id, set()))) or "none"
            raise ValueError(f"{shot['id']} keys unknown morph targets on {object_id}: "
                             f"{', '.join(sorted(unknown))} (model has: {known})")
    focus_times = [key["at"] for key in spec.get("focus", [])]
    if focus_times != sorted(set(focus_times)):
        raise ValueError(f"{shot['id']} requires increasing 3D focus times")
