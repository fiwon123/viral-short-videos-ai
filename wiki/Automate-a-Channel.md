# ⚙️ Automate a Channel

The goal is not “one button makes a video”. The goal is a repeatable loop where the AI does the production and a person approves the creative direction.

## 🏭 The weekly loop

| Day | Job | Output |
| --- | --- | --- |
| Monday | Research and idea generation | 10–15 scored ideas |
| Tuesday | Choose 2–3 and write beat sheets | Timed beats |
| Wednesday | Build manifests and audio | Validated episodes + mix |
| Thursday | Preview and fix | Approved previews |
| Friday | Master, thumbnail and publish | Packages + posts |
| Weekend | Review analytics at the same age | One test for next week |

Start with one upload per week. Add a second only when the review loop is stable.

## 🧱 Make the channel reusable

Before scaling, lock:

- Channel palette and typography
- Character silhouettes and voices
- Opening rhythm
- Payoff families
- Caption style
- Runtime range
- Thumbnail language
- Audio library and reverb
- Camera and transition grammar

Store these in `channel/channel.json`, `channel/brief.md`, `channel/audio/`, `channel/scene-library/`, `channel/vfx/` and `presets/styles/`.

## 📦 Batch prompt

```text
Read the channel brief, the last 5 episodes and this week's analytics.
Propose 12 ideas that fit the promise but use a new situation.
Score each on hook, visual, payoff, loop, effort and repeatability.
Wait for me to choose three. Then write beat sheets only, not manifests.
```

After approval:

```text
Build the three manifests in parallel under workspace/<channel>/episodes/.
Use the same cast, palette, caption style and audio library.
Validate all three. Render audio-only for review before any visual render.
```

## ✅ Quality gates

Do not scale past these gates:

| Gate | Pass condition |
| --- | --- |
| Hook | The first frame raises one question |
| Muted | The action reads with sound off |
| Phone | Face, prop and caption read at small size |
| Payoff | It pays off the title and thumbnail |
| Loop | The last frame leads back |
| Audio | Dialogue is forward, impacts land, loudness is in range |
| Originality | No copied character, joke or unlicensed asset |
| Packaging | Title, description, tags and thumbnail agree |

If a gate fails twice, stop the batch and fix the format, not just the episode.

## 🤖 What to automate

- Research summaries
- Idea lists and scoring
- Beat sheets
- Manifests and keyframes
- Foley generation and mix
- Caption timing
- Thumbnail variants
- Publishing copy
- QA reports
- Batch folder organization

## 🧑 What to keep human

- The audience promise
- The final story taste
- Character and brand approval
- Rights and licensing
- Final publish decision
- Replies to comments and community

## 📈 Analytics loop

Review at the same age:

- First-second retention
- Average view duration
- Completion
- Shares and saves
- Profile visits
- Subscriber conversion
- Comments quoting a specific moment

Change one variable per week. Keep a note in `research/` with the hypothesis and result.

## 🚫 What not to automate

- Copying another creator’s work
- Fake views or engagement
- Uploading to a platform without authorization
- Publishing a render that failed QA
- Ignoring platform policy or music rights

## Next

- [Make Shorts Travel](Make-Shorts-Travel)
- [YouTube and TikTok Monetization](YouTube-and-TikTok-Monetization)
- [Contributing](Contributing)
