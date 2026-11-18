"""Make a generated head act: lift the eyes onto their own layers and swap the mouth for a lip-sync set.

Generated art has the face painted into the head. ``lift_face`` finds the skin
colour and the feature blobs inside the head outline, then:

* eyes: the pixels around each eye become ``eye-l``/``eye-r`` layers (role ``eye``),
  and the head under them is filled with skin, so ``alive`` blinks reveal eyelid
  skin instead of a second pair of eyes;
* mouth: the painted mouth is filled with skin, and ``mouth_layers`` adds the
  13-shape vector mouth set from ``studio/character.py`` (rest, open, wide, o,
  smile, frown, flat and the visemes) in the art's line colour, so
  ``alive: {"talk": speaker}`` lip-syncs.

Detection looks for the eyes as a pair of blobs in the upper middle of the face
and the mouth as the blob nearest the lower centre. Override with boxes in
fractions of the head's bounds, or turn it off::

    "face": {"eyes": [[0.25, 0.35, 0.45, 0.55], [0.55, 0.35, 0.75, 0.55]], "mouth": [0.35, 0.65, 0.65, 0.85]}
    "face": false
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .depthphoto import push_pull


def _components(mask, min_area):
    """Connected blobs of ``mask`` (bool arrays), largest first, ignoring ones under ``min_area``."""
    work = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L").copy()
    found = []
    for _ in range(400):
        remaining = np.asarray(work) == 255
        points = np.argwhere(remaining)
        if not points.size:
            break
        y, x = points[0]
        ImageDraw.floodfill(work, (int(x), int(y)), 128, thresh=0)
        blob = np.asarray(work) == 128
        work.paste(0, mask=Image.fromarray(np.where(blob, 255, 0).astype(np.uint8), "L"))
        if blob.sum() >= min_area:
            found.append(blob)
    return sorted(found, key=lambda blob: -blob.sum())


def _box(blob):
    ys, xs = np.nonzero(blob)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def _nearest(blobs, target, limit):
    best, best_distance = None, limit
    for blob in blobs:
        ys, xs = np.nonzero(blob)
        distance = np.hypot(xs.mean() - target[0], ys.mean() - target[1])
        if distance < best_distance:
            best, best_distance = blob, distance
    return best


def find_face(rgb, head, override=None):
    """Eye boxes, mouth box (pixel ``[x0, y0, x1, y1]``), skin and line colours for a head mask."""
    ys, xs = np.nonzero(head)
    hx0, hy0, hx1, hy1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    hw, hh = hx1 - hx0, hy1 - hy0
    size = max(3, int(hw * 0.08) | 1)
    interior = np.asarray(Image.fromarray(np.where(head, 255, 0).astype(np.uint8), "L")
                          .filter(ImageFilter.MinFilter(size))) > 127
    face_rows = np.zeros_like(head)
    face_rows[hy0 + int(hh * 0.45):hy0 + int(hh * 0.85)] = True
    sample = rgb[interior & face_rows] if (interior & face_rows).any() else rgb[interior]
    if not sample.size:
        return None
    skin = np.median(sample, axis=0)
    luminance = rgb[head].mean(axis=1)
    line = np.median(rgb[head][luminance <= np.percentile(luminance, 3)], axis=0)
    result = {"skin": "#" + "".join(f"{int(v):02X}" for v in skin),
              "line": "#" + "".join(f"{int(v):02X}" for v in line), "head_box": [int(hx0), int(hy0), int(hx1), int(hy1)]}

    def absolute(box):
        return [int(hx0 + box[0] * hw), int(hy0 + box[1] * hh), int(hx0 + box[2] * hw), int(hy0 + box[3] * hh)]
    if override:
        result["eyes"] = [absolute(box) for box in override.get("eyes", [])] or None
        result["mouth"] = absolute(override["mouth"]) if override.get("mouth") else None
        return result
    # Features are dark (lines, pupils, mouths) or near-white (eye whites, teeth); lighter or tinted
    # paint such as a belly patch or blush differs from the skin too but is not a feature.
    darker = rgb.mean(axis=2) < skin.mean() - 50
    whiteish = (rgb.min(axis=2) > 190) & (rgb.max(axis=2) - rgb.min(axis=2) < 60)
    feature = interior & (np.sqrt(((rgb - skin) ** 2).sum(axis=2)) > 60) & (darker | whiteish)
    cx = (hx0 + hx1) / 2
    blobs = _components(feature, max(4, int(head.sum() * 0.0008)))
    small = [blob for blob in blobs if blob.sum() <= head.sum() * 0.08]
    eyes = []
    for side in (-1, 1):
        target = (cx + side * hw * 0.2, hy0 + hh * 0.48)
        candidates = [blob for blob in small if (np.nonzero(blob)[1].mean() - cx) * side > hw * 0.04
                      and hy0 + hh * 0.22 <= np.nonzero(blob)[0].mean() <= hy0 + hh * 0.7]
        eye = _nearest(candidates, target, hw * 0.35)
        if eye is not None:
            eyes.append(eye)
    if len(eyes) == 2 and abs(np.nonzero(eyes[0])[0].mean() - np.nonzero(eyes[1])[0].mean()) < hh * 0.12:
        result["eyes"] = [_box(eye) for eye in eyes]
    else:
        result["eyes"] = None
    taken = [id(eye) for eye in eyes] if result["eyes"] else []
    candidates = [blob for blob in small if id(blob) not in taken
                  and np.nonzero(blob)[0].mean() >= hy0 + hh * 0.58 and abs(np.nonzero(blob)[1].mean() - cx) < hw * 0.3]
    mouth = _nearest(candidates, (cx, hy0 + hh * 0.78), hh * 0.3)
    result["mouth"] = _box(mouth) if mouth is not None else None
    return result


def _grow(box, amount, limit):
    x0, y0, x1, y1 = box
    dx, dy = (x1 - x0) * amount, (y1 - y0) * amount
    return [max(0, int(x0 - dx)), max(0, int(y0 - dy)), min(limit[1], int(x1 + dx) + 1), min(limit[0], int(y1 + dy) + 1)]


def face_part(masks):
    """The part that carries the face: the head, or the body of a character without one (a blob)."""
    return "head" if "head" in masks and masks["head"].any() else "body"


def lift_face(cutout, masks, override=None):
    """Return ``{"masks", "sources", "eyes", "mouth", "skin", "line", "part"}`` or None when no face is found."""
    rgba = np.asarray(cutout.convert("RGBA"))
    rgb = rgba[..., :3].astype(np.float64)
    part = face_part(masks)
    head = masks[part]
    region = head
    if part == "body":
        # A blob's face sits in the upper body; search the top three quarters as if it were a head,
        # starting where the body is wide (an antenna or a tuft on top is not part of the face).
        widths = head.sum(axis=1)
        rows = np.flatnonzero(widths >= widths.max() * 0.4)
        top, bottom = rows.min(), np.nonzero(head)[0].max()
        region = head.copy()
        region[:top] = False
        region[top + int((bottom - top) * 0.75):] = False
    face = find_face(rgb, region, override)
    if not face or not (face.get("eyes") or face.get("mouth")):
        return None
    hole = np.zeros_like(head)
    new_masks, feathered = {}, {}
    for name, box in zip(("eye-l", "eye-r"), sorted(face.get("eyes") or [], key=lambda box: box[0])):
        # An ellipse, not the box: its edge falls on skin, where the eye layer and the filled head
        # underneath match, so no rectangle shows around the eye.
        x0, y0, x1, y1 = _grow(box, 0.22, head.shape)
        shape = Image.new("L", (head.shape[1], head.shape[0]), 0)
        ImageDraw.Draw(shape).ellipse([x0, y0, x1 - 1, y1 - 1], fill=255)
        region = np.asarray(shape) > 127
        new_masks[name] = region & head
        # Feather the eye layer so it fades into the fill instead of showing a seam.
        soft = max(1.0, (x1 - x0) * 0.08)
        fade = np.asarray(shape.filter(ImageFilter.MinFilter(int(soft * 2) | 1))
                          .filter(ImageFilter.GaussianBlur(soft)), dtype=np.float64) / 255
        eye = rgba.copy()
        eye[..., 3] = (eye[..., 3] * fade).astype(np.uint8)
        feathered[name] = Image.fromarray(eye, "RGBA")
        hole |= region
    if face.get("mouth"):
        x0, y0, x1, y1 = _grow(face["mouth"], 0.3, head.shape)
        hole[y0:y1, x0:x1] = True
    hole &= head
    # Fill the holes from the surrounding head pixels so a blink or a new mouth shows skin.
    # Sample the paint around each hole but not the lines or whites: an outline next to a hole would
    # smear dark into it, while a belly patch or blush under a mouth should continue through the fill.
    skin = np.array([int(face["skin"][i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float64)
    darker = rgb.mean(axis=2) < skin.mean() - 50
    whiteish = (rgb.min(axis=2) > 190) & (rgb.max(axis=2) - rgb.min(axis=2) < 60)
    # Anti-aliased line edges are half line colour: keep a few pixels away from every dark line too.
    reach = max(3, int(min(head.shape) * 0.012)) | 1
    halo = np.asarray(Image.fromarray(np.where(darker, 255, 0).astype(np.uint8), "L")
                      .filter(ImageFilter.MaxFilter(reach))) > 127
    weight = (head & ~hole & ~halo & ~whiteish).astype(np.float64)
    filled = push_pull(rgb / 255, weight) * 255
    head_pixels = rgba.copy()
    head_pixels[..., :3] = np.where(hole[..., None], np.clip(filled, 0, 255), rgba[..., :3]).astype(np.uint8)
    face.update({"masks": new_masks, "sources": {part: Image.fromarray(head_pixels, "RGBA"), **feathered},
                 "part": part})
    return face


def mouth_layers(face, cutout, masks, marks, spec, folder, out_dir):
    """Write the vector mouth set coloured from the art and return its rig layers (children of the head)."""
    from .aiart import _pivot, geometry
    from .character import DEFAULT, UNIT, mouth_parts

    feet, scale, (canvas_w, canvas_h) = geometry(cutout, spec)
    hx0, hy0, hx1, hy1 = face["head_box"]
    hw, hh = hx1 - hx0, hy1 - hy0
    if face.get("mouth"):
        x0, y0, x1, y1 = face["mouth"]
        centre = ((x0 + x1) / 2, (y0 + y1) / 2)
        width_px = min(max(x1 - x0, hw * 0.18), hw * 0.45)
    else:
        centre = ((hx0 + hx1) / 2, hy0 + hh * 0.76)
        width_px = hw * 0.26
    mouth_spec = {"mouth": {"width": 0.17, "y": 0}, "line_width": 14,
                  "palette": {**DEFAULT["palette"], "line": face["line"]}}
    per_unit = width_px / (0.17 * UNIT)  # art pixels per design unit
    mouth_spec["line_width"] = max(1.5, hw * 0.025) / per_unit

    class Face:
        extra = {"pad": 0, "h": 0, "pivot_y": 0}
    owner = face.get("part", "head")
    head_pivot = _pivot(owner, masks[owner], marks)
    layers = []
    for part in mouth_parts(mouth_spec, owner, Face()):
        shape = part.extra["shape"]
        (out_dir / f"{part.name}.svg").write_text(part.svg(), encoding="utf-8")
        layer = {"id": part.name, "kind": "svg", "file": f"{folder}/{part.name}.svg", "asset_scope": "channel",
                 "x": round((centre[0] - head_pivot[0]) * scale / canvas_w, 5),
                 "y": round((centre[1] - head_pivot[1]) * scale / canvas_h, 5),
                 "width": round(part.width * per_unit * scale / canvas_w, 5),
                 "height": round(part.height * per_unit * scale / canvas_h, 5),
                 "pivot": part.pivot, "role": "mouth", "parent": owner,
                 "variant_group": "mouth", "mouth_shape": shape}
        if shape != "rest":
            layer["visible"] = False
        layers.append(layer)
    return layers
