"""Hero clips: turn a still into a short AI video for the hook, with a 2.5D fallback.

    python -m studio.heroclip <episode.json> --shot A [--image start.png] [--prompt "the fox leaps"]
        [--seconds 4] [--seed 7] [--workflow wan-i2v-api.json] [--backend auto|comfyui|diffusers|parallax]
        [--channel channel.json] [--dry-run]

The start image is ``--image`` (inserted under the shot's layers as a moving
background plate) or, when omitted, the shot's own first frame rendered with
``video.py still`` (inserted over the shot, so the clip replaces its look; the
other layers stay in the manifest for later edits and captions still burn on top).
``--keep title,subtitle`` leaves those layers out of the start frame and above the
clip, so a hook title stays sharp instead of being warped by the video model.

Backends, best first (``python -m studio.hardware`` shows what is found):

* ``comfyui`` with a workflow you exported from ComfyUI (**Save (API)**) and
  passed as ``--workflow``. Any string value equal to ``{{image}}``, ``{{prompt}}``,
  ``{{negative}}``, ``{{seed}}``, ``{{frames}}``, ``{{width}}``, ``{{height}}`` or
  ``{{fps}}`` is replaced (numbers become numbers). Use it for Wan 2.1/2.2 14B,
  LTX-Video or anything else ComfyUI runs.
* ``comfyui`` with the built-in Wan 2.2 TI2V 5B graph (Apache-2.0, about 8 GB VRAM
  with ComfyUI's offloading) when its files are installed:
  ``wan2.2_ti2v_5B_fp16.safetensors`` (diffusion_models), ``umt5_xxl_fp8_e4m3fn_scaled.safetensors``
  (text_encoders) and ``wan2.2_vae.safetensors`` (vae).
* ``diffusers`` LTX-Video image-to-video on a GPU with 12 GB or more (check the
  model card's licence for commercial use).
* ``parallax``: no video model. The image is split into depth layers
  (``studio/depthphoto.py``) that push in, nearer layers more (a dolly without a
  camera, so kept layers and captions stay put). Runs anywhere; ``make art-models``
  downloads Depth Anything V2 Small, which gives much cleaner layers than the rough guess.

The frames are encoded as ``art/hero/<name>/clip-<key>.mp4`` at the model's size
and inserted as a ``video`` layer (``studio/videolayer.py``) that plays once and
holds its last frame. Results are cached
by image, prompt, seed, model and length; ``clip.json`` records the backend,
model, licence, seed and prompt.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
WAN = {"unet": "wan2.2_ti2v_5b", "clip": "umt5_xxl", "vae": "wan2.2_vae", "node": "Wan22ImageToVideoLatent",
       "license": "Apache-2.0", "fps": 24, "step": 4, "max_seconds": 5}
LTX = {"repo": "Lightricks/LTX-Video", "license": "LTX-Video licence (see the model card)", "fps": 24, "step": 8,
       "max_seconds": 5}
NEGATIVE = "blurry, distorted, warped face, extra limbs, flicker, text, watermark, static, still frame"
PLACEHOLDERS = ("image", "prompt", "negative", "seed", "frames", "width", "height", "fps")


# ---------------------------------------------------------------- planning

def _pick(names, needle):
    return next((name for name in names or [] if needle in name.lower()), None)


def plan(report, options):
    """``{"backend", ...}`` for this machine and request, with a reason."""
    backend = options.get("backend") or "auto"
    comfy = report.get("comfyui")
    gpu = report.get("gpu") or {}
    vram = float(gpu.get("vram_gb") or 0)
    if comfy and backend in ("auto", "comfyui"):
        if options.get("workflow"):
            return {"backend": "comfyui", "graph": "workflow", "url": comfy["url"], "fps": options.get("fps", 24),
                    "step": 1, "max_seconds": 10, "model": "workflow", "license": "see the workflow's models",
                    "reason": f"ComfyUI with workflow {Path(options['workflow']).name}"}
        video = comfy.get("video") or {}
        files = {"unet": _pick(video.get("unets"), WAN["unet"]), "clip": _pick(video.get("clips"), WAN["clip"]),
                 "vae": _pick(video.get("vaes"), WAN["vae"])}
        if video.get("wan_node") and all(files.values()):
            return {"backend": "comfyui", "graph": "wan22-5b", "url": comfy["url"], "files": files,
                    "fps": WAN["fps"], "step": WAN["step"], "max_seconds": WAN["max_seconds"],
                    "model": "wan2.2-ti2v-5b", "license": WAN["license"],
                    "reason": f"ComfyUI has Wan 2.2 TI2V 5B ({files['unet']})"}
        if backend == "comfyui":
            missing = [name for name, value in files.items() if not value]
            raise ValueError("ComfyUI has no usable video model: pass --workflow, or install Wan 2.2 TI2V 5B "
                             f"(missing: {', '.join(missing) or WAN['node'] + ' node'})")
    if report.get("diffusers") and backend in ("auto", "diffusers"):
        if gpu and vram >= 12:
            device = "mps" if gpu.get("vendor") == "apple" else "cuda"
            return {"backend": "diffusers", "device": device, "model": "ltx-video", "repo": LTX["repo"],
                    "license": LTX["license"], "fps": LTX["fps"], "step": LTX["step"],
                    "max_seconds": LTX["max_seconds"], "reason": f"diffusers LTX-Video on {gpu.get('name')}"}
        if backend == "diffusers":
            raise ValueError("diffusers video needs a GPU with 12 GB or more")
    if backend not in ("auto", "parallax"):
        raise ValueError(f"The {backend} video backend is not available on this machine")
    return {"backend": "parallax", "model": "depth layers + push-in keys", "license": "n/a",
            "reason": "no local video model found; using 2.5D depth parallax"}


def probe_video(comfy):
    """Add the video model files and nodes a ComfyUI install has to its probe."""
    from .hardware import get_json

    url = comfy["url"]
    video = {}
    for node, field, key in (("UNETLoader", "unet_name", "unets"), ("CLIPLoader", "clip_name", "clips"),
                             ("VAELoader", "vae_name", "vaes")):
        try:
            spec = get_json(f"{url}/object_info/{node}")[node]["input"]["required"][field]
            video[key] = list(spec[0]) if spec and isinstance(spec[0], list) else []
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            video[key] = []
    try:
        video["wan_node"] = bool(get_json(f"{url}/object_info/{WAN['node']}"))
    except (OSError, ValueError):
        video["wan_node"] = False
    comfy["video"] = video
    return comfy


def frame_count(seconds, choice):
    """Frames to request: the model's step pattern (4n+1 for Wan, 8n+1 for LTX), capped to its length."""
    seconds = max(0.5, min(float(seconds), choice.get("max_seconds", 5)))
    step = int(choice.get("step", 1))
    frames = round(seconds * choice.get("fps", 24))
    return frames if step <= 1 else (frames // step) * step + 1


def clip_size(canvas, longest=832):
    """Generation size with the episode's aspect, a multiple of 32, longest side ``longest``."""
    width, height = canvas
    scale = longest / max(width, height)
    return max(32, round(width * scale / 32) * 32), max(32, round(height * scale / 32) * 32)


# ---------------------------------------------------------------- comfyui

def wan_graph(choice, image_name, prompt, negative, seed, frames, size):
    files = choice["files"]
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": files["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": files["clip"], "type": "wan"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": files["vae"]}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "7": {"class_type": "Wan22ImageToVideoLatent",
              "inputs": {"vae": ["3", 0], "width": size[0], "height": size[1], "length": frames, "batch_size": 1,
                         "start_image": ["4", 0]}},
        "8": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "9": {"class_type": "KSampler",
              "inputs": {"model": ["8", 0], "seed": seed, "steps": 20, "cfg": 5.0, "sampler_name": "uni_pc",
                         "scheduler": "simple", "positive": ["5", 0], "negative": ["6", 0],
                         "latent_image": ["7", 0], "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "studio-hero"}},
    }


def fill_workflow(workflow, values):
    """Replace ``{{name}}`` placeholder strings anywhere in an API-format workflow."""
    if isinstance(workflow, dict):
        return {key: fill_workflow(value, values) for key, value in workflow.items()}
    if isinstance(workflow, list):
        return [fill_workflow(value, values) for value in workflow]
    if isinstance(workflow, str):
        for name in PLACEHOLDERS:
            token = "{{" + name + "}}"
            if workflow == token:
                return values[name]
            if token in workflow:
                workflow = workflow.replace(token, str(values[name]))
    return workflow


def upload_image(url, image):
    boundary = uuid.uuid4().hex
    buffer = BytesIO()
    image.save(buffer, "PNG")
    name = f"studio-hero-{hashlib.sha256(buffer.getvalue()).hexdigest()[:12]}.png"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + buffer.getvalue() + \
        (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
         f"--{boundary}--\r\n").encode()
    request = urllib.request.Request(f"{url}/upload/image", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - local ComfyUI
        data = json.loads(response.read())
    return f"{data['subfolder']}/{data['name']}" if data.get("subfolder") else data["name"]


def run_comfy(url, graph, timeout=3600):
    """Queue ``graph`` and return every output image, in order."""
    body = json.dumps({"prompt": graph, "client_id": str(uuid.uuid4())}).encode()
    request = urllib.request.Request(f"{url}/prompt", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        prompt_id = json.loads(response.read())["prompt_id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with urllib.request.urlopen(f"{url}/history/{prompt_id}", timeout=30) as response:  # noqa: S310
            entry = json.loads(response.read()).get(prompt_id)
        if entry:
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise ValueError(f"ComfyUI failed: {status.get('messages')}")
            frames = []
            for output in (entry.get("outputs") or {}).values():
                for item in output.get("images") or []:
                    query = urllib.parse.urlencode({"filename": item["filename"], "subfolder": item.get("subfolder", ""),
                                                    "type": item.get("type", "output")})
                    with urllib.request.urlopen(f"{url}/view?{query}", timeout=60) as response:  # noqa: S310
                        frames.append(Image.open(BytesIO(response.read())).convert("RGB"))
            if frames:
                return frames
            if status.get("completed"):
                raise ValueError("ComfyUI finished without image outputs (end the workflow with SaveImage)")
        time.sleep(1.0)
    raise ValueError(f"ComfyUI did not finish within {timeout} s")


def generate_diffusers(choice, image, prompt, negative, seed, frames, size):  # pragma: no cover - needs a GPU
    import torch
    from diffusers import LTXImageToVideoPipeline

    pipe = LTXImageToVideoPipeline.from_pretrained(choice["repo"], torch_dtype=torch.bfloat16)
    if choice["device"] == "cuda":
        pipe.enable_model_cpu_offload()
    else:
        pipe = pipe.to(choice["device"])
    result = pipe(image=image.resize(size), prompt=prompt, negative_prompt=negative, width=size[0], height=size[1],
                  num_frames=frames, num_inference_steps=40,
                  generator=torch.Generator("cpu").manual_seed(seed))
    return [frame.convert("RGB") for frame in result.frames[0]]


# ---------------------------------------------------------------- encoding and insertion

def write_clip(frames, fps, path):
    """Encode frames as a high-quality H.264 MP4 (even dimensions, no audio)."""
    from .core import run

    width, height = frames[0].size
    width, height = width - width % 2, height - height % 2
    data = b"".join(frame.convert("RGB").resize((width, height)).tobytes() for frame in frames)
    run("ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
        "-r", f"{fps:g}", "-i", "-", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "14",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path), data=data)


def video_layer(name, file):
    """A full-frame video layer; the video expander plays it once and holds the last frame."""
    return {"id": f"hero-{name}", "kind": "video", "file": file, "x": 0.5, "y": 0.5, "width": 1.0, "height": 1.0,
            "fit": "cover", "hero_clip": name}


def _shot(episode, shot_id):
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot["id"] == shot_id:
                return shot
    raise ValueError(f"Unknown shot: {shot_id}")


def first_frame(episode_path, shot_id, channel, out, keep=()):
    """The shot's first frame, without the ``keep`` layers (they stay crisp above the clip)."""
    episode = json.loads(Path(episode_path).read_text(encoding="utf-8"))
    shot = _shot(episode, shot_id)
    for layer in shot.get("layers", []):
        if layer["id"] in keep or layer.get("hero_clip") or str(layer.get("depth_photo", "")).startswith("hero-"):
            layer.update({"opacity": 0, "keyframes": []})  # Hidden, not removed: other fields may name them.
    temp = Path(episode_path).with_name(f".hero-start-{uuid.uuid4().hex[:8]}.json")
    temp.write_text(json.dumps(episode), encoding="utf-8")
    command = [sys.executable, str(ROOT / "video.py"), "still", str(temp), "--shot", shot_id, "--at", "0",
               "--no-audio", "--no-captions", "--out", str(out)]
    if channel:
        command += ["--channel", str(channel)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    finally:
        temp.unlink(missing_ok=True)
    if result.returncode or not Path(out).is_file():
        raise ValueError(f"Could not render the shot's first frame: {(result.stdout + result.stderr)[-800:]}")
    return Image.open(out).convert("RGB")


def place(layers, ours, over, keep=()):
    """Under everything (a background plate), or over the shot with only the ``keep`` layers above it."""
    rest = [layer for layer in layers if layer not in ours]
    if not over:
        return ours + rest
    return [layer for layer in rest if layer["id"] not in keep] + ours + [layer for layer in rest if layer["id"] in keep]


def push_keys(layers, strength=0.1):
    """A 2.5D push without a camera: nearer depth layers grow more (the dolly look), text stays put."""
    far = max(float(layer.get("z", 0)) for layer in layers) or 1.0
    for layer in layers:
        near = 1 - float(layer.get("z", 0)) / far
        layer["keyframes"] = [{"at": 0, "scale": 1}, {"at": 1, "scale": round(1 + strength * (0.25 + 0.75 * near), 4),
                                                       "ease": "sine"}]
    return layers


def run(episode_path, shot_id, *, image=None, prompt="", seconds=None, seed=0, workflow=None, backend=None,
        channel=None, name=None, keep=(), dry_run=False, report=None):
    from .hardware import probe

    episode_path = Path(episode_path).resolve()
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    shot = _shot(episode, shot_id)
    keep = set(keep or ())
    unknown = keep - {layer["id"] for layer in shot.get("layers", [])}
    if unknown:
        raise ValueError(f"--keep names layers that are not in {shot_id}: {', '.join(sorted(unknown))}")
    shot_seconds = float(shot["duration"])
    canvas = (int(episode.get("width", 1080)), int(episode.get("height", 1920)))
    if report is None:
        report = probe()
        if report.get("comfyui"):
            probe_video(report["comfyui"])
    options = {"backend": backend, "workflow": workflow, "fps": int(episode.get("fps", 24))}
    choice = plan(report, options)
    name = name or f"{shot_id.lower()}"
    if dry_run:
        return {"shot": shot_id, "plan": choice, "start": str(image) if image else "the shot's first frame"}
    folder = episode_path.parent / "art" / "hero" / name
    folder.mkdir(parents=True, exist_ok=True)
    over = image is None
    if image is not None:
        start = ImageOps.exif_transpose(Image.open(image)).convert("RGB")
    else:
        start = first_frame(episode_path, shot_id, channel, folder / "start.png", keep)
    if choice["backend"] == "parallax":
        from .depthphoto import run as depth_run

        start_path = folder / "start.png"
        start.save(start_path)
        result = depth_run(episode_path, start_path, name=f"hero-{name}", shot_id=shot_id)
        episode = json.loads(episode_path.read_text(encoding="utf-8"))
        shot = _shot(episode, shot_id)
        ours = push_keys([layer for layer in shot["layers"] if layer.get("depth_photo") == f"hero-{name}"])
        if over:
            # Renderers sort by z far-to-near, which would put the far plate behind the shot it replaces.
            # The push keys already carry the depth, so list order decides here.
            for layer in ours:
                layer.pop("z", None)
        shot["layers"] = place(shot["layers"], ours, over, keep)
        episode_path.write_text(json.dumps(episode, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        record = {"backend": "parallax", "reason": choice["reason"], "depth": result["method"],
                  "layers": [layer["id"] for layer in ours], "kept_above": sorted(keep)}
        (folder / "clip.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return {"shot": shot_id, "plan": choice, **record}
    frames_wanted = frame_count(seconds or shot_seconds, choice)
    size = clip_size(canvas)
    negative = NEGATIVE
    key_data = {"image": hashlib.sha256(start.tobytes()).hexdigest(), "prompt": prompt, "seed": seed,
                "model": choice["model"], "frames": frames_wanted, "size": size,
                "workflow": hashlib.sha256(Path(workflow).read_bytes()).hexdigest() if workflow else None}
    key = hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()[:16]
    clip_path = folder / f"clip-{key}.mp4"
    meta_path = folder / f"clip-{key}.json"
    if clip_path.is_file() and meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        if choice["backend"] == "comfyui":
            uploaded = upload_image(choice["url"], start.resize(size, Image.Resampling.LANCZOS))
            if choice["graph"] == "workflow":
                values = {"image": uploaded, "prompt": prompt, "negative": negative, "seed": seed,
                          "frames": frames_wanted, "width": size[0], "height": size[1], "fps": choice["fps"]}
                graph = fill_workflow(json.loads(Path(workflow).read_text(encoding="utf-8")), values)
            else:
                graph = wan_graph(choice, uploaded, prompt, negative, seed, frames_wanted, size)
            frames = run_comfy(choice["url"], graph)
        else:
            frames = generate_diffusers(choice, start, prompt, negative, seed, frames_wanted, size)
        write_clip(frames, choice["fps"], clip_path)
        meta = {"count": len(frames), "fps": choice["fps"], "size": list(frames[0].size)}
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")
    clip_seconds = meta["count"] / meta["fps"]
    file = str(clip_path.relative_to(episode_path.parent))
    layer = video_layer(name, file)
    kept = [item for item in shot.get("layers", []) if item.get("hero_clip") != name]
    shot["layers"] = place(kept, [layer], over, keep)
    episode_path.write_text(json.dumps(episode, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    record = {"backend": choice["backend"], "model": choice["model"], "license": choice["license"],
              "reason": choice["reason"], "seed": seed, "prompt": prompt, "frames": meta["count"],
              "seconds": round(clip_seconds, 2), "clip": file, "placed": "over the shot" if over else "under the shot",
              "kept_above": sorted(keep)}
    (folder / "clip.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return {"shot": shot_id, "plan": choice, **record}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--shot", required=True)
    parser.add_argument("--image", type=Path, help="start image (default: the shot's first frame)")
    parser.add_argument("--prompt", default="", help="the motion to see, for example 'the fox leaps over the fence'")
    parser.add_argument("--seconds", type=float, help="clip length (default: the shot, capped by the model)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workflow", type=Path, help="ComfyUI API workflow with {{placeholders}}")
    parser.add_argument("--backend", choices=("auto", "comfyui", "diffusers", "parallax"))
    parser.add_argument("--channel", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--keep", default="", help="comma separated layer ids to keep crisp above the clip (hook titles)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args.episode, args.shot, image=args.image, prompt=args.prompt, seconds=args.seconds,
                     seed=args.seed, workflow=args.workflow, backend=args.backend, channel=args.channel,
                     name=args.name, keep=[item for item in args.keep.split(",") if item], dry_run=args.dry_run)
    except (OSError, ValueError, KeyError) as error:
        print(f"studio: {error}")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
