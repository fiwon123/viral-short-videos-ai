"""Expand deterministic 2D particle emitters into ordinary layers.

The renderers already know how to draw image/SVG layers with keyframes, so a
particle system is resolved once at load time instead of being implemented
twice. This keeps Python and browser output identical for the same seed.
"""

import math
import random


def _clamp(value, low, high):
    return max(low, min(high, value))


def expand(episode):
    fps = int(episode.get("fps", 24))
    rate = max(12, fps)
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            duration = float(shot.get("duration", 1))
            layers = []
            for index, layer in enumerate(shot.get("layers", [])):
                if layer.get("kind") != "particles":
                    layers.append(layer)
                    continue
                count = int(layer.get("count") or max(1, round(float(layer.get("rate", 30)) * duration)))
                life = float(layer.get("life", 1.2))
                seed = int(layer.get("seed", 17)) + index * 101
                rng = random.Random(seed)
                file = layer["file"]
                kind = "svg" if str(file).lower().endswith(".svg") else "image"
                speed_min, speed_max = (layer.get("velocity") or [0.2, 1.6])[:2]
                gx, gy = (layer.get("gravity") or [0, -2.4])[:2]
                area = layer.get("area") or [0.2, 0.2]
                size_range = layer.get("size") or [0.02, 0.05]
                spread = float(layer.get("spread", 0.8))
                for index in range(min(300, count)):
                    start = rng.uniform(0, max(0, duration - life))
                    lifespan = rng.uniform(life * 0.65, life)
                    x0 = float(layer["x"]) + rng.uniform(-area[0] / 2, area[0] / 2)
                    y0 = float(layer["y"]) + rng.uniform(-area[1] / 2, area[1] / 2)
                    speed = rng.uniform(speed_min, speed_max)
                    angle = rng.uniform(-spread, spread) * math.pi / 2
                    vx = speed * math.sin(angle)
                    vy = -speed * math.cos(angle)
                    size = rng.uniform(size_range[0], size_range[-1])
                    base_rotate = rng.uniform(-180, 180)
                    keys = []
                    samples = max(6, int(lifespan * rate))
                    for step in range(samples + 1):
                        local = lifespan * step / samples
                        x = x0 + vx * local + 0.5 * gx * local * local
                        y = y0 + vy * local + 0.5 * gy * local * local
                        at = _clamp((start + local) / max(duration, 1e-6), 0, 1)
                        opacity = (1 - step / samples) ** 1.5 * float(layer.get("opacity", 1))
                        keys.append({"at": round(at, 6), "x": round(x, 6), "y": round(y, 6),
                                     "opacity": round(opacity, 6),
                                     "rotate": round(base_rotate + local * 120, 4)})
                    layers.append({
                        "id": f"{layer['id']}-p{index}",
                        "kind": kind,
                        "file": file,
                        "asset_scope": layer.get("asset_scope", "episode"),
                        "plane": layer.get("plane", "foreground"),
                        "x": x0,
                        "y": y0,
                        "width": size,
                        "height": size,
                        "blend": layer.get("blend", "normal"),
                        "opacity": layer.get("opacity", 1),
                        "keyframes": keys,
                    })
            shot["layers"] = layers
    return episode
