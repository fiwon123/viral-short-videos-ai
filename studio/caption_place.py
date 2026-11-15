"""Keep kinetic captions off faces and key props.

For every caption cue, estimate where faces are on screen while it shows
(rig parts with role head/eye/mouth, plus any layer marked
``caption_avoid: true``) and pick the first caption band that stays clear:
the configured position first, then the other bands. The choice is stored on
the cue as ``placement`` and used by both renderers, so it never jumps
mid-page.
"""

from .design import pose_at, poses

FACE_ROLES = {"head", "eye", "mouth", "brow"}
BANDS = [("top", 0.0), ("top", 0.06), ("center", -0.12), ("bottom", 0.0), ("bottom", 0.06), ("center", 0.12)]
BASE = {"top": 0.13, "center": 0.5, "bottom": 0.76}


def _boxes(shot, progress):
    """Approximate on-screen boxes (x0, y0, x1, y1 fractions) of protected layers."""
    layers = {layer["id"]: layer for layer in shot.get("layers", [])}
    cache = {}

    def world(layer_id):
        if layer_id in cache:
            return cache[layer_id]
        layer = layers[layer_id]
        pose = pose_at(poses(layer), progress)
        sx = float(pose.get("scale_x", pose.get("scale", 1)))
        sy = float(pose.get("scale_y", pose.get("scale", 1)))
        parent = layer.get("parent")
        if parent in layers:
            px, py, psx, psy, visible = world(parent)
            x, y = px + pose["x"] * psx, py + pose["y"] * psy
            sx, sy = sx * psx, sy * psy
            visible = visible and pose["visible"] and pose["opacity"] > 0.05
        else:
            x, y = pose["x"], pose["y"]
            visible = pose["visible"] and pose["opacity"] > 0.05
        cache[layer_id] = (x, y, sx, sy, visible)
        return cache[layer_id]

    faces = {}
    for layer in shot.get("layers", []):
        protected = layer.get("caption_avoid") or layer.get("role") in FACE_ROLES
        if not protected or "width" not in layer:
            continue
        x, y, sx, sy, visible = world(layer["id"])
        if not visible:
            continue
        pivot = layer.get("pivot", [0.5, 0.5])
        w, h = float(layer["width"]) * abs(sx), float(layer.get("height", layer["width"])) * abs(sy)
        box = (x - pivot[0] * w, y - pivot[1] * h, x + (1 - pivot[0]) * w, y + (1 - pivot[1]) * h)
        # Group a rig's face parts into one box per instance so the gap between eyes counts.
        owner = layer["id"].split("/")[0] if layer.get("role") in FACE_ROLES else layer["id"]
        old = faces.get(owner)
        faces[owner] = box if old is None else (min(old[0], box[0]), min(old[1], box[1]),
                                                max(old[2], box[2]), max(old[3], box[3]))
    return list(faces.values())


def _band(position, offset, font_size):
    centre = BASE[position] + offset
    half = 0.07 * float(font_size)
    return (0.08, centre - half, 0.92, centre + half)


def _overlap(a, b):
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, width) * max(0.0, height)


def place(timeline, episode, config):
    """Annotate kinetic caption cues with a face-free ``placement``."""
    if config.get("style") != "kinetic" or config.get("avoid", True) is False:
        return
    from .captions import settings

    merged = settings(config)
    shots = {shot["id"]: shot for scene in episode["scenes"] for shot in scene["shots"]}
    spans = [(item["start"], item["end"], shots.get(item["id"]))
             for scene in timeline["scenes"] for item in scene["shots"]]
    preferred = (merged["position"], float(merged.get("offset", 0)))
    order = [preferred] + [band for band in BANDS if band != preferred]
    for cue in timeline["captions"]:
        span = next(((start, end, shot) for start, end, shot in spans if start <= cue["start"] < end), None)
        if not span or not span[2]:
            continue
        start, end, shot = span
        frames = max(1, end - start - 1)
        moments = [min(1.0, max(0.0, (frame - start) / frames))
                   for frame in (cue["start"], (cue["start"] + cue["end"]) // 2, cue["end"] - 1)]
        faces = [box for moment in moments for box in _boxes(shot, moment)]
        if not faces:
            continue
        best, score = preferred, None
        for position, offset in order:
            band = _band(position, offset, merged["font_size"])
            if (position, offset) != preferred and (band[1] < 0.06 or band[3] > 0.9):
                continue
            hit = sum(_overlap(band, face) for face in faces)
            if score is None or hit < score - 1e-9:
                best, score = (position, offset), hit
            if hit == 0:
                break
        if best != preferred:
            cue["placement"] = {"position": best[0], "offset": best[1]}
