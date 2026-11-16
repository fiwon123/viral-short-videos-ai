# Studio roadmap

This is the tracked memory for studio work: the renderer, schema, tools, presets and skill. Read it before resuming studio work, and update the status as items land. Keep it generic, with no channel names, episodes or brand details. Those go under `workspace/<slug>/`.

## Status (update as you go)

| Item | State | Notes |
| --- | --- | --- |
| Track A1: measured word timing | Done | `studio/wordtiming.py`. Uses energy/pause alignment, or Whisper if `faster-whisper` is installed (`STUDIO_WORD_TIMING`). Hooked in `audio.measured_words`. |
| Track A2: kinetic captions | Done | `studio/captions.py` and `browser/captions.mjs` (they mirror each other). The `style: kinetic` presets include hormozi-pop, with `*word*` emphasis. `captions.hold` defaults to 0.45 s. |
| Track A2: caption face/hitbox avoidance | Done | `studio/caption_place.py` picks a clear band per cue (`placement`) from rig face roles and `caption_avoid` layers. Kinetic style only. |
| Track A3: caption QA in `make check` | Done | `captions.audit` lists `caption_notes` (fast, short, flicker, ui-zone) from `check-visual`. Notes don't block the render. |
| Track B1: recorded SFX import | Done | `studio/samples.py` and `make sfx-import DIR=... [DRY=1]`. |
| Track B2: per-cue tone | Done | `highpass`, `lowpass`, `punch`, `saturate` on cues and layers (`audio.shape_tone`). Spotting sets defaults. |
| Track B3: SFX auto-spotting | Done | `studio/spotting.py` and `make spot [APPLY=1]`. Cues carry `"spotted": true`. |
| Track B4: mix polish | Done | SFX bus `glue()`, music `sfx_duck`, and `sound_notes` density check in `check-visual`. |
| Phase 1.1: shared expansion pipeline | Done | `studio/pipeline.py:prepare_episode` is used by `video.py` and `editor.py`. |
| Phase 1.2: SVG easing parity | Done | GSAP pose path removed from `painter.mjs`. Every layer uses `poseAt`, including `ease_props` and `auto`. |
| Phase 1.3: motion-blur parity | Done | Browser shot blur averages real sub-frames like Python. Layer blur samples the full pose over `MOTION_SHUTTER` (0.08 s), not 5% of the shot. |
| Phase 1.4: lint warnings | Done | `studio/lint.py` (sub-frame keys, particle cap, 2D fov). Reported by `validate` and `render`. |
| Phase 5.3: parity gate | Done | `video.py parity --threshold 0.03` exits non-zero when renderers drift. |
| Track C1: rig-ready character generator | Done | `studio/character.py` and `make character SPEC=...`. Outputs shaded part SVGs, a role-tagged rig and `preview.svg`. |
| Track C2: auto life | Done | `studio/life.py`, run in `pipeline.prepare_episode`. Layer field `alive` covers breathe, blink, glance, sway and follow-through. Talking uses the `quiet_for`/`talk_only` mouth swap in both renderers. |
| Track C3: style passes | Done | The generator has cel shade, rim, gloss and texture. Line boil (`studio/boil.py`, `boil`/`boil_fps` on SVG layers, browser) is done. `finish` on SVG layers (`studio/stylepass.py`) adds an SVG-filter cel shade, rim, grain and outline to any existing SVG while it is staged for the browser. |
| Track C4: finishing post | Done | `post.paper`, `post.leak`, plus `post.grade` (6 baked looks) and `post.lut` (.cube) via `studio/grade.py`. Browser gets the same baked table (`lut_data`). |
| Track C5: art-quality checks | Done | Dead frames are the motion report's `dead-hold`. `contrast_notes` adds WCAG contrast for text (3:1) and foreground shapes (1.4:1) against the solid layer behind, from authored fills. Background-plane scenery and same-colour stacks are skipped. SVG/image art is not judged (would need pixels). |
| Phase 2.1: motion paths | Done | `studio/moves.py` `path` (Catmull-Rom, arc-length, `orient`). |
| Phase 2.2: wiggle | Done | `wiggle` seeded value noise on any property. |
| Phase 2.3: follow | Done | `follow` chase and drag spring modes. `alive` adds drag on ears and antenna. |
| Phase 2.5: manifest-native recipes | Done | `motion: [{recipe, t, d}]`: pop, anticipate, impact, settle, shake, spin, enter, exit, drop, jump, nod, wobble. |
| Phase 2.6: pose library | Done | `studio/poses.py` `pose_keys`. Poses live in the rig library `poses.<rig>` or episode `poses`. `make character` writes 10 starter poses. Two-bone IK: `ik` on a group (`studio/ik.py`) solves one- or two-part chains from poses only (no sprite sizes), with screen or layer targets, blend/glide/release keys and `bend`. Generated limbs carry a `tip`. |
| Phase 6: animation cookbook | Done | `.agents/skills/viral-video-studio/references/animation-cookbook.md`, linked from SKILL.md. |
| Phase 5.1: onion-skin stills | Done | `still --onion N --onion-step s` (`make still ONION=3`). Median background, tinted ghosts. Works on every renderer. |
| Phase 5.2: motion report | Done | `studio/motion_report.py` and `make motion-report`. Flags dead holds, linear moves, lockstep starts, snaps and frozen rigs, and writes a speed chart PNG. |
| Phase 5.4: browser pose parity test | Done | `BrowserPoseParityTests` runs `browser/pose.mjs` in node against `design.pose_at` for every ease, `ease_props`, booleans, `frame` and colour lists. It caught `auto` on lists (Python used smoothstep; now Catmull-Rom per channel, tint clamped). |
| Phase 3.1: z depth | Done | Layer `z` uses authoring-relative depth: no change at rest, parallax on pans, perspective on camera `z` dollies. Adds depth fade, `camera.focus` depth of field, far-to-near `depth_order`, and 2D `fov` support. |
| Phase 3.2: perspective tilt | Done | Keyable `turn_x`/`turn_y` (degrees, about the pivot). Python uses `turn_tile` (PIL `PERSPECTIVE`), the browser uses a 10×10 triangle-mesh warp (`turnedTile`). Wipe applies before the turn. Groups and children don't inherit it. |
| Phase 3.3: depth camera presets | Done | `dolly-in`, `dolly-out`, `dolly-zoom` (vertigo) and `fly-through`. |
| Bug fix: child layers got the camera twice | Done | The camera now applies only to top-level layers in both renderers. Rig parts no longer drift on zooms or pans. |
| Phase 4.1: 3D camera rigs | Done | `studio/rig3d.py` `three.camera_rig`: orbit, dolly, crane, flyby and follow, with handheld and fov. |
| Phase 4.2: lights and atmosphere | Done | Scene `lights` (point, spot, hemisphere), `fog`, and `environment: room` (PMREM). Lights keyable per shot. |
| Phase 4.3: text in 3D | Done | `text` is a canvas-textured plane, or extruded `TextGeometry` with `depth`/`bevel`. `studio/typeface.py` reads TrueType `glyf` outlines (no dependency) into typeface JSON with only the used glyphs, staged by `browser._stage_typeface`. CFF .otf falls back to the plane. |
| Phase 4.4: materials | Done | `material: toon/basic/standard`, `opacity`, keyable `opacity` and `emissive_intensity`, shot `outline` (OutlineEffect, cleared each frame). New shapes: plane, cone, capsule. GLB morph targets: `morph` weights on object keys and objects, names checked against the model (`scenes.morph_names`), applied after the mixer. |
| Phase 4.5: anchor3d | Done | 2D layers pinned to projected 3D objects. The 3D frame renders first so the camera is current. |
| Phase 2.4: animatable paint | Done | Keyable `tint_color` and `wipe` draw-on (`wipe_from`) in both renderers. Keyed `fill`/`stroke_width`/`stroke_color` on shapes and text expand in `studio/paint.py` into `paint_frames` sprites plus `frame` keys (≤120 looks, sampled at min(24, fps)). `keys.compose` takes a `rate` and no longer puts grid samples within 0.9 sample of an authored key. Also fixed `gradient_image` clipping angles past 90°. |
| Bug fix: Python rotated clockwise | Done | Since `ab19891`, `transform.rotate` turned positive degrees clockwise while the browser (and the old PIL path) turned counter-clockwise. Python now matches. Path `orient` flipped with it. The parity fixture has an asymmetric `needle`, and `RotationConventionTests` pins the direction. |
| Channel growth workflow | Done | Skill interviews new channels one question at a time, ranks trends (`discover --rank views/velocity/outlier --shorts --snapshots`, growth between runs), and keeps channel memory: direction history, ledger with results and lessons, idea bank with seasonal calendar, series bible (`make channel-memory`, `references/episode-planning.md`). |
| Viral check | Done | `studio/viral_check.py`, `make viral-check [VIDEO=]`: hook, pacing, runtime, captions, packaging from the manifest; first frame, first-second change, silent start, loop match and loudness from the MP4. A 0–100 checklist score. |
| Shape morphing | Done | Keyable polygon `points` (any count, corners kept, aligned to avoid twisting) through the paint expander. SVG `morph_to` with keyable `morph` blends numbers and hex colours between same-structure files, staged as 25 frames. |
| Bendy limbs | Done | Keyable `bend` (degrees) curves a part as a circular arc from its pivot. Python inverse-maps with NumPy (`design.bend_tile`), the browser draws a forward triangle mesh (`bentTile`), and children ride the curve (`bend_child`/`bendChild`). Parity test diff 0.0004. |
| Character range | Done | `character.py` `archetype` presets (blob, human, cat, dog, bird, robot) with deep-merged overrides. New parts: hair (tuft, spiky, curly, bob, bun), nose (dot, button, snout, beak, cat + whiskers), floppy ears, tails (with `tip` and rest `bend`), outfits, `skin` for heads and hands. Behind-parts hang from the face's parent so they draw behind it. `alive` wags tails. Preview shows rest rotations. |
| 3D physics | Done | `studio/physics3d.py`: gravity, ground, walls, bounce, sliding friction and rolling resistance, sphere collisions, rolling spin, settling on a face. Baked into object keys before the camera rigs. |
| 3D posing and IK | Done | Object `bones` keys (degree offsets after the mixer, reset each frame) and `three.ik` CCD chains with point or object targets and weights, in a second pass after all objects are posed. `studio/glbcharacter.py` writes a rigged, vertex-coloured low-poly humanoid GLB. Bone names are validated against GLB nodes. |
| 3D quality preset | Done | Scene `quality: high` switches to PCFSoftShadowMap with 2048 maps. Shot or scene high adds GTAO ambient occlusion, OutputPass and SMAA to the composer chain (bokeh and bloom keep working). |
| Music library | Done | `studio/music.py`, `make music-import DIR=... [DRY=1]`, `make music-list`. Hash-deduplicated import with mood tags from names, measured tempo/loudness/energy, `channel.music_library`. Episode or style `music: {mood, energy, bpm}` resolves to a deterministic track after the style merge. Voice and SFX ducking unchanged. |
| Voice acting and engines | Done | `command` cast engine runs any local TTS (Piper, XTTS, F5, Chatterbox), cached per line. Per-line `pitch`, `pace` (native Kokoro speed) and `intensity` on every engine (`audio.act`). |
| Lip sync | Done | `studio/lipsync.py`: eSpeak NG IPA (spelling fallback) to 9 visemes, spread over measured words, closed on silences, 2-frame hold with closure priority, 1-frame lead. Auto for any speaker with `viseme_for` layers, resolved to the mouths a character has (fallback chain, Rhubarb letters). Active viseme overrides keyed/variant visibility in both renderers. Generator adds `mbp`/`e`/`u`/`fv`/`l`/`etc` mouths; `alive.talk` lip-syncs when a rig has them. |
| Lighting on 2D layers | Done | `studio/light2d.py` and `lightTile` in `painter.mjs`: episode/shot `light` (angle, colour, intensity, shadow, rim, softness, depth, elevation), layer `lit` inherited by children. Dome normals from a wide alpha blur plus rim from a narrow one, in layer space via world rotation and flips, cached per tile and 5° bucket. Parity fixture shot A lights the ball. |
| Depth from a photo | Done | `studio/depthphoto.py`, `make depth-photo`: depth from a supplied map, a local Depth Anything ONNX model, or a rough fallback. Crops to the frame, cuts equal-area feathered bands, push-pull fills hidden areas, writes image layers with `z` (inserted into a shot with `SHOT=`). |
| Layering and contact audit | Done | Starter poses were mirrored since the rotation fix (arms crossed the face, brows set absolute dropped to the feet): angles flipped, x/y written as rest + offset, `think` aimed per rig. Arms draw last. `turn_x`/`turn_y` children follow (`turn_child`/`turnChild`, `turn_depth`). Keyed `z` re-sorts per frame. Physics: scene objects are static colliders (GLB bounds from accessors), rotated extents on floors, SAT box contacts, resting tolerance. `anchor3d` occlusion raycast. Lint `contact_warnings` for 3D interpenetration and hovering. |
| Contact check on real channels | Done | Tested on a 3D channel built from expression-swapped GLBs: keyed scale and visibility now apply to the lint and to physics colliders, fixed large scenery is skipped, model pairs need a deeper overlap (outer boxes are coarse), shot `checks.ignore_3d` excludes decals, bodies inside a set model are not ejected, and colliders are placed once per frame. `three.physics.colliders` is in the schema. |
| Channel style lock | Done | `studio/stylelock.py`, `channel/style-lock.json` (schema `style_lock`). Enforced in `validate`/`audio`/`check-visual`/`still`/`render`: cast rigs, forbidden paths, dialogue, runtime, format, grades, music, same-shot cast scale, sound library. Episode `style_exceptions` with a reason; lock `exempt` for older episodes. Generates the block in `channel/AGENTS.md`; `make style-lock [INIT=1] [CHANGE=...]`, `make style-check`. Character generator: `palette.tail`. |
| Still pending | Pending | Nothing from the original plan or the 2026-11-15 audit. |

