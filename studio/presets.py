"""Resolve a high-level style preset into concrete episode defaults."""

import json
from pathlib import Path

from .core import validate

ROOT = Path(__file__).resolve().parents[1]
STYLE_DIR = ROOT / "presets" / "styles"


def available_styles(channel_base=None):
    found = {}
    folders = [Path(channel_base) / "presets" / "styles"] if channel_base else []
    folders.append(STYLE_DIR)
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            found.setdefault(path.stem, path)
    return found


def deep_merge(base, override):
    """Recursive merge where later values win. Arrays replace as a unit."""
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override if override is not None else base
    result = {**base}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_style(name, channel_base=None):
    candidates = []
    if channel_base:
        candidates.append(Path(channel_base) / "presets" / "styles" / f"{name}.json")
    candidates.append(STYLE_DIR / f"{name}.json")
    for path in candidates:
        if path.is_file():
            preset = json.loads(path.read_text(encoding="utf-8"))
            return validate(preset, "style_preset", f"Style preset {path.name}")
    found = available_styles(channel_base)
    names = ", ".join(sorted(found)) or "none"
    raise ValueError(f"Unknown style preset: {name}. Available: {names}")


def apply_style(episode, channel, channel_base=None):
    """Merge a preset under channel defaults and explicit episode values.

    Precedence: preset < channel defaults < episode overrides < shot overrides.
    A single episode field can now override one preset field without replacing
    the whole block.
    """
    style = {**(channel.get("style") or {}), **(episode.get("style") or {})}
    name = style.get("preset")
    if not name:
        return episode
    preset = load_style(name, channel_base)
    for key in ("post", "captions", "audio", "render", "music"):
        base = preset.get(key)
        channel_value = channel.get(key)
        episode_value = episode.get(key)
        merged = {}
        for part in (base, channel_value, episode_value):
            if isinstance(part, dict):
                merged = deep_merge(merged, part)
            elif part is not None:
                merged = part
        if merged:
            episode[key] = merged
    for key in ("motion_blur", "supersample"):
        if key not in episode:
            if key in channel:
                episode[key] = channel[key]
            elif key in preset:
                episode[key] = preset[key]
    if camera := preset.get("camera"):
        for scene in episode.get("scenes", []):
            for shot in scene.get("shots", []):
                shot["camera"] = deep_merge(camera, shot.get("camera") or {})
    return episode


def resolved_config(episode, channel, channel_dir=None):
    """Return the effective episode/render/audio values after style merge."""
    from .audio import merge_audio
    from .render import render_config

    return {
        "style": {
            **(channel.get("style") or {}),
            **(episode.get("style") or {}),
        },
        "render": render_config(channel, episode),
        "audio": merge_audio(channel, episode),
        "post": {**(channel.get("post") or {}), **(episode.get("post") or {})},
        "captions": {**(channel.get("captions") or {}), **(episode.get("captions") or {})},
        "episode": episode,
    }
