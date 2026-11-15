"""Inverse kinematics for rigs: key where a hand or foot goes, not each joint.

``ik`` on a rig instance (or any group) lists limbs to solve. Each limb is a
chain of one or two parts: one part aims at the target, two parts bend at the
middle joint like an elbow or knee.

    "ik": [{"chain": ["arm-upper", "arm-lower"], "end": "hand", "bend": 1,
            "keys": [{"t": 0.3, "x": 0.62, "y": 0.40, "d": 0.3, "ease": "smooth"},
                     {"t": 1.2, "layer": "ball"},
                     {"t": 2.0, "release": true, "d": 0.4}]}]

The end effector is the pivot of ``end`` (a part), or ``tip`` (``[x, y]`` in
canvas fractions in the last part's frame, from its pivot), or the last
part's own ``tip`` field (``make character`` writes it for limbs). Targets are
screen fractions before the camera, or the pivot of another ``layer``. A key
blends onto its target over ``d`` seconds; a later target moves the end there
over ``d``; ``release`` blends back to the authored motion. ``bend`` flips
which way the middle joint points.

The solve uses only poses: a child's pivot sits at its parent's pivot plus
the parent chain's rotation, skew and scale applied to ``(x * W, y * H)``.
Sprite sizes cancel out, so Python and the browser agree. The result is
written as ordinary ``rotate`` keys on the chain parts.
"""

import math

from .design import pose_at, poses
from .easing import ease
from .transform import multiply, rotate, scale, skew

LINEAR = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _apply(matrix, x, y):
    a, b, c, d, _, _ = matrix
    return a * x + c * y, b * x + d * y


def _wrap(degrees):
    return (degrees + 180.0) % 360.0 - 180.0


def _angle(vector):
    return math.degrees(math.atan2(vector[1], vector[0]))


class Skeleton:
    """Forward kinematics over a shot's layers, from poses only."""

    def __init__(self, shot, width, height):
        self.width, self.height = width, height
        self.duration = float(shot["duration"])
        self.layers = {layer["id"]: layer for layer in shot.get("layers", [])}
        self.points = {layer_id: poses(layer) for layer_id, layer in self.layers.items()}

    def pose(self, layer_id, seconds):
        return pose_at(self.points[layer_id], max(0.0, min(1.0, seconds / self.duration if self.duration else 0)))

    def world(self, layer_id, seconds, overrides=None):
        """World pivot (pixels) and linear matrix of a layer."""
        layer = self.layers[layer_id]
        pose = dict(self.pose(layer_id, seconds))
        if overrides and layer_id in overrides:
            pose["rotate"] = overrides[layer_id]
        uniform = float(pose.get("scale", 1.0))
        own = multiply(rotate(float(pose.get("rotate", 0.0))),
                       multiply(skew(pose.get("skew_x", 0.0), pose.get("skew_y", 0.0)),
                                scale(float(pose.get("scale_x", uniform)), float(pose.get("scale_y", uniform)))))
        offset = (float(pose["x"]) * self.width, float(pose["y"]) * self.height)
        parent = layer.get("parent")
        if parent and parent in self.layers:
            origin, linear = self.world(parent, seconds, overrides)
            dx, dy = _apply(linear, *offset)
            return (origin[0] + dx, origin[1] + dy), multiply(linear, own)
        return offset, own

    def point(self, layer_id, seconds, local=None, overrides=None):
        """World position of a point given in the layer's frame (canvas fractions from its pivot)."""
        origin, linear = self.world(layer_id, seconds, overrides)
        if not local:
            return origin
        dx, dy = _apply(linear, float(local[0]) * self.width, float(local[1]) * self.height)
        return origin[0] + dx, origin[1] + dy


def _sign(skeleton, part, seconds, effector, overrides):
    """+1 when raising ``part``'s rotate turns the effector clockwise on screen, -1 when mirrored."""
    base = overrides.get(part, skeleton.pose(part, seconds)["rotate"])
    pivot = skeleton.world(part, seconds, overrides)[0]
    before = effector({**overrides, part: base})
    after = effector({**overrides, part: base + 1.0})
    turn = _wrap(_angle((after[0] - pivot[0], after[1] - pivot[1])) - _angle((before[0] - pivot[0], before[1] - pivot[1])))
    return 1.0 if turn >= 0 else -1.0


