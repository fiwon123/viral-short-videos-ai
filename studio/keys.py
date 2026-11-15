"""Resample a layer's keyframes and layer procedural motion on top.

Every load-time motion expander (alive, motion recipes, paths, wiggle, follow,
poses) works the same way: sample the authored pose densely, apply its
modifiers, and write plain linear keys both renderers already understand.
"""

from .design import pose_at, poses

RATE = 24  # Samples per second for composed keys.
PROPS = ("x", "y", "scale", "scale_x", "scale_y", "rotate", "opacity", "skew_x", "skew_y",
         "blur", "tint_opacity", "frame", "visible", "z", "wipe", "tint_color", "turn_x", "turn_y")


def compose(layer, duration, modifiers, rate=RATE):
    """Resample a layer's keys at ``rate`` (default RATE) and apply modifiers.

    Each modifier maps seconds to ``{prop: (op, value)}`` with op ``add``, ``mul`` or
    ``set``; ``scale_xy`` multiplies scale_x and scale_y by a pair.
    """
    points = poses(layer)
    authored = {round(float(key["at"]) * duration, 4) for key in layer.get("keyframes", [])} | {round(duration, 4)}
    # Grid samples that crowd an authored key would make a sub-frame pair; the key itself is kept.
    times = {seconds for seconds in (round(i / rate, 4) for i in range(int(duration * rate) + 1))
             if seconds == 0 or all(abs(seconds - key) >= 0.9 / rate for key in authored)} | authored
    keys, changed = [], set()
    for seconds in sorted(times):
        progress = min(1.0, seconds / duration) if duration else 0.0
        pose = dict(pose_at(points, progress))
        for modifier in modifiers:
            for prop, (op, value) in modifier(seconds).items():
                if prop == "scale_xy":
                    pose["scale_x"] *= value[0]
                    pose["scale_y"] *= value[1]
                    changed |= {"scale_x", "scale_y"}
                    continue
                if op == "mul":
                    pose[prop] = pose[prop] * value
                elif op == "set":
                    pose[prop] = value
                else:
                    pose[prop] = pose[prop] + value
                changed.add(prop)
        keys.append((progress, pose))
    animated = set(changed)
    first = keys[0][1]
    for _, pose in keys:
        animated |= {prop for prop in PROPS if prop in pose and pose[prop] != first[prop]}
    result = []
    for progress, pose in keys:
        key = {"at": round(progress, 5)}
        for prop in PROPS:
            if prop in animated and prop in pose:
                value = pose[prop]
                if prop == "tint_color":
                    value = "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in value)
                key[prop] = round(value, 5) if isinstance(value, float) else value
        result.append(key)
    # Start values become the layer's base pose so the first key matches.
    for prop in animated:
        value = first[prop]
        if prop == "tint_color":
            value = "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in value)
        layer[prop] = round(value, 5) if isinstance(value, float) else value
    layer["keyframes"] = [key for key in result if key["at"] > 0] or result[-1:]
    for key in layer["keyframes"]:
        key["ease"] = "linear"
    return layer
