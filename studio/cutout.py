"""Cut a character out of its background: rembg, a local ONNX matting model, or a colour key.

    python -m studio.cutout in.png out.png [--method auto|rembg|onnx|key]

``auto`` uses the best available: ``rembg`` (pip install rembg), then an ONNX
matting model (``STUDIO_CUTOUT_MODEL`` or the first ``*.onnx`` under
``audio-models/cutout/``; U2-Net, IS-Net and BiRefNet exports work), then a
key on the flat background colour. Generated art is prompted onto a plain
background, so the key is usually enough. It only removes background that is
connected to the image border, which keeps white eyes and teeth opaque.
"""

import argparse
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]


def model_path():
    explicit = os.environ.get("STUDIO_CUTOUT_MODEL")
    if explicit:
        return Path(explicit)
    found = sorted((ROOT / "audio-models" / "cutout").glob("*.onnx"))
    return found[0] if found else None


def available(method):
    import importlib.util

    if method == "rembg":
        return importlib.util.find_spec("rembg") is not None
    if method == "onnx":
        path = model_path()
        return importlib.util.find_spec("onnxruntime") is not None and bool(path and path.is_file())
    return method == "key"


def choose(method="auto"):
    if method != "auto":
        if not available(method):
            raise ValueError(f"Cutout method {method!r} is not available on this machine")
        return method
    return next(name for name in ("rembg", "onnx", "key") if available(name))


def key_background(image, tolerance=38, feather=1.2):
    """Alpha from a flat background: flood the border-connected pixels near the border colour."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    colour = np.median(border, axis=0)
    near = np.sqrt(((rgb - colour) ** 2).sum(axis=2)) <= tolerance
    mask = Image.fromarray(np.where(near, 255, 0).astype(np.uint8), "L").copy()  # fromarray may share a read-only buffer
    height, width = near.shape
    step = max(1, min(width, height) // 64)
    edge = [(x, 0) for x in range(0, width, step)] + [(x, height - 1) for x in range(0, width, step)]
    edge += [(0, y) for y in range(0, height, step)] + [(width - 1, y) for y in range(0, height, step)]
    for point in edge:
        if mask.getpixel(point) == 255:
            ImageDraw.floodfill(mask, point, 128, thresh=0)
    background = np.asarray(mask) == 128
    alpha = Image.fromarray(np.where(background, 0, 255).astype(np.uint8), "L")
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    return alpha


def onnx_alpha(image, path):
    import onnxruntime

    session = onnxruntime.InferenceSession(str(path), providers=onnxruntime.get_available_providers())
    entry = session.get_inputs()[0]
    shape = entry.shape
    size = shape[2] if len(shape) == 4 and isinstance(shape[2], int) else 320
    rgb = np.asarray(image.convert("RGB").resize((size, size), Image.BICUBIC), dtype=np.float32) / 255
    rgb = (rgb - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    batch = rgb.transpose(2, 0, 1)[None].astype(np.float32)
    out = np.asarray(session.run(None, {entry.name: batch})[0], dtype=np.float32).squeeze()
    if out.ndim == 3:
        out = out[0]
    if out.min() < 0 or out.max() > 1:
        out = 1 / (1 + np.exp(-out))
    out = (out - out.min()) / max(float(out.max() - out.min()), 1e-6)
    return Image.fromarray((out * 255).astype(np.uint8), "L").resize(image.size, Image.BILINEAR)


def cut(image, method="auto"):
    """Return ``(RGBA image, method used)``."""
    method = choose(method)
    image = image.convert("RGBA")
    if method == "rembg":
        from rembg import remove

        return remove(image).convert("RGBA"), method
    alpha = onnx_alpha(image, model_path()) if method == "onnx" else key_background(image)
    out = image.copy()
    out.putalpha(alpha)
    return out, method


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--method", default="auto", choices=("auto", "rembg", "onnx", "key"))
    args = parser.parse_args()
    try:
        image, method = cut(Image.open(args.source), args.method)
    except (OSError, ValueError) as error:
        print(f"studio: {error}")
        return 1
    image.save(args.out)
    print(f"{args.out} ({method})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
