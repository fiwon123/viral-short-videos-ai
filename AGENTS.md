# Viral Short Videos

For channel discovery, channel branding, reference breakdowns, and episode production, read [.agents/skills/viral-video-studio/SKILL.md](.agents/skills/viral-video-studio/SKILL.md). It defines the user's decision points and the local production workflow. Run tools from the repository root. See [README.md](README.md) for commands and [studio/schema.json](studio/schema.json) for the data contract.

Use one workspace per channel: `workspace/<slug>/channel/channel.json`, `workspace/<slug>/episodes/<episode>/episode.json`, `workspace/<slug>/research/`, and `workspace/<slug>/renders/`. Keep local source videos under `reference-media/`. Run `make channel-doc` after editing `channel.json` to refresh the copy/paste `channel.md`. The tracked `examples/` folder is a public showcase; `workspace/` and `reference-media/` are local. Version the reusable studio, presets and skill. Keep API keys in the environment.

`make help` lists the local shortcuts, `make status` shows what channel and episode resolve to, `make still` renders one review frame or a contact sheet, `make presets` and `make motion` list reusable building blocks, `make assets` reports the channel files an episode render actually reads, and `make prune-<group>` (dry run; add `APPLY=1`) removes assets that no render uses. Never prune a file a channel manifest still points at. Every channel has `renders/_old/` and `episodes/_old/` (created by `make channel-memory`, backfilled by `make archive`): moving a folder there marks it for deletion. `make archive` (dry run; add `APPLY=1`) empties both `_old` folders and removes caches, previews and superseded `-vN` renders in every channel. After an upload, `make published EPISODE=...` marks the episode so its render's upload files are archived to `workspace/<slug>/archive/` (`NOVIDEO=1` keeps only the publishing copy). It never deletes a render or episode that a channel file references, even inside `_old`. `make sound RECIPE=...` and `make effect RECIPE=...` generate custom audio and SVG recipes. `make support` writes the renderer support matrix, `make parity` renders the shared fixture, and `make editor EPISODE=...` opens the local shot inspector. `make review EPISODE=...` lets the user leave notes on a frame of the render; `make comments EPISODE=... [DONE=<id> REPLY=...]` gives them to the agent with the frame and a close-up of the spot, and records the reply. Per-machine defaults live in an ignored `.env` (see `.env.example`); nothing about a specific channel belongs in tracked files.

## Style lock (any assistant, every channel)

A channel's approved look lives in `workspace/<slug>/channel/style-lock.json`, and the studio enforces it: `validate`, `audio`, `still` and `render` refuse an episode that uses another cast, adds dialogue to a wordless channel, leaves the runtime or format, uses an unapproved grade, or touches a forbidden path. Its rules are copied into a generated block in `channel/AGENTS.md`; read that before planning. Never work around a refusal by editing the lock yourself. Fix the episode. When the user approves a one-off, add `style_exceptions` with their reason to the episode. When the user changes the channel's direction, edit `style-lock.json` and run `make style-lock CHANNEL=... CHANGE="what changed and why"` (it bumps the version, logs the change and refreshes `channel/AGENTS.md`), then `make style-check` to see which episodes the change affects. A channel without a lock gets one with `make style-lock CHANNEL=... INIT=1` once its look is approved.

## Resuming work (memory)

Keep working memory in files so a new session or an interrupted one can pick up where the last stopped. Update them as you go, not only at the end.

- **Studio and repository work** (renderer, schema, tools, presets, skill): read and update [docs/ROADMAP.md](docs/ROADMAP.md). It is tracked, so it must stay generic: no channel names, episodes or brand details.
- **A channel**: before planning or making anything for `workspace/<slug>/`, read `workspace/<slug>/MEMORY.md` (current direction, direction history, decisions, next step), then `workspace/<slug>/channel/AGENTS.md` (channel rules), `channel/episode-ledger.md` (made, in progress, planned, results and lessons), `channel/ideas.md` (idea bank and seasonal calendar) and `channel/series.md` (series bible) when they exist. Create missing ones from the templates in [docs/memory-templates.md](docs/memory-templates.md). After each episode, update the ledger, series bible, idea bank and memory as described in the skill's episode planning guide.
- **An episode**: keep `workspace/<slug>/episodes/<episode>/NOTES.md` with its status, open issues, and the exact next command to run, and `treatment.md` with its plan (idea, route, energy curve, shot table; `make treatment-lint`). Hold it to the skill's `references/direction.md`. To resume, run `make state EPISODE=...`: it reports the stage the files prove and the next command, so a stale status line cannot mislead you. Hand over a master only through `make deliver`.

