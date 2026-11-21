# Direct the Short

The studio can animate almost anything: rigs, IK, lip sync, 2.5D depth, 3D, physics. None of that makes a Short good on its own. Quality comes from decisions made before the first keyframe and from looking hard at the render afterwards. This guide is the standard every episode is held to, and the order of work that gets there.

Read it before writing a treatment, again before the director round, and whenever the user says an episode is "fine but boring", "static", "amateur" or "like slides".

## The bar

A stranger scrolling with the sound off knows where to look on frame one, understands the situation in a second, feels the payoff land, and wants to watch it again or send it to someone. A Short can pass every check here and miss that; the checks exist because most Shorts that miss it fail in the same few ways.

**Three tests, in the order Shorts fail them:**

1. **Is something happening on frame one?** The subject is already in frame and already moving: a prop mid-fall, a hand reaching, a face reacting. Never a title card, an empty set, or the cast standing in a row waiting for the first line.
2. **Does the energy have a shape?** A hook, a build in steps, sometimes a held breath, a peak on the payoff, a landing. `film-qa/energy.png` shows the shape of the render; a flat line is a flat Short however good each frame is.
3. **Is any stretch a slide?** One framing, a group of characters standing in it, the caption changing underneath. That is a slide however well it eases. Every stretch gets its own shot size or its own move.

## How Shorts from this studio have gone wrong

These come from measured channel renders, not theory. Each has a number that catches it.

| Failure | What it looks like | Caught by | The fix |
| --- | --- | --- | --- |
| **The stage play** | One wide side-on framing for the whole Short, the cast at a quarter of the frame height in a row, a third of the frame empty floor | `one-size` (treatment), `one-framing` (film-qa) | Wide only to set up. Cut to a close-up for the reaction and an insert for the prop. At the moment of change, the thing that changes fills a third of the frame or more. |
| **The frozen tail** | The payoff lands, then the picture stands still for seconds while the caption holds | `frozen-end` (film-qa) | End on an action: a reaction, a settle, a second small gag, or a move back into frame one for the loop. |
| **Alive is not acting** | The rig blinks and breathes, so the manifest "moves", but nothing happens | `flat`, `dead` (film-qa) | `alive` is the floor. Key the acting on top: anticipation, the action, the settle, a specific expression on each beat. |
| **Camera as habit** | A slow push on every shot, or a shake on every hit | `push-run`, `accents` (treatment) | Camera moves are punctuation (below). Go in, then come back out. Keep accents for the reveal and the payoff. |
| **Captions carry the film** | The words change, the picture does not | `text-led`, `flat` | Cover the captions and read the contact sheet. Every beat must still say what is happening. |
| **Mush** | A dark, low-contrast grade; the subject melts into the set at feed size | Hook still at feed size, `first-frame` (viral-check) | One key light, a value step between subject and ground, a rim on the silhouette. Check the hook still at 270 px wide. |
| **The sticker cast** | Characters in a different style from the set, generic bean faces, faces drawn on every prop | The character bar (below) | Rig and improve the approved art. Props act through shape and motion, not faces. |
| **The late hit** | The thud lands a few frames after the contact, the pop before the bubble bursts | `sound-late`, `sound-early` (film-qa) | Put an impulsive cue on the frame where the motion starts or stops: `at` on that key's time, or anchor it. Check `metrics.sync` in the film-qa report. |
| **Same grammar again** | The new episode opens and pays off exactly like the last three | `repeat` (treatment) | Change the opening device or the payoff device; the ledger's Grammar column remembers them. |

## Plan: the treatment

Write `episodes/<episode>/treatment.md` (template in [memory templates](../../../../docs/memory-templates.md), created by `make channel-memory SLUG=... EPISODE=...`) before building any shot, and pass `make treatment-lint EPISODE=...`. It is short: a few lines and two tables.

**The idea in one sentence.** The visible change the viewer waits for, and why it lands: "the duck lifts a barbell that is secretly the octopus, and the rat sees it first". If you cannot write it, the episode is not ready to animate.

**The route.** Choose how the eye is carried:

