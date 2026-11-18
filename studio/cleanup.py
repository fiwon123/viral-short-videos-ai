"""Clean regenerable files, empty the ``_old`` folders and archive published renders.

Dry run by default; ``--apply`` makes the changes. Every channel has two
``_old`` folders, created with the channel and backfilled by this tool:
``renders/_old/`` and ``episodes/_old/``. Moving something into one means
"delete it on the next cleanup".

* **delete**: everything in ``renders/_old/`` and ``episodes/_old/`` (except
  their README), preview packages, stills and review folders, render staging,
  audio takes, raster sprites, ``__pycache__``, ``episode-raster.json``, and
  render versions superseded by a newer ``-vN`` of the same episode.
* **archive**: render packages of episodes marked published
  (``episodes/<ep>/published.json``, written by ``mark_published``). The
  upload files (video, thumbnail, captions, publishing copy) move to
  ``workspace/<slug>/archive/<package>/`` and the rest (mix, timeline, QA) is
  deleted. With ``keep_video=False`` only the publishing copy is kept.
* **keep**: everything else, including channel files, episode sources, the
  latest unpublished render of each episode, and any render or episode that a
  channel file (for example ``style-lock.json`` reference renders) names, even
  inside ``_old``.
"""

import argparse
import datetime
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_FILES = ("video.mp4", "thumbnail.png", "captions.srt", "publishing.md", "publishing.json")
SMALL_FILES = ("publishing.md", "publishing.json")
CACHE_DIRS = (".audio-takes", ".raster", ".video-frames", "__pycache__")
CACHE_FILES = ("episode-raster.json",)
JUNK_RENDER = re.compile(r"(-preview|-stills)$|^_review$|^\.studio-")
VERSION = re.compile(r"^(?P<base>.+?)(?:-v(?P<n>\d+))?$")
MARKER = "published.json"
OLD = "_old"
OLD_README = {
    "renders": "# Old renders\n\nMove render folders you no longer need here. "
               "`make archive` lists them and `make archive APPLY=1` deletes them. "
               "To keep an uploaded video, use `make published EPISODE=...` instead; "
               "its upload files are then archived to `archive/`.\n",
    "episodes": "# Old episodes\n\nMove episode folders you will never re-render or continue here. "
                "`make archive` lists them and `make archive APPLY=1` deletes them, sources included. "
                "Keep an episode in `episodes/` if a series or the ledger may still need it.\n",
}


@dataclass
class Item:
    action: str  # delete | archive | keep
    path: Path
    reason: str
    size: int = 0


def size_of(path):
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def human(n):
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


def channel_roots(workspace):
    return sorted(p for p in Path(workspace).iterdir()
                  if p.is_dir() and (p / "channel" / "channel.json").exists())


def ensure_old_folders(root):
    """Create renders/_old and episodes/_old with a short README; returns created paths."""
    created = []
    for kind, text in OLD_README.items():
        readme = Path(root) / kind / OLD / "README.md"
        if not readme.exists():
            readme.parent.mkdir(parents=True, exist_ok=True)
            readme.write_text(text, encoding="utf-8")
            created.append(readme)
    return created


def is_package(path):
    return path.is_dir() and ((path / "video.mp4").exists() or (path / "qa.json").exists())


def split_version(name):
    match = VERSION.match(name)
    return match["base"], int(match["n"] or 0)


def referenced_packages(root):
    """Render package and episode folder names that any channel JSON file points at."""
    names, links = set(), []
    for manifest in (root / "channel").glob("*.json"):
        try:
            text = manifest.read_text()
        except OSError:
            continue
        for found in re.findall(r'"([^"]*(?:renders|episodes)/[^"]+)"', text):
            tail = re.split(r"(?:renders|episodes)/", found, maxsplit=1)[1]
            parts = [p for p in tail.split("/") if p]
            if parts and parts[0] == OLD:
                parts = parts[1:]
            if parts:
                names.add(parts[0])
                links.append((manifest, found))
    return names, links


def published_episodes(root):
    return {p.parent.name for p in (root / "episodes").glob(f"*/{MARKER}")}


def plan_channel(root, keep_video=True):
    items, notes = [], []
    protected, links = referenced_packages(root)
    for manifest, link in links:
        if not any((base / link).exists() for base in (manifest.parent, root, ROOT)):
            notes.append(f"{manifest.relative_to(root)} points at {link}, which does not exist")
    published = published_episodes(root)

    # Episode and channel caches (episodes/_old is removed whole below).
    for folder in (root / "episodes", root / "channel"):
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if OLD in path.relative_to(folder).parts[:1]:
                continue
            if path.is_dir() and path.name in CACHE_DIRS:
                items.append(Item("delete", path, "cache, regenerated on the next build or render"))
            elif path.is_file() and path.name in CACHE_FILES:
                items.append(Item("delete", path, "generated by the legacy raster export"))

    # Anything moved into episodes/_old.
    old_episodes = root / "episodes" / OLD
    if old_episodes.exists():
        for path in sorted(old_episodes.iterdir()):
            if path.name == "README.md":
                continue
            if path.name in protected:
                items.append(Item("keep", path, "a channel file references it; move it back to episodes/"))
            else:
                items.append(Item("delete", path, "moved to episodes/_old"))

    renders = root / "renders"
    entries = []
    for parent in (renders, renders / OLD):
        if parent.exists():
            entries += [(p, parent.name == OLD) for p in sorted(parent.iterdir())
                        if p.name != OLD and not (parent.name == OLD and p.name == "README.md")]
    newest = {}
    for path, _ in entries:
        if is_package(path):
            base, n = split_version(path.name)
            newest[base] = max(newest.get(base, -1), n)

    for path, in_old in entries:
        base, n = split_version(path.name)
        if path.name in protected:
            where = "; move it back to renders/" if in_old else ""
            items.append(Item("keep", path, f"a channel file references it (style-lock reference render){where}"))
        elif in_old:
            items.append(Item("delete", path, "moved to renders/_old"))
        elif JUNK_RENDER.search(path.name):
            items.append(Item("delete", path, "preview, stills or staging output"))
        elif is_package(path) and n < newest[base]:
            items.append(Item("delete", path, f"superseded by {base}-v{newest[base]}"))
        elif is_package(path) and base in published:
            items.append(Item("archive", path, "episode marked published"))
        else:
            items.append(Item("keep", path, "latest render of an unpublished episode"))

    for item in items:
        item.size = size_of(item.path) if item.path.exists() else 0
        if item.action == "archive" and item.path.is_dir():
            kept = UPLOAD_FILES if keep_video else SMALL_FILES
            item.size = sum(size_of(item.path / f) for f in kept if (item.path / f).exists())
    return items, notes


