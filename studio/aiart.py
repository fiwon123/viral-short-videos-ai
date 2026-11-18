"""Local AI character art: generate once, cut out, split into parts, rig for animation.

    python -m studio.aiart workspace/<slug>/channel --spec art/characters/mika.json
        [--image my-art.png] [--parts-dir layers/] [--backend auto|comfyui|diffusers|procedural]
        [--seed 7] [--dry-run]
    python -m studio.hardware      # what this machine can use, and the plan

The art is drawn by a local image model, then animated by the studio like any
rig (``alive`` breathing and sway, poses, IK, motion recipes). It is generated
once and reused all season: the prompt, model, seed and LoRA are locked in the
spec, and the source image is cached by their hash.

Spec (``id`` and ``description`` are required for generation)::

    {"id": "mika", "description": "a cheerful courier fox girl with a red scarf",
     "style": "flat cel-shaded cartoon, bold clean outlines, soft pastel palette",
     "negative": "photo, realistic", "seed": 1234, "model": "auto",
     "lora": {"name": "my-style.safetensors", "weight": 0.8},
     "height": 0.32, "canvas": [1080, 1920],
     "image": null, "parts_dir": null, "parts": null, "fallback": {...}}

A channel-wide ``art/style.json`` (``style``, ``negative``, ``model``, ``lora``,
``seed``) is merged under every spec, so the whole cast shares one look.

**Backend choice** (``plan``): ComfyUI when one is running (``STUDIO_COMFYUI_URL``,
default ``http://127.0.0.1:8188``), else ``diffusers`` + ``torch`` on the local
GPU (CUDA, ROCm, Apple MPS) or the CPU, else the procedural ``make character``
generator with ``fallback`` (or the spec's own character fields). The model is
picked by VRAM from the commercial-use list in ``MODELS``; weights with a
non-commercial licence (Flux dev and similar) are refused unless
``"allow_noncommercial": true``.

**Manual paths.** ``image`` (or ``--image``) skips generation and rigs your own
art. ``parts_dir`` takes already separated PNG layers on one shared canvas
(``body.png``, ``head.png``, ``arm-l.png``, ``arm-r.png``, ``leg-l.png``,
``leg-r.png``; ``mouth-<shape>.png``, ``eye-l.png``... are kept with their role),
as Krita, Photoshop or GIMP export them. ``parts`` overrides the automatic split
with boxes in fractions of the cut-out character::

    "parts": {"head": [0.2, 0.0, 0.8, 0.32], "arm-l": [0.0, 0.3, 0.25, 0.7]}

The face is made to act (``studio/aiface.py``): eyes lifted for blinks, the painted
mouth replaced by a lip-sync mouth set. ``"face": false`` keeps the art as drawn.

Outputs ``art/characters/<id>/`` (``source.png``, ``cutout.png``, one PNG per
part, ``preview.png``, ``art.json`` with the model, licence and seed) and the
rig ``<id>`` in the channel rig library, with starter poses.
"""

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
import uuid
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# Commercial use: "yes" is permissive; "conditional" has a revenue cap or similar; "no" is refused by default.
MODELS = {
    "flux-schnell": {"repo": "black-forest-labs/FLUX.1-schnell", "license": "Apache-2.0", "commercial": "yes",
                     "min_vram": 12, "steps": 4, "cfg": 1.0, "size": [1024, 1024], "sampler": "euler",
                     "scheduler": "simple", "files": ["flux1-schnell", "flux-schnell", "flux_schnell"]},
    "qwen-image": {"repo": "Qwen/Qwen-Image", "license": "Apache-2.0", "commercial": "yes", "min_vram": 24,
                   "steps": 30, "cfg": 4.0, "size": [1024, 1024], "sampler": "euler", "scheduler": "simple",
                   "files": ["qwen_image", "qwen-image"]},
    "sdxl": {"repo": "stabilityai/stable-diffusion-xl-base-1.0", "license": "CreativeML Open RAIL++-M",
             "commercial": "yes", "min_vram": 8, "steps": 28, "cfg": 6.0, "size": [1024, 1024],
             "sampler": "dpmpp_2m", "scheduler": "karras", "files": ["sd_xl_base", "sdxl_base", "sdxl-base"]},
    "sdxl-turbo": {"repo": "stabilityai/sdxl-turbo", "license": "Stability AI Community License",
                   "commercial": "conditional", "min_vram": 6, "steps": 4, "cfg": 0.0, "size": [512, 512],
                   "sampler": "euler_ancestral", "scheduler": "normal",
                   "files": ["sd_xl_turbo", "sdxl_turbo", "sdxl-turbo"],
                   "note": "Commercial use is free under the licence's annual revenue cap; check it for your channel."},
    "sd15": {"repo": "stable-diffusion-v1-5/stable-diffusion-v1-5", "license": "CreativeML Open RAIL-M",
             "commercial": "yes", "min_vram": 4, "steps": 25, "cfg": 7.0, "size": [512, 768],
             "sampler": "dpmpp_2m", "scheduler": "karras", "files": ["v1-5", "sd15", "sd-v1-5", "sd_v1-5"]},
}
NONCOMMERCIAL = ["flux1-dev", "flux-dev", "flux_dev", "flux1-kontext-dev", "sd3_medium", "sd3-medium"]
# Best first, per VRAM tier (GB). CPU uses the last tier.
TIERS = [(20, ["flux-schnell", "qwen-image", "sdxl", "sdxl-turbo", "sd15"]),
         (12, ["flux-schnell", "sdxl", "sdxl-turbo", "sd15"]),
         (7, ["sdxl", "sdxl-turbo", "sd15"]),
         (0, ["sd15", "sdxl-turbo"])]