| Route | What carries the eye | Cuts | Use it for |
| --- | --- | --- | --- |
| **Continuous** | One world, a camera travelling through it, one subject followed | 0–2 | Loops, ASMR, a single physical process, a journey |
| **Montage** | Cuts on the beat (`snap: "beat"` on each shot, `at_beat` on keys and hits), each shot readable at a glance | Many, on the beat | Lists ("five ways to…"), escalation gags, music-led Shorts |
| **Hybrid** | A continuous spine broken by a quick burst at the turn or the payoff | A burst | Most character gags and stories |

**The energy curve.** Rate each stretch 0 to 10 before deciding a single key. The shapes that work in an 8–20 s Short:

- **Hook at 5 or more, inside the first second.** Shorter than a launch film's three seconds: the swipe comes sooner.
- **Climb in steps.** Each step adds something nameable: a second character enters, the prop gets bigger, the camera starts moving. A slope you cannot name is a plateau.
- **An optional stop.** 0.3–0.8 s of near stillness before the payoff, with the sound pulled out (a `punchline` line or `pause_after`). Declare it as `Stop: <start>-<end>` so film-qa does not flag it. A signature move, not a requirement.
- **The peak on the payoff**, usually at 60–85 % of the runtime, at 7 or more.
- **A landing.** One or two seconds after the peak: the reaction, a tag, or the move back into frame one. A Short that stops on its peak frame feels cut off.

Shapes that read as boring: a flat line at 3–5 with one hit at the end; a slow build that peaks in the last half second; every shot at the same energy.

**The shot table.** One row per shot: time, **subject** (a noun you could point at), **action** (a verb), size, camera, on-screen words, sound. A row you cannot fill with a noun and a verb is a shot you cannot animate yet. Rules of thumb for a Short:

- Something new every 1.5–2 s: a cut, a landing, a camera move starting or stopping, a reaction, a new sound. Only a declared stop is exempt.
- Shots of 1.5–4 s. A shot over 6 s needs a travelling camera with a job, or a split at the turn.
- Change at least two things at every section boundary: shot size, camera (still / travelling / whip), density (one subject / a crowd), speed, light or colour, sound texture. Change all of them at the payoff.
- On-screen text: two to six words, one line at a time, never the only thing changing. Text cards fill under 30 % of the runtime, never the first or last shot.

**The continuity chain.** One line per cut: what carries the eye from shot to shot (the prop, a gaze, the direction of motion, a colour, a sound). A cut you cannot name a link for is a jump; keep it only when the jump is the joke.

**Four key stills.** Hook, hero (the payoff frame), densest, end. Render them for real with `make still EPISODE=... SHOT=... PROGRESS=...` as soon as their shots exist. If a still does not work as a poster at phone size, the moving version will not either. The hook still is also the thumbnail candidate.

## Stage: the frame is on the change

- **Size the subject for a phone.** At the moment something changes, the thing that changes fills a third of the frame or more. In 9:16 that usually means head-and-shoulders or a prop insert, not full bodies in a lineup. A wide shot where a small region changes is a spot-the-difference puzzle.
- **Stage in depth, not in a row.** Diagonals, overlap and three planes: foreground (a prop edge, `z` > 0), action plane, background (`plane: "background"`, `parallax` below 1). Characters look at each other or at the prop, not at the lens, unless they are talking to the viewer.
- **Keep the eye where it is and change what it sees.** For a list or an escalation, hold the anchor (a character, a counter, a frame) in place while the thing beside it changes on each beat. The viewer learns once where to look.
- **One caption position.** Captions live in one band, clear of faces (`caption_avoid` and the kinetic placement do this) and clear of platform buttons. A caption over the action it describes is the most common note.
- **The background is alive.** Light shifts, ambient life, a parallax drift, a reaction in the background. A flat colour or a static set behind a small moving subject reads as dead.
- **One look for the whole Short.** The style lock already holds the cast and grade; also hold the line weight, shading and palette for every prop and effect you add. A clean, consistent Short beats a collage of techniques.

## Camera: punctuation, not decoration

Before moving the camera, answer three questions: where should the viewer look right now, and can they see it at this size? Is this a transition or an accent? What did the previous shot's camera do?