Everything specific to a channel or video lives under the ignored `workspace/`, never in tracked files.

## Runtime environment

The studio runs in one of two places. Both use the same Makefile targets and the same checkout.

| Mode | Start | What the agent can reach |
| --- | --- | --- |
| **Docker sandbox** (recommended for an agent) | `make claude`, `make codex`, `make opencode` (`-auto` for no prompts), `make shell` | This checkout and the sandbox's own volumes. Not the home directory, not the Docker socket. |
| **Host** | `make setup-host`, then the agent as usual | Whatever the host user can reach. |

- The image (`Dockerfile`) carries Python 3.13 with both requirement files, FFmpeg, eSpeak NG, Node 22 with `node_modules`, Chromium, and the three agents, pinned. `make agents-upgrade` moves the pins. `make dev-doctor` checks the image, the studio inside it, and each agent's login.
- `make dev-up` never rebuilds. After editing `Dockerfile`, `requirements*.txt`, `package*.json` or `scripts/dev-sandbox-rc.sh`, run `make dev-build`; a stale image is refused by name.
- Agent logins live in named volumes and survive `dev-down`/`dev-build`. `make reset` deletes them.
- Inside the sandbox there is no Docker: run the studio targets directly (`make test`, `make render ...`). The sandbox targets say so if you try.
- `audio-models/` (Kokoro files, `make models`) and `workspace/` are in the checkout, so both modes share them. `node_modules` is not shared: the sandbox keeps its own in a volume.
- Native Windows: `python scripts/dev-up.py claude` (and `dev-up`, `shell`, `doctor`, ...).

## Key conventions

- **Assignee**: `ASSIGNEE` is `fiwon123`; `.opencode/instructions/workflow.md` reads it from here.
- **Two-tier branch model**: `main` (release only) ← `dev` (integration) ← `<type>/<issue-number>-<slug>`. Types: `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`, `ci/`.
- **Issue first**: issue (labelled, in a milestone) → branch from `dev` → PR to `dev` with `Closes #N` → close the issue after the merge. Full steps: `.opencode/instructions/workflow.md`.
- Never push to `dev` or `main`. Do not merge a PR, open a release PR, or merge to `main` unless the user asks. A release merge uses `gh pr merge --merge`, never `--delete-branch`.
- **Conventional commits**: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `ci:`.
- **Agents**: `opencode.json` assigns models and permissions; each agent's prompt is `.opencode/agents/<name>.md` only. `CLAUDE.md` imports this file and the instructions. The studio skill lives in `.agents/skills/` (Codex) and, byte for byte, in `.claude/skills/` (Claude Code, opencode): edit one, copy it to the other; `make test` fails when they differ.
- **Testing**: `make test` before every PR; `.opencode/instructions/testing.md` has the gates and the visual-check rules.

## Environment and secret files

- `.env` holds `YOUTUBE_API_KEY`. Never open, print, quote or summarize `.env`, `.env.*` or `.envrc`, and never run `printenv`, `env`, `docker compose config` or `docker inspect`, which dump values. To confirm a variable is set: `test -n "$YOUTUBE_API_KEY" && echo set`.
- **In the sandbox the secrets are not there.** `.env` is an empty read-only file inside the container, so no agent can read or change the keys, in any mode. This is the only guard that covers Codex, which has no file deny list. The sandbox refuses to start while any other `.env*`/`.envrc` file is in the checkout (`.env.example` excepted). API keys are never forwarded into it: run `make discover` (YouTube API) on the host; in the sandbox the studio uses browser research instead.
- **On the host** `.claude/settings.json` and `opencode.json` deny these by path and command string — a backstop with gaps (an interpreter can still open a file), not permission — and nothing stops Codex. Run Codex through `make codex`.
- `GH_TOKEN` is forwarded into the sandbox so agents can open issues and PRs. Any agent that can run `gh` can use it; give the sandbox a fine-grained token limited to this repository if that matters.
- Never put a key, token or credential in a tracked file, a commit or a reply.

## CI

`.github/workflows/ci.yml` runs on release PRs (`dev` → `main`) and by hand: the studio tests on the host toolchain (a skipped test fails the run), and the sandbox image build with the tests inside it. Feature branches are gated by `make test` locally. `branch-gate.yml` checks branch names on every PR. **Skipped is not passed**: a run that did not happen, or a job gated out, verified nothing — say the change is unverified instead.
