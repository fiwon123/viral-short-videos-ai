# Viral Short Videos

For channel discovery, channel branding, reference breakdowns, and episode production, read [.agents/skills/viral-video-studio/SKILL.md](.agents/skills/viral-video-studio/SKILL.md). It defines the user's decision points and the local production workflow. Run tools from the repository root. See [README.md](README.md) for commands and [studio/schema.json](studio/schema.json) for the data contract.

Store approved channel identities under `channels/<slug>/` and episode sources under `episodes/<slug>/`. Keep discovery notes under `research/` and local source videos under `reference-media/`. Save episode packages under `output/<channel-slug>/`, using the folder that holds the selected channel manifest as the channel slug. These folders and `examples/` are local. Version the reusable studio and skill. Keep API keys in the environment.

`make help` lists the local shortcuts, `make status` shows what channel and episode resolve to, `make assets` reports the channel files an episode render actually reads, and `make prune-<group>` (dry run; add `APPLY=1`) removes assets that no render uses. Never prune a file a channel manifest still points at. Per-machine defaults live in an ignored `.env` (see `.env.example`); nothing about a specific channel belongs in tracked files.