| Move | Studio field | What it says | Starting numbers |
| --- | --- | --- | --- |
| Hold | no `camera` | Read this; the action is the point | As long as the action needs |
| Drift | `float`, or a 3–6 % scale key | The shot is alive while nothing else changes | Linear, slow; under every hold longer than 0.8 s |
| Slow push | `push-in`, `dolly-in` | Lean in to a detail or a feeling | 0.6–1.5 s, 10–40 %, ease in-out |
| Pull out | `pull-out`, `dolly` back | Reveal context, close a section, end | 0.8–2 s, fast start, long landing |
| Pan / follow | `x` keys, `follow`, `fly-through` | Travel with a moving subject or along a set | Speed of the subject |
| Cut in | a new shot one size closer | The reaction: comedy's main tool | 0 frames; the cut lands on the reaction's first frame |
| Crash zoom | `crash-zoom` | The reveal, the realisation, the punchline | 0.2–0.35 s, 18–32 %, then hold |
| Whip | `whip-pan`, `whip-left`/`whip-right` transition | Attention or time jumps | 0.25–0.3 s with `motion_blur` |
| Shake | `shake`, `handheld` | An impact or panic | On the contact frame, decaying in 0.3 s |
| Dolly zoom | `dolly-zoom` | Dread, a world shifting | Once a film at most |

Rules:

- **In, then out.** After a push in, the next move pulls out, pans across or cuts to a new size. Three pushes in a row and the viewer feels a metronome.
- **Accents are rationed.** About one crash zoom, whip or shake per six seconds. Every one on the reveal and the payoff; none on setup lines.
- **In comedy, hold and cut.** A locked frame, then a hard cut to the reaction close-up, lands harder than any push.
- **A camera move has a job and lands.** Front-loaded, eased, and finished before the cut. Never a float that drifts back to where it started.
- **Zoom is even by default.** Camera `zoom` keys interpolate in log space, so a linear key moves at a constant visual rate (1× to 4× passes 2× halfway) and the ease you write is the shape you see. Shape a push with the ease, not by adding keys to fight the interpolation.

## Acting and motion

