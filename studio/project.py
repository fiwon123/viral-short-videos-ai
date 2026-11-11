"""Find the channel manifest and episode source a command should use.

The repository is a template: it ships no channel and no episode. Everything
here is discovered from whatever is on disk, so a fresh clone, a new channel,
and a resumed project all work without editing tracked files.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def is_channel(data):
    return isinstance(data, dict) and {"name", "mark", "palette"} <= data.keys()


def is_episode(data):
    return isinstance(data, dict) and {"title", "width", "height", "fps", "scenes"} <= data.keys()


def read(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data


def channel_manifests(folder):
    return [path for path in sorted(folder.glob("*.json")) if is_channel(read(path))]


def channels(root):
    """Channel folders that contain at least one manifest."""
    rows = []
    for folder in sorted((root / "channels").glob("*")):
        found = channel_manifests(folder) if folder.is_dir() else []
        if found:
            rows.append((folder, found))
    return rows


def episodes(root):
    rows = []
    for folder in sorted((root / "episodes").glob("*")):
        if folder.is_dir():
            found = [path for path in sorted(folder.glob("*.json")) if is_episode(read(path))]
            if found:
                rows.append((folder, found))
    return rows


def resolve_channel(root=ROOT):
    found = channels(root)
    if not found:
        raise ValueError("No channel manifest found. Create channels/<slug>/channel.json "
                         "or set CHANNEL=channels/<slug>/channel.json.")
    if len(found) > 1:
        names = ", ".join(str(folder.relative_to(root)) for folder, _ in found)
        raise ValueError(f"Several channels found ({names}). Set CHANNEL=<manifest> or run make init.")
    folder, manifests = found[0]
    canonical = folder / "channel.json"
    if canonical in manifests:
        return canonical
    if len(manifests) == 1:
        return manifests[0]
    names = ", ".join(path.name for path in manifests)
    raise ValueError(f"{folder.relative_to(root)} has several manifests ({names}). "
                     f"Set CHANNEL={folder.relative_to(root)}/<manifest> or run make init.")


def resolve_episode(root=ROOT):
    found = episodes(root)
    if not found:
        raise ValueError("No episode found. Create episodes/<slug>/episode.json "
                         "or set EPISODE=episodes/<slug>/episode.json.")
    if len(found) > 1:
        names = ", ".join(str(folder.relative_to(root)) for folder, _ in found)
        raise ValueError(f"Several episodes found ({names}). Set EPISODE=<manifest> or run make init.")
    folder, manifests = found[0]
    canonical = folder / "episode.json"
    if canonical in manifests:
        return canonical
    if len(manifests) == 1:
        return manifests[0]
    names = ", ".join(path.name for path in manifests)
    raise ValueError(f"{folder.relative_to(root)} has several manifests ({names}). "
                     f"Set EPISODE={folder.relative_to(root)}/<manifest>.")


def status(root=ROOT):
    lines = []
    found_channels = channels(root)
    if not found_channels:
        lines.append("channel  none — create channels/<slug>/channel.json")
    for folder, manifests in found_channels:
        canonical = folder / "channel.json"
        active = canonical if canonical in manifests else manifests[0]
        lines.append(f"channel  {active.relative_to(root)}")
        alternates = [path.name for path in manifests if path != active]
        if alternates:
            lines.append(f"         alternates: {', '.join(alternates)}")
    found_episodes = episodes(root)
    if not found_episodes:
        lines.append("episode  none")
    for folder, manifests in found_episodes:
        names = ", ".join(path.name for path in manifests)
        lines.append(f"episode  {folder.relative_to(root)} ({names})")
    lines.append(f".env     {'found' if (root / '.env').is_file() else 'not found (optional; cp .env.example .env)'}")
    return "\n".join(lines)


def init(root=ROOT, force=False):
    target = root / ".env"
    if target.exists() and not force:
        raise ValueError(".env already exists. Delete it, or run make init FORCE=1.")
    template = root / ".env.example"
    if not template.is_file():
        raise ValueError("Missing .env.example")
    channel = episode = ""
    try:
        channel = str(resolve_channel(root).relative_to(root))
    except ValueError:
        pass
    try:
        episode = str(resolve_episode(root).relative_to(root))
    except ValueError:
        pass
    rows = []
    for line in template.read_text(encoding="utf-8").splitlines():
        if line.startswith("CHANNEL="):
            line = f"CHANNEL={channel}"
        elif line.startswith("EPISODE="):
            line = f"EPISODE={episode}"
        rows.append(line)
    target.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("what", choices=("channel", "episode", "status", "init"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--force", action="store_true", help="overwrite .env when initialising")
    args = parser.parse_args()
    try:
        if args.what == "channel":
            print(resolve_channel(args.root))
        elif args.what == "episode":
            print(resolve_episode(args.root))
        elif args.what == "status":
            print(status(args.root))
        else:
            print(f"wrote {init(args.root, args.force)}")
        return 0
    except (OSError, ValueError) as error:
        print(f"studio: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
