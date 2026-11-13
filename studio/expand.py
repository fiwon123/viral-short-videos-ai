"""Expand reusable layer groups declared in ``episode.defs``.

A ``use`` layer is replaced by a transform group plus prefixed copies of the
definition's layers. Local parent links, mask sources and variant groups are
rewritten so several instances can share one shot without collisions.
"""

import copy


def _prefix(instance, value):
    if value is None:
        return instance
    return f"{instance}/{value}"


def _clone(source, instance, local_ids, plane):
    layer = copy.deepcopy(source)
    local = layer["id"]
    layer["id"] = _prefix(instance, local)
    layer["plane"] = plane
    parent = layer.get("parent")
    layer["parent"] = _prefix(instance, parent) if parent in local_ids else instance
    if "mask" in layer and str(layer["mask"].get("source", "")).startswith("layer:"):
        target = layer["mask"]["source"].split(":", 1)[1]
        if target in local_ids:
            layer["mask"]["source"] = "layer:" + _prefix(instance, target)
    if "variant_group" in layer:
        layer["variant_group"] = _prefix(instance, layer["variant_group"])
    return layer


def expand(episode, channel_rigs=None):
    definitions = {**(channel_rigs or {}), **(episode.get("defs") or {})}
    if not definitions:
        return episode
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            layers = []
            for layer in shot.get("layers", []):
                if layer.get("kind") != "use":
                    layers.append(layer)
                    continue
                name = layer.get("ref")
                if name not in definitions:
                    available = ", ".join(sorted(definitions)) or "none"
                    raise ValueError(f"Unknown layer definition: {name}. Available: {available}")
                source_layers = definitions[name]
                local_ids = {item["id"] for item in source_layers}
                if any(item.get("kind") == "use" for item in source_layers):
                    raise ValueError(f"Layer definition {name} cannot contain another use")
                group = copy.deepcopy(layer)
                group.pop("ref", None)
                group["kind"] = "group"
                group["plane"] = layer.get("plane", "foreground")
                layers.append(group)
                for source in source_layers:
                    layers.append(_clone(source, layer["id"], local_ids, group["plane"]))
            shot["layers"] = layers
    return episode
