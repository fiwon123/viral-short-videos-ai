# 📈 Make Shorts Travel

<p align="center">
  <img src="https://raw.githubusercontent.com/fiwon123/viral-short-videos-ai/main/docs/assets/short-anatomy.svg" alt="Anatomy of a strong Short" width="900">
</p>

No one can guarantee a viral video. You can increase the chance that the right viewer stops, watches to the end, and shares by making the first second clear and the payoff worth the wait.

## The six things that matter

### 1. One question in the first second

The viewer should know what they are waiting for:

- What is behind the door?
- Will the crane catch the letter?
- Why is the robot pressing the wrong button?

Start on the face, prop or action that raises the question. Do not open on an empty establishing shot unless the emptiness is the question.

### 2. One visible change

A Short is not a monologue with pictures. Something must change:

- A prop moves
- A character changes pose
- A light changes
- A scale changes
- A new object enters

If the viewer can skip 10 seconds and miss nothing, the middle is too static.

### 3. One payoff

Pay off the title, thumbnail and first frame. Do not introduce a second joke at the end. Hold the payoff long enough to register, then get out.

### 4. Loop

The last frame should lead naturally back to the first:

- A door closes and reopens
- A character returns to the start pose
- A sound or line repeats
- A camera move reverses

A loop is not a trick; it is a second viewing.

### 5. Captions and sound that survive the phone

- Keep captions short and clear.
- Put the active word on the spoken word.
- Keep music under dialogue.
- Put the contact sound on the contact frame.
- Check on a phone speaker, not just headphones.

### 6. A repeatable signature

The audience should recognize the next video before the title:

- Same character silhouette
- Same palette and type
- Same opening rhythm
- Same payoff family
- Same runtime range

Consistency is how a viewer becomes a subscriber.

## Studio tools for the hook

- **`make preview HOOK=20`** renders only the opening 20 seconds, with sound and captions. Approve the hook before the full render.
- **`"punchline": true`** on a speech line holds 0.3 s of silence before the next line, and `pause_after` sets any length. Captions, lip sync and sound effects follow.
- **`make hero SHOT=A KEEP=<title id>`** gives the opening shot motion: an AI video clip on a GPU, or a 2.5D depth push anywhere else. See [AI Characters and Hook Clips](AI-Characters-and-Hook-Clips).
- **`make viral-check`** notes a slow first line, no motion or words in the first second, no sound hit at t=0, long holds, a weak loop and loudness.
- **`make film-qa`** (run by every render into `film-qa/`) reads the pixels: motion per second, stretches where nothing moves, a frozen ending, blank frames, one framing held too long, single-frame pops, and a first frame that is not the opening picture (the poster feeds show). A shot can have a camera move on paper and still stand still on screen.

## Pacing template

| Time | Job | Check |
| --- | --- | --- |
| 0–1 s | Face, prop or action | Can you tell what to watch? |
| 1–2 s | The question | Would you keep watching? |
| 2–6 s | Setup | Is the stakes clear without a paragraph? |
| 6–18 s | Escalation | Does something visible change every 2–4 s? |
| 18–26 s | Payoff | Does it pay off the hook? |
| 26–30 s | Loop | Does the last frame lead back? |

For a 45–60 s Short, extend the escalation, not the setup. For TikTok Creator Rewards, the video must be at least 1 minute; make the story earn that minute rather than padding it.

## Hook patterns that work

| Pattern | Example |
| --- | --- |
| Wrong expectation | “This button definitely does not open the moon.” |
| Forbidden action | “Do not press the yellow one.” |
| Wrong recipient | A letter arrives at the wrong planet |
| Escalating mistake | One small error becomes three |
| Exact instruction | A literal reading of a normal human phrase |
| Countdown | Three attempts, one second each |
| Visual contradiction | A tiny character with an enormous prop |

## Test one variable at a time

Change one thing per upload:

- Hook framing
- Opening line
- Caption style
- Runtime
- Payoff hold
- Thumbnail text

Compare uploads at the same age, not raw lifetime views. Look at:

- First-second retention
- Average view duration
- Completion
- Shares
- Saves
- Comments that quote a specific moment

## Common failure modes

| Problem | Fix |
| --- | --- |
| Slow opening | Start on the action; remove the establishing shot |
| Explanation | Replace a line with a visible action |
| Flat middle | Add a new obstacle or visual change every 2–4 s |
| Weak payoff | Make the answer visible, not narrated |
| No loop | End on the start pose or return the prop |
| Captions cover the action | Move captions or reframe |
| Loud music | Duck harder under dialogue |
| Unclear character | Increase silhouette, contrast and size |
| Too long | Cut the setup, not the payoff |
| One wide framing with the cast in a row | Wide only to set up; cut to a close-up for the reaction and an insert for the prop |
| The picture freezes after the payoff | End on a reaction, a settle, or a move back into frame one |
| Every shot pushes in | Go in, then come back out; keep crash zooms for the payoff |

## Direct before you animate

Most weak Shorts are not missing features; they are missing a plan and a hard look at the render. The studio's assistant works in this order (the full standard is in the skill's `references/direction.md`):

1. **Treatment.** `episodes/<episode>/treatment.md` holds the idea in one sentence, the route (continuous, montage or hybrid), an energy curve rated 0–10 per stretch, and a shot table where every row names a subject and an action, with its shot size and camera move. `make treatment-lint EPISODE=...` fails a plan that opens on a title card, keeps one shot size throughout, pushes in three times in a row, has a flat energy curve, or repeats the last three episodes' opening or payoff.
2. **Stills, then a whole draft.** The hardest shot and the hook as stills first, then the complete Short as a preview.
3. **Measure and review.** Every render writes `film-qa/`: the energy per second, the stretches where nothing moves, and a contact sheet. A reviewer that did not build the episode gives the three notes a demanding director would give. The P0s are fixed before the master.
4. **Learn.** The ledger records each episode's grammar and film-qa verdict, so the next one varies.

## Do not chase virality by copying

Use references to learn structure. Build original characters, jokes, voices and art. Reuploads, compilations and unedited third-party clips are risky for policy and monetization.

## 🔗 Related guides

- [YouTube and TikTok Monetization](YouTube-and-TikTok-Monetization)
- [Automate a Channel](Automate-a-Channel)
- [QA, Export and Publishing](QA-Export-and-Publishing)
