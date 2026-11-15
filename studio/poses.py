"""Named poses for rigs: act with a few keys instead of animating every part.

A pose lists part overrides relative to the rig's rest pose, plus an optional
mouth expression. Poses live in the channel rig library (``poses.<rig>``) or
in the episode (``poses.<rig>``); ``make character`` writes a starter set.

    "pose_keys": [{"t": 0.4, "pose": "wave", "d": 0.25, "ease": "back"},
                  {"t": 1.6, "pose": "idle"}]

Parts not named in the current pose blend back to rest. Mouth expressions
toggle the rig's mouth layers; the talk swap from ``alive`` still opens the
mouth while the character speaks.
"""

from .design import pose_at, poses as layer_points
from .easing import ease
from .keys import compose


def _blend(keys, base_value, duration):
    """Value over time for one prop, blending between pose targets."""
    def value_at(t):
        current = None
        for index, key in enumerate(keys):
            if t < key["t"]:
                break
            current = index
        if current is None:
            return base_value(t)
        key = keys[current]
        start = value_at(key["t"] - 1e-6) if current or key["t"] > 0 else base_value(0)
        target = key["value"] if key["value"] is not None else base_value(t)
        k = 1.0 if key["d"] <= 0 else min(1.0, (t - key["t"]) / key["d"])
        return start + (target - start) * ease(k, key["ease"])
    return value_at


def apply(shot, group, library):
    rig = group.get("rig")
    keys = group.pop("pose_keys", None)
    if not keys:
        return
    available = library.get(rig, {})
    duration = float(shot["duration"])
    prefix = group["id"] + "/"
    members = {item["id"][len(prefix):]: item for item in shot["layers"] if item["id"].startswith(prefix)}
    timeline = []
    for key in sorted(keys, key=lambda item: float(item["t"])):
        name = key["pose"]
        if name not in available and name not in {"idle", "rest"}:
            raise ValueError(f"{group['id']}: unknown pose {name} for rig {rig}. "
                             f"Available: {', '.join(sorted(available)) or 'none'}")
        timeline.append({"t": float(key["t"]), "d": float(key.get("d", 0.25)), "ease": key.get("ease", "smooth"),
                         "pose": available.get(name, {})})
    touched = {}
    for entry in timeline:
        for part, props in entry["pose"].items():
            if part == "mouth":
                continue
            for prop in props:
                touched.setdefault(part, set()).add(prop)
    for part, props in touched.items():
        layer = members.get(part)
        if layer is None:
            continue
        points = layer_points(layer)
        modifiers = []
        for prop in props:
            base = (lambda p: lambda t: pose_at(points, max(0.0, min(1.0, t / duration)))[p])(prop)
            track = [{"t": e["t"], "d": e["d"], "ease": e["ease"],
                      "value": e["pose"].get(part, {}).get(prop)} for e in timeline]
            value = _blend(track, base, duration)
            modifiers.append((lambda p, v: lambda t: {p: ("set", v(t))})(prop, value))
        compose(layer, duration, modifiers)
    if any("mouth" in entry["pose"] for entry in timeline):
        mouths = {item.get("mouth_shape"): item for item in members.values() if item.get("role") == "mouth"}
        for shape, layer in mouths.items():
            def visible(t, shape=shape):
                chosen = "rest"
                for entry in timeline:
                    if t >= entry["t"]:
                        chosen = entry["pose"].get("mouth", "rest")
                return chosen == shape
            # Talk-only open mouths keep their own visibility rule.
            if layer.get("talk_only"):
                continue
            compose(layer, duration, [lambda t, visible=visible: {"visible": ("set", visible(t))}])
            layer.pop("variant_group", None)


def expand(episode, rig_poses=None):
    library = {}
    for source in (rig_poses or {}, episode.get("poses") or {}):
        for rig, entries in source.items():
            library.setdefault(rig, {}).update(entries)
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            for layer in list(shot.get("layers", [])):
                if "pose_keys" in layer:
                    apply(shot, layer, library)
    return episode
