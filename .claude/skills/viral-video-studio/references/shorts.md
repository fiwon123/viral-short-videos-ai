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

## Use a beat sheet before locking the manifest

Save the plan with the episode. Each row can map to a shot or a timed event within a shot. Track starting and ending state so the same prop, orientation, and light carry across the cut.

| Start–end | What the viewer learns | Framing and position | Acting and motion | Prop contact, layers, light | Voice, caption, sound | Cut or hold |
| --- | --- | --- | --- | --- | --- | --- |
| | Hook / setup / escalation / payoff / exit | Shot size, screen position, eye line | Start, key pose, end | Support, occlusion, shadow | Cue and offset, optional silence | Trigger and duration |

Use scratch timing for the rough edit. For dialogue, audition the recurring voice in context, using a line that matches the character's design, physicality, and attitude. Leave room for a thought or a breath where it improves the performance. Then measure the approved take and lock the shot and captions against that take. For a physical gag, try one recognizable sound for the action that changes the scene. Place its attack on the visible contact, and check whether silence gives the reaction more room. See the [audio guide](audio.md).

## Check the rough edit at phone size

1. **Opening.** Check the first frame and the first second. Can someone tell where to look and what question the shot raises? If the opening is ambiguous, compare two versions with the same body and ending. A tight prop insert and a character-led opening are two practical options.
2. **Muted.** Check the direction of the action, the difference between poses, the payoff, and whether platform overlays will cover the important action. For dialogue-led comedy, make the emotional turn visible and check that the essential words fit in the caption area.
3. **With sound.** Check character delivery, contact timing, caption sync, and whether the payoff is easy to hear on a phone speaker.
4. **Frame step.** Check the most important contact, a frame on either side of a layer crossing, and any 2D-to-3D cut for scale, light, and motion continuity. Use the [staging and visual QA guide](visual-qa.md) for the resolved render.

Use a rough `render --preview` or an animatic with equivalent timing. Record which opening was selected and what the playback exposed. Fix unclear story beats before finishing artwork or rendering the master. After publication, the channel's own Shorts analytics can test hook and retention hypotheses when available.