## Professional gaps (next work, from the 2026-11-15 audit)

| Gap | Area | Why it matters | Idea |
| --- | --- | --- | --- |
| ~~Shape morphing / path tweening~~ Done: polygon `points` keys (`paint.py`), SVG `morph_to`/`morph` (`morph.py`) | 2D | Morphing mouths, liquid, blob transitions and smears need point-level interpolation | Keyable `points` on polygons and matched SVG path morph in both painters |
| ~~Mesh deformation (bend/bone skinning)~~ Done: keyable `bend` arc deformer, children ride the curve | 2D | Rigid parts read as cut-out; bendy arms, squash on a body, cloth need deformation | A bend deformer on a part (curve the sprite along a 2-bone chain) in both renderers |
| ~~Character art range~~ Done: archetypes human/cat/dog/bird/robot + hair, nose, tail, outfit, skin | 2D | `make character` makes one cute bean family; other genres need humans, animals, props | More generator archetypes, or a documented import path for layered artwork (PSD/SVG to rig) |
| ~~Lip sync~~ Done: `studio/lipsync.py`, automatic for `viseme_for` mouths | 2D | Visemes exist but mouth sets are generic | Map Whisper phonemes to the 6+ mouth shapes per character |
| ~~Lighting on 2D layers~~ Done: shot `light` + layer `lit` | 2.5D | Flat layers ignore scene light | Normal/rim light pass driven by a light direction per shot |
| ~~Depth from a photo~~ Done: `make depth-photo` | 2.5D | "Photo parallax" is a popular format | Split an image into depth layers from a depth map |
| ~~3D character animation~~ Done: `bones` keys, `three.ik` (CCD), `make character3d` rigged GLB | 3D | Only GLB clip playback; no authored bones, no 3D IK, no retargeting | Bone keys and 3D IK on GLB skeletons; docs for free CC0 rigs (Quaternius, Kenney) and Mixamo |
| ~~3D physics~~ Done: `three.physics` baked rigid bodies | 3D | Falls, collisions and debris are hand-keyed | Bake rigid-body motion into object keys with a small solver |
| ~~Render quality~~ Done: `quality: high` (soft shadows, GTAO, SMAA, OutputPass); speed unchanged | 3D | Real-time WebGL look; no path tracing; ~2 min per 15 s at 540p | Accept for stylised channels; add a quality preset (SSAO, soft shadows) and parallel shot rendering |
| ~~Music~~ Done: `make music-import`, `music: {mood, energy, bpm}` | Audio | Preset beds are synthetic; channels need real tracks | Index a local royalty-free/CC0 music folder like `sfx-import`, with mood tags and auto-duck |
| ~~Voices~~ Done: `command` engine, per-line `pitch`/`pace`/`intensity`, free options documented in the audio reference | Audio | Kokoro is good but limited in acting range and languages | Keep the `recorded` engine path; document free voice options per language |

