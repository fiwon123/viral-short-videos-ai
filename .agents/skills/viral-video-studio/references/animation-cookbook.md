# Animation cookbook

Use this when blocking and polishing motion. Every field below expands at load time into plain keyframes, so it works on every renderer and composes with keys you write by hand. Positive `rotate` turns counter-clockwise on screen in both renderers. Kinetic caption wobble is the one exception (clockwise). Times in `motion`, `pose_keys`, `ik` and `wiggle` are in **seconds** from shot start (`t`, `d`). Times in `keyframes`, `path.at` and `wiggle.at` are **0–1 shot progress**.

## The principles, mapped to fields

| Principle | Field | Typical use |
| --- | --- | --- |
| Squash and stretch | `motion: impact`, `jump`, `drop` | Contacts, landings, hits |
| Anticipation | `motion: anticipate` 0.2–0.35 s before the action | Before jumps, throws, dashes |
| Staging | `pose_keys` on clear silhouettes, `camera` | One readable idea per beat |
| Pose to pose | `pose_keys` (`wave`, `surprise`, `shrug`...), `ik` for contact | Character acting |
| Follow-through and overlap | `follow` (`mode: drag`), automatic for ears and antenna under `alive` | Tails, hair, antennae, props in hand |
| Slow in and slow out | `ease` (`smooth`, `out`, `back`, `auto`) | Never leave a big move `linear` |
| Arcs | `path` with 3+ points, `orient: true` for flying things | Throws, flights, swoops |
| Secondary action | `wiggle`, `alive` (blink, breathe, glance) | Keep held shots alive |
| Timing | `d` on recipes and poses; hold 0.3–0.6 s on key poses | Weight and comedy beats |
| Exaggeration | `amount`/`height` on recipes, `emphasis_scale` on captions | Push 20–30% past real |
| Solid drawing | `make character` rigs (shaded parts) | Volume and consistency |
| Appeal | Clear shapes, big eyes with catchlights, readable poses | Every character |

## Recipes (`motion`)

```json
"motion": [
  {"recipe": "anticipate", "t": 0.40, "d": 0.25},
  {"recipe": "jump",       "t": 0.65, "d": 0.60, "height": 0.12, "to": [0.2, 0]},
  {"recipe": "impact",     "t": 1.25}
]
```

| Recipe | Params | Notes |
| --- | --- | --- |
| `pop` | `amount`, `appear` (hidden before `t`, default true) | Entrances for props, titles and icons |
| `anticipate` | `amount` | Squash down before a move |
| `impact` | `amount` | Squash on contact, rebound stretch |
| `jump` | `height`, `squash`, `to: [dx, dy]` | Crouch, stretched arc, landing squash |
| `drop` | `height`, `bounces`, `restitution`, `squash` | Falls in from above, bounces and settles; hidden before `t` |
| `settle` | `amount`, `direction` | Damped overshoot after a stop |
| `shake` | `amount`, `seed` | Fear, cold, rage, impact tremor |
| `spin` | `turns`, `ease` | Full turns |
| `enter` / `exit` | `from` / `to` offsets, `ease` | Slide on or off from the authored pose |
| `nod` | `amount` (degrees) | Yes, emphasis on a word |
| `wobble` | `amount` (degrees) | A decaying rock after a bump |

Put the `impact` on the frame of contact and the sound cue on the same `t`. `make spot` will propose one.

## Paths

```json
"path": {"points": [[0.1, 0.85], [0.45, 0.25], [0.9, 0.7]], "at": [0.1, 0.7], "ease": "smooth", "orient": true}
```

Points are canvas fractions. The curve passes through every point, so three points make an arc. `orient: true` rotates the layer to face the direction of travel; give a number to offset art that doesn't face right.

## Wiggle and follow

```json
"wiggle": [{"prop": "rotate", "amp": 2.5, "freq": 1.2}, {"prop": "y", "amp": 0.004, "freq": 0.8}]
"follow": {"target": "hero", "lag": 0.1, "offset": [0.05, -0.12]}
"follow": {"target": "hero", "mode": "drag", "gain": 6}
```

Use `wiggle` sparingly on held props, floating things or nervous characters. A chase `follow` trails a target on a spring, as with a pet, a balloon or a pursuer. A `drag` follow swings its rotation against the target's acceleration, as with a tail, a hanging sign or a scarf.

## Characters