POSE_PROMPT = ("single character, full body, front view, standing straight, arms held slightly away from the body, "
               "legs slightly apart, centered, plain flat white background, no ground shadow")
NEGATIVE = ("text, watermark, signature, cropped, out of frame, multiple characters, scenery, background objects, "
            "floor, cast shadow, blurry, extra limbs")
ROLE = {"body": "body", "head": "head", "arm-l": "arm", "arm-r": "arm", "leg-l": "leg", "leg-r": "leg",
        "tail": "tail", "ear-l": "ear", "ear-r": "ear", "eye-l": "eye", "eye-r": "eye", "pupil-l": "pupil",
        "pupil-r": "pupil", "brow-l": "brow", "brow-r": "brow", "shadow": "shadow"}
PARENT = {"head": "body", "arm-l": "body", "arm-r": "body", "tail": "body", "ear-l": "head", "ear-r": "head",
          "eye-l": "head", "eye-r": "head", "pupil-l": "eye-l", "pupil-r": "eye-r", "brow-l": "head",
          "brow-r": "head"}
ORDER = ["shadow", "tail", "leg-l", "leg-r", "body", "head", "ear-l", "ear-r", "eye-l", "eye-r", "pupil-l",
         "pupil-r", "brow-l", "brow-r", "arm-l", "arm-r"]


# ---------------------------------------------------------------- planning

def _noncommercial(name):
    lowered = name.lower()
    return any(tag in lowered for tag in NONCOMMERCIAL)


def checkpoint_for(model, checkpoints):
    patterns = MODELS[model]["files"]
    for name in checkpoints:
        lowered = name.lower()
        if any(pattern in lowered for pattern in patterns) and not (model == "sdxl" and "turbo" in lowered):
            return name
    return None


def preferred(vram):
    for floor, models in TIERS:
        if vram >= floor:
            return models
    return TIERS[-1][1]