Tests: `make test` passes, 113 tests including the style-lock tests.

## Log

- 2026-11-15: Channel style lock landed so any assistant keeps a channel's approved look.
- 2026-11-15: Contact check and colliders tuned on a real 3D channel (113 warnings to 10 real ones on an existing episode).
- 2026-11-15: Layering and contact audit across 2D, 2.5D and 3D (see the status row).
- 2026-11-15: 2D scene lighting and photo depth layers landed; the audit's gap list is done.
- 2026-11-15: Automatic lip sync landed.
- 2026-11-15: Music library and voice acting (command TTS engine, pitch/pace/intensity) landed.
- 2026-11-15: 3D high-quality render preset landed.
- 2026-11-15: 3D bone posing, 3D IK and the rigged GLB character generator landed.
- 2026-11-15: Baked 3D physics landed.
- 2026-11-15: Character archetypes and new parts landed.
- 2026-11-15: Bendy limbs landed (`bend`).
- 2026-11-15: Shape morphing landed (polygons and SVG).
- 2026-11-15: Viral check landed.
- 2026-11-15: Channel growth workflow (interview, trend ranking with velocity/outlier/snapshots, channel memory files) and the professional gap audit.
- 2026-11-15: `examples/pocket-stars` showcase landed. The timed script now summarises composed key tracks, and `turn_x`/`turn_y` allow ±3600°.
- 2026-11-15: Motion report flags unreachable IK targets.
- 2026-11-15: Phase 2.6 IK landed. Fixed the Python/browser rotation direction mismatch.
- 2026-11-15: Phase 4.4 GLB morph target keys landed.
- 2026-11-15: Phase 2.4 fill/stroke keys landed, plus the gradient angle fix.
- 2026-11-15: Phase 4.3 extruded 3D text landed.
- 2026-11-15: C5 contrast check landed in the motion report.
- 2026-11-15: C3 `finish` style pass for existing SVGs landed.
- 2026-11-15: Phase 5.4 browser pose parity test landed and fixed `auto` easing on colour lists.
- 2026-11-15: Phase 3.2 perspective turn (`turn_x`/`turn_y`) landed in both renderers. Parity gate passes.
- 2026-11-15: LUT grading landed.
- 2026-11-15: Caption QA, per-cue tone and SFX density notes landed.
- 2026-11-15: Line boil landed.
- 2026-11-15: Kinetic caption face avoidance landed.
- 2026-11-15: Phase 2.4 tint_color and wipe landed.
- 2026-11-15: Phase 4 3D upgrades landed (rigs, lights, fog, env, toon/outline, text plane, anchor3d).
- 2026-11-15: Phase 3 depth landed, along with the double-camera fix for child layers.
- 2026-11-15: Phase 5 onion stills and motion report landed.
- 2026-11-15: Phase 2 motion primitives and poses landed. `studio/keys.py` is the shared resampler.
- 2026-11-15: Phase 1 parity and lint landed.
- 2026-11-15: Track C core landed (character generator, `alive`, paper/leak post).
- 2026-11-15: Tracks A and B landed (captions, word timing, SFX import, spotting, bus glue) along with the shared pipeline. Set up the memory files. Next: Track C.