1. Write `art/characters/<id>.json` in the channel and run `make character SPEC=art/characters/<id>.json`. Review `preview.svg` with the user before casting. Start from an `archetype`: `blob` (the classic bean), `human` (separate head, `skin` colour, hair, nose, longer limbs), `cat`, `dog`, `bird`, or `robot`. Any field you set overrides the archetype. Options:
   - `hair`: `tuft`, `spiky`, `curly`, `bob` (with back hair), `bun`
   - `nose`: `dot`, `button`, `snout`, `beak`, `cat` (with whiskers)
   - `ears`: `round`, `pointy`, `bunny`, `floppy`
   - `tail`: `cat` (curled with `bend`), `wag`, `fluffy`, `feather`, `dino`
   - `outfit`: `shirt`, `overalls`, `scarf`, `panel`
   - `palette`: `skin`, `hair`, `outfit`, plus the usual `body`, `limb`, `accent`

   `alive` wags and curls tails. Tails and limbs carry a `tip`, so `ik` and `bend` work on them.
2. Place the character: `{"id": "pip", "kind": "use", "ref": "pip", "x": 0.3, "y": 0.86, "alive": {"talk": "Pip"}}`. Here `x`/`y` is the feet.
3. Act with poses, not per-part keys: `"pose_keys": [{"t": 0.6, "pose": "wave", "d": 0.2, "ease": "back"}, {"t": 2.0, "pose": "idle"}]`. The starter poses are `idle`, `wave`, `cheer`, `point-left`, `point-right`, `shrug`, `surprise`, `sad`, `angry` and `think`. Add channel poses under `poses.<rig>` in the rig library, or under `poses` in the episode.
4. Move the whole body with `motion`, `path` and keys on the `use` layer. `alive` adds breathing, blinks, glances, sway, ear and antenna follow-through, and the talking mouth on top. Generated rigs lip-sync to the speaker's line from its phonemes and measured word timing.
5. Reach with `ik` when a hand or foot must land on something: `"ik": [{"chain": ["arm-r"], "keys": [{"t": 0.3, "layer": "ball", "d": 0.3, "ease": "out"}, {"t": 2.0, "release": true, "d": 0.3}]}]`. Generated limbs are one bone with a `tip`, so they aim (and point toward targets they can't reach). Hand-built rigs can use two parts (`["arm-upper", "arm-lower"]`, plus `end: "hand"` or `tip`) for a bending elbow or knee, and `bend: -1` flips it. Targets are screen `x`/`y` or another layer's pivot. Later keys glide the hand to the next target, and `release` hands control back to poses and keys. IK runs after `alive`, so a planted hand stays put while the body breathes.
6. Hit one pose change per beat. Hold readable poses for at least 0.4 s, and change pose on the word that motivates it.

## Colour grade

`post.grade` gives every shot one coherent look: `teal-orange` (punchy, cinematic), `warm-film` (cosy, nostalgic), `cool-night` (moody), `bleach` (gritty), `vintage` (faded memory) or `pastel` (soft, cute). Use `post.lut` for any `.cube` file, and `post.grade_amount` (0–1) to blend. Set it on the episode for consistency, and override per shot for flashbacks or dream beats.

## Hand-drawn feel

`boil: 0.4` on an SVG layer (or `"boil": 0.4` in a character spec, which is the default for generated characters) redraws its lines with slight seeded wobble at `boil_fps` (12). It makes vector art feel drawn rather than clip-art. Combine it with `post.paper` and light `grain`.

`finish` on an SVG layer gives flat or stock vector art the same finish as generated characters: `{"shade": 0.35, "rim": 0.4, "texture": 0.2, "outline": 0.015}`. `shade` adds a cel shadow band away from `light` (`[-1, -1]` is top left), `rim` a thin lit edge, `texture` paper grain and `outline` an ink line (fraction of the artwork size, colour `line`). `per: "silhouette"` (default) shades the drawing as one shape. `per: "shapes"` shades each top-level element, which suits separated parts, but bands are sized from the whole artwork, so keep `outline` low there. Browser renderers only. It runs before `boil`, so the two combine.

## Colour and draw-on

- `tint_color` (hex) is keyable and blends with `tint_opacity`: a blush, a danger flash, a sunset shift. Set `tint_opacity` to 1 on the layer and key the colour.
- `fill`, `stroke_width` and `stroke_color` are keyable on `rect`, `ellipse`, `polygon` and `text`: a button lighting up, a warning outline swelling, a sky gradient shifting from dusk to night. Solid fills, solid↔gradient and same-stop-count gradients blend. Gradients with different stop counts switch at the key. The look is pre-drawn into at most 120 sprite frames per layer, so prefer `tint_color` for colour changes on art layers (svg, image).
- **Bendy limbs.** Key `bend` (degrees) on a part to curve it smoothly from its pivot along its length: rubber-hose arms, tails, antennas, grass, noodle legs. Parts hang down from the pivot, as generated limbs do. Positive bends counter-clockwise like `rotate`. Children (a hand on a forearm) ride the curve: they stay at the tip and turn with the final tangent. Combine with `rotate` for the shoulder and `bend` for the elbow-less curve, and with `follow` or `wiggle` on `bend` for floppy follow-through.
- **Shape morphing.** Key `points` on a `polygon` to morph between any outlines (squash a blob, turn a square into a star, splash liquid). Point counts can differ, and corners stay sharp. For drawn art, give an SVG layer `morph_to: "other.svg"` and key `morph` from 0 to 1: every number and hex colour blends, so mouth shapes, eyelids, flames and liquid can morph. Both files need the same elements and path commands (duplicate the first file, then move its points). Morph and `boil` can't share a layer.
- `wipe` (0–1) reveals a layer from `wipe_from` (`left`, `right`, `top`, `bottom`, `center`), as with a title writing on, a line drawing itself or a progress bar. Key it from 0 to 1 with an `out` ease.
- `turn_x` / `turn_y` (degrees) turn a layer in perspective about its `pivot`: card flips (`turn_y` 0→180, the back shows mirrored), a floor or tabletop plane (`turn_x` 50–70 with `pivot: [0.5, 1]`), a door swing (pivot on an edge). Past 90° the layer is seen from behind. Children and groups don't inherit the turn, so turn leaf layers.

## Depth (2.5D)

Give top-level layers a `z` (0 is the picture plane, positive is farther, slightly negative is in front). Lay everything out as it should look. `z` changes nothing at rest; it only sets how each layer reacts when the camera moves:

- **Pans:** camera `x`/`y` moves far layers less, so parallax comes for free.
- **Dollies:** camera `z` (or the `dolly-in`, `dolly-out` and `fly-through` presets) grows near layers faster than far ones. Layers that reach the camera fade out.
- **Vertigo:** `dolly-zoom` holds the `z: 0` subject while the background stretches away.
- **Depth of field:** `camera.focus: {"z": 0, "range": 0.3, "amount": 0.6}` blurs layers outside the focus band.

Children inherit their parent's depth, and paint order runs far to near automatically. Overscan far backdrops (`width`/`height` 1.4–2) when the camera zooms out or uses `dolly-zoom`, or their edges show. Typical depths: sky 6–10, mountains 2–4, trees 0.6–1.5, characters and ground 0, foreground foliage −0.3 to −0.5.

**Photo parallax.** `make depth-photo EPISODE=... IMAGE=photo.jpg SHOT=A` crops a photo to the frame, splits it into depth layers (`LAYERS=4`) and inserts them at the bottom of the shot with `z` from 1.2 (far) to 0 (near). Hidden areas behind each band are filled in from that band, so moves stay clean. Then add `"camera": {"preset": "dolly-in"}` or a small `x` pan. Supply a depth map for good cuts (`DEPTH=depth.png`, white = near; `INVERT=1` for white = far) from Depth Anything, Marigold or a photo editor, or put a Depth Anything V2 ONNX model in `audio-models/depth/` (or `STUDIO_DEPTH_MODEL`). Without either, a rough "lower and busier is nearer" guess is used, which suits landscapes and streets only. Keep moves small (dolly `z` ≤ 0.35, pans ≤ 0.04), because large moves expose the filled areas. Rerunning with the same `NAME` replaces the earlier split. Use photos the channel owns or may use.

## Light on 2D layers

Give the episode or a shot a `light` and mark layers `lit` to shade flat art from one direction: `"light": {"angle": 135, "color": "#FFE7B8", "intensity": 0.45, "shadow": 0.4, "shadow_color": "#2B1F4F", "rim": 0.7}`. `angle` is where the light comes from on screen (0 right, 90 top, 135 top left). Each lit tile gets a soft lit side and shadow side from its silhouette and a rim light on the edges facing the light. `lit` on a `use` or group layer lights the whole rig (children inherit, `lit: false` opts a part out, a number scales it). The light stays on the same screen side when a part rotates or flips. Match the angle to the background's sun or lamp, use the palette's warm accent for `color` and a cool dark for `shadow_color`, and set `light: false` on a shot to switch it off. `softness` sets the rim width, `depth` how round the body reads, and `elevation` how raking the light is.

## 3D shots

The scene library (`scene_library` in the channel) holds reusable sets. Shots key them through `three`.

- **Camera rigs:** `"camera_rig": {"kind": "orbit", "from": -30, "to": 40, "ease": "smooth"}`. The kinds are `orbit`, `dolly` (`to` distance), `crane` (`to` height), `flyby` (`from`/`to` positions) and `follow` (`object`, `offset`, `lag`). Add `handheld: 0.02` for life and `fov: [40, 30]` for a lens change. Missing values come from the scene camera.
- **Light and atmosphere:** scene `lights` (`point`, `spot`, `hemisphere`), `fog` (`near`/`far` or `density`), and `environment: "room"` for believable reflections on PBR materials. Key a light per shot with `"lights": {"spot": [{"at": 1, "intensity": 4}]}`, for example a lamp flicker or a reveal.
- **Look:** object `material: "toon"` (three-band cel shading) plus shot `outline` reads as 2D-friendly 3D. Use `standard` with `metalness`/`roughness` for realism. Objects can fade (`opacity`) and glow (`emissive_intensity`) per key.
- **3D characters you can pose:** `make character3d OUT=channel/scene-library/hero.glb SPEC=colours.json` writes a rigged low-poly figure (bones `Hips`, `Spine`, `Head`, `UpperArm.L/R`, `LowerArm.L/R`, `Hand.L/R`, `UpperLeg.L/R`, `LowerLeg.L/R`, `Foot.L/R`). Free CC0 rigged models (Quaternius, Kenney) and Mixamo characters work the same way; use their bone names.
  - **Pose bones** with object keys: `{"at": 0.5, "bones": {"Head": [0, 25, 8], "UpperArm.L": [0, 0, -150]}}` (degrees, added on top of the rest pose or a playing clip).
  - **Reach with IK:** `"ik": {"hero": [{"chain": ["UpperArm.R", "LowerArm.R", "Hand.R"], "keys": [{"at": 0.2, "object": "ball", "weight": 1}]}]}` on the shot's `three` block. Targets are a `target` point or an `object` (plus `offset`), `weight` blends from the pose, and keys glide between targets.
  - Bone and target names are checked against the model when you validate.
- **Render quality:** set `"quality": "high"` on a scene in the scene library for soft 2048 shadows plus ambient occlusion (contact shadows), SMAA antialiasing and the colour output pass on every shot. Set it on a shot's `three` block to add only the post chain. `ao` (0–2) tunes the occlusion. It costs render time, so use it for masters and hero shots.
- **Physics:** add `three.physics` to a shot, e.g. `{"ground": 0, "bodies": {"ball": {"velocity": [2, 1, 0], "bounce": 0.6}, "crate": {"spin": [0, 0, 180]}, "post": {"fixed": true}}}`. Bodies start at their scene positions, fall under `gravity`, bounce on `ground` and `walls`, collide as spheres, and roll or settle flat on a face. The result is baked into position and rotation keys, so a `follow` camera rig can track a body and every render matches.
- **Morph targets:** key a GLB's shape keys with `morph` on object keys, e.g. `{"at": 0.4, "morph": {"smile": 1, "blink": 0}}`, and set starting weights with `morph` on the scene object. Names come from the model (`extras.targetNames`), or use indices like `"0"`. Validation lists the model's targets when a name is wrong. Keyed weights override clips that drive the same targets.
- **Shapes and text:** `plane`, `cone`, `capsule` and `text` (a flat title plane in the scene) join `box`, `sphere`, `cylinder`, `torus` and `glb`. Give `text` a `depth` (0.1–0.3) to extrude it into real lit geometry with an optional `bevel` (0–1). It uses the channel font, or `typeface` (a font role or .ttf path). Letters are about 0.5 units tall in both forms. CFF `.otf` fonts can't be extruded and fall back to the flat plane with a warning.
- **Labels on 3D:** a top-level 2D layer with `"anchor3d": {"object": "ball", "offset3d": [0, 0.7, 0]}` follows that object on screen. Its own `x`/`y` are ignored; use `offset` for a screen nudge.
- Outline and bloom/focus don't combine; when `bloom` or `focus` is set, the outline is skipped.

## See and check the motion

- `make motion-report EPISODE=...` lists dead holds (nothing moves for 1 s or more), long `linear` moves, layers that start in lockstep, one-frame snaps, frozen rigs, `ik` targets out of reach and low contrast (text under 3:1 or a foreground shape under 1.4:1 against the solid fill behind it; SVG and image art isn't judged). It also writes `motion-report.png` with speed curves per shot. Fix every note or say why it is intentional.
- `make still EPISODE=... SHOT=... AT=1.2 ONION=3` overlays ghost poses, warm before and cool after, to check arcs, spacing and overlap at a key moment.

## Polish checklist

- Every big move has an ease other than `linear`, plus an anticipation or a settle.
- Things that land or hit get `impact` or `drop`, with a sound cue on the same frame.
- No character stands frozen: use `alive`, or at least a `wiggle` or `breathe`.
- Arcs, not straight lines, for anything thrown or flying.
- Stagger starts by 2–4 frames when several things move together.
- Check a `--sheet` still across the beat before rendering. Turn on `motion_blur` (0.3–0.6) for fast moves only after timing is locked.
