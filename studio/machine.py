"""Fit the studio to this PC: detect it, pick safe defaults, and never overload it.

    python -m studio.hardware      # shows this profile and the art/video plans

Every heavy step reads ``profile()``: FFmpeg's x264 threads, Chromium render
workers, ONNX Runtime and torch threads, parallel batch jobs, and whether a
multi-minute AI generation may run on the CPU. Work also runs at below-normal
priority, so the PC stays usable while a video renders.

Tiers (from CPU cores, RAM and the best GPU):

=======  ==========================================  =======  ====  =======  ======
tier     when                                        threads  jobs  browser  CPU AI
=======  ==========================================  =======  ====  =======  ======
low      4 cores or fewer, or under 8 GB RAM          half     1     1        off
mid      everything else                              cores-2  1-2   2        off
high     a 12 GB+ GPU, or 12+ cores with 32+ GB RAM   cores-1  2-4   2-4      off
=======  ==========================================  =======  ====  =======  ======

Override any of it in the environment or ``.env`` (all optional):

``STUDIO_PROFILE``          low, mid or high instead of the detected tier
``STUDIO_THREADS``          CPU threads for encoders and models
``STUDIO_JOBS``             episodes rendered at once by ``batch``
``STUDIO_BROWSER_WORKERS``  Chromium workers per render
``STUDIO_NICE``             process niceness, 0 (normal) to 19 (lowest); default 10
``STUDIO_CPU_AI``           1 lets ``make art`` run an image model on the CPU (slow, minutes per image)
"""

import os
import platform

TIERS = ("low", "mid", "high")
_APPLIED = False


def memory_gb():
    """Total RAM in GB (Linux, macOS, Windows), or 0 when unknown."""
    try:
        if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
            return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except (OSError, ValueError):
        pass
    if platform.system() == "Windows":
        try:
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("free", ctypes.c_ulonglong), ("page_total", ctypes.c_ulonglong),
                            ("page_free", ctypes.c_ulonglong), ("virtual_total", ctypes.c_ulonglong),
                            ("virtual_free", ctypes.c_ulonglong), ("extended", ctypes.c_ulonglong)]
            status = Status()
            status.length = ctypes.sizeof(Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return round(status.total / 2**30, 1)
        except (OSError, AttributeError):
            pass
    return 0.0


def specs(gpu="detect"):
    """``{"cores", "ram_gb", "gpu"}`` for this machine (``gpu`` may be passed to skip detection)."""
    if gpu == "detect":
        from .hardware import probe_gpu

        gpu = probe_gpu()
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    return {"cores": max(1, cores), "ram_gb": memory_gb(), "gpu": gpu}


def _int(env, name, low, high):
    value = env.get(name)
    if value in (None, ""):
        return None
    try:
        return max(low, min(high, int(value)))
    except ValueError:
        raise ValueError(f"{name} must be a whole number, got {value!r}") from None


def profile(machine=None, env=None):
    """The budget for this machine: tier, threads, jobs, browser workers, niceness and AI switches."""
    env = os.environ if env is None else env
    machine = machine or specs()
    cores, ram = machine["cores"], machine["ram_gb"] or 8
    vram = float((machine.get("gpu") or {}).get("vram_gb") or 0)
    if cores <= 4 or ram < 8:
        tier = "low"
    elif vram >= 12 or (cores >= 12 and ram >= 32):
        tier = "high"
    else:
        tier = "mid"
    forced = (env.get("STUDIO_PROFILE") or "").strip().lower()
    if forced:
        if forced not in TIERS:
            raise ValueError(f"STUDIO_PROFILE must be one of {', '.join(TIERS)}, got {forced!r}")
        tier = forced
    threads = {"low": max(1, cores // 2), "mid": max(1, cores - 2), "high": max(1, cores - 1)}[tier]
    jobs = {"low": 1, "mid": 2 if ram >= 16 and cores >= 8 else 1, "high": max(2, min(4, cores // 4))}[tier]
    browser = {"low": 1, "mid": 2, "high": max(2, min(4, cores // 3))}[tier]
    result = {
        "tier": tier, "cores": cores, "ram_gb": machine["ram_gb"], "gpu": machine.get("gpu"),
        "threads": _int(env, "STUDIO_THREADS", 1, 256) or threads,
        "jobs": _int(env, "STUDIO_JOBS", 1, 64) or jobs,
        "browser_workers": _int(env, "STUDIO_BROWSER_WORKERS", 1, 32) or browser,
        "nice": _int(env, "STUDIO_NICE", 0, 19) if env.get("STUDIO_NICE") not in (None, "") else 10,
        "cpu_ai": env.get("STUDIO_CPU_AI", "").strip().lower() in ("1", "true", "yes", "on"),
        "gpu_ai": vram >= 4,
    }
    result["overrides"] = sorted(name for name in ("STUDIO_PROFILE", "STUDIO_THREADS", "STUDIO_JOBS",
                                                   "STUDIO_BROWSER_WORKERS", "STUDIO_NICE", "STUDIO_CPU_AI")
                                 if env.get(name) not in (None, ""))
    return result


_CACHED = None


def current():
    """The profile for this process (detected once)."""
    global _CACHED
    if _CACHED is None:
        _CACHED = profile()
    return _CACHED


def apply(budget=None):
    """Lower this process's priority and cap library threads; child processes inherit both. Idempotent."""
    global _APPLIED
    budget = budget or current()
    if _APPLIED:
        return budget
    _APPLIED = True
    threads = str(budget["threads"])
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
                 "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(name, threads)
    os.environ.setdefault("STUDIO_BROWSER_WORKERS", str(budget["browser_workers"]))
    nice = budget["nice"]
    if nice:
        try:
            if hasattr(os, "nice"):
                current_nice = os.nice(0)
                if current_nice < nice:
                    os.nice(nice - current_nice)
            elif platform.system() == "Windows":
                import ctypes

                below_normal = 0x00004000
                ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), below_normal)
        except (OSError, AttributeError):
            pass
    return budget


def x264_threads():
    """FFmpeg arguments that cap the H.264 encoder to the budget."""
    return ["-threads", str(current()["threads"])]


def onnx_options():
    """ONNX Runtime session options with the thread budget."""
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = current()["threads"]
    options.inter_op_num_threads = 1
    return options