---

## Context
The studio turns `episode.json` into video through two renderers. `python` (`studio/design.py`) handles flat 2D raster. `hyperframes`/`remotion` are browser renderers (`browser/painter.mjs`, `browser/three.mjs`). Almost every feature is expanded into plain `at` keyframes before rendering.

The AI author is limited in four ways today:
- **Missing primitives.** There are no motion paths, no wiggle/noise on layers, no secondary motion, colour can't be animated, there is no z-depth for 2D layers, there are no 3D camera rigs, and 3D has only basic lights.
- **Parity bugs.** SVG layers lose `ease_props`, and `auto` easing on SVG falls back to smoothstep. Motion blur means different things in each renderer.
- **Duplicated expansion pipeline.** It is copied in `video.py:310-324`, `video.py:355-371` and `editor.py:19`, and the copies run steps in different orders.
- **Thin feedback loop.** Stills don't show motion, parity has no pass/fail threshold, and physics and motion recipes produce JSON the author must merge by hand.

The goal is more expressive primitives that expand into the existing keyframe model, plus tools that let an AI *see* and *check* motion.

Design rule: each new feature is a load-time expander, like `particles.py`, `trails.py` and `reveal.py`. It emits ordinary keys, so both renderers get it for free and parity holds. Browser-only work is limited to genuinely 3D features.

