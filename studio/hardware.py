"""What can this machine generate art with? Probe GPUs, ComfyUI and Python ML packages.

    python -m studio.hardware          # JSON report and the plan ``make art`` would use

Nothing here imports torch unless it is installed, and every probe has a short
timeout, so the report is safe to run on any machine (the sandbox has no GPU).
Detection order for the GPU: a running ComfyUI's own ``/system_stats`` (it knows
the device it renders on), ``nvidia-smi``, ``rocm-smi``, ``torch``, then Apple
silicon (unified memory, used through MPS).
"""

import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request

COMFYUI_URL = "http://127.0.0.1:8188"


def _run(*args, timeout=4):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _importable(name):
    import importlib.util

    return importlib.util.find_spec(name) is not None


def comfyui_url():
    return os.environ.get("STUDIO_COMFYUI_URL", COMFYUI_URL).rstrip("/")


def get_json(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - local ComfyUI only
        return json.loads(response.read().decode("utf-8"))


def probe_comfyui(url=None):
    """``{"url", "devices", "checkpoints", "loras"}`` for a reachable ComfyUI, else None."""
    url = (url or comfyui_url()).rstrip("/")
    try:
        stats = get_json(f"{url}/system_stats")
    except (OSError, ValueError, urllib.error.URLError):
        return None
    info = {"url": url, "devices": [], "checkpoints": [], "loras": []}
    for device in stats.get("devices") or []:
        info["devices"].append({"name": device.get("name", ""), "type": device.get("type", ""),
                                "vram_gb": round(float(device.get("vram_total", 0)) / 2**30, 1)})
    for node, field, key in (("CheckpointLoaderSimple", "ckpt_name", "checkpoints"),
                             ("LoraLoader", "lora_name", "loras")):
        try:
            spec = get_json(f"{url}/object_info/{node}")[node]["input"]["required"][field]
            info[key] = list(spec[0]) if spec and isinstance(spec[0], list) else []
        except (OSError, ValueError, KeyError, IndexError, TypeError, urllib.error.URLError):
            pass
    return info


def probe_gpu():
    """``{"vendor", "name", "vram_gb", "source"}`` for the best local GPU, else None."""
    if shutil.which("nvidia-smi"):
        rows = _run("nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits")
        gpus = []
        for row in rows.strip().splitlines():
            name, _, memory = row.rpartition(",")
            try:
                gpus.append({"vendor": "nvidia", "name": name.strip(), "vram_gb": round(float(memory) / 1024, 1),
                             "source": "nvidia-smi"})
            except ValueError:
                continue
        if gpus:
            return max(gpus, key=lambda gpu: gpu["vram_gb"])
    if shutil.which("rocm-smi"):
        out = _run("rocm-smi", "--showmeminfo", "vram", "--json")
        try:
            cards = json.loads(out or "{}")
            sizes = [float(value) for card in cards.values() for key, value in card.items()
                     if "total" in key.lower() and "used" not in key.lower()]
            if sizes:
                return {"vendor": "amd", "name": "ROCm GPU", "vram_gb": round(max(sizes) / 2**30, 1),
                        "source": "rocm-smi"}
        except (ValueError, AttributeError):
            pass
    if _importable("torch"):
        try:
            import torch

            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                vendor = "amd" if getattr(torch.version, "hip", None) else "nvidia"
                return {"vendor": vendor, "name": props.name, "vram_gb": round(props.total_memory / 2**30, 1),
                        "source": "torch"}
        except Exception:  # noqa: BLE001 - a broken torch install must not break the report
            pass
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        memory = _run("sysctl", "-n", "hw.memsize")
        total = round(int(memory) / 2**30, 1) if memory.strip().isdigit() else 0
        # Unified memory: about two thirds is usable by the GPU.
        return {"vendor": "apple", "name": "Apple silicon", "vram_gb": round(total * 0.66, 1), "source": "sysctl"}
    return None


def probe(comfy=True):
    report = {"gpu": probe_gpu(), "comfyui": probe_comfyui() if comfy else None,
              "diffusers": _importable("diffusers") and _importable("torch"),
              "rembg": _importable("rembg"), "onnxruntime": _importable("onnxruntime")}
    if report["comfyui"] and report["comfyui"]["devices"] and not report["gpu"]:
        best = max(report["comfyui"]["devices"], key=lambda device: device["vram_gb"])
        if best["type"] not in ("cpu", ""):
            report["gpu"] = {"vendor": best["type"], "name": best["name"], "vram_gb": best["vram_gb"],
                             "source": "comfyui"}
    return report


def main():
    from .aiart import plan

    report = probe()
    report["plan"] = plan(report, {})
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
