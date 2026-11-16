# Viral Short Videos

For channel discovery, channel branding, reference breakdowns, and episode production, read [.agents/skills/viral-video-studio/SKILL.md](.agents/skills/viral-video-studio/SKILL.md). It defines the user's decision points and the local production workflow. Run tools from the repository root. See [README.md](README.md) for commands and [studio/schema.json](studio/schema.json) for the data contract.

Use one workspace per channel: `workspace/<slug>/channel/channel.json`, `workspace/<slug>/episodes/<episode>/episode.json`, `workspace/<slug>/research/`, and `workspace/<slug>/renders/`. Keep local source videos under `reference-media/`. Run `make channel-doc` after editing `channel.json` to refresh the copy/paste `channel.md`. The tracked `examples/` folder is a public showcase; `workspace/` and `reference-media/` are local. Version the reusable studio, presets and skill. Keep API keys in the environment.

`make help` lists the local shortcuts, `make status` shows what channel and episode resolve to, `make still` renders one review frame or a contact sheet, `make presets` and `make motion` list reusable building blocks, `make assets` reports the channel files an episode render actually reads, and `make prune-<group>` (dry run; add `APPLY=1`) removes assets that no render uses. Never prune a file a channel manifest still points at. `make sound RECIPE=...` and `make effect RECIPE=...` generate custom audio and SVG recipes. `make support` writes the renderer support matrix, `make parity` renders the shared fixture, and `make editor EPISODE=...` opens the local shot inspector. Per-machine defaults live in an ignored `.env` (see `.env.example`); nothing about a specific channel belongs in tracked files.

## Style lock (any assistant, every channel)

A channel's approved look lives in `workspace/<slug>/channel/style-lock.json`, and the studio enforces it: `validate`, `audio`, `still` and `render` refuse an episode that uses another cast, adds dialogue to a wordless channel, leaves the runtime or format, uses an unapproved grade, or touches a forbidden path. Its rules are copied into a generated block in `channel/AGENTS.md`; read that before planning. Never work around a refusal by editing the lock yourself. Fix the episode. When the user approves a one-off, add `style_exceptions` with their reason to the episode. When the user changes the channel's direction, edit `style-lock.json` and run `make style-lock CHANNEL=... CHANGE="what changed and why"` (it bumps the version, logs the change and refreshes `channel/AGENTS.md`), then `make style-check` to see which episodes the change affects. A channel without a lock gets one with `make style-lock CHANNEL=... INIT=1` once its look is approved.

## Resuming work (memory)

Keep working memory in files so a new session or an interrupted one can pick up where the last stopped. Update them as you go, not only at the end.

- **Studio and repository work** (renderer, schema, tools, presets, skill): read and update [docs/ROADMAP.md](docs/ROADMAP.md). It is tracked, so it must stay generic: no channel names, episodes or brand details.
- **A channel**: before planning or making anything for `workspace/<slug>/`, read `workspace/<slug>/MEMORY.md` (current direction, direction history, decisions, next step), then `workspace/<slug>/channel/AGENTS.md` (channel rules), `channel/episode-ledger.md` (made, in progress, planned, results and lessons), `channel/ideas.md` (idea bank and seasonal calendar) and `channel/series.md` (series bible) when they exist. Create missing ones from the templates in [docs/memory-templates.md](docs/memory-templates.md). After each episode, update the ledger, series bible, idea bank and memory as described in the skill's episode planning guide.
- **An episode**: keep `workspace/<slug>/episodes/<episode>/NOTES.md` with its status, open issues, and the exact next command to run.

Everything specific to a channel or video lives under the ignored `workspace/`, never in tracked files.
