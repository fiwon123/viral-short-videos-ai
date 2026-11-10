"""Validate authored visual checks and audit the resolved animation timeline."""

import json
from pathlib import Path

from .core import require, run
from .design import poses

ENTRY = Path(__file__).resolve().parents[1] / "browser" / "check.mjs"


def validate_visual(episode, library):
    scenes = library[0]["scenes"] if library else {}
    previous_scene = None
    for scene in episode["scenes"]:
        for shot in scene["shots"]:
            checks = shot.get("checks", {})
            layers = {layer["id"] for layer in shot["layers"]}
            layer_checks = set(checks.get("keep_in_frame", []))
            for pair in checks.get("avoid_2d", []):
                layer_checks.update(pair)
            if unknown := layer_checks - layers:
                raise ValueError(f"{shot['id']} checks reference unknown 2D layers: {', '.join(sorted(unknown))}")

            stage = scenes.get(shot.get("three", {}).get("scene"))
            objects = {obj["id"]: obj for obj in stage["objects"]} if stage else {}
            bounds = set(checks.get("floor", {}).get("objects", []))
            for pair in checks.get("avoid_3d", []):
                bounds.update(pair)
            for contact in checks.get("contacts", []):
                bounds.update(contact["objects"])
            if missing := bounds - {key for key, obj in objects.items() if "hitbox" in obj}:
                raise ValueError(f"{shot['id']} requires hitboxes for 3D checks: {', '.join(sorted(missing))}")
            if continuity := checks.get("continuity"):
                if stage is None or previous_scene is None:
                    raise ValueError(f"{shot['id']} continuity requires two adjacent 3D shots")
                previous = {obj["id"] for obj in previous_scene["objects"]}
                if missing := set(continuity.get("objects", [])) - (objects.keys() & previous):
                    raise ValueError(f"{shot['id']} continuity requires these objects in both shots: {', '.join(sorted(missing))}")
            previous_scene = stage


def audit_visual(episode, library, timeline, *, include_cameras=False):
    scenes = library[0]["scenes"] if library else {}
    shots = []
    for scene, timing in zip(episode["scenes"], timeline["scenes"]):
        for shot, resolved in zip(scene["shots"], timing["shots"]):
            three = shot.get("three")
            checks = shot.get("checks", {})
            groups = three and any(obj.get("variant_group") for obj in scenes[three["scene"]]["objects"])
            shots.append({
                "id": shot["id"], "start": resolved["start"], "end": resolved["end"],
                "three": three, "checks": checks, "audit": bool(checks or groups or (three and include_cameras)),
                "layers": [{"id": layer["id"], "poses": poses(layer),
                            "hitbox": layer.get("hitbox", [layer.get("width", 0.55), layer.get("height", 0.2)])}
                           for layer in shot["layers"]] if checks.get("avoid_2d") or checks.get("keep_in_frame") else [],
            })
    if not any(shot["audit"] for shot in shots):
        return {"checked_shots": 0, "checked_frames": 0, "issues": []}
    require("node")
    if not (ENTRY.parent.parent / "node_modules" / "three").is_dir():
        raise ValueError("Install visual check dependencies with npm ci from the repository root")
    data = {"width": episode["width"], "height": episode["height"], "scenes": scenes, "shots": shots}
    return json.loads(run("node", str(ENTRY), data=json.dumps(data).encode()))
