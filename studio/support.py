"""Single source of truth for renderer feature support.

The Python renderer is intentionally the raster-2D path. HyperFrames and
Remotion both cover the full browser path. Anything outside that contract is
listed here so the studio never silently pretends two renderers match.
"""

from .renderers import RENDERER_NAMES as RENDERERS

SUPPORT = {
    "layers.rect": {"python": True, "hyperframes": True, "remotion": True},
    "layers.ellipse": {"python": True, "hyperframes": True, "remotion": True},
    "layers.polygon": {"python": True, "hyperframes": True, "remotion": True},
    "layers.text": {"python": True, "hyperframes": True, "remotion": True},
    "layers.image": {"python": True, "hyperframes": True, "remotion": True},
    "layers.svg": {"python": False, "hyperframes": True, "remotion": True},
    "layers.sheet": {"python": True, "hyperframes": True, "remotion": True},
    "layers.group": {"python": True, "hyperframes": True, "remotion": True},
    "layers.parent_pivot": {"python": True, "hyperframes": True, "remotion": True},
    "layers.visible_variants": {"python": True, "hyperframes": True, "remotion": True},
    "layers.blend": {"python": True, "hyperframes": True, "remotion": True},
    "layers.blur": {"python": True, "hyperframes": True, "remotion": True},
    "layers.mask": {"python": True, "hyperframes": True, "remotion": True},
    "layers.scale_x_y": {"python": True, "hyperframes": True, "remotion": True},
    "layers.skew": {"python": True, "hyperframes": True, "remotion": True},
    "layers.gradient": {"python": True, "hyperframes": True, "remotion": True},
    "layers.stroke": {"python": True, "hyperframes": True, "remotion": True},
    "layers.shadow_glow": {"python": True, "hyperframes": True, "remotion": True},
    "layers.tint": {"python": True, "hyperframes": True, "remotion": True},
    "layers.motion_blur": {"python": True, "hyperframes": True, "remotion": True},
    "layers.trail": {"python": True, "hyperframes": True, "remotion": True},
    "layers.use": {"python": True, "hyperframes": True, "remotion": True},
    "text.fonts": {"python": True, "hyperframes": True, "remotion": True},
    "text.typography": {"python": True, "hyperframes": True, "remotion": True},
    "text.reveal": {"python": True, "hyperframes": True, "remotion": True},
    "easings": {"python": True, "hyperframes": True, "remotion": True},
    "easings.cubic-bezier": {"python": True, "hyperframes": True, "remotion": True},
    "easings.spring-object": {"python": True, "hyperframes": True, "remotion": True},
    "easings.auto": {"python": True, "hyperframes": True, "remotion": True},
    "easings.per-property": {"python": True, "hyperframes": True, "remotion": True},
    "camera.keyframes": {"python": True, "hyperframes": True, "remotion": True},
    "camera.presets": {"python": True, "hyperframes": True, "remotion": True},
    "camera.shake": {"python": True, "hyperframes": True, "remotion": True},
    "camera.track": {"python": True, "hyperframes": True, "remotion": True},
    "post.grade": {"python": True, "hyperframes": True, "remotion": True},
    "post.bloom": {"python": True, "hyperframes": True, "remotion": True},
    "post.grain": {"python": True, "hyperframes": True, "remotion": True},
    "post.vignette": {"python": True, "hyperframes": True, "remotion": True},
    "post.chromatic": {"python": True, "hyperframes": True, "remotion": True},
    "transitions.basic": {"python": True, "hyperframes": True, "remotion": True},
    "transitions.luma-wipe": {"python": True, "hyperframes": True, "remotion": True},
    "transitions.mask": {"python": True, "hyperframes": True, "remotion": True},
    "captions.box": {"python": True, "hyperframes": True, "remotion": True},
    "captions.karaoke": {"python": True, "hyperframes": True, "remotion": True},
    "captions.minimal": {"python": True, "hyperframes": True, "remotion": True},
    "captions.animation": {"python": True, "hyperframes": True, "remotion": True},
    "captions.layout": {"python": True, "hyperframes": True, "remotion": True},
    "captions.palette-roles": {"python": True, "hyperframes": True, "remotion": True},
    "captions.fade-rise": {"python": True, "hyperframes": True, "remotion": True},
    "thumbnails.styles": {"python": True, "hyperframes": True, "remotion": True},
    "thumbnails.variants": {"python": True, "hyperframes": True, "remotion": True},
    "audio.master": {"python": True, "hyperframes": True, "remotion": True},
    "audio.stems": {"python": True, "hyperframes": True, "remotion": True},
    "audio.cross_cut": {"python": True, "hyperframes": True, "remotion": True},
    "particles.2d": {"python": True, "hyperframes": True, "remotion": True},
    "three.primitives": {"python": False, "hyperframes": True, "remotion": True},
    "three.glb": {"python": False, "hyperframes": True, "remotion": True},
    "three.clip-playback": {"python": False, "hyperframes": True, "remotion": True},
    "three.clip-blending": {"python": False, "hyperframes": True, "remotion": True},
    "three.fov-keys": {"python": False, "hyperframes": True, "remotion": True},
    "three.focus-pull": {"python": False, "hyperframes": True, "remotion": True},
    "three.bloom": {"python": False, "hyperframes": True, "remotion": True},
    "three.particles": {"python": False, "hyperframes": True, "remotion": True},
    "alignment.words": {"python": True, "hyperframes": True, "remotion": True},
    "visemes": {"python": True, "hyperframes": True, "remotion": True},
    "review.still": {"python": True, "hyperframes": True, "remotion": True},
    "review.contact-sheet": {"python": True, "hyperframes": True, "remotion": True},
}


def matrix():
    return {
        "renderers": list(RENDERERS),
        "features": {name: dict(value) for name, value in SUPPORT.items()},
    }


def unsupported(renderer, feature):
    return not SUPPORT.get(feature, {}).get(renderer, False)


def markdown():
    rows = ["# Renderer Support Matrix", "",
            "| Feature | Python | HyperFrames | Remotion |",
            "| --- | --- | --- | --- |"]
    for name, values in SUPPORT.items():
        marks = [("✅" if values[renderer] else "❌") for renderer in RENDERERS]
        rows.append(f"| `{name}` | {' | '.join(marks)} |")
    rows.extend(["", "Python is the raster-2D path. SVG, Three.js and browser-only",
                 "finishing are marked honestly rather than approximated."])
    return "\n".join(rows) + "\n"
