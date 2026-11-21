# Plan and preview an original Short

## Design the joke or story beat

Write the viewer's immediate question and the visible change that answers it. Start on the character, prop, or action that raises that question. For a fast visual gag, test whether the first second works as a still and in motion. A slower opening can work when the viewer already has something specific to anticipate. Set the length after timing the action and reaction in a rough edit. For a single gag, a short first cut is an inexpensive way to find the essential beats.

Use one dominant point of attention in each beat. Let the character's body, gaze, and pose carry their intent, and give an important prop enough room to read on a phone. Add an insert or a wider reveal where it changes what the viewer knows. Keep the edit with the character or effect long enough to register the payoff. Try a loop when the final action leads naturally into the first frame.

## Choose the technique per shot

| Approach | Use it when | Inspect in the preview |
| --- | --- | --- |
| **2D** with SVG and GSAP | Silhouette, pose, and expression communicate the action. | Face and prop read against the background. Anticipation, impact, and settle have distinct poses. |
| **2.5D** with layered art or a mixed stage | The audience needs to see depth, a reveal behind something, or the scale of a prop. | Establish foreground, action plane, and background. Check parallax, the contact shadow, and where the subject passes behind an object. Match light direction and perspective across media. |
| **3D** with Three.js or an authored rig | A camera angle, rotation, reflection, contact, or change of scale carries information. | Test the silhouette, eyeline, lens and scale, contact poses, and cast shadows from the chosen camera. Use the existing hitbox and continuity checks where applicable. |

For a mixed shot, test the hardest overlap before making the surrounding shots. Screen-space SVG layers can sit in front of or behind the entire Three.js stage. If an element must pass between 3D objects, stage it in the same depth space or author a mask or render pass. Verify the actual composite on both sides of the overlap.

## Write the treatment before locking the manifest

Plan the episode in `episodes/<episode>/treatment.md` and pass `make treatment-lint EPISODE=...` before building shots. The [direction standard](direction.md) explains each part: the idea in one sentence, the route (continuous, montage or hybrid), the energy curve, the shot table (time, subject, action, size, camera, on-screen words, sound), the continuity chain and four key stills. The lint fails a plan that opens on a text card, holds one shot size throughout, pushes in three times running, has a flat energy curve, ends on a text card, or repeats the opening or payoff of the last three ledger episodes. Track each shot's starting and ending state in its row so the same prop, orientation, and light carry across the cut.

Use scratch timing for the rough edit. For dialogue, audition the recurring voice in context, using a line that matches the character's design, physicality, and attitude. Leave room for a thought or a breath where it improves the performance. Then measure the approved take and lock the shot and captions against that take. For a physical gag, try one recognizable sound for the action that changes the scene. Place its attack on the visible contact, and check whether silence gives the reaction more room. See the [audio guide](audio.md).

## Check the rough edit at phone size

1. **Opening.** Check the first frame and the first second. Can someone tell where to look and what question the shot raises? If the opening is ambiguous, compare two versions with the same body and ending. A tight prop insert and a character-led opening are two practical options.
2. **Muted.** Check the direction of the action, the difference between poses, the payoff, and whether platform overlays will cover the important action. For dialogue-led comedy, make the emotional turn visible and check that the essential words fit in the caption area.
3. **With sound.** Check character delivery, contact timing, caption sync, and whether the payoff is easy to hear on a phone speaker.
4. **Frame step.** Check the most important contact, a frame on either side of a layer crossing, and any 2D-to-3D cut for scale, light, and motion continuity. Use the [staging and visual QA guide](visual-qa.md) for the resolved render.

Render the four key stills from the treatment as soon as their shots exist, then use a hook preview (`make preview HOOK=20`, the opening 20 seconds with audio) or an animatic with equivalent timing. For the hook shot, `make hero EPISODE=... SHOT=... PROMPT="what moves" KEEP=<title id>` turns the shot's first frame (or `IMAGE=`) into an AI video clip on a machine with a video model (ComfyUI with Wan 2.2 TI2V 5B or an exported `WORKFLOW=`, or diffusers LTX-Video on 12 GB+), and into a 2.5D depth push everywhere else; run it automatically after the shot's still is approved, and check the clip in the hook preview. `KEEP=` holds hook titles crisp above the clip (video models warp text); `DRY=1` shows the plan. Open on a sound hit at t=0 (`viral-check` notes `hook-hit` otherwise) and words on screen in the first second so the hook reads with the sound off. Record which opening was selected and what the playback exposed. Fix unclear story beats before finishing artwork or rendering the master. Then render the whole Short as a preview, read its `film-qa/` folder and run the director round from the [direction standard](direction.md) before the master. After publication, the channel's own Shorts analytics can test hook and retention hypotheses when available.
