"""Non-blocking warnings about authoring that silently does less than it says.

Validation rejects broken input; lint flags input that renders but probably
isn't what the author meant, so an AI author can fix it before a render.
"""

MAX_PARTICLES = 300


def lint(source, expanded):
    """Return a list of human-readable warnings."""
    warnings = []
    fps = float(source.get("fps", 24))
    for scene in source.get("scenes", []):
        for shot in scene.get("shots", []):
            duration = float(shot.get("duration", 1))
            for layer in shot.get("layers", []):
                if layer.get("kind") == "particles":
                    count = int(layer.get("count") or max(1, round(float(layer.get("rate", 30)) * duration)))
                    if count > MAX_PARTICLES:
                        warnings.append(f"{shot['id']}/{layer['id']}: {count} particles requested; only "
                                        f"{MAX_PARTICLES} render. Lower rate or split into two emitters.")
            camera = shot.get("camera") or {}
            if not shot.get("three") and any("fov" in key for key in camera.get("keyframes", [])):
                warnings.append(f"{shot['id']}: 2D camera keys ignore fov; use zoom (or a three camera).")
    for scene in expanded.get("scenes", []):
        for shot in scene.get("shots", []):
            duration = float(shot.get("duration", 1))
            frame = 1 / (fps * max(duration, 1e-6))
            for layer in shot.get("layers", []):
                times = [float(key["at"]) for key in layer.get("keyframes", [])]
                close = [(a, b) for a, b in zip(times, times[1:]) if b - a < frame * 0.9]
                if close:
                    a, b = close[0]
                    warnings.append(f"{shot['id']}/{layer['id']}: keys at {a:g} and {b:g} are under one frame "
                                    f"apart in a {duration:g}s shot, so the change snaps. Space them or "
                                    f"use a hold ease.")
    return warnings