- **Pose to pose.** Block the anticipation, the key pose and the settle before easing (the [animation cookbook](animation-cookbook.md) maps these to `pose_keys`, `motion` recipes and `ik`). Every appearance gets an expression and a pose that belong to that beat: frowning at the phone, a sigh of relief while pocketing it, not just a blink and a bob.
- **Nothing moves linearly** except a drift. Hard ease-out for snappy arrivals, springs only for things that should feel physical, overshoot only on a true landing. Squash on contact, stretch on speed.
- **No pixel-still holds.** A hold longer than 0.8 s keeps a drift, an idle or a breath. Only a declared stop is still.
- **Action on the word.** When a line names a thing, the thing appears, moves or changes on that word, not a second later. Write the key with `at_word` (the [animation cookbook](animation-cookbook.md) shows the fields) so it stays on the word when a take is re-recorded.
- **Sound lands with the motion.** A hit on the contact frame, a whoosh under the whip, silence before the payoff. Frame one has a sound (viral-check's `hook-hit`).

## The character bar

A rough character is worse than none: one glance at a generic bean face and the viewer files the Short as cheap. Before casting, zoom the character to 2× in a `--sheet` still and check:

1. **The silhouette reads.** Filled solid black, you still know who it is and what they are doing.
2. **Proportions have joints.** A neck, shoulders, elbows and wrists that the rig bends at; the head-to-body ratio stays the same all film.
3. **Hands hold things.** The prop is in the hand (parented or IK), not pasted beside it.
4. **Two tones and a rim.** Base, shadow and a highlight or rim, lit from the same side as the set (`light`, `lit`).
5. **Material detail.** At least three details the character should have: seams, hair groups, a strap, a texture.
6. **Specific acting.** Each appearance has its own expression and pose for that beat.
7. **Same hand as the set.** Line, shading and palette match the background; not a sticker on someone else's painting.
8. **Consistent.** Face, hair, outfit and colours identical in every shot.

Props act through shape, scale and motion. A prop gets a face only when it is a designed lead character, chosen as one of three directions and held to this bar.

## Three directions, when the look is being decided

When a channel's look is chosen, a series changes format, or a punch-up would change the style, show three directions as **real key frames** (`make still`), not descriptions. They differ in staging, composition and technique, not in palette: for example one flat 2D cut-out, one 2.5D layered depth, one 3D. Name each by a reference the user knows. Users often mix by layer ("A's staging with B's light"), so describe palette, staging and rhythm as separate lines that can be recombined. For a routine episode inside a locked style, one concept sentence with its hook still is enough.

## Review: two rounds of your own notes before the user sees it

Episodes that came out well had a demanding critic. When the user gives one line and no notes, be that critic yourself.

1. **Stills round.** The four key stills and a `make still SHEET=6` per busy shot. Fix composition, subject size, captions and contrast here, where fixes are cheap.
2. **Draft round.** Render a full preview. Read `film-qa/report.json`, `energy.png` and `sheet.png`, then run the **director pass** with a reviewer that did not build the episode (a subagent, given only the review pack below). Fix every P0, as many P1s as time allows, re-render, and rerun film-qa. Only then render the master.

`make review-pack EPISODE=...` builds the packet for that reviewer in `episodes/<episode>/review/pack-<render>/`: the contact sheet, the energy chart, the film-qa report, the treatment, a frame at each of the treatment's key stills, and a filled `prompt.md` (picture first with words covered, the frame-time questions, the three notes a demanding director would give, ranked P0/P1). Hand the reviewer only that folder. Their notes go to `review/director-<render>.md`, which `make state` and `make deliver` look for.

The same pack prepares two more reviewers, each given one lens and its own evidence; run them as separate subagents so one reviewer's taste does not cover another's blind spot:

- **Sound** (`prompt-sound.md`). The reviewer cannot hear, so it reads `sound.png` (the mix's level over time, every cue and cut marked, the picture's energy behind) and `sound-cues.json` (every cue with its shot and film-qa's sync status). It checks the hook's first sound, the lock of every hit, a visible cause for every sound and a sound for every expected action, stacked effects, the payoff as the loudest moment, the music's joins and the end. Notes to `review/sound-<render>.md`.
- **Continuity** (`prompt-continuity.md`). `cuts.png` puts the last frame before and the first frame after every hard cut side by side; with the key stills it checks contact with the floor, who owns each limb and prop, the same cast, props, direction and scale across the cut, layering, set edges and one style. Notes to `review/continuity-<render>.md`.

Every prompt lists the earlier review notes, so a second round checks the fixes instead of repeating them. `LENS=sound` (or `continuity`, `director`, comma-separated) prepares only those.

When no independent reviewer is available, run the pass yourself from the same packet and say so in the notes. A director's note written by the maker is weaker evidence; `delivery.md` lists the file either way and never reads it.

The notes that come up most: the opening is not one strong idea; the energy is the same throughout; the payoff is too small or too wide; the picture is thin (one ground, one framing); text sits over the action; the end freezes; nothing in it could only be this channel.

## Punch-up: a Short that is correct but flat

When the user says an existing episode should be much better, polishing will not get there: longer eases and one more sound effect leave a flat Short flat.

1. **Diagnose with numbers first.** film-qa (mean energy, low-energy share, longest framing, dead runs) and the contact sheet. Reconstruct the treatment from the manifest and run the lint. Tell the user three or four lines with the numbers before rebuilding.
2. **Keep** the idea, the approved lines and voice takes, the cast, the look and the length within a second or two. **Rebuild** the shot sizes, staging, camera, timing inside each beat and the sound placement.
3. Render to a new `-vN` folder; never overwrite the old render, which the user will compare.
4. Report before and after with the same numbers. The numbers prove it moves; only the user can say it is better, so call the result "rebuilt, not yet judged".

## Learn from every episode

- Fill the ledger's **Grammar** (opening, payoff, camera) and **Film QA** columns at delivery, so the next treatment can vary them.
- Quote the user's notes word for word in the channel's `MEMORY.md`, marked as a **preference** (their taste, holds until they change it), **observed** (seen in one episode) or **verified** (seen in two or more, or measured). One user's taste is never a studio rule.
- When a lesson repeats, promote it to the channel's `AGENTS.md` rules.
- **When a tool could catch a lesson, change the tool instead of adding a rule.** Open a studio issue (a new note in `film-qa` or `treatment-lint`) with the episode as evidence. A check runs every time; a sentence in a guide gets skipped.

---

The method is adapted from four open agent video skills (MIT): huashu-motion (energy curve, rhythm sheet, the slide test, self-notes, harvesting feedback), huashu-art-motion (shot-list lint, camera language, the character bar, independent review), cinetic (the numeric standard, the single director pass, variety against recent films) and lanshu-create-ai-presenter-video (action on the word, stillness checks, evidence before claims). The rules here are rewritten for vertical character Shorts and this studio's tools.