def plan(report, spec):
    """Pick the backend and model for this machine: ``{"backend", "model", ...}`` plus a reason."""
    backend = spec.get("backend", "auto")
    if spec.get("image") or spec.get("parts_dir"):
        return {"backend": "image", "reason": "using supplied art"}
    gpu = report.get("gpu") or {}
    vram = float(gpu.get("vram_gb") or 0)
    wanted = spec.get("model", "auto")
    allow_nc = bool(spec.get("allow_noncommercial"))
    if wanted != "auto" and wanted not in MODELS and not spec.get("checkpoint"):
        raise ValueError(f"Unknown model {wanted!r}; choose one of {', '.join(MODELS)} or set checkpoint")
    comfy = report.get("comfyui")
    if comfy and backend in ("auto", "comfyui"):
        checkpoints = comfy.get("checkpoints") or []
        if spec.get("checkpoint"):
            name = spec["checkpoint"]
            if _noncommercial(name) and not allow_nc:
                raise ValueError(f"{name} has a non-commercial licence; set allow_noncommercial to use it anyway")
            model = wanted if wanted in MODELS else "sdxl"
            return {"backend": "comfyui", "url": comfy["url"], "model": model, "checkpoint": name,
                    "reason": "checkpoint named in the spec"}
        order = [wanted] if wanted != "auto" else preferred(vram or 8)
        for model in order:
            name = checkpoint_for(model, checkpoints)
            if name:
                return {"backend": "comfyui", "url": comfy["url"], "model": model, "checkpoint": name,
                        "reason": f"ComfyUI has {name}; best fit for {vram:g} GB" if vram else f"ComfyUI has {name}"}
        if backend == "comfyui":
            raise ValueError("ComfyUI has none of the supported checkpoints: "
                             + ", ".join(f"{m} ({MODELS[m]['repo']})" for m in order))
    budget = report.get("profile") or {}
    usable_gpu = gpu if vram >= 4 else {}  # Under 4 GB a GPU cannot hold an image model; treat it as absent.
    if report.get("diffusers") and backend in ("auto", "diffusers") and (usable_gpu or budget.get("cpu_ai")
                                                                         or backend == "diffusers"):
        gpu = usable_gpu
        vendor = gpu.get("vendor")
        device = "mps" if vendor == "apple" else "cuda" if gpu else "cpu"
        order = [wanted] if wanted != "auto" else preferred(vram if gpu else 0)
        order = [model for model in order if model != "qwen-image" or vram >= MODELS[model]["min_vram"]] or order
        result = {"backend": "diffusers", "device": device, "model": order[0],
                  "reason": f"diffusers on {device}" + (f" ({gpu.get('name')}, {vram:g} GB)" if gpu else "")}
        if device == "cpu":
            result["warning"] = "No usable GPU: CPU generation takes several minutes per image."
        return result
    if report.get("diffusers") and backend == "auto":
        return {"backend": "procedural", "reason": "no GPU with 4 GB or more; CPU image generation is off to keep "
                                                   "this PC responsive (set STUDIO_CPU_AI=1 to allow it, or pass "
                                                   "IMAGE= with art made elsewhere)"}
    if backend in ("comfyui", "diffusers"):
        raise ValueError(f"The {backend} backend is not available on this machine (run python -m studio.hardware)")
    return {"backend": "procedural", "reason": "no local image generator found (no ComfyUI, no diffusers/torch); "
                                               "using the procedural character generator"}


def merged_spec(channel_dir, raw):
    style_file = Path(channel_dir) / "art" / "style.json"
    shared = json.loads(style_file.read_text(encoding="utf-8")) if style_file.is_file() else {}
    spec = {**shared, **raw}
    if shared.get("style") and raw.get("style") and raw["style"] != shared["style"]:
        spec["style"] = f"{shared['style']}, {raw['style']}"
    return spec


def prompts(spec):
    positive = ", ".join(part for part in (spec.get("description", ""), spec.get("style", ""), POSE_PROMPT) if part)
    negative = ", ".join(part for part in (NEGATIVE, spec.get("negative", "")) if part)
    return positive, negative


def cache_key(spec, choice):
    model = MODELS.get(choice.get("model"), {})
    positive, negative = prompts(spec)
    data = {"positive": positive, "negative": negative, "seed": int(spec.get("seed", 0)),
            "model": choice.get("checkpoint") or model.get("repo"), "lora": spec.get("lora"),
            "size": spec.get("size") or model.get("size"), "steps": spec.get("steps") or model.get("steps")}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- generation

