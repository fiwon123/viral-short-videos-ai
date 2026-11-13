"""Resolve the optional per-channel workspace layout.

A workspace channel keeps the manifest, episodes, research and renders under
one folder::

    workspace/<slug>/channel/channel.json
    workspace/<slug>/episodes/<episode>/episode.json
    workspace/<slug>/research/notes.md
    workspace/<slug>/renders/<episode>-v1/

Legacy projects with ``channels/`` and ``episodes/`` at the repository root
continue to work. The helpers here only describe paths; discovery lives in
``studio.project``.
"""

from pathlib import Path

WORKSPACE_DIRS = ("workspace", "examples")


def channel_root(path):
    """Return ``workspace/<slug>`` for a manifest inside the new layout."""
    path = Path(path).resolve()
    folder = path.parent
    if folder.name == "channel" and folder.parent.parent.name in WORKSPACE_DIRS:
        return folder.parent
    return None


def episode_root(path):
    """Return ``workspace/<slug>`` for an episode inside the new layout."""
    path = Path(path).resolve()
    folder = path.parent
    if folder.parent.name == "episodes" and folder.parent.parent.parent.name in WORKSPACE_DIRS:
        return folder.parent.parent
    return None


def channel_slug(path):
    root = channel_root(path)
    return root.name if root else Path(path).resolve().parent.name


def episode_slug(path):
    return Path(path).resolve().parent.name


def default_output(episode_path, channel_path, suffix):
    """Package path for a render, respecting the workspace layout."""
    root = channel_root(channel_path) or episode_root(episode_path)
    if root is not None:
        return root / "renders" / f"{episode_slug(episode_path)}-{suffix}"
    return Path("output") / channel_slug(channel_path) / f"{episode_slug(episode_path)}-{suffix}"


def layout_for(channel_path):
    root = channel_root(channel_path)
    if root:
        return f"{root.parent.name}/{root.name}/channel"
    return f"channels/{channel_slug(channel_path)}"
