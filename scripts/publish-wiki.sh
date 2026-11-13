#!/usr/bin/env sh
# Publish the versioned wiki/ pages to the GitHub Wiki.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WIKI_REMOTE=${WIKI_REMOTE:-git@github.com:fiwon123/viral-short-videos-ai.wiki.git}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

if ! git clone "$WIKI_REMOTE" "$WORK/wiki" 2>/dev/null; then
  cat >&2 <<EOF
studio: the GitHub Wiki repository is not available yet.

Open https://github.com/fiwon123/viral-short-videos-ai/wiki
and create the first Home page once. Then run: make wiki
EOF
  exit 1
fi

rm -f "$WORK"/wiki/*.md
cp "$ROOT"/wiki/*.md "$WORK"/wiki/
git -C "$WORK/wiki" add -A
if git -C "$WORK/wiki" diff --cached --quiet; then
  echo "wiki already up to date"
  exit 0
fi
git -C "$WORK/wiki" commit -m "Update studio wiki"
git -C "$WORK/wiki" push
echo "wiki published"
