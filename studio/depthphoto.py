"""Photo parallax: split one image into depth layers the camera can move through.

    python -m studio.depthphoto <episode.json> --image photo.jpg [--depth depth.png]
        [--layers 4] [--name street] [--range 1.2] [--shot A]

Depth comes from, in order: ``--depth`` (a greyscale map, white = near, as Depth
Anything, Marigold, ZoeDepth or Photoshop write; ``--invert`` for white = far),
a local ONNX depth model (``STUDIO_DEPTH_MODEL``, or the first ``*.onnx`` under
``audio-models/depth/``; Depth Anything V2 Small from Hugging Face
``onnx-community/depth-anything-v2-small`` works; ``make art-models`` downloads it), or a rough fallback that
treats lower and more detailed areas as nearer. The fallback suits landscapes
and street scenes; give a real depth map for portraits and close objects.

The photo is cut into equal-area depth bands with feathered edges. Each band
also covers everything nearer than itself with colour filled in from its own
pixels (push-pull inpainting), so when nearer layers slide during a camera move
the gap behind them shows plausible background instead of a hole. Layers are
cropped to the episode's aspect (``--focus`` picks the horizontal centre of a
wide photo) and written as PNGs to ``art/depth/<name>/`` beside the episode with a ``z`` from
``--range`` (far) to 0 (near), oversized slightly so pans never show an edge.
With ``--shot`` they are inserted at the bottom of that shot (replacing an
earlier split of the same name); otherwise the layer JSON is printed. Pair them
with a depth camera: ``"camera": {"preset": "dolly-in"}`` or small ``x`` pans.
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def _smoothstep(values):
    values = np.clip(values, 0, 1)
    return values * values * (3 - 2 * values)


def _normalise(depth):
    low, high = np.percentile(depth, 1), np.percentile(depth, 99)
    return np.clip((depth - low) / max(high - low, 1e-6), 0, 1)


def model_path():
    explicit = os.environ.get("STUDIO_DEPTH_MODEL")
    if explicit:
        return Path(explicit)
    found = sorted((ROOT / "audio-models" / "depth").glob("*.onnx"))
    return found[0] if found else None


def estimate_onnx(image, path):
    """Relative depth (1 = near) from a Depth Anything style ONNX model."""
    import onnxruntime

    session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    entry = session.get_inputs()[0]
    shape = entry.shape
    size = shape[2] if len(shape) == 4 and isinstance(shape[2], int) else 518
    width = shape[3] if len(shape) == 4 and isinstance(shape[3], int) else size
    rgb = np.asarray(image.convert("RGB").resize((width, size), Image.Resampling.BICUBIC), dtype=np.float32) / 255
    rgb = (rgb - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
    output = session.run(None, {entry.name: rgb.transpose(2, 0, 1)[None]})[0]
    depth = np.squeeze(np.asarray(output, dtype=np.float32))
    if depth.ndim != 2:
        raise ValueError(f"Unexpected depth output shape {output.shape} from {path.name}")
    resized = Image.fromarray(_normalise(depth).astype(np.float32), "F").resize(image.size, Image.Resampling.BICUBIC)
    return _normalise(np.asarray(resized, dtype=np.float64))


def estimate_fallback(image):
    """Rough depth: lower in frame and more detailed reads as nearer."""
    grey = np.asarray(image.convert("L"), dtype=np.float64) / 255
    height, width = grey.shape
    vertical = np.linspace(0, 1, height)[:, None] ** 1.3 * np.ones((1, width))
    gy, gx = np.gradient(grey)
    detail = Image.fromarray((np.clip(np.hypot(gx, gy) * 6, 0, 1) * 255).astype(np.uint8))
    detail = np.asarray(detail.filter(ImageFilter.GaussianBlur(max(2, min(width, height) / 40))), dtype=np.float64) / 255
    return _normalise(0.7 * vertical + 0.3 * _normalise(detail))


def load_depth(image, depth_path=None, invert=False):
    if depth_path:
        with Image.open(depth_path) as source:
            depth = np.asarray(ImageOps.exif_transpose(source).convert("F").resize(image.size, Image.Resampling.BICUBIC),
                               dtype=np.float64)
        depth, method = _normalise(depth), "map"
    elif (path := model_path()) and path.is_file():
        depth, method = estimate_onnx(image, path), f"onnx:{path.name}"
    else:
        depth, method = estimate_fallback(image), "fallback"
    if invert:
        depth = 1 - depth
    # Soften so band edges follow shapes rather than pixel noise.
    from .light2d import _blur
    return _blur(depth, max(1, round(min(image.size) / 400))), method


def _upsample(color, shape):
    """Bilinear (pixel-centre) upsample of an (h, w, c) array to ``shape``."""
    height, width = color.shape[:2]
    ys = np.clip((np.arange(shape[0]) + 0.5) * height / shape[0] - 0.5, 0, height - 1)
    xs = np.clip((np.arange(shape[1]) + 0.5) * width / shape[1] - 0.5, 0, width - 1)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, height - 1), np.minimum(x0 + 1, width - 1)
    fy, fx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    top = color[y0][:, x0] * (1 - fx) + color[y0][:, x1] * fx
    bottom = color[y1][:, x0] * (1 - fx) + color[y1][:, x1] * fx
    return top * (1 - fy) + bottom * fy


def push_pull(color, weight):
    """Fill low-weight pixels from a weighted image pyramid (weights 0-1)."""
    height, width = weight.shape
    if weight.min() >= 0.999 or min(height, width) <= 1:
        return color
    pad_h, pad_w = height % 2, width % 2
    c = np.pad(color * weight[..., None], ((0, pad_h), (0, pad_w), (0, 0)))
    w = np.pad(weight, ((0, pad_h), (0, pad_w)))
    c2 = c[0::2, 0::2] + c[1::2, 0::2] + c[0::2, 1::2] + c[1::2, 1::2]
    w2 = w[0::2, 0::2] + w[1::2, 0::2] + w[0::2, 1::2] + w[1::2, 1::2]
    coarse = push_pull(c2 / np.maximum(w2, 1e-6)[..., None], np.minimum(w2, 1))
    up = _upsample(coarse, (height + pad_h, width + pad_w))[:height, :width]
    return color * weight[..., None] + up * (1 - weight[..., None])


def split(image, depth, count=4, feather=0.04):
    """RGBA float layers far to near, and the band thresholds."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float64) / 255
    thresholds = [float(np.quantile(depth, k / count)) for k in range(1, count)]

    def nearer(t):
        return _smoothstep((depth - t) / max(feather, 1e-3) + 0.5)
    layers = []
    for k in range(count):
        cover = np.ones_like(depth) if k == 0 else nearer(thresholds[k - 1])
        beyond = nearer(thresholds[k]) if k < count - 1 else np.zeros_like(depth)
        own = cover * (1 - beyond)
        colour = push_pull(rgb, np.where(own > 0.5, 1.0, own * 0.5)) if k < count - 1 else rgb
        layers.append(np.concatenate([colour, cover[..., None]], axis=2))
    return layers, thresholds


