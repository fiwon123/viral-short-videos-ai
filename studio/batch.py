"""Validate or render a season manifest without hand-running every episode."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys

from .core import validate
from .workspace import default_output

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    validate(data, "season", path.name)
    return data, path


def selected(season, base, *, only=(), status=None):
    wanted = {value for value in only if value}
    rows = []
    for entry in season["episodes"]:
        if wanted and entry["id"] not in wanted:
            continue
        if status is not None and entry.get("status", "") != status:
            continue
        path = Path(entry.get("path") or f"episodes/{entry['id']}/episode.json")
        if not path.is_absolute():
            path = (base / path).resolve()
        rows.append((entry, path))
    return rows


def _command(episode, channel, season, entry, *, renderer, preview, validate_only, package):
    command = [sys.executable, str(ROOT / "video.py"), "validate" if validate_only else "render",
               str(episode), "--channel", str(channel)]
    if not validate_only:
        command.extend(["--renderer", renderer])
        if preview:
            command.append("--preview")
        command.extend(["--out", str(package)])
    return command


def run(season_path, *, only=(), status=None, renderer=None, preview=None, jobs=1,
        validate_only=False, dry_run=False, out_root=None):
    season, path = load(season_path)
    base = path.parent
    defaults = season.get("defaults") or {}
    channel = (base / season.get("channel", "channel/channel.json")).resolve()
    renderer = renderer or defaults.get("renderer", "hyperframes")
    preview = bool(defaults.get("preview", False) if preview is None else preview)
    status = defaults.get("status") if status is None else status
    rows = selected(season, base, only=only, status=status)
    if not rows:
        raise ValueError("No episodes matched the season filters")
    if not channel.is_file():
        raise ValueError(f"Season channel manifest not found: {channel}")

    plan = []
    for entry, episode in rows:
        suffix = "preview" if preview else "v1"
        package = (Path(out_root) / f"{entry['id']}-{suffix}").resolve() if out_root \
            else default_output(episode, channel, suffix)
        plan.append({
            "id": entry["id"],
            "title": entry.get("title", entry["id"]),
            "status": entry.get("status", ""),
            "episode": str(episode),
            "package": str(package),
            "command": _command(episode, channel, season, entry, renderer=renderer,
                                preview=preview, validate_only=validate_only, package=package),
        })
    if dry_run:
        return {"season": season.get("title", path.stem), "channel": str(channel),
                "dry_run": True, "episodes": plan}

    def execute(item):
        result = subprocess.run(item["command"], cwd=ROOT, capture_output=True, text=True)
        detail = (result.stderr or result.stdout).strip().splitlines()
        return {**item, "ok": result.returncode == 0,
                "returncode": result.returncode,
                "detail": detail[-1] if detail else ""}

    results = []
    workers = max(1, min(int(jobs), len(plan)))
    if workers == 1:
        results = [execute(item) for item in plan]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(execute, item): item for item in plan}
            for future in as_completed(futures):
                results.append(future.result())
        order = {item["id"]: index for index, item in enumerate(plan)}
        results.sort(key=lambda item: order[item["id"]])
    return {
        "season": season.get("title", path.stem),
        "channel": str(channel),
        "renderer": renderer,
        "preview": preview,
        "validated_only": validate_only,
        "episodes": results,
        "ok": all(item["ok"] for item in results),
    }
