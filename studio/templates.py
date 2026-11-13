"""Load and parameterise reusable shot templates."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / "presets" / "shots"


def load(name, channel_base=None):
    candidates = []
    if channel_base:
        candidates.append(Path(channel_base) / "presets" / "shots" / f"{name}.json")
    candidates.append(SHOT_DIR / f"{name}.json")
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"Unknown shot template: {name}")


def _literal(value):
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def substitute(value, params):
    if isinstance(value, str):
        for key, replacement in params.items():
            token = "{{" + key + "}}"
            if value == token:
                return _literal(str(replacement))
            value = value.replace(token, str(replacement))
        return value
    if isinstance(value, list):
        return [substitute(item, params) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item, params) for key, item in value.items()}
    return value


def build(name, params=None, channel_base=None):
    return substitute(load(name, channel_base), params or {})
