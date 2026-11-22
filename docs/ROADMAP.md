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
| Workspace cleanup and archive | Done | `studio/cleanup.py`, `make archive [SLUG= APPLY=1 NOVIDEO=1 VERBOSE=1]` and `make published EPISODE=... [URL=...]` (writes `published.json`). Every channel gets `renders/_old/` and `episodes/_old/` with a README (`memory.create` and each archive run); their contents are deleted. Tiers: delete `_old` contents, caches, previews and superseded `-vN`; archive renders of episodes with `published.json` (upload files only); keep anything a channel file references, even in `_old`. Tests in `tests/test_cleanup.py`. Note: `make clean-cache` and `clean-previews` still only scan the legacy `output/` and `episodes/` paths. |
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
| Hook preview and punchline beats | Done | `render --seconds N` / `make preview HOOK=20` renders only the shots that start in the opening window and trims the MP4 and SRT (`render.opening`, `trim_video`). Speech `punchline: true` (0.3 s) or `pause_after` holds silence after a line (`audio.pause_after`). `viral-check` notes `hook-hit` when nothing sounds in the first 0.25 s. |
| Local AI character art | Done | `studio/hardware.py` (`make hardware`) probes ComfyUI `/system_stats`, nvidia-smi, rocm-smi, torch and Apple silicon. `studio/aiart.py` (`make art`) plans backend and model by VRAM from a commercial-licence list (`MODELS`, `TIERS`), generates through ComfyUI's API or diffusers, caches the source by prompt/model/seed, records `art.json`, cuts out (`studio/cutout.py`: rembg, ONNX matting, border-connected key) and splits head/body/arms/legs from the silhouette into a role-tagged `image` rig with starter poses. Manual: `IMAGE=`, `PARTS=` layers, spec `parts` boxes. Falls back to `make character`. Image layers may now use `asset_scope: channel`. Faces: `studio/aiface.py` finds the eyes and mouth inside the head, lifts the eyes to `eye-*` layers over push-pull skin fill (skin-only samples), and swaps the painted mouth for the `character.py` mouth set, so `alive` blinks and lip-syncs. diffusers path untested here (no GPU in the sandbox). |
| Hero clips | Done | `studio/heroclip.py`, `make hero`: start frame from `IMAGE=` (background plate) or the shot's first frame via `video.py still` (over the shot; `--keep` layers hidden from it and kept above). Backends: ComfyUI exported workflow with `{{placeholders}}`, built-in Wan 2.2 TI2V 5B graph (`probe_video` checks UNET/CLIP/VAE files and the `Wan22ImageToVideoLatent` node), diffusers LTX-Video on 12 GB+, else depth layers with per-layer push keys (no camera, so kept layers and captions stay put; `z` dropped over the shot because renderers sort by z). Frames are packed into one sheet (≤8192 px) played by `frame` keys, cached by image/prompt/seed/model/length. Untested on real models here (no GPU). |
| Art models | Done | `make art-models` (sandbox.mk `ART_MODELS`) downloads Depth Anything V2 Small and IS-Net anime ONNX into `audio-models/depth|cutout/`. `cutout.onnx_alpha` picks size and normalisation by model family (IS-Net: 1024, mean only; U2-Net: 320, BiRefNet: 1024, ImageNet mean/std). The hero fallback with the depth model keeps the subject clean; flat shapes crossing depth bands still ghost slightly at the end of the push. |
| Flat-region depth refinement | Done | `depthphoto.regions` (median-cut quantise + min-label propagation with pointer jumping) and `flatten_regions`: big regions with colour std ≤ 8 take their median depth, a big flat region touching two frame edges goes to the 2nd-percentile depth (backdrop), small regions are push-pull filled from their surroundings unless they cover half the frame (photos untouched). On by default in `load_depth`, `--no-refine`. Removes the band ghosting on flat art in the hero fallback. About 2.5 s at 720×1280. |
| Video layers | Done | `studio/videolayer.py`: layer `kind: video` with `fit`, `clip_start`, `clip_speed`, `loop`. `expand` (run by `prepare_episode(..., episode_dir=)`) writes one `frame` key per frame change (renderers hold `frame`), `tiles` decodes with ffmpeg at layer size and episode fps into `.video-frames/<hash>/` (a cleanup cache) and returns a lazy `Frames` list (6-frame LRU). Python and HyperFrames read it like a sheet. `make hero` now writes `clip-<key>.mp4` (CRF 14) with a cover-fit video layer, replacing the 8192 px sprite sheet. 4 s 1080×1920 render: +45 MB peak versus an image layer. Callers without `episode_dir` (none in the CLI) leave a video on frame 0. |
| Machine profile | Done | `studio/machine.py`: cores (affinity), RAM (sysconf / Windows API) and GPU give a tier and a budget: threads, batch jobs, Chromium workers, niceness 10, `cpu_ai` off. `apply()` (video.py and module mains) lowers priority (POSIX nice, Windows BELOW_NORMAL) and sets BLAS/OMP thread env for children; x264 gets `-threads`, ONNX sessions `intra_op_num_threads`, torch `set_num_threads`, `browser/render.mjs` reads `STUDIO_BROWSER_WORKERS`, `batch --jobs` defaults to the profile. `aiart.plan` refuses CPU diffusion and sub-4 GB GPUs unless `STUDIO_CPU_AI=1`. Overrides: `STUDIO_PROFILE/THREADS/JOBS/BROWSER_WORKERS/NICE/CPU_AI`. |
| Film QA (pixel gate) | Done | `studio/film_qa.py`, `make film-qa VIDEO= [EPISODE=]`; every full render writes `film-qa/` (report, energy chart, contact sheet) and a `film_qa` verdict in `qa.json` (never fails the render). Colour frame diffs at 90 px wide: energy per second, dead runs (0.8 s medium, 1.5 s high) outside treatment `Stop:` lines, frozen ending, blank runs, hard cuts (and, since #67, a lone spike of 8+ that is 6x its neighbours and changes 15% of the frame: a cut-in on the same set), longest framing (6/12 s; `Route: continuous` relaxes it). Red exits 1. `viral-check` no longer exempts a shot over 10 s because it has a camera or 3D block. Calibrated on channel renders: the manifest checks passed films whose last 7 s were frozen. Method adapted from huashu-motion, huashu-art-motion and lanshu (MIT). |
| Treatment lint | Done | `studio/treatment.py`, `make treatment-lint EPISODE=`. Parses `episodes/<episode>/treatment.md` (template in `docs/memory-templates.md`, created by `make channel-memory SLUG= EPISODE=`): idea, route, energy table, shot table (time, subject, action, size, camera, on screen, sound). Notes: unfilled rows, time gaps, text-card hook or ending, hook over 3 s on a still camera, over six on-screen words, one size throughout, same size and still camera twice, three push-ins in a row, accent budget, shot length (6/12 s), flat or low energy, slow open, peak with no landing, opening/payoff repeated from the last three ledger rows (new ledger `Grammar` column), runtime and shot count against `episode.json`. Shares `Route:`/`Stop:` parsing with film-qa (`film_qa.meta_from_text`). |
| Direction standard | Done | Skill reference `direction.md`: the three tests (moving on frame one, energy shape, no slides), failure modes measured on channel renders, treatment method (route, energy curve, shot table, continuity chain, four stills), staging and subject size, camera as punctuation with studio fields and numbers, acting, the character bar, three directions as key frames, two review rounds with a cold director pass (prompt template, `review/director.md`), punch-up, learning loop (ledger Grammar/Film QA, preference/observed/verified, lessons become checks). `shorts.md` treatment replaces the beat sheet; `production.md` has the order of work; SKILL.md "Direct before you animate". Wiki prompts updated. |
| Word and beat anchors | Done | `studio/anchors.py`: `at_word` / `at_beat` on keyframes, camera keys, `motion` recipes and sfx cues; shot `snap: beat|bar`; `music.beat` grid. Resolved first in `prepare_episode` (estimate from text), and by `pipeline.prepare_measured` on the measured takes for render/still/audio/check-visual (one extra audio pass, only for anchored episodes). Source-reading tools (motion-report, viral-check, spot) get `resolve_source`. `music.beat_grid`/`first_beat` measure tempo and phase; imports record `first_beat`; the expander sets `music.beat`. Fixed a `tempo()` octave error (non-integer beat period in hops halved the tempo): 3-tap smoothing, half-lag check, parabolic peak. Timeline `music.beat`; film-qa `cuts_on_beat` and `off-beat`. Real-track beat accuracy untested here (no music library locally); synthetic tracks within ±25 ms. |
| Film QA pops | Done | `film_qa` reports `pop` (a frame that jumps away from both neighbours while they match; huashu-motion's single-frame pops) and `first-frame` (frame 0 is a different picture from the opening: the poster is wrong). Both high; neither counts as a cut or as motion. Caught the frame-0 camera bug (#46) on a real render; no false positives across 40 channel renders. |
| Episode state, delivery gate, review pack | Done | `studio/episode_state.py`. `make state EPISODE= [WRITE=1]`: furthest stage proven by files (planned: treatment not red · built: `video.py validate` · stills: `renders/<ep>-stills/*.png` · previewed: fresh preview with film-qa · reviewed: `review/*.md` · mastered: fresh `-vN` not red · delivered: verified `delivery.md` · published: `published.json`), renders older than `episode.json` are stale, next command printed (lanshu's evidence state machine). `make deliver EPISODE= [VIDEO=]`: reruns film-qa, treatment-lint, viral-check; red exits 2; writes `delivery.md` with a sha256-sealed facts section (mp4 sha256, probe, loudness, film-qa, treatment, viral, review files listed not read, studio commit) and keeps the maker's notes across re-delivery; `VERIFY=` detects edited facts or a changed MP4 (huashu-art-motion's deliver.py). `make review-pack`: sheet, energy, report, treatment, key-still frames and a filled director prompt in `review/pack-<render>/` (cinetic critic files). |
| Bug fix: camera shakes smeared the camera | Done | `resolve_camera` baked shakes on 60 samples per shot with linear interpolation, so `hold` cuts became 0.25 s slides in a 14 s shot, crash zooms drifted and the jitter aliased; `duration`/`frequency` ran in shot fractions. Now 48 samples a second plus every key time and a point before each `hold` key, `duration` in seconds and `frequency` in Hz against the resolved shot length (`seconds`, passed by render, still and browser). Shakes in long shots are now short and sharp, as documented, instead of multi-second wobbles. |
| Sound sync in film-qa | Done | `film_qa.sync` (#53): each sfx cue in `timeline.json` is heard in the MP4's audio (first 10 dB rise in 15 ms from the cue, level floored at -60 dB) and matched to the nearest clear picture event (a jump in frame-to-frame motion, 1.0 and 5x its surroundings) in the same shot, walked back to where the change begins. Cuts, pops and caption/word changes are not events; a sound within tolerance of a cut is `on-cut`; an event nearer another cue is not this one's; sustained sounds (no 6 dB fall within 0.2 s) are not judged, nor (#68) a cue whose own sample (found through the channel's audio library or the episode folder) has two or more attacks in its first 0.3 s: a rattle, a splash, chewing. `sound-early` > 45 ms, `sound-late` > 125 ms (ITU-R BT.1359), each + half a frame; medium. Swept on 23 channel renders: 16 synced, 1 false flag (a rattle during an ongoing shake), 1 from an undetected cut-in; small cast in a wide shot is mostly unmatched. Idea from cinetic's check-sync (MIT). |
| Music fitted on bar lines | Done | `music.arrange` (#55), run by the music expander for a library pick with a beat grid: trailing silence trimmed, whole bars removed from the middle (long track, keeping a full bar of ending) or repeated by jumping back (short track, unless `loop: false`), joins only on bar lines and chosen for the smallest loudness step (0.4 s either side); the remainder under one bar comes out of the ring-out (keeping 0.3 s, faded) and then off the head. Exactly the runtime; `music.beat.offset` shifted to the film; `audio.play_segments` mixes the spans with 10 ms equal-power crossfades and the mixer no longer wraps an arranged bed. `music.arrangement` in the timeline; film-qa `music-join` (medium) over 6 dB. `fit: false` opts out. Since #71 `music.file` is fitted too (authored `beat`, or `beat_grid` measured when `pulse_clarity` >= 0.35: the onset autocorrelation at one beat minus half a beat over lag 0; click tracks 0.8-0.95, drones and ambience <= 0.16, so `beat_grid` no longer reports a tempo for a drone). Tested on synthetic tracks only (no local music library); real-track join quality unheard. Idea from huashu-motion (MIT). |
| Log-space camera zoom | Done | `easing.LOG_KEYS` (#57): `zoom` is interpolated as log(zoom) in `design.pose_at` (eased and `auto`), `camera._sample` (the shake bake) and `browser/pose.mjs` `poseAt`; a linear 1x-to-4x key passes 2x halfway, so the visual rate is even and an authored ease is the shape seen. Layer `scale` and the parallax blend (`1 + (zoom - 1) * amount`) are unchanged. Browser parity test on every ease; `make parity` passed. Idea from cinetic's motion rules (MIT). |
| Review lenses | Done | `review-pack` (#59) writes `prompt.md` (director), `prompt-sound.md` and `prompt-continuity.md`, `LENS=` for a subset. Sound evidence: `sound.png` (mix level in dB at 20 ms, cue ticks coloured by film-qa sync status, cuts, energy per second) and `sound-cues.json` (timeline cues merged with `metrics.sync`). Continuity evidence: `cuts.png`, the frames either side of each hard cut (exact frames via `select`, up to 12 cuts). Every prompt lists earlier `review/*.md`. Method adapted from cinetic's critic lenses (MIT): one lens per reviewer, measured evidence, ranked fixes naming the field, rounds. |
| Narration check | Done | `studio/narration.py`, `make narration-check` (#61): transcribes each line's `take` (the render's mix around the line when the take is gone) with faster-whisper's multilingual model (`STUDIO_ASR_MODEL`, default `base`; ffmpeg decode, no PyAV), no script prompt; normalises case, punctuation, `*emphasis*`, letter-digit joins, pt/en contractions, number words to digits, several-word numbers merged since #73 ("vinte e um", "two hundred and five") (en/pt/es/fr/it; "one" never counts as a number, it is also "a"); characters for ja/zh; scores against the best of `text`, `caption`, `spoken_text`. `unheard` (high, 4+ words), `misread` (WER 25% net of repeats, or a 6+ letter word missing), `number`, `repeat` (medium). Optional dependency: `unchecked` without it or with `STUDIO_ASR=off`; `narration: false` per line. `make deliver` adds it to the sealed facts and the amber list, reusing a fresh `narration.json`. Real runs (scratch venv): 5 English lines green, a Portuguese draft flagged "SSD pediu demissão" heard as "ss dependiu da missão" and a halting 3-word line. Not in the image: adding faster-whisper to requirements needs `make dev-build`. Idea from lanshu (MIT). |
| Frame comments | Done | `studio/comments.py`, `editor/review.html`/`review.js` (#63). `make review`: a local page (editor port and host settings) plays the newest preview or master, served with HTTP ranges for seeking; pause, click the spot, write the note (Enter saves); stored in `review/comments.json` with time, frame, shot, shot progress and the point; the list seeks to a comment and rings its spot, polls for replies. `make comments`: open notes with `review/comments/<id>-frame.png` (spot ringed) and `-spot.png` (30% of the width around it at 2x, spot ringed); `DONE=<id> REPLY=` resolves. Checked in headless Chromium at 1280 and 390 wide. Since #75 the editor stylesheet is all variables with a `prefers-color-scheme: light` palette (both pages checked in both themes), `PORT=` on `make editor`/`make review`, and the review server falls through to the next free port when `make editor` holds 8765. Idea from huashu-motion's point-at-the-frame review (MIT); built on the MP4 so it works for every renderer. |
| Camera coverage and ghost cuts | Done | #77: `lint.coverage_warnings` (in `make validate`): for each 2D shot's backdrop (`plane: background`, or a full-frame bottom layer, no keys, no `z`), the resolved camera (shakes in) sampled 48 times a second, the view in layer space with the layer's parallax as the painters apply it, compared with the layer's box; warns over 0.5% of the frame with the amount and times. A pixel edge detector was tried first and rejected: it could not tell empty canvas from a flat floor, sky or wipe panel (30+ false flags). Found real gaps in two older channel episodes (8.4%, 3.1%, both visible in stills). #78: film-qa `ghost-cut` (high): a frame beside a cut that is a blend of its neighbours (weight 15-85%, residual under 35% of the shots' difference); no false flags on the local renders. Ideas from cinetic's edge-cover and ghost-cut checks (MIT). |
| Delivery sound gate | Done | `episode_state.audio_gate` (#80), run by `make deliver` on the master: a full `ffmpeg -f null` decode (errors refuse delivery), no audio stream or under -45 LUFS (`silent`), integrated loudness over 1 LU off the render's `audio.master.loudness` (`loudness`; the note names a peak-held mix when the true peak already sits within 1 dB of the ceiling), true peak over -1 dBTP (`true-peak`), last 0.25 s within 12 dB of the loudest 2 s (`audio-cut`); all amber, in the sealed facts. Found the channel's 14 s masters at -15.6/-16.1 LUFS against -14, peak-held by a few hits. Ideas from lanshu's finalizer and cinetic's audio-end (MIT). |
| Camera wander | Done | `lint.wander_warnings` (#82, in `make validate`): the authored camera keys (no preset, no shakes) of each 2D shot, split at `hold` keys into setups, sampled 24 times a second; runs of one sign on x, y and log zoom over the moving frames (a hold ends a run); a move of 7.4% of the frame or 3% zoom followed within 1 s by a return of half of it or more (the return run at most 2 s) is a wobble. Flags three of 412 local authored shots. Idea from cinetic's camera-wander check (MIT), restated on keyframes. |
| Nothing new | Done | film-qa `nothing-new` (#84, medium): events are hard cuts, sound cues, caption and word changes, and clear motion starts or stops (a jump in frame-to-frame motion of 1.0 and 5x its surroundings, the sync check's measure); a gap over 4 s (8 s on `Route: continuous`) outside declared stops is noted; `metrics.longest_quiet`. On the local renders: median longest gap 3.5 s; 18 of 47 flagged, those looked at confirmed (5-6 s of one tableau after a hook, a 6 s static ending). Idea from huashu-motion's rhythm density rule (MIT). |
| Boredom question, reviews bound to a file | Done | #86: the director prompt asks where the film starts to lose the reviewer (the second, what is or is not happening, why); every review prompt names the render and its sha256 (`reviewed_line`) and asks for a `Reviewed: <render> sha256 <12 hex>` first line; `make deliver` reads that line from each `review/*.md` and lists the render each review judged (this master / not this master / names no render), still without reading the notes. Ideas from huashu-motion's verification rules (MIT). |
| faster-whisper in the image | Done | #88: `faster-whisper==1.2.1` in `requirements-voice.txt`, so the narration check and Whisper word timing run in the sandbox. Word timing now takes the voice's language: `base.en` for English, the multilingual `base` otherwise (it was `base.en` for every line, which would mistime Portuguese); models in `audio-models/whisper/`. `make test` sets `STUDIO_WORD_TIMING=energy` and `STUDIO_ASR=off` so the suite never loads a model. Real runs: a pt-br and an en-us take timed by Whisper, ends 0.4-0.7 s tighter than the energy fallback. |
| Master loudness | Done | #91: `audio.master_audio` measures loudness after the pre-chain (it measured the raw mix while applying a compressor first), raises the gain to the target into an `alimiter` run at 4x the sample rate just under the true-peak ceiling (a sample-rate limiter let inter-sample peaks overshoot by ~1.5 dB, so the final trim took the loudness back), and corrects up to three times for what the limiter takes; lift bounded to +12 dB. 15 of 47 local renders had been more than 1 LU under -14 (worst -20.2); re-mastered, five channel mixes land at -13.96 to -14.44 LUFS, -1.57 to -1.80 dBTP. |
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

Tests: `make test` passes, 217 tests.

## Log

- 2026-11-21: Episode state, delivery gate and review pack (#49).
- 2026-11-21: Film QA pops and first-frame jumps (#48).
- 2026-11-21: Word and beat anchors landed (#41).
- 2026-11-21: Direction standard landed (#38).
- 2026-11-21: Film QA landed (#39): the render's pixels gate delivery. Started the direction work from a study of four MIT agent video skills: treatment lint (#40), direction standard (#38), word and beat anchoring (#41).
- 2026-11-21: Camera shake bake fixed (#46).
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
