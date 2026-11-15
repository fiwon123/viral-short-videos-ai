"""Resample a layer's keyframes and layer procedural motion on top.

Every load-time motion expander (alive, motion recipes, paths, wiggle, follow,
poses) works the same way: sample the authored pose densely, apply its
modifiers, and write plain linear keys both renderers already understand.
"""

from .design import pose_at, poses

RATE = 24  # Samples per second for composed keys.
PROPS = ("x", "y", "scale", "scale_x", "scale_y", "rotate", "opacity", "skew_x", "skew_y",
         "blur", "tint_opacity", "frame", "visible")


def compose(layer, duration, modifiers):
    """Resample a layer's keys at RATE and apply modifiers.

    Each modifier maps seconds to ``{prop: (op, value)}`` with op ``add``, ``mul`` or
    ``set``; ``scale_xy`` multiplies scale_x and scale_y by a pair.
    """
    points = poses(layer)
    times = {round(i / RATE, 4) for i in range(int(duration * RATE) + 1)} | {round(duration, 4)}
    times |= {round(float(key["at"]) * duration, 4) for key in layer.get("keyframes", [])}
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
        animated |= {prop for prop in PROPS if pose[prop] != first[prop]}
    result = []
    for progress, pose in keys:
        key = {"at": round(progress, 5)}
        for prop in PROPS:
            if prop in animated:
                value = pose[prop]
                key[prop] = round(value, 5) if isinstance(value, float) else value
        result.append(key)
    # Start values become the layer's base pose so the first key matches.
    for prop in animated:
        value = first[prop]
        layer[prop] = round(value, 5) if isinstance(value, float) else value
    layer["keyframes"] = [key for key in result if key["at"] > 0] or result[-1:]
    for key in layer["keyframes"]:
        key["ease"] = "linear"
    return layer