---

## Priority tracks (from user feedback: weak subtitles, amateur SFX, simple art)
These run first. The phases below follow them.

### Track A: Pro subtitles
Root cause: `studio/audio.py:148 caption_words` guesses word timing from character counts. Real timing comes in only through a manual `align` import (`studio/alignment.py`). Styling is a static PIL sprite (`design.py:1034 draw_caption`) with 3 styles and 4 whole-cue animations.

1. **Real word timing, automatically.** After Kokoro TTS, run local forced alignment with `faster-whisper` word timestamps (CPU int8, in the existing `audio-models/venv`). Write the result to `speech[].words` through `alignment.apply`. The estimator stays as a fallback. `make audio` does this by default.
2. **Viral caption engine.** Words are drawn live per frame in `painter.mjs` and `design.py`, not as one sprite.
   - **Chunking:** 1–3 words per page, broken at phrase and punctuation boundaries, never orphaning a word.
   - **Per-word animation:** pop-in scale overshoot, bounce, slide-up, typewriter, wave. The active word gets a scale bump, colour swap or highlight pill.
   - **Emphasis:** `emphasis` keywords (or `*word*` in the speech text) get accent colour, bigger size, shake and an optional emoji or icon sprite.
   - **Look:** thick outline, soft drop shadow, gradient fill, and per-channel caption presets in `presets/captions/` (hormozi-pop, clean-karaoke, documentary-lower, kinetic-big).
   - **Placement:** safe-area aware (`studio/safearea.py`), and captions move automatically to avoid faces or hitboxes, reusing `visual.py` overlap checks.
