#!/bin/bash
# CRLF guard — the first executable statement, above `set -euo pipefail`. A
# Windows checkout made before .gitattributes pinned LF keeps CRLF bytes, and
# bash then dies with `set: pipefail: invalid option name`. Every line of the
# guard ends in a `# crlf-guard` comment, which absorbs the trailing `\r`.
# Do not put an empty line above it: in a CRLF copy that is a bare `\r` command.
if [[ -f "${BASH_SOURCE[0]}" ]] && grep -q $'\r$' "${BASH_SOURCE[0]}"; then # crlf-guard
    printf '%s\n' "[dev] ${BASH_SOURCE[0]##*/} has CRLF line endings, so bash cannot parse it." "      Re-check the repository out with LF endings:" >&2 # crlf-guard
    printf '%s\n' "        git rm --cached -r . >/dev/null && git reset --hard" >&2; exit 1 # crlf-guard
fi # crlf-guard
set -euo pipefail

# Dev sandbox entrypoint. The studio has no server to run, so the container
# stays up for `make shell`, `make claude` and friends.

cd /workspace

if ! getent passwd "$(id -u)" >/dev/null; then
    echo "[dev] WARNING: UID $(id -u) has no passwd entry — rebuild with make dev-build." >&2
fi

# The node_modules volume is filled from the image once, when it is created, and
# never again. When package-lock.json has changed since, install what it names.
stamp=node_modules/.package-lock.sha256
want="$(sha256sum package-lock.json | cut -d' ' -f1)"
if [[ "$(cat "$stamp" 2>/dev/null || true)" != "$want" ]]; then
    echo "[dev] package-lock.json changed — npm ci into the node_modules volume..."
    npm ci --ignore-scripts --no-audit --no-fund
    printf '%s\n' "$want" > "$stamp"
fi

echo "[dev] Sandbox ready. Run 'make shell', or an agent: make claude | codex | opencode."
exec sleep infinity
