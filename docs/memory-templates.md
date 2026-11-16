# Memory templates

Working memory lets a new or interrupted session resume without guessing. Studio memory is [ROADMAP.md](ROADMAP.md), which is tracked and generic. Channel and episode memory live under the ignored `workspace/` folder. Copy these templates there and keep them short, dated, and current. How to use them is in the skill's [episode planning guide](../.agents/skills/viral-video-studio/references/episode-planning.md).

## `workspace/<slug>/MEMORY.md` (channel)

```markdown
# <Channel name>: working memory

Updated: YYYY-MM-DD

## Now
- Current focus: <episode or task>
- Next step: <exact action or command>

## Direction now
- Audience and promise:
- Tone and genre:
- Format (series / standalone / explainer), length, cadence, platform, language:
- Look and art technique:
- Voice cast, caption preset, music mood:
- Sound: sample packs imported, signature cues:

## Direction history
- YYYY-MM-DD: <what changed>, because <reason>. From episode <n>.

## Open issues
- 

## Where things are
- Onboarding answers: research/onboarding.md
- Trend research: research/trends-YYYY-MM-DD.md, research/snapshots/
- Rules: channel/AGENTS.md (style-lock block generated from channel/style-lock.json)
- Episodes made, in progress and planned: channel/episode-ledger.md
- Idea bank and seasonal calendar: channel/ideas.md
- Series bible: channel/series.md
- Brief and brand: channel/brief.md, channel/channel.md
- Latest renders: renders/
```

## `workspace/<slug>/channel/AGENTS.md` (channel rules)

Write the rules that hold for every episode here: tone, story rules, visual and sound identity, caption style, thumbnail language, and what to avoid repeating. Add a rule when a lesson repeats. The block between the `style-lock` markers is generated from `style-lock.json` by `make style-lock`; edit the lock, not the block.

## `workspace/<slug>/channel/episode-ledger.md`

| # | Episode | Status | Published | Topic and angle | Hook (first 2 s) | Series and arc | Format and length | Results (24 h / 7 d) | Lessons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

Status: planned, in progress, delivered, published. Leave results empty until the user shares them.

## `workspace/<slug>/channel/ideas.md` (idea bank)

```markdown
# Idea bank

## Seasonal calendar
| Date or window | Event or season | Angle for this channel |
| --- | --- | --- |

## Unused ideas
- <idea> · source: <trend link / ledger lesson / user> · timely until: <date or "evergreen">

## Used
- <idea> → episode <n>

## Rejected
- <idea>: <why>
```

## `workspace/<slug>/channel/series.md` (series bible)

```markdown
# Series bible

## Characters
- <name>: look, voice, personality, current state (what they know, have, feel)

## World rules
- 

## Running gags and signatures
- 

## Continuity facts
- Ep <n>: <fact that later episodes must respect>

## Open threads
- <setup> (opened ep <n>), planned payoff: <idea>

## Next episode setup
- 
```

## `workspace/<slug>/episodes/<episode>/NOTES.md` (episode)

```markdown
# <Episode>: notes

Status: concept | script | audio locked | animating | preview | master delivered | published
Updated: YYYY-MM-DD

## Research
- Date and season angle:
- Trends considered (links, views, growth):
- Ledger check (repeats avoided, lessons applied):
- Series continuity used:

## Next step
<exact command, e.g. make still EPISODE=... SHOT=... --sheet 5>

## Open issues
- 

## Done
- 

## After publish
- Results:
- Lessons for the ledger:
- Follow-up ideas:
```
