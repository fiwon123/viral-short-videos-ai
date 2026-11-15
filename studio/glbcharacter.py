"""Generate a rigged low-poly 3D character as a GLB, locally and for free.

    python -m studio.glbcharacter OUT.glb [--spec spec.json]

The model is about 1.7 units tall, faces +z, and has these bones (pose them
with object ``bones`` keys and ``three.ik``):

    Hips > Spine > Head
    Spine > UpperArm.L > LowerArm.L > Hand.L      (and .R)
    Hips > UpperLeg.L > LowerLeg.L > Foot.L        (and .R)

Every body part is a flat-shaded block skinned to one bone, so it bends at the
joints like a toy figure. The spec sets colours and proportions::

    {"skin": "#F2C7A5", "shirt": "#4C7BD9", "pants": "#2E3A59", "shoes": "#1A1638",
     "hair": "#3B2A20", "height": 1.7, "build": 1.0, "head": 1.0}
"""

import argparse
import json
import math
from pathlib import Path
import struct

DEFAULTS = {"skin": "#F2C7A5", "shirt": "#4C7BD9", "pants": "#2E3A59", "shoes": "#1A1638", "hair": "#3B2A20",
            "eyes": "#1A1638", "height": 1.7, "build": 1.0, "head": 1.0}


def _rgb(colour):
    colour = colour.lstrip("#")
    return [int(colour[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _linear(rgb):
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _norm(v):
    length = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / length for c in v]


def skeleton(spec):
    """Bone name -> (parent, rest position relative to parent), and world positions."""
    h = float(spec["height"]) / 1.7
    w = float(spec["build"])
    bones = {
        "Hips": (None, [0, 0.92 * h, 0]),
        "Spine": ("Hips", [0, 0.12 * h, 0]),
        "Head": ("Spine", [0, 0.5 * h, 0]),
    }
    for side, sign in (("L", 1), ("R", -1)):
        bones[f"UpperArm.{side}"] = ("Spine", [sign * 0.22 * w * h, 0.42 * h, 0])
        bones[f"LowerArm.{side}"] = (f"UpperArm.{side}", [0, -0.28 * h, 0])
        bones[f"Hand.{side}"] = (f"LowerArm.{side}", [0, -0.26 * h, 0])
        bones[f"UpperLeg.{side}"] = ("Hips", [sign * 0.1 * w * h, -0.04 * h, 0])
        bones[f"LowerLeg.{side}"] = (f"UpperLeg.{side}", [0, -0.42 * h, 0])
        bones[f"Foot.{side}"] = (f"LowerLeg.{side}", [0, -0.42 * h, 0])
    world = {}
    for name, (parent, offset) in bones.items():
        base = world[parent] if parent else [0, 0, 0]
        world[name] = [base[i] + offset[i] for i in range(3)]
    return bones, world


def _box(start, end, half_x, half_z, colour, joint, out):
    """A block from ``start`` to ``end`` with flat normals, skinned to ``joint``."""
    axis = _sub(end, start)
    up = [0, 0, 1] if abs(axis[1]) > abs(axis[2]) else [0, 1, 0]
    side = _norm(_cross(axis, up))
    front = _norm(_cross(side, axis))
    corners = []
    for t in (0, 1):
        for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            base = start if t == 0 else end
            corners.append([base[i] + side[i] * a * half_x + front[i] * b * half_z for i in range(3)])
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    _faces(corners, faces, colour, joint, out)


def _faces(corners, faces, colour, joint, out):
    for quad in faces:
        a, b, c, d = (corners[i] for i in quad)
        normal = _norm(_cross(_sub(b, a), _sub(c, a)))
        centre = [sum(p[i] for p in (a, b, c, d)) / 4 for i in range(3)]
        mid = [sum(p[i] for p in corners) / len(corners) for i in range(3)]
        if sum(normal[i] * (centre[i] - mid[i]) for i in range(3)) < 0:  # Keep normals pointing outward.
            a, b, c, d = d, c, b, a
            normal = [-n for n in normal]
        for tri in ((a, b, c), (a, c, d)):
            for point in tri:
                out["position"].append(point)
                out["normal"].append(normal)
                out["color"].append(colour)
                out["joint"].append(joint)


def _ball(centre, radius, colour, joint, out, rings=6, segments=10, squash=(1, 1, 1), top=None):
    points = [[[centre[0] + radius * squash[0] * math.sin(math.pi * r / rings) * math.cos(2 * math.pi * s / segments),
                centre[1] + radius * squash[1] * math.cos(math.pi * r / rings),
                centre[2] + radius * squash[2] * math.sin(math.pi * r / rings) * math.sin(2 * math.pi * s / segments)]
               for s in range(segments)] for r in range(rings + 1)]
    flat = [p for ring in points for p in ring]
    faces = []
    for r in range(top or rings):  # ``top`` rings only: a cap instead of a whole ball.
        for s in range(segments):
            n = (s + 1) % segments
            faces.append((r * segments + s, r * segments + n, (r + 1) * segments + n, (r + 1) * segments + s))
    for quad in faces:
        a, b, c, d = (flat[i] for i in quad)
        normal = _norm(_cross(_sub(c, a), _sub(b, a)))
        outward = _norm(_sub([sum(p[i] for p in (a, b, c, d)) / 4 for i in range(3)], centre))
        if sum(normal[i] * outward[i] for i in range(3)) < 0:
            a, b, c, d = d, c, b, a
            normal = [-x for x in normal]
        for tri in ((a, b, c), (a, c, d)):
            for point in tri:
                out["position"].append(point)
                out["normal"].append(normal)
                out["color"].append(colour)
                out["joint"].append(joint)


def build(spec=None):
    spec = {**DEFAULTS, **(spec or {})}
    bones, world = skeleton(spec)
    names = list(bones)
    index = {name: i for i, name in enumerate(names)}
    colours = {key: _linear(_rgb(spec[key])) for key in ("skin", "shirt", "pants", "shoes", "hair", "eyes")}
    h, w = float(spec["height"]) / 1.7, float(spec["build"])
    out = {"position": [], "normal": [], "color": [], "joint": []}
    _box(world["Hips"], world["Spine"], 0.17 * w * h, 0.11 * h, colours["pants"], index["Hips"], out)
    _box(world["Spine"], [world["Spine"][0], world["Spine"][1] + 0.46 * h, 0], 0.19 * w * h, 0.12 * h,
         colours["shirt"], index["Spine"], out)
    head_r = 0.13 * h * float(spec["head"])
    head_c = [world["Head"][0], world["Head"][1] + head_r * 1.05, 0]
    _ball(head_c, head_r, colours["skin"], index["Head"], out)
    # Hair: the upper rings of a slightly larger ball, set back so the face stays clear.
    _ball([head_c[0], head_c[1] + head_r * 0.08, head_c[2] - head_r * 0.12], head_r * 1.08, colours["hair"],
          index["Head"], out, rings=8, segments=12, top=4)
    for sign in (-1, 1):
        _ball([head_c[0] + sign * head_r * 0.38, head_c[1] + head_r * 0.05, head_c[2] + head_r * 0.9],
              head_r * 0.13, colours["eyes"], index["Head"], out, rings=4, segments=6)
    for side in ("L", "R"):
        _box(world[f"UpperArm.{side}"], world[f"LowerArm.{side}"], 0.055 * h, 0.055 * h, colours["shirt"],
             index[f"UpperArm.{side}"], out)
        _box(world[f"LowerArm.{side}"], world[f"Hand.{side}"], 0.045 * h, 0.045 * h, colours["skin"],
             index[f"LowerArm.{side}"], out)
        _ball([world[f"Hand.{side}"][0], world[f"Hand.{side}"][1] - 0.05 * h, 0], 0.055 * h, colours["skin"],
              index[f"Hand.{side}"], out, rings=4, segments=8)
        _box(world[f"UpperLeg.{side}"], world[f"LowerLeg.{side}"], 0.075 * h, 0.075 * h, colours["pants"],
             index[f"UpperLeg.{side}"], out)
        _box(world[f"LowerLeg.{side}"], world[f"Foot.{side}"], 0.065 * h, 0.065 * h, colours["pants"],
             index[f"LowerLeg.{side}"], out)
        foot = world[f"Foot.{side}"]
        _box([foot[0], foot[1], foot[2] - 0.04 * h], [foot[0], foot[1], foot[2] + 0.16 * h], 0.065 * h, 0.035 * h,
             colours["shoes"], index[f"Foot.{side}"], out)
    return names, bones, world, out


def write_glb(path, spec=None):
    names, bones, world, out = build(spec)
    count = len(out["position"])
    blob = b""

    def add(data, fmt):
        nonlocal blob
        offset = len(blob)
        packed = b"".join(struct.pack(fmt, *item) if isinstance(item, (list, tuple)) else struct.pack(fmt, item)
                          for item in data)
        blob += packed + b"\0" * (-len(packed) % 4)
        return offset, len(packed)

    views, accessors = [], []

    def accessor(data, fmt, kind, component, extra=None):
        offset, length = add(data, fmt)
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": length})
        accessors.append({"bufferView": len(views) - 1, "componentType": component, "count": len(data),
                          "type": kind, **(extra or {})})
        return len(accessors) - 1

    xs = [p for p in out["position"]]
    position = accessor(out["position"], "<3f", "VEC3", 5126,
                        {"min": [min(p[i] for p in xs) for i in range(3)], "max": [max(p[i] for p in xs) for i in range(3)]})
    normal = accessor(out["normal"], "<3f", "VEC3", 5126)
    colour = accessor(out["color"], "<3f", "VEC3", 5126)
    joints = accessor([[j, 0, 0, 0] for j in out["joint"]], "<4H", "VEC4", 5123)
    weights = accessor([[1.0, 0.0, 0.0, 0.0]] * count, "<4f", "VEC4", 5126)
    inverse = accessor([[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -world[n][0], -world[n][1], -world[n][2], 1]
                        for n in names], "<16f", "MAT4", 5126)
    nodes = [{"name": "Character", "children": [1, 2]},
             {"name": "Body", "mesh": 0, "skin": 0}]
    first_bone = len(nodes)
    for name in names:
        parent, offset = bones[name]
        node = {"name": name, "translation": offset}
        children = [first_bone + i for i, other in enumerate(names) if bones[other][0] == name]
        if children:
            node["children"] = children
        nodes.append(node)
    model = {
        "asset": {"version": "2.0", "generator": "viral-short-videos glbcharacter"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes,
        "meshes": [{"name": "Body", "primitives": [{"attributes": {"POSITION": position, "NORMAL": normal,
                                                                    "COLOR_0": colour, "JOINTS_0": joints,
                                                                    "WEIGHTS_0": weights}, "material": 0}]}],
        "materials": [{"name": "Toy", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0,
                                                               "roughnessFactor": 0.7}}],
        "skins": [{"joints": [first_bone + i for i in range(len(names))], "inverseBindMatrices": inverse,
                   "skeleton": first_bone}],
        "buffers": [{"byteLength": len(blob)}], "bufferViews": views, "accessors": accessors,
    }
    text = json.dumps(model, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    body = struct.pack("<I4s", len(text), b"JSON") + text + struct.pack("<I4s", len(blob), b"BIN\0") + blob
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
    return {"glb": str(path), "bones": names, "vertices": count, "height": float({**DEFAULTS, **(spec or {})}["height"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--spec", type=Path, help="JSON with colours and proportions")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8")) if args.spec else {}
    print(json.dumps(write_glb(args.out, spec), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
