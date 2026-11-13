"""Expand named timing markers into sound, camera and effect events.

A marker is the authoring unit. The renderer sees ordinary SFX, camera shakes
and layers, so moving a marker moves every attached event together.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EFFECT_DIR = ROOT / "presets" / "effects"


def _effect_template(name, channel_base=None):
    candidates = []
    if channel_base:
        candidates.append(Path(channel_base) / "presets" / "effects" / f"{name}.json")
    candidates.append(EFFECT_DIR / f"{name}.json")
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"Unknown marker effect template: {name}")


def expand(episode, channel_base=None):
    shots = {
        shot["id"]: shot
        for scene in episode.get("scenes", [])
        for shot in scene.get("shots", [])
    }
    for marker in episode.get("markers", []):
        shot = shots.get(marker["shot"])
        if shot is None:
            raise ValueError(f"Marker {marker['id']} references unknown shot: {marker['shot']}")
        duration = max(1e-6, float(shot.get("duration", 1)))
        at = float(marker.get("at", 0))
        for event in marker.get("events", []):
            kind = event.get("kind")
            if kind == "sfx":
                cue = {key: value for key, value in event.items()
                       if key not in {"kind", "template", "offset", "duration"}}
                cue["at"] = max(0, at * duration + float(event.get("offset", 0)))
                shot.setdefault("sfx", []).append(cue)
            elif kind == "camera_shake":
                camera = shot.setdefault("camera", {})
                camera.setdefault("shakes", []).append({
                    "at": at,
                    "duration": float(event.get("duration", 0.35)),
                    "amplitude": float(event.get("amplitude", 0.015)),
                    "frequency": float(event.get("frequency", 12)),
                    "decay": float(event.get("decay", 0.35)),
                    "seed": float(event.get("seed", 1)),
                })
            elif kind == "effect":
                template = _effect_template(event.get("template", ""), channel_base)
                effect_duration = float(template.get("duration", 0.5))
                for item in template.get("layers", []):
                    layer = json.loads(json.dumps(item))
                    layer["id"] = f"{marker['id']}-{layer['id']}"
                    layer["x"] = float(event.get("x", layer.get("x", 0.5)))
                    layer["y"] = float(event.get("y", layer.get("y", 0.5)))
                    for key in ("width", "height", "scale", "opacity", "rotate"):
                        if key in event:
                            layer[key] = event[key]
                    for key in layer.get("keyframes", []):
                        key["at"] = round(at + float(key.get("at", 0)) * effect_duration / duration, 6)
                    shot.setdefault("layers", []).append(layer)
            else:
                raise ValueError(f"Marker {marker['id']} has unknown event kind: {kind}")
    return episode