def apply_item(item, root, keep_video=True):
    if item.action == "delete":
        shutil.rmtree(item.path) if item.path.is_dir() else item.path.unlink()
    elif item.action == "archive":
        target = root / "archive" / item.path.name
        if item.path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item.path), target)
            return
        target.mkdir(parents=True, exist_ok=True)
        for name in (UPLOAD_FILES if keep_video else SMALL_FILES):
            source = item.path / name
            if source.exists():
                shutil.move(str(source), target / name)
        shutil.rmtree(item.path)


def is_cache(item):
    return item.action == "delete" and item.path.name in CACHE_DIRS + CACHE_FILES


def run(workspace, slug=None, apply=False, keep_video=True, verbose=False, out=sys.stdout):
    totals = {"delete": 0, "archive": 0, "freed": 0}
    roots = [r for r in channel_roots(workspace) if slug in (None, r.name)]
    if slug and not roots:
        raise SystemExit(f"No channel workspace named {slug!r} under {workspace}")
    for root in roots:
        for readme in ensure_old_folders(root):
            print(f"created {readme.relative_to(Path(workspace))}", file=out)
        items, notes = plan_channel(root, keep_video)
        changes = [i for i in items if i.action != "keep"]
        if not changes and not notes:
            continue
        print(f"\n== {root.name}", file=out)
        caches = [i for i in items if is_cache(i)]
        if caches and not verbose:
            print(f"  delete  {len(caches)} cache folders and files in episodes/ and channel/ "
                  f"({human(sum(i.size for i in caches))})  .audio-takes, .raster, __pycache__, "
                  "episode-raster.json (VERBOSE=1 lists them)", file=out)
        for item in items:
            rel = item.path.relative_to(root)
            if item.action == "keep" and "references" not in item.reason:
                continue
            quiet = is_cache(item) and not verbose
            label = {"delete": "delete ", "archive": "archive", "keep": "keep   "}[item.action]
            if item.action == "archive" and item.path.is_dir():
                full = size_of(item.path)
                note = f"{human(full)} -> keep {human(item.size)}"
            else:
                note = human(item.size)
            if not quiet:
                print(f"  {label} {rel}  ({note})  {item.reason}", file=out)
            if item.action == "delete":
                totals["delete"] += 1
                totals["freed"] += item.size
            elif item.action == "archive":
                totals["archive"] += 1
                if item.path.is_dir():
                    totals["freed"] += size_of(item.path) - item.size
            if apply:
                apply_item(item, root, keep_video)
        for note in notes:
            print(f"  warning  {note}", file=out)
    verb = "Freed" if apply else "Would free"
    print(f"\n{verb} {human(totals['freed'])}: {totals['delete']} deleted, "
          f"{totals['archive']} archived to workspace/<slug>/archive/.", file=out)
    if not apply:
        print("Dry run. Add APPLY=1 (or --apply) to make these changes.", file=out)
    return totals


def mark_published(episode_dir, url=None, date=None):
    """Write episodes/<ep>/published.json so the next archive run packs its renders."""
    episode_dir = Path(episode_dir)
    if episode_dir.name == "episode.json":
        episode_dir = episode_dir.parent
    if not (episode_dir / "episode.json").exists():
        raise SystemExit(f"No episode.json in {episode_dir}")
    marker = episode_dir / MARKER
    data = json.loads(marker.read_text()) if marker.exists() else {}
    data["date"] = date or data.get("date") or datetime.date.today().isoformat()
    if url:
        data.setdefault("urls", [])
        if url not in data["urls"]:
            data["urls"].append(url)
    marker.write_text(json.dumps(data, indent=2) + "\n")
    return marker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    clean = sub.add_parser("archive", help="clean caches and archive published renders")
    clean.add_argument("--workspace", type=Path, default=ROOT / "workspace")
    clean.add_argument("--channel", help="limit to one channel slug")
    clean.add_argument("--apply", action="store_true")
    clean.add_argument("--verbose", action="store_true", help="list every cache entry")
    clean.add_argument("--no-video", action="store_true",
                       help="archive only the publishing copy, not the MP4")
    mark = sub.add_parser("published", help="mark an episode as uploaded")
    mark.add_argument("episode", type=Path)
    mark.add_argument("--url")
    args = parser.parse_args(argv)
    if args.command == "published":
        marker = mark_published(args.episode, args.url)
        print(f"Marked published: {marker}. Run `make archive` to pack its renders.")
    else:
        run(args.workspace, args.channel, args.apply, not args.no_video, args.verbose)


if __name__ == "__main__":
    main()