def layer_specs(name, files, size, canvas, depth_range=1.2, margin=1.08):
    """Episode image layers that cover the frame, far to near."""
    aspect = size[0] / size[1]
    height_px = margin * max(canvas[1], canvas[0] / aspect)
    width_px = height_px * aspect
    count = len(files)
    specs = []
    for k, file in enumerate(files):
        z = round(depth_range * (count - 1 - k) / max(1, count - 1), 3)
        specs.append({"id": f"{name}-{k}", "kind": "image", "file": file, "x": 0.5, "y": 0.5,
                      "width": round(width_px / canvas[0], 4), "height": round(height_px / canvas[1], 4),
                      "z": z, "depth_photo": name})
    return specs


def run(episode_path, image_path, depth_path=None, count=4, name=None, depth_range=1.2, shot_id=None,
        invert=False, feather=0.04, focus=0.5):
    episode_path = Path(episode_path).resolve()
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    name = name or Path(image_path).stem.lower().replace(" ", "-")
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    canvas = (int(episode.get("width", 1080)), int(episode.get("height", 1920)))
    # Crop to the frame's aspect around the focus so the layers cover it without a huge width.
    target_aspect = canvas[0] / canvas[1]
    if image.width / image.height > target_aspect:
        crop = round(image.height * target_aspect)
        left = round(max(0, min(image.width - crop, focus * image.width - crop / 2)))
        image = image.crop((left, 0, left + crop, image.height))
    else:
        crop = round(image.width / target_aspect)
        top = round(max(0, min(image.height - crop, 0.5 * image.height - crop / 2)))
        image = image.crop((0, top, image.width, top + crop))
    longest = 2048
    if max(image.size) > longest:
        image.thumbnail((longest, longest), Image.Resampling.LANCZOS)
    depth, method = load_depth(image, depth_path, invert)
    layers, thresholds = split(image, depth, max(2, min(8, count)), feather)
    folder = episode_path.parent / "art" / "depth" / name
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for k, layer in enumerate(layers):
        target = folder / f"layer-{k}.png"
        Image.fromarray(np.round(layer * 255).astype(np.uint8), "RGBA").save(target, optimize=True)
        files.append(str(target.relative_to(episode_path.parent)))
    Image.fromarray((depth * 255).astype(np.uint8), "L").save(folder / "depth.png")
    specs = layer_specs(name, files, image.size, canvas, depth_range)
    result = {"method": method, "layers": specs, "folder": str(folder),
              "thresholds": [round(t, 3) for t in thresholds]}
    if shot_id:
        shots = {shot["id"]: shot for scene in episode.get("scenes", []) for shot in scene.get("shots", [])}
        if shot_id not in shots:
            raise ValueError(f"Unknown shot: {shot_id}")
        shot = shots[shot_id]
        kept = [layer for layer in shot.get("layers", []) if layer.get("depth_photo") != name]
        shot["layers"] = specs + kept
        episode_path.write_text(json.dumps(episode, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result["inserted"] = shot_id
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--depth", type=Path)
    parser.add_argument("--invert", action="store_true", help="the depth map is white = far")
    parser.add_argument("--layers", type=int, default=4)
    parser.add_argument("--name")
    parser.add_argument("--range", type=float, default=1.2, dest="depth_range", help="z of the farthest layer")
    parser.add_argument("--feather", type=float, default=0.04)
    parser.add_argument("--shot", help="insert the layers at the bottom of this shot")
    parser.add_argument("--focus", type=float, default=0.5, help="horizontal crop centre, 0-1, for wide photos")
    args = parser.parse_args()
    print(json.dumps(run(args.episode, args.image, args.depth, args.layers, args.name, args.depth_range, args.shot,
                         args.invert, args.feather, args.focus), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