def comfy_graph(spec, choice):
    model = MODELS[choice["model"]]
    positive, negative = prompts(spec)
    width, height = spec.get("size") or model["size"]
    graph = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": choice["checkpoint"]}}}
    source_model, source_clip = ["1", 0], ["1", 1]
    lora = spec.get("lora")
    if lora:
        graph["2"] = {"class_type": "LoraLoader",
                      "inputs": {"model": source_model, "clip": source_clip, "lora_name": lora["name"],
                                 "strength_model": float(lora.get("weight", 0.8)),
                                 "strength_clip": float(lora.get("weight", 0.8))}}
        source_model, source_clip = ["2", 0], ["2", 1]
    graph["3"] = {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": source_clip}}
    graph["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": source_clip}}
    graph["5"] = {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
    graph["6"] = {"class_type": "KSampler",
                  "inputs": {"model": source_model, "seed": int(spec.get("seed", 0)),
                             "steps": int(spec.get("steps") or model["steps"]),
                             "cfg": float(spec.get("cfg", model["cfg"])), "sampler_name": model["sampler"],
                             "scheduler": model["scheduler"], "positive": ["3", 0], "negative": ["4", 0],
                             "latent_image": ["5", 0], "denoise": 1.0}}
    graph["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}}
    graph["8"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "studio-art"}}
    return graph


def generate_comfyui(spec, choice, timeout=900):
    url = choice["url"].rstrip("/")
    body = json.dumps({"prompt": comfy_graph(spec, choice), "client_id": str(uuid.uuid4())}).encode()
    request = urllib.request.Request(f"{url}/prompt", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - local ComfyUI
        prompt_id = json.loads(response.read())["prompt_id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with urllib.request.urlopen(f"{url}/history/{prompt_id}", timeout=30) as response:  # noqa: S310
            history = json.loads(response.read())
        entry = history.get(prompt_id)
        if entry:
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise ValueError(f"ComfyUI failed: {status.get('messages')}")
            for output in (entry.get("outputs") or {}).values():
                for image in output.get("images") or []:
                    query = urllib.parse.urlencode({"filename": image["filename"],
                                                    "subfolder": image.get("subfolder", ""),
                                                    "type": image.get("type", "output")})
                    with urllib.request.urlopen(f"{url}/view?{query}", timeout=60) as response:  # noqa: S310
                        return Image.open(BytesIO(response.read())).convert("RGB")
        time.sleep(0.5)
    raise ValueError(f"ComfyUI did not finish within {timeout} s")


def generate_diffusers(spec, choice):  # pragma: no cover - needs torch and downloaded weights
    import torch
    from diffusers import AutoPipelineForText2Image

    from .machine import current

    torch.set_num_threads(current()["threads"])
    model = MODELS[choice["model"]]
    device = choice["device"]
    dtype = torch.float16 if device == "cuda" else torch.float32
    if choice["model"] == "flux-schnell" and device == "cuda":
        dtype = torch.bfloat16
    pipe = AutoPipelineForText2Image.from_pretrained(model["repo"], torch_dtype=dtype)
    lora = spec.get("lora")
    if lora:
        pipe.load_lora_weights(lora.get("path") or lora["name"])
        pipe.fuse_lora(lora_scale=float(lora.get("weight", 0.8)))
    if device == "cuda" and choice.get("offload"):
        pipe.enable_model_cpu_offload()
    else:
        pipe = pipe.to(device)
    positive, negative = prompts(spec)
    width, height = spec.get("size") or model["size"]
    options = {"prompt": positive, "width": width, "height": height,
               "num_inference_steps": int(spec.get("steps") or model["steps"]),
               "guidance_scale": float(spec.get("cfg", model["cfg"])),
               "generator": torch.Generator("cpu").manual_seed(int(spec.get("seed", 0)))}
    if choice["model"] not in ("flux-schnell",):
        options["negative_prompt"] = negative
    return pipe(**options).images[0].convert("RGB")


# ---------------------------------------------------------------- splitting

def _runs(row):
    padded = np.concatenate([[False], row, [False]])
    change = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(change[::2], change[1::2]))


def _run_at(row, x):
    for start, end in _runs(row):
        if start <= x < end:
            return start, end
    return None


def _component(mask, seeds):
    """Pixels of ``mask`` connected to any of ``seeds`` (x, y)."""
    image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L").copy()
    for point in seeds:
        if image.getpixel(point) == 255:
            ImageDraw.floodfill(image, point, 128, thresh=0)
    return np.asarray(image) == 128


def split(alpha, boxes=None):
    """Split a character silhouette (bool array, cropped to its bounds) into part masks.

    Legs: the background gap between the feet, followed up to the hip. Head: the
    narrowest row of the centre column run in the upper body (the neck), when the
    head is clearly wider. Arms: what sticks out beside the torso (hip width)
    between the neck and the hip. Shapes that don't show a part keep it in the body.
    """
    height, width = alpha.shape
    if boxes:
        masks, rest = {}, alpha.copy()
        for name, (x0, y0, x1, y1) in boxes.items():
            box = np.zeros_like(alpha)
            box[round(y0 * height):round(y1 * height), round(x0 * width):round(x1 * width)] = True
            masks[name] = alpha & box & rest
            rest &= ~masks[name]
        masks["body"] = rest | masks.get("body", np.zeros_like(alpha))
        return {name: mask for name, mask in masks.items() if mask.any()}, {}
    ys, xs = np.nonzero(alpha)
    cx = int(np.median(xs))
    masks, marks = {}, {}
    # Legs.
    hip = height
    probe = min(height - 1, int(height * 0.97))
    runs = sorted(_runs(alpha[probe]), key=lambda run: run[1] - run[0], reverse=True)[:2]
    if len(runs) == 2 and min(r[1] - r[0] for r in runs) >= width * 0.03:
        left, right = sorted(runs)
        gap = (left[1] + right[0]) // 2
        row = probe
        while row > 0 and not alpha[row, gap]:
            row -= 1
        if height - row >= height * 0.08 and row > height * 0.3:
            hip = row + 1
            region = alpha.copy()
            region[:hip] = False
            for name, run in (("leg-l", left), ("leg-r", right)):
                leg = _component(region, [((run[0] + run[1]) // 2, probe)])
                overlap = alpha.copy()
                overlap[:max(0, hip - int(height * 0.03))] = False
                overlap[hip:] = False
                overlap[:, gap:] = False if name == "leg-l" else overlap[:, gap:]
                overlap[:, :gap] = False if name == "leg-r" else overlap[:, :gap]
                cols = np.flatnonzero(leg.any(axis=0))
                if cols.size:
                    overlap[:, :cols[0]] = False
                    overlap[:, cols[-1] + 1:] = False
                masks[name] = leg | overlap
            marks["gap"] = gap
    marks["hip"] = hip
    # Head.
    widths = np.array([(lambda run: run[1] - run[0] if run else 0)(_run_at(alpha[y], cx)) for y in range(height)])
    kernel = max(1, int(height * 0.015))
    smooth = np.convolve(widths, np.ones(kernel * 2 + 1) / (kernel * 2 + 1), mode="same")
    top, bottom = int(height * 0.12), int(min(hip, height) * 0.55)
    neck = None
    if bottom > top + 2:
        candidate = top + int(np.argmin(smooth[top:bottom]))
        head_width = smooth[:candidate].max() if candidate else 0
        below = smooth[candidate:min(height, candidate + int(height * 0.12))].max()
        if smooth[candidate] < 0.82 * head_width and smooth[candidate] < 0.9 * below:
            neck = candidate
    if neck:
        head = alpha.copy()
        head[neck + int(height * 0.015):] = False
        masks["head"] = head
        marks["neck"] = neck
    # Arms.
    # Torso width: the widest centre run over the band just above the hip (rounded corners narrow one row).
    low = hip - 1 if hip < height else int(height * 0.7)
    band = range(max(0, low - int(height * 0.15)), low + 1)
    spans = [_run_at(alpha[y], marks.get("gap", cx)) or _run_at(alpha[y], cx) for y in band]
    spans = [span for span in spans if span]
    torso = (min(span[0] for span in spans), max(span[1] for span in spans)) if spans else None
    if torso:
        pad = max(1, int(width * 0.015))
        left_edge, right_edge = max(0, torso[0] - pad), min(width, torso[1] + pad)
        start = (neck or int(height * 0.2)) + int(height * 0.02)
        for name, columns in (("arm-l", slice(0, left_edge)), ("arm-r", slice(right_edge, width))):
            side = np.zeros_like(alpha)
            side[start:, columns] = alpha[start:, columns]
            for leg in ("leg-l", "leg-r"):
                if leg in masks:
                    side &= ~masks[leg]
            if side.sum() >= alpha.sum() * 0.012:
                masks[name] = side
        marks["torso"] = [left_edge, right_edge]
    body = alpha.copy()
    if "head" in masks:
        body[:neck] = False
    for name in ("arm-l", "arm-r"):
        if name in masks:
            body &= ~masks[name]
    if hip < height:
        body[hip:] = False
    masks["body"] = body
    return masks, marks


# ---------------------------------------------------------------- rigging

def _pivot(name, mask, marks):
    ys, xs = np.nonzero(mask)
    top, bottom, left, right = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    if name.startswith("leg"):
        row = xs[ys == top]
        return float(row.mean()), float(top)
    if name == "head":
        neck = marks.get("neck", bottom)
        row = xs[ys == min(bottom - 1, neck)]
        return float(row.mean() if row.size else (left + right) / 2), float(neck)
    if name.startswith("arm"):
        inner = right if name == "arm-l" else left
        return float(inner), float(top + (bottom - top) * 0.08)
    if name == "body":
        hip = marks.get("hip", bottom)
        row = xs[ys == min(bottom - 1, hip - 1)]
        return float(row.mean() if row.size else (left + right) / 2), float(min(bottom, hip))
    if name.startswith("mouth") or name.startswith("eye") or name.startswith("brow") or name.startswith("pupil"):
        return (left + right) / 2, (top + bottom) / 2
    if name.startswith("ear") or name == "tail":
        return (left + right) / 2, float(bottom)
    return (left + right) / 2, (top + bottom) / 2


def geometry(image, spec):
    """``(feet pixel, canvas units per pixel, canvas)`` for a cut-out character image."""
    alpha = np.asarray(image.convert("RGBA"))[..., 3] > 127
    ys, xs = np.nonzero(alpha)
    feet = (float(np.median(xs[ys >= ys.max() - max(2, alpha.shape[0] // 50)])), float(ys.max() + 1))
    canvas = spec.get("canvas") or [1080, 1920]
    scale = float(spec.get("height", 0.3)) * canvas[1] / max(1, ys.max() + 1 - ys.min())
    return feet, scale, canvas


def build_rig(image, masks, marks, spec, folder, out_dir, sources=None):
    """Write one PNG per part and return rig layers (canvas fractions, feet at 0,0).

    ``sources`` maps a part to its own layer image (separated artwork keeps the pixels
    hidden under other parts); otherwise every part is cut from ``image``.
    """
    rgba = np.asarray(image.convert("RGBA"))
    feet, scale, (canvas_w, canvas_h) = geometry(image, spec)
    pivots, layers = {}, []
    names = sorted(masks, key=lambda name: ORDER.index(name) if name in ORDER else
                   (ORDER.index("head") + 0.5 if name.startswith("mouth") else len(ORDER)))
    for name in names:
        mask = masks[name]
        if not mask.any():
            continue
        pivots[name] = _pivot(name, mask, marks)
    for name in names:
        if name not in pivots:
            continue
        mask = masks[name]
        part_ys, part_xs = np.nonzero(mask)
        x0, y0 = max(0, part_xs.min() - 2), max(0, part_ys.min() - 2)
        x1, y1 = min(mask.shape[1], part_xs.max() + 3), min(mask.shape[0], part_ys.max() + 3)
        pixels = np.asarray(sources[name].convert("RGBA")) if sources and name in sources else rgba
        tile = pixels[y0:y1, x0:x1].copy()
        tile[..., 3] = np.where(mask[y0:y1, x0:x1], tile[..., 3], 0)
        Image.fromarray(tile, "RGBA").save(out_dir / f"{name}.png")
        px, py = pivots[name]
        role = ROLE.get(name, "mouth" if name.startswith("mouth") else "prop")
        parent = PARENT.get(name)
        if name.startswith("mouth"):
            parent = "head" if "head" in pivots else "body"
        parent = parent if parent in pivots else (None if name.startswith("leg") or name == "body" else
                                                  "body" if "body" in pivots and name != "body" else None)
        origin = pivots[parent] if parent else feet
        layer = {"id": name, "kind": "image", "file": f"{folder}/{name}.png", "asset_scope": "channel",
                 "x": round((px - origin[0]) * scale / canvas_w, 5), "y": round((py - origin[1]) * scale / canvas_h, 5),
                 "width": round((x1 - x0) * scale / canvas_w, 5), "height": round((y1 - y0) * scale / canvas_h, 5),
                 "pivot": [round((px - x0) / (x1 - x0), 4), round((py - y0) / (y1 - y0), 4)], "role": role}
        if parent:
            layer["parent"] = parent
        if name.startswith("arm"):
            far = np.argmax((part_xs - px) ** 2 + (part_ys - py) ** 2)
            layer["tip"] = [round((part_xs[far] - px) * scale / canvas_w, 5),
                            round((part_ys[far] - py) * scale / canvas_h, 5)]
        if name.startswith("mouth"):
            shape = name.split("-", 1)[1] if "-" in name else "rest"
            layer.update({"variant_group": "mouth", "mouth_shape": shape})
            if shape != "rest":
                layer["visible"] = False
        layers.append(layer)
    return layers


def starter_poses(layers):
    from .character import POSES

    rest = {layer["id"]: layer for layer in layers}
    fitted = {}
    for pose, parts in POSES.items():
        out = {}
        for part, props in parts.items():
            if part not in rest or not isinstance(props, dict):
                continue
            out[part] = {prop: (round(float(rest[part].get(prop, 0)) + value, 5) if prop in ("x", "y") else value)
                         for prop, value in props.items()}
        fitted[pose] = out
    return fitted


def preview(image, masks):
    """Cut-out with each part tinted, to check the split at a glance."""
    colours = [(255, 90, 90), (90, 170, 255), (110, 220, 120), (255, 200, 60), (200, 120, 255), (60, 220, 220)]
    base = image.convert("RGBA")
    overlay = np.zeros((*base.size[::-1], 4), dtype=np.uint8)
    for index, mask in enumerate(masks.values()):
        overlay[mask] = (*colours[index % len(colours)], 90)
    sheet = Image.new("RGBA", (base.width * 2, base.height), (238, 241, 247, 255))
    sheet.alpha_composite(base, (0, 0))
    tinted = base.copy()
    tinted.alpha_composite(Image.fromarray(overlay, "RGBA"))
    sheet.alpha_composite(tinted, (base.width, 0))
    return sheet.convert("RGB")


def load_parts_dir(folder):
    """Separated layers on one shared canvas -> (composite image, masks)."""
    files = sorted(Path(folder).glob("*.png"))
    if not files:
        raise ValueError(f"No PNG layers in {folder}")
    images = {file.stem: Image.open(file).convert("RGBA") for file in files}
    size = next(iter(images.values())).size
    if any(image.size != size for image in images.values()):
        raise ValueError("Part layers must share one canvas size (export them from the same document)")
    if "body" not in images:
        raise ValueError("Part layers need a body.png")
    composite = Image.new("RGBA", size, (0, 0, 0, 0))
    order = sorted(images, key=lambda name: ORDER.index(name) if name in ORDER else len(ORDER))
    for name in order:
        composite.alpha_composite(images[name])
    alpha = np.asarray(composite)[..., 3] > 127
    ys, xs = np.nonzero(alpha)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    composite = composite.crop(box)
    # Each layer keeps its own pixels, so read colours from the layer, not the composite.
    masks = {}
    for name in order:
        part = np.asarray(images[name].crop(box))
        masks[name] = part[..., 3] > 127
    marks = {}
    if "head" in masks and masks["head"].any():
        marks["neck"] = int(np.nonzero(masks["head"])[0].max())
    legs = [masks[name] for name in ("leg-l", "leg-r") if name in masks and masks[name].any()]
    if legs:
        marks["hip"] = int(min(np.nonzero(leg)[0].min() for leg in legs))
    return composite, masks, marks, {name: images[name].crop(box) for name in order}


def _crop(cutout):
    alpha = np.asarray(cutout)[..., 3] > 127
    if not alpha.any():
        raise ValueError("The cut-out is empty: the background key removed everything (try another cutout method)")
    ys, xs = np.nonzero(alpha)
    return cutout.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def generate(channel_dir, spec_path, *, image=None, parts_dir=None, backend=None, seed=None, dry_run=False,
             report=None, rig_library=None):
    from .cutout import cut
    from .hardware import probe

    channel_dir = Path(channel_dir).resolve()
    spec_file = Path(spec_path) if Path(spec_path).is_absolute() else channel_dir / spec_path
    raw = json.loads(spec_file.read_text(encoding="utf-8"))
    if not raw.get("id"):
        raise ValueError("Art spec needs an id")
    spec = merged_spec(channel_dir, raw)
    if image:
        spec["image"] = str(image)
    if parts_dir:
        spec["parts_dir"] = str(parts_dir)
    if backend:
        spec["backend"] = backend
    if seed is not None:
        spec["seed"] = seed
    if report is None:
        from .machine import current

        report = {**probe(), "profile": current()}
    choice = plan(report, spec)
    if choice["backend"] in ("comfyui", "diffusers") and not spec.get("description"):
        raise ValueError("Art spec needs a description to generate from")
    if dry_run:
        return {"character": raw["id"], "plan": choice, "prompt": prompts(spec)[0] if choice["backend"] in
                ("comfyui", "diffusers") else None, "gpu": report.get("gpu")}
    if choice["backend"] == "procedural":
        from .character import generate as procedural

        fallback = {**{k: v for k, v in raw.items() if k not in ("description", "style", "negative", "seed",
                                                                    "model", "lora", "fallback", "backend")},
                    **(raw.get("fallback") or {}), "id": raw["id"]}
        folder = channel_dir / "art" / "characters" / raw["id"]
        folder.mkdir(parents=True, exist_ok=True)
        fallback_path = folder / "fallback-spec.json"
        fallback_path.write_text(json.dumps(fallback, indent=2) + "\n", encoding="utf-8")
        result = procedural(channel_dir, fallback_path, rig_library=rig_library)
        return {**result, "plan": choice}
    folder = f"art/characters/{raw['id']}"
    out = channel_dir / folder
    out.mkdir(parents=True, exist_ok=True)
    provenance = {"id": raw["id"], "backend": choice["backend"], "reason": choice["reason"]}
    piece_images = None
    if spec.get("parts_dir"):
        source_dir = Path(spec["parts_dir"])
        source_dir = source_dir if source_dir.is_absolute() else channel_dir / source_dir
        cutout, masks, marks, piece_images = load_parts_dir(source_dir)
        provenance["source"] = str(spec["parts_dir"])
    else:
        if spec.get("image"):
            source_path = Path(spec["image"])
            source_path = source_path if source_path.is_absolute() else channel_dir / source_path
            source = Image.open(source_path)
            provenance["source"] = str(spec["image"])
        else:
            key = cache_key(spec, choice)
            cached = out / f"source-{key}.png"
            if cached.is_file():
                source = Image.open(cached)
                provenance["cached"] = True
            else:
                source = generate_comfyui(spec, choice) if choice["backend"] == "comfyui" else \
                    generate_diffusers(spec, choice)
                source.save(cached)
            model = MODELS.get(choice["model"], {})
            provenance.update({"model": choice["model"], "checkpoint": choice.get("checkpoint") or model.get("repo"),
                               "license": model.get("license"), "commercial": model.get("commercial"),
                               "seed": int(spec.get("seed", 0)), "prompt": prompts(spec)[0],
                               "negative": prompts(spec)[1], "lora": spec.get("lora"), "cache": cached.name})
            if model.get("note"):
                provenance["license_note"] = model["note"]
        source.convert("RGB").save(out / "source.png")
        cutout, method = cut(source, spec.get("cutout", "auto"))
        provenance["cutout"] = method
        cutout = _crop(cutout)
        alpha = np.asarray(cutout)[..., 3] > 127
        masks, marks = split(alpha, spec.get("parts"))
    face = None
    if not piece_images and spec.get("face", True) is not False and "head" in masks:
        from .aiface import lift_face

        face = lift_face(cutout, masks, spec.get("face") if isinstance(spec.get("face"), dict) else None)
        if face:
            masks.update(face["masks"])
            piece_images = face["sources"]
            provenance["face"] = {key: face[key] for key in ("eyes", "mouth", "skin", "line")}
    cutout.save(out / "cutout.png")
    rig = build_rig(cutout, masks, marks, spec, folder, out, sources=piece_images)
    if face:
        from .aiface import mouth_layers

        mouths = mouth_layers(face, cutout, masks, marks, spec, folder, out)
        arms = [index for index, layer in enumerate(rig) if layer["role"] == "arm"]
        at = arms[0] if arms else len(rig)
        rig[at:at] = mouths  # Over the face, under the arms.
    preview(cutout, masks).save(out / "preview.png")
    provenance["parts"] = [layer["id"] for layer in rig]
    (out / "art.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    channel_path = channel_dir / "channel.json"
    channel = json.loads(channel_path.read_text(encoding="utf-8"))
    rig_name = rig_library or channel.get("rig_library") or "rigs.json"
    rig_path = channel_dir / rig_name
    library = json.loads(rig_path.read_text(encoding="utf-8")) if rig_path.is_file() else {"version": 1, "rigs": {}}
    library.setdefault("rigs", {})[raw["id"]] = rig
    library.setdefault("poses", {})[raw["id"]] = starter_poses(rig)
    rig_path.write_text(json.dumps(library, indent=2) + "\n", encoding="utf-8")
    linked = channel.get("rig_library") != rig_name
    if linked:
        channel["rig_library"] = rig_name
        channel_path.write_text(json.dumps(channel, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    talk = any(layer["role"] == "mouth" for layer in rig)
    return {"character": raw["id"], "plan": choice, "parts": [layer["id"] for layer in rig], "folder": folder,
            "rig_library": rig_name, "linked_rig_library": linked, "preview": f"{folder}/preview.png",
            "provenance": f"{folder}/art.json",
            "use": {"id": raw["id"], "kind": "use", "ref": raw["id"], "x": 0.5, "y": 0.86,
                    "alive": {"talk": "<speaker>"} if talk else True}}


def main():
    from .machine import apply

    apply()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("channel", type=Path, help="channel folder")
    parser.add_argument("--spec", required=True, help="art spec JSON, relative to the channel or absolute")
    parser.add_argument("--image", help="rig this image instead of generating one")
    parser.add_argument("--parts-dir", help="folder of separated PNG layers on one canvas")
    parser.add_argument("--backend", choices=("auto", "comfyui", "diffusers", "procedural"))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--rig-library")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without generating")
    args = parser.parse_args()
    try:
        result = generate(args.channel, args.spec, image=args.image, parts_dir=args.parts_dir,
                          backend=args.backend, seed=args.seed, dry_run=args.dry_run, rig_library=args.rig_library)
    except (OSError, ValueError, KeyError) as error:
        print(f"studio: {error}")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