3. **Caption QA in `make check`:** words per second, minimum on-screen time, and a check that the caption stays inside the platform UI safe zone.

### Track B: Professional SFX
Root cause: every sound is synthesized from oscillators and noise (`studio/sfx.py` with 40 recipes, `studio/soundlab.py`). There is no sample layer and no mix polish beyond ducking and reverb.

1. **Sample library support.** Add a `sounds/` index (local, ignored) built by `make sfx-index DIR=...`. It scans any CC0/licensed pack the user drops in (e.g. Kenney, Sonniss GDC bundles) and tags files by category from filenames and folders, plus loudness and duration.
   - Cues can use `{sound: "impact/wood", variant: auto}`. The resolver picks a sample, varies pitch ±1–3 semitones and gain, and avoids repeating a sample.
   - Synthesis stays as the fallback when no library is installed.
2. **Layered design.** A cue becomes transient + body + tail (sample or synth per layer), with per-layer EQ (high-pass mud cut), a short compressor/limiter and a stereo width option. This lives in `audio.py:apply_cue_shape`.
3. **Auto-spotting from animation.** `studio/spotting.py` scans expanded keyframes for these events and proposes cue markers:
   - fast moves become whooshes, scaled by speed and panned by screen x
   - sharp velocity stops and `impact`/`drop` recipes become impacts
   - appear/pop becomes a pop
   - `text reveal` becomes ticks
   - camera crash-zoom becomes a riser or boom
   An author can accept the proposals or let render apply them in `auto` mode.
4. **Mix polish.** Sidechain music under SFX as well as voice, a bus with a gentle glue compressor, -14 LUFS short-form master (extend `master_audio`), and a "too dense" check that flags more than N cues per second.

### Track C: Richer art + character animation
Root cause: characters are hand-written flat SVGs with about 9 paths (a typical channel character). Each is rasterized as one sprite, so it can't act. There is no shading, texture or finishing pass.

1. **Rig-ready character spec.** Add `make character SPEC=...`, which generates a part-separated SVG set from one JSON:
   - parts: body, head, eyes (open/half/closed/look-L/R), brows, mouth set (6 visemes plus smile/frown/O), arms, hands and legs, each with a pivot
   - a matching `rig_library` def with `poses` (idle, talk, surprise, point, walk-cycle keys)
   This plugs straight into existing `use`, `parent`, `pivot` and `viseme_for` and Phase 2.6 pose keys.
2. **Auto life on characters.** Rigs get default `blink` (randomized seeded intervals), `breathe` (from the motion lib), eye saccades and `talk` (mouth from aligned visemes or amplitude). These add base liveliness without authoring.
3. **Art-style richness.** SVG style passes in `studio/effectlab.py`:
   - cel shading (an inner shadow shape derived by offset/clip)
   - rim light
   - halftone or grain texture fills
   - line weight variation
   - "line boil" (subtle per-2-frame path jitter for a hand-drawn feel)
   Backgrounds get layered depth templates (sky / far / mid / near / foreground) that use Phase 3 `z`.
