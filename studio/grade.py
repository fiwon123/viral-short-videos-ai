"""Colour grading with 3D LUTs: built-in looks or any .cube file.

``post.grade`` picks a built-in look and ``post.lut`` loads a .cube file (a
path from the repository root, or a name in ``presets/luts/``).
``post.grade_amount`` (0–1) mixes it in. Python bakes every look into the
same 17³ table that the browser renderer receives, so both apply an
identical trilinear lookup.
"""

from functools import lru_cache
from pathlib import Path

import numpy as np

SIZE = 17
ROOT = Path(__file__).resolve().parents[1]


def _luma(rgb):
    return rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _saturate(rgb, amount):
    grey = _luma(rgb)[..., None]
    return grey + (rgb - grey) * amount


def _split(rgb, shadows, highlights, strength):
    luma = _luma(rgb)[..., None]
    low = np.array(shadows, dtype=np.float32) - 0.5
    high = np.array(highlights, dtype=np.float32) - 0.5
    return rgb + strength * (low * (1 - luma) ** 2 + high * luma ** 2)


def _curve(rgb, contrast=1.0, lift=0.0, gain=1.0):
    rgb = lift + rgb * (gain - lift)
    return 0.5 + (rgb - 0.5) * contrast


LOOKS = {
    "teal-orange": lambda c: _curve(_saturate(_split(c, (0.32, 0.55, 0.62), (0.72, 0.52, 0.32), 0.55), 1.12), 1.08),
    "warm-film": lambda c: _curve(_saturate(_split(c, (0.52, 0.47, 0.44), (0.68, 0.56, 0.4), 0.35), 0.9), 1.02, 0.045, 0.97),
    "cool-night": lambda c: _curve(_saturate(_split(c, (0.3, 0.42, 0.7), (0.5, 0.56, 0.68), 0.5), 0.8), 1.05, 0.02, 0.88),
    "bleach": lambda c: _curve(_saturate(c, 0.55), 1.22, 0.0, 1.0),
    "vintage": lambda c: _curve(_saturate(_split(c, (0.6, 0.42, 0.55), (0.66, 0.64, 0.4), 0.4), 0.82), 0.92, 0.08, 0.95),
    "pastel": lambda c: _curve(_saturate(_split(c, (0.58, 0.48, 0.58), (0.56, 0.52, 0.5), 0.3), 0.75), 0.85, 0.1, 1.0),
}


def _grid(size=SIZE):
    axis = np.linspace(0, 1, size, dtype=np.float32)
    b, g, r = np.meshgrid(axis, axis, axis, indexing="ij")
    return np.stack([r, g, b], axis=-1).reshape(-1, 3)  # Red varies fastest, like .cube.


@lru_cache(maxsize=16)
def bake(name):
    if name not in LOOKS:
        raise ValueError(f"Unknown grade: {name}. Available: {', '.join(sorted(LOOKS))}")
    return SIZE, np.clip(LOOKS[name](_grid()), 0, 1).astype(np.float32)


@lru_cache(maxsize=16)
def load_cube(name):
    candidates = [Path(name), ROOT / name, ROOT / "presets" / "luts" / name, ROOT / "presets" / "luts" / f"{name}.cube"]
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        raise ValueError(f"LUT not found: {name}")
    size, rows = None, []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("LUT_3D_SIZE"):
            size = int(line.split()[-1])
        elif line[0].isdigit() or line[0] in "-.":
            parts = line.split()
            if len(parts) >= 3:
                rows.append([float(value) for value in parts[:3]])
    if not size or len(rows) != size ** 3:
        raise ValueError(f"{path.name} is not a 3D .cube LUT")
    return size, np.clip(np.array(rows, dtype=np.float32), 0, 1)


def table(config):
    """(size, flat table) for a post config, or None."""
    if config.get("lut"):
        return load_cube(config["lut"])
    if config.get("grade"):
        return bake(config["grade"])
    return None


def apply(data, size, lut, amount=1.0):
    """Trilinear 3D LUT on float RGB in [0, 1]. Mirrored by applyLut in painter.mjs."""
    cube = lut.reshape(size, size, size, 3)  # [b][g][r]
    scaled = np.clip(data, 0, 1) * (size - 1)
    low = np.floor(scaled).astype(np.int32)
    high = np.minimum(low + 1, size - 1)
    frac = scaled - low
    r0, g0, b0 = low[..., 0], low[..., 1], low[..., 2]
    r1, g1, b1 = high[..., 0], high[..., 1], high[..., 2]
    fr, fg, fb = frac[..., 0:1], frac[..., 1:2], frac[..., 2:3]
    c00 = cube[b0, g0, r0] * (1 - fr) + cube[b0, g0, r1] * fr
    c01 = cube[b1, g0, r0] * (1 - fr) + cube[b1, g0, r1] * fr
    c10 = cube[b0, g1, r0] * (1 - fr) + cube[b0, g1, r1] * fr
    c11 = cube[b1, g1, r0] * (1 - fr) + cube[b1, g1, r1] * fr
    graded = (c00 * (1 - fg) + c10 * fg) * (1 - fb) + (c01 * (1 - fg) + c11 * fg) * fb
    return data + (graded - data) * float(amount)
