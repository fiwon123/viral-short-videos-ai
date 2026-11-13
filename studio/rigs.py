"""Load the optional channel-level reusable layer library."""

from .core import asset, load


def load_rigs(channel, base):
    name = (channel or {}).get("rig_library")
    if not name:
        return {}
    path = asset(base, name)
    data = load(path, "rig_library")
    return data.get("rigs", {})
