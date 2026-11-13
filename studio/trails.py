"""Expand a declarative trail into ordinary delayed layers.

The renderers already draw transformed layers, so an echo is cheaper and more
predictable as a load-time expansion than a new compositor feature. Each copy
shows the same animation a little later, with lower opacity and optional scale
falloff.
"""

import copy


def _shift(key, delay):
    shifted = copy.deepcopy(key)
    shifted["at"] = round(min(1.0, max(0.0, float(key["at"]) + delay)), 6)
    return shifted


def _scale(key, factor, base_scale):
    if "scale" in key:
        key["scale"] = round(float(key["scale"]) * factor, 6)
    if "scale_x" in key:
        key["scale_x"] = round(float(key["scale_x"]) * factor, 6)
    if "scale_y" in key:
        key["scale_y"] = round(float(key["scale_y"]) * factor, 6)
    if "scale" not in key and "scale_x" not in key and "scale_y" not in key:
        key["scale_x"] = round(base_scale * factor, 6)
        key["scale_y"] = round(base_scale * factor, 6)


def _opacity(key, factor, base_opacity):
    key["opacity"] = round(float(key.get("opacity", base_opacity)) * factor, 6)


def echo(layer, index, spec):
    copy_layer = copy.deepcopy(layer)
    copy_layer.pop("trail", None)
    copy_layer["id"] = f"{layer['id']}-trail-{index}"
    copy_layer["parent"] = layer.get("parent")
    copy_layer["blend"] = spec.get("blend", layer.get("blend", "normal"))
    opacity = max(0.05, float(spec.get("opacity", 0.55)) ** index)
    falloff = max(0.05, float(spec.get("scale_falloff", 1.0)) ** index)
    base_scale = float(layer.get("scale", layer.get("scale_x", 1)))
    base_opacity = float(layer.get("opacity", 1))
    delay = float(spec.get("spacing", 0.06)) * index
    original = layer.get("keyframes", [])
    keys = []
    if original:
        first = copy.deepcopy(original[0])
        first["at"] = 0
        keys.append(first)
        for key in original:
            keys.append(_shift(key, delay))
        keys = {round(key["at"], 6): key for key in keys}
        keys = [keys[moment] for moment in sorted(keys)]
    for key in keys:
        _scale(key, falloff, base_scale)
        _opacity(key, opacity, base_opacity)
    copy_layer["keyframes"] = keys
    copy_layer["opacity"] = round(base_opacity * opacity, 6)
    if not keys:
        copy_layer["scale_x"] = round(base_scale * falloff, 6)
        copy_layer["scale_y"] = round(base_scale * falloff, 6)
    return copy_layer


def expand(episode):
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            layers = []
            for layer in shot.get("layers", []):
                spec = layer.get("trail")
                if not spec or layer.get("kind") in {"particles", "group"}:
                    layers.append(layer)
                    continue
                count = int(spec.get("count", 3))
                for index in range(count, 0, -1):
                    layers.append(echo(layer, index, spec))
                layers.append(layer)
            shot["layers"] = layers
    return episode
