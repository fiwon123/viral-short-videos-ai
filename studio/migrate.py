"""Move one legacy channel into ``workspace/<slug>/``.

The migration is deliberately cautious: channels move automatically, episodes
and research move only when named explicitly, and the default is a dry run.

    python -m studio.migrate channels/my-channel/channel.json \\
        --episode episodes/my-episode/episode.json --apply
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from .workspace import channel_root, channel_slug


def _input(path, root):
    path = Path(path)
    return (path if path.is_absolute() else root / path).resolve()


def plan(channel, episodes=(), research=(), root=None):
    channel = Path(channel).resolve()
    root = Path(root or Path.cwd()).resolve()
    if channel_root(channel):
        raise ValueError("This channel is already inside the workspace layout")
    slug = channel_slug(channel)
    target = root / "workspace" / slug
    steps = [{"from": str(channel.parent), "to": str(target / "channel"), "kind": "channel"}]
    for episode in episodes:
        source = _input(episode, root)
        folder = source.parent if source.is_file() else source
        steps.append({"from": str(folder), "to": str(target / "episodes" / folder.name),
                      "kind": "episode"})
    for note in research:
        source = _input(note, root)
        if source.is_file():
            steps.append({"from": str(source), "to": str(target / "research" / source.name),
                          "kind": "research"})
        elif source.name == "research":
            for child in sorted(source.iterdir()):
                steps.append({"from": str(child), "to": str(target / "research" / child.name),
                              "kind": "research"})
        else:
            steps.append({"from": str(source), "to": str(target / "research" / source.name),
                          "kind": "research"})
    for step in steps:
        if Path(step["to"]).exists():
            raise ValueError(f"Target already exists: {step['to']}")
    return {"channel": slug, "root": str(target), "steps": steps}


def move(plan_data, root):
    for step in plan_data["steps"]:
        source, target = Path(step["from"]), Path(step["to"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    env = Path(root) / ".env"
    if env.is_file():
        text = env.read_text(encoding="utf-8")
        for step in plan_data["steps"]:
            old = os.path.relpath(step["from"], root)
            new = os.path.relpath(step["to"], root)
            text = text.replace(old, new)
        env.write_text(text, encoding="utf-8")
    return plan_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", type=Path)
    parser.add_argument("--episode", action="append", default=[], type=Path,
                        help="episode manifest or folder to move into the channel workspace")
    parser.add_argument("--research", action="append", default=[], type=Path,
                        help="research file or folder to move into the channel workspace")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = plan(args.channel, args.episode, args.research, args.root)
        if args.apply:
            move(result, args.root)
        result["applied"] = bool(args.apply)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(f"studio: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
