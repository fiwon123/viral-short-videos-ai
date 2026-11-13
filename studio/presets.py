"""Resolve a high-level style preset into concrete episode defaults."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE_DIR = ROOT / "presets" / "styles"


def load_style(name, channel_base=None):
    candidates = []
    if channel_base:
        candidates.append(Path(channel_base) / "presets" / "styles" / f"{name}.json")
    candidates.append(STYLE_DIR / f"{name}.json")
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"Unknown style preset: {name}")


def apply_style(episode, channel, channel_base=None):
    """Merge a preset under explicit episode values.

    A preset never overwrites a field the episode already declared. This keeps
    a single `style.preset` useful while allowing precise overrides.
    """
    style = {**(channel.get("style") or {}), **(episode.get("style") or {})}
    name = style.get("preset")
    if not name:
        return episode
    preset = load_style(name, channel_base)
    for key in ("post", "captions", "audio", "render", "music"):
        if key not in episode and key in preset:
            episode[key] = preset[key]
    for key in ("motion_blur", "supersample"):
        if key not in episode and key in preset:
            episode[key] = preset[key]
    if camera := preset.get("camera"):
        for scene in episode.get("scenes", []):
            for shot in scene.get("shots", []):
                shot.setdefault("camera", dict(camera))
    return episode