4. **Finishing post stack.** Shot/episode `post` adds film grain, paper texture, vignette, chromatic aberration on impacts, light leaks, colour grade LUT and bloom on 2D. It is applied in both painters and the parity-tested fixture.
5. **Art-quality checks.** Contrast against the background (subject readable), a minimum number of moving elements per second, and "dead frame" detection (no motion for more than 0.5 s).

---

## Phase 1: Foundations (fix before adding)
1. **One expansion pipeline.** Add `studio/expand.py: expand_episode(episode, channel)` that runs these steps in a fixed order: defs/rigs → new expanders → particles → trails → reveal → markers. Replace the three copies in `video.py` and `editor.py` with calls to it.
2. **SVG easing parity.** In `browser/painter.mjs:153-165`, stop handing poses to GSAP. Use `pose.mjs` interpolation for SVG layers too, which brings in `ease_props` and Catmull-Rom `auto`.
3. **Motion blur parity.** Make the browser shot-level blur use real sub-frames: render N sub-samples to an offscreen canvas and average them, matching `render.py:169`. Extend per-layer blur (`design.py:730`) to cover rotation and scale by sampling full poses, then mirror that in `painter.mjs`. Remove the dead `self.motion_blur` assignment at `design.py:513`.
4. **Validation warnings** in `core.validate_episode`:
   - keyframes closer than one frame apart at the shot's duration
   - particle cap truncation
   - `parallax` set on a `plane` that ignores it
   - `fov` given in 2D camera keys (either implement it, see Phase 3, or warn)

## Phase 2: Richer 2D motion (all expanders, renderer-agnostic)
1. **Motion paths** (`studio/paths.py`). A layer gets `path: {points | svg_d, from, to, ease, orient: true, offset}`. It is sampled into x/y (and rotate when `orient` is set), at about 1 key per frame or with adaptive density.
2. **Wiggle / noise** (`studio/noise.py`). A layer gets `wiggle: [{prop, amp, freq, seed, octaves}]`. Seeded value noise is added on top of the existing keys, for idle life, jitter and handheld feel on any property. The noise can reuse `camera.py`'s handheld noise.
3. **Secondary motion / follow-through.** A layer gets `follow: {target, lag, spring:{stiffness, damping}}`. It simulates a damped spring chasing the target layer's pose, using the integrator in `studio/physics.py`, and gives hair, tails, antennas and cloth-like overlap.
4. **Animatable paint.** Add `fill`, `tint` (colour), `stroke_width`, `glow` radius and `draw` (stroke draw-on 0..1 for polygon/svg/path strokes) to the keyframe props. These need colour interpolation in OKLab in `easing.py` and in `pose.mjs`. The two painters need these keys wired in `design.py` and `painter.mjs`.
5. **Physics + motion recipes become manifest-native.** A layer gets `motion: [{recipe:"drop", at:[0.1,0.4], ...}]`, expanded with the existing `studio/motion.py` and `studio/physics.py` (`to_layer_keys`). This replaces copy-paste JSON. Add `make physics RECIPE=...` for previews and fix the stale `shot.move` docstring.
6. **Pose library for rigs.** A def gets `poses: {name: {child: pose}}`. A `use` layer gets `pose_keys: [{at, pose, ease}]`, which expand into child keys. This gives character acting without bones. Two-bone IK (`ik: {root, mid, end, target}`) is an optional stretch goal.

## Phase 3: True 2.5D
1. **`z` depth for 2D layers** (`transform.py`). A layer gets `z` (keyable), and the 2D camera gets `z` / `fov`, which honours the currently ignored `fov`. The projected scale is `f/(f+z−cam_z)`, parallax falls out of the projection automatically, and paint order is sorted by z (stable for ties). Optionally add `depth_blur: {focus_z, range}` for depth of field driven from z. The existing `parallax` field stays as a manual override.
2. **Perspective tilt.** Add `tilt_x` / `tilt_y` keys, rendered as a projective warp (canvas `setTransform` cannot do projective transforms, so this needs a quad mesh draw in the browser and `PIL.Image.transform(PERSPECTIVE)` in Python). This gives card flips, floor planes and "paper cutout in space" shots.
3. **Camera presets that use z.** Add `dolly-zoom`, `fly-through` and `rack-focus` to `camera.py`.

