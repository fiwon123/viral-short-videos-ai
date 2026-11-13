"""Import measured word timings into speech lines.

Alignment tools differ, so the studio accepts a small stable JSON shape:

    {"lines": [{"shot": "A", "index": 0,
                "words": [{"text": "Small", "start": 0.0, "end": 0.18}]}]}

The audio planner uses these timings when present and falls back to the
proportional estimator otherwise.
"""

import json
from pathlib import Path


def apply(episode, payload):
    shots = {
        shot["id"]: shot
        for scene in episode.get("scenes", [])
        for shot in scene.get("shots", [])
    }
    for entry in payload.get("lines", []):
        shot = shots.get(entry.get("shot"))
        if shot is None:
            raise ValueError(f"Alignment references unknown shot: {entry.get('shot')}")
        lines = shot.get("speech", [])
        index = int(entry.get("index", 0))
        if index >= len(lines):
            raise ValueError(f"Alignment line index {index} is out of range in {shot['id']}")
        words = entry.get("words") or []
        times = [float(word["start"]) for word in words]
        if times != sorted(times):
            raise ValueError(f"Alignment words must be sorted in {shot['id']}")
        lines[index]["words"] = words
        if "visemes" in entry:
            lines[index]["visemes"] = entry["visemes"]
    return episode


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
