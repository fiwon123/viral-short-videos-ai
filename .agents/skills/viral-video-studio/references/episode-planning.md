# Episode planning and channel memory

A channel grows through consistency: the same promise, look, and voice, with fresh ideas inside it. Keep that consistency in files, not in your head, so any session can continue the channel. The templates are in [memory templates](../../../../docs/memory-templates.md).

## The channel's memory files

| File | Holds | Update when |
| --- | --- | --- |
| `workspace/<slug>/MEMORY.md` | Current direction, decisions that stand, direction history, next step | Every session, and whenever direction changes |
| `channel/AGENTS.md` | Rules for every episode: tone, story rules, look, sound, what to avoid | A rule is learned or the user changes one |
| `channel/episode-ledger.md` | One row per episode: topic, hook, series arc, format, results, lessons | An episode is planned, delivered, or its results come in |
| `channel/ideas.md` | Idea bank: unused ideas with their source and timing, the seasonal calendar, used and rejected ideas | Research turns up an idea, an idea is used, or one is rejected |
| `channel/series.md` | Series bible: characters and their current state, world rules, running gags, continuity facts, open threads | Every episode of a series |
| `episodes/<episode>/NOTES.md` | Status, research, open issues, next command, after-publish notes | During the episode |

Create any missing file from the templates before planning. Keep entries short and dated.

## Plan each new episode

1. **Load the channel.** Read `MEMORY.md`, `channel/AGENTS.md`, the ledger, `ideas.md`, and `series.md` when it exists.
2. **Check the calendar.** Today's date and the publishing window: upcoming holidays, seasons, school or sports events, releases, and anniversaries that fit the channel and the market. Add the useful ones to the seasonal calendar in `ideas.md`.
3. **Check what is moving.** Run a short trend pass for the niche over the last seven days (see [discovery](discovery.md): `discover --shorts --rank velocity --snapshots ...`, or browser research). Note topics, hooks, and formats that are rising, and anything the channel could answer or put its own spin on.
4. **Avoid repeats.** Compare candidates against the ledger: the same topic, hook pattern, punchline, reveal, or setting used recently. Change at least the angle or the form. Re-read the "lessons" column, and do not repeat a problem already logged.
5. **Respect the format.**
   - **Standalone:** prefer a timely angle (season, event, trend) that still fits the channel promise, and keep one or two evergreen ideas in reserve.
   - **Series:** continue the open threads in `series.md`. Pay off earlier setups, escalate stakes or relationships, keep continuity facts (names, injuries, objects, locations, running gags) exact, and end on a hook for the next episode. A timely topic can enter a series as the episode's situation, not as a break in the story.
6. **Offer concepts.** Give two to four concepts with a hook, payoff, length, and visual approach, saying which is timely (and until when) and which is evergreen, and which trend or ledger lesson each draws on.
7. **Stay recognisable.** Ideas and references can evolve, but the channel's look, characters, voice, caption style, and format change only when the user decides. Prefer small, deliberate variations, such as a new location, a guest character, or a new recurring segment, over drastic shifts.

## Push the odds before publishing

- Run `make viral-check EPISODE=...` on the manifest while blocking, and again with `VIDEO=.../video.mp4` after the preview render. Fix every high and medium note, or write in `NOTES.md` why it is intentional. Record the score.
- The check covers the opening (speech by 0.5 s, motion in the first half second, words in the first second, a non-blank first frame), pacing (a visible change every 2–4 s), runtime (15–45 s), captions, the loop (last frame leading into the first), loudness, and packaging (2–4 word thumbnail text, a title under 60 characters echoed in the first line).
- **Act fast on timely topics.** A trend that is rising in views per hour is worth an episode within 24–72 hours. After that, prefer evergreen ideas.
- **Double down on outliers.** When an episode clearly beats the channel's median (about 2× at the same age), plan a follow-up or a series continuation within days, and log why it may have worked.
- **Keep a sustainable cadence.** Early on, a steady rhythm of several Shorts a week finds the format faster than polishing one. Use `thumbnails` variants to test covers, and change one thing at a time between episodes so the ledger's lessons stay readable.
- **End with a reason to continue.** Series episodes end on the next question. Standalone episodes end on a loop or a payoff that invites a replay.

## After each episode

- **Ledger:** mark the row delivered with the date, topic, hook, arc, and format.
- **Series bible:** record what changed (character state, new facts, new running gag, threads opened or closed) and the setup for the next episode.
- **Ideas:** mark the idea used, and add follow-ups the episode suggested.
- **Results:** when the user shares numbers (views at 24 hours and 7 days, retention, comments), log them in the ledger with a one-line lesson. Prefer the patterns of episodes that outperformed the channel's median.
- **Memory:** set the next step in `MEMORY.md`.

## When the user changes direction

Update `MEMORY.md` "Direction now" and add a dated line to "Direction history" (what changed, why, from which episode). Update `channel/AGENTS.md` rules, and `brief.md` and `channel.json` when the branding or format changes (then run `make channel-doc`). Mark ideas in `ideas.md` that no longer fit, and note in `series.md` how the series adapts so existing viewers are not lost.