## Phase 4: 3D upgrades (`browser/three.mjs` + schema)
1. **3D camera rigs.** Add `camera.rig: {kind: orbit|dolly|crane|flyby|follow, target, radius, from, to, ease}`, expanded into position/target keys in a new `studio/rig3d.py`. The 2D presets have no 3D equivalent today.
2. **Lights and atmosphere.** Add point, spot and area lights (keyable intensity and colour), `fog` (linear/exp), and `environment: {preset | hdr}` through RoomEnvironment/PMREM for nice PBR without asset hunting.
3. **Text3D.** Add an extruded text object kind (TextGeometry, with a bundled font), so titles can live in the scene.
4. **Material tricks.** Add keyable `emissive`/`opacity`, a `toon` material option, and an outline pass. Morph targets come from GLB `morphTargetInfluences` keys.
5. **3D↔2D anchoring.** A 2D layer gets `anchor3d: {object, offset}`, so the renderer projects every frame through `lens.screen()`. This replaces placing layers by hand.

## Phase 5: Let the AI *see* motion (feedback loop)
1. **Onion-skin / trail stills.** Add `make still ... ONION=5`, which overlays ghosted poses at previous and next sample times, plus motion-path polylines per layer, in `still.py` and `browser/still.mjs`.
2. **Motion report.** Add `make motion-report SHOT=...`, which writes a PNG of per-layer velocity and acceleration curves and flags:
   - dead holds longer than N seconds with no motion anywhere on screen
   - linear-only moves with no ease
   - simultaneous starts (no overlap or stagger)
   - snaps faster than 1 frame
   These are concrete animation-principle lints an AI can act on.
3. **Parity gate.** `make parity` fails when `mean_difference` exceeds a threshold. Add fixtures for SVG easing, z-depth, paths and paint keys. Optionally derive the `support` matrix from which fixtures pass.
4. **Tests.** Extend `tests/test_studio.py` with one test per new expander (deterministic key output), and add a node smoke test for `pose.mjs` colour and ease parity against Python output.

## Phase 6: AI-author documentation
- Add `.agents/skills/viral-video-studio/references/animation-cookbook.md`. It maps the 12 animation principles to studio fields (anticipation → `motion: anticipate`, follow-through → `follow`, arcs → `path`, secondary → `wiggle`, and so on), and holds idiom recipes for 2D, 2.5D and 3D shots, each with a minimal JSON snippet.
- Link the cookbook from SKILL.md, and add "run motion-report + onion still before render" to the workflow.
- Add one showcase example under `examples/` that uses z-depth, paths, follow and a 3D camera rig.

---

## Critical files
`studio/expand.py`, `video.py`, `editor.py`, `studio/design.py`, `studio/transform.py`, `studio/easing.py`, `studio/camera.py`, `studio/physics.py`, `studio/motion.py`, `studio/core.py`, `studio/schema.json`, `studio/still.py`, `studio/parity.py`, `studio/support.py`, `browser/painter.mjs`, `browser/pose.mjs`, `browser/three.mjs`, `browser/still.mjs`, `Makefile`, `tests/test_studio.py`, SKILL.md and references.
New files: `studio/paths.py`, `studio/noise.py`, `studio/rig3d.py`, `studio/motion_report.py`.

## Verification
- `make test` passes, including the new expander unit tests.
- `make validate` and `make check` on the existing `examples/` show no regressions.
- `make parity` passes the threshold on the extended fixtures, so Python and hyperframes match for paths, wiggle, follow, paint keys, z-depth and SVG easing.
- `make still ... ONION=5` and `make still --sheet` on the new showcase example show visual confirmation of arcs, depth sorting and overlap.
- `make render` the showcase on hyperframes, plus a 3D shot using a camera rig, fog and text3D. Inspect the MP4.
- `make motion-report` flags a deliberately bad fixture (all-linear, simultaneous starts) and is clean on the showcase.

Extra checks for the priority tracks:
- `make audio` on an existing episode writes aligned words. Spot-check that caption timings sit within about 60 ms of the spoken audio.
- `make still --sheet` shows the per-word caption pop, emphasis and safe-area placement.
- Index a small CC0 pack, render an episode, then compare the before/after mix and LUFS.
- `make character` produces a rig. A test shot shows blink, breathe, talk and pose changes in an onion still and the render.

## Execution order
Track A (captions) → Track B (SFX) → Phase 1 foundations → Track C (art/characters) → Phases 2, 5, 3, 4. Each item is its own commit series with tests.

New dependency: `faster-whisper` (local, CPU). The SFX sample packs come from the user, stay in an ignored folder, and nothing is downloaded automatically.
