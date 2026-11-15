"""Create a channel's memory files from docs/memory-templates.md.

    python -m studio.memory <slug> [--episode <name>] [--root workspace]

Each ``## `workspace/<slug>/...` `` section of the templates becomes a file:
its first fenced block, else its table, else a heading plus the section's
guidance. Existing files are never overwritten, so this is safe to run any
time to fill in whatever is missing.
"""

import argparse
from datetime import date
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "docs" / "memory-templates.md"
HEADING = re.compile(r"^## `workspace/<slug>/(.+?)`", re.M)


def templates(text=None):
    """{relative path with <episode> placeholders: content}."""
    text = text if text is not None else TEMPLATES.read_text(encoding="utf-8")
    found = {}
    matches = list(HEADING.finditer(text))
    for index, match in enumerate(matches):
        body = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        fenced = re.search(r"```markdown\n(.*?)```", body, re.S)
        if fenced:
            content = fenced.group(1)
        else:
            table = [line for line in body.splitlines() if line.startswith("|")]
            label = re.match(r"\s*\(([^)]+)\)", body)
            title = (label.group(1) if label else Path(match.group(1)).stem.replace("-", " ")).capitalize()
            body = body[label.end():] if label else body
            prose = " ".join(line for line in body.strip().splitlines() if line and not line.startswith("|"))
            content = f"# {title}\n\n" + ("\n".join(table) + "\n" if table else f"<!-- {prose} -->\n")
        found[match.group(1)] = content
    return found


def create(slug, episode=None, root=None, today=None):
    """Write missing memory files; returns the paths created."""
    base = Path(root or ROOT / "workspace") / slug
    stamp = (today or date.today()).isoformat()
    created = []
    for relative, content in templates().items():
        if "<episode>" in relative:
            if not episode:
                continue
            relative = relative.replace("<episode>", episode)
        target = base / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        content = content.replace("YYYY-MM-DD", stamp, 1) if "Updated: YYYY-MM-DD" in content else content
        target.write_text(content, encoding="utf-8")
        created.append(str(target))
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slug")
    parser.add_argument("--episode")
    parser.add_argument("--root", type=Path, help="workspace folder (default: ./workspace)")
    args = parser.parse_args()
    created = create(args.slug, args.episode, args.root)
    print(json.dumps({"created": created, "kept_existing": not created or None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