def solve(skeleton, chain, effector, target, seconds, bend=1):
    """Rotate values for the chain parts that put the effector on ``target``."""
    root = chain[0]
    overrides = {}
    p0 = skeleton.world(root, seconds)[0]
    if len(chain) == 2:
        mid = chain[1]
        pm = skeleton.world(mid, seconds)[0]
        end = effector(overrides)
        upper = math.dist(p0, pm)
        lower = math.dist(pm, end)
        reach = math.dist(p0, target)
        reach = max(abs(upper - lower) + 1e-6, min(upper + lower - 1e-6, reach))
        if upper > 1e-6 and reach > 1e-6:
            cosine = max(-1.0, min(1.0, (upper ** 2 + reach ** 2 - lower ** 2) / (2 * upper * reach)))
            elbow = _angle((target[0] - p0[0], target[1] - p0[1])) + (1 if bend >= 0 else -1) * math.degrees(math.acos(cosine))
            sign = _sign(skeleton, root, seconds, lambda o: skeleton.world(mid, seconds, o)[0], overrides)
            current = skeleton.pose(root, seconds)["rotate"]
            overrides[root] = current + sign * _wrap(elbow - _angle((pm[0] - p0[0], pm[1] - p0[1])))
        pm = skeleton.world(mid, seconds, overrides)[0]
        end = effector(overrides)
        sign = _sign(skeleton, mid, seconds, effector, overrides)
        current = skeleton.pose(mid, seconds)["rotate"]
        overrides[mid] = current + sign * _wrap(_angle((target[0] - pm[0], target[1] - pm[1]))
                                                - _angle((end[0] - pm[0], end[1] - pm[1])))
        return overrides
    end = effector(overrides)
    sign = _sign(skeleton, root, seconds, effector, overrides)
    current = skeleton.pose(root, seconds)["rotate"]
    overrides[root] = current + sign * _wrap(_angle((target[0] - p0[0], target[1] - p0[1]))
                                             - _angle((end[0] - p0[0], end[1] - p0[1])))
    return overrides


def _timeline(spec, skeleton):
    entries = []
    for key in sorted(spec.get("keys", []), key=lambda item: float(item["t"])):
        entry = {"t": float(key["t"]), "d": float(key.get("d", 0.25)), "ease": key.get("ease", "smooth"),
                 "release": bool(key.get("release"))}
        if not entry["release"]:
            if "layer" in key:
                entry["target"] = (lambda layer_id: lambda s: skeleton.world(layer_id, s)[0])(key["layer"])
            else:
                point = (float(key["x"]) * skeleton.width, float(key["y"]) * skeleton.height)
                entry["target"] = (lambda value: lambda s: value)(point)
        entries.append(entry)
    return entries


def _state(entries, seconds):
    """(weight, target) at ``seconds``; target is None when IK is off."""
    weight, target = 0.0, None
    for index, entry in enumerate(entries):
        if seconds < entry["t"]:
            break
        k = 1.0 if entry["d"] <= 0 else min(1.0, (seconds - entry["t"]) / entry["d"])
        k = ease(k, entry["ease"])
        previous_weight, previous_target = weight, target
        if entry["release"]:
            weight = previous_weight * (1 - k)
            target = previous_target
        else:
            here = entry["target"](seconds)
            if previous_target is not None and previous_weight > 0:
                target = (previous_target[0] + (here[0] - previous_target[0]) * k,
                          previous_target[1] + (here[1] - previous_target[1]) * k)
                weight = previous_weight + (1 - previous_weight) * k
            else:
                target, weight = here, k
    return weight, target


def apply(shot, group, width, height, fps=24):
    from .keys import RATE, compose
    specs = group.pop("ik", None)
    if not specs:
        return
    prefix = group["id"] + "/"
    skeleton = Skeleton(shot, width, height)

    def resolve(name):
        for candidate in (prefix + name, name):
            if candidate in skeleton.layers:
                return candidate
        raise ValueError(f"{group['id']}: ik part {name!r} is not in shot {shot['id']}")

    duration = skeleton.duration
    for spec in specs:
        chain = [resolve(name) for name in spec["chain"]]
        if not 1 <= len(chain) <= 2:
            raise ValueError(f"{group['id']}: an ik chain has one or two parts, not {len(chain)}")
        if "end" in spec:
            end_id = resolve(spec["end"])
            effector = (lambda end_id: lambda s, o: skeleton.world(end_id, s, o)[0])(end_id)
        else:
            tip = spec.get("tip") or skeleton.layers[chain[-1]].get("tip")
            if not tip:
                raise ValueError(f"{group['id']}: ik chain {spec['chain']} needs `end` or `tip`")
            effector = (lambda last, tip: lambda s, o: skeleton.point(last, s, tip, o))(chain[-1], tip)
        entries = []
        for key in spec.get("keys", []):
            if "layer" in key:
                key = {**key, "layer": resolve(key["layer"])}
            entries.append(key)
        timeline = _timeline({**spec, "keys": entries}, skeleton)
        cache = {}

        def angles(seconds, chain=chain, effector=effector, timeline=timeline, spec=spec):
            if seconds not in cache:
                weight, target = _state(timeline, seconds)
                result = {}
                if target is not None and weight > 0:
                    solved = solve(skeleton, chain, lambda o: effector(seconds, o), target, seconds,
                                   spec.get("bend", 1))
                    for part, value in solved.items():
                        base = skeleton.pose(part, seconds)["rotate"]
                        result[part] = base + weight * _wrap(value - base)
                cache[seconds] = result
            return cache[seconds]

        for part in chain:
            compose(skeleton.layers[part], duration,
                    [(lambda part: lambda s: ({"rotate": ("set", angles(s)[part])} if part in angles(s) else {}))(part)],
                    rate=min(RATE, float(fps)))


def expand(episode):
    width, height = float(episode.get("width", 1080)), float(episode.get("height", 1920))
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            for layer in list(shot.get("layers", [])):
                if layer.get("ik"):
                    apply(shot, layer, width, height, episode.get("fps", 24))
    return episode
