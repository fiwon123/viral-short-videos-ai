# Animation cookbook

Use this when blocking and polishing motion. Every field below expands at load time into plain keyframes, so it works on every renderer and composes with keys you write by hand. Times in `motion`, `pose_keys` and `wiggle` are in **seconds** from shot start (`t`, `d`). Times in `keyframes`, `path.at` and `wiggle.at` are **0–1 shot progress**.

## The principles, mapped to fields

| Principle | Field | Typical use |
| --- | --- | --- |
| Squash and stretch | `motion: impact`, `jump`, `drop` | Contacts, landings, hits |
| Anticipation | `motion: anticipate` 0.2–0.35 s before the action | Before jumps, throws, dashes |
| Staging | `pose_keys` on clear silhouettes, `camera` | One readable idea per beat |
| Pose to pose | `pose_keys` (`wave`, `surprise`, `shrug`...) | Character acting |
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

1. Write `art/characters/<id>.json` in the channel and run `make character SPEC=art/characters/<id>.json`. Review `preview.svg` with the user before casting.
2. Place the character: `{"id": "pip", "kind": "use", "ref": "pip", "x": 0.3, "y": 0.86, "alive": {"talk": "Pip"}}`. Here `x`/`y` is the feet.
3. Act with poses, not per-part keys: `"pose_keys": [{"t": 0.6, "pose": "wave", "d": 0.2, "ease": "back"}, {"t": 2.0, "pose": "idle"}]`. The starter poses are `idle`, `wave`, `cheer`, `point-left`, `point-right`, `shrug`, `surprise`, `sad`, `angry` and `think`. Add channel poses under `poses.<rig>` in the rig library, or under `poses` in the episode.
4. Move the whole body with `motion`, `path` and keys on the `use` layer. `alive` adds breathing, blinks, glances, sway, ear and antenna follow-through, and the talking mouth on top.
5. Hit one pose change per beat. Hold readable poses for at least 0.4 s, and change pose on the word that motivates it.

## Hand-drawn feel

`boil: 0.4` on an SVG layer (or `"boil": 0.4` in a character spec, which is the default for generated characters) redraws its lines with slight seeded wobble at `boil_fps` (12). It makes vector art feel drawn rather than clip-art. Combine it with `post.paper` and light `grain`.

## Colour and draw-on

- `tint_color` (hex) is keyable and blends with `tint_opacity`: a blush, a danger flash, a sunset shift. Set `tint_opacity` to 1 on the layer and key the colour.
- `wipe` (0–1) reveals a layer from `wipe_from` (`left`, `right`, `top`, `bottom`, `center`), as with a title writing on, a line drawing itself or a progress bar. Key it from 0 to 1 with an `out` ease.

## Depth (2.5D)

Give top-level layers a `z` (0 is the picture plane, positive is farther, slightly negative is in front). Lay everything out as it should look. `z` changes nothing at rest; it only sets how each layer reacts when the camera moves:

- **Pans:** camera `x`/`y` moves far layers less, so parallax comes for free.
- **Dollies:** camera `z` (or the `dolly-in`, `dolly-out` and `fly-through` presets) grows near layers faster than far ones. Layers that reach the camera fade out.
- **Vertigo:** `dolly-zoom` holds the `z: 0` subject while the background stretches away.
- **Depth of field:** `camera.focus: {"z": 0, "range": 0.3, "amount": 0.6}` blurs layers outside the focus band.

Children inherit their parent's depth, and paint order runs far to near automatically. Overscan far backdrops (`width`/`height` 1.4–2) when the camera zooms out or uses `dolly-zoom`, or their edges show. Typical depths: sky 6–10, mountains 2–4, trees 0.6–1.5, characters and ground 0, foreground foliage −0.3 to −0.5.

## 3D shots

The scene library (`scene_library` in the channel) holds reusable sets. Shots key them through `three`.

- **Camera rigs:** `"camera_rig": {"kind": "orbit", "from": -30, "to": 40, "ease": "smooth"}`. The kinds are `orbit`, `dolly` (`to` distance), `crane` (`to` height), `flyby` (`from`/`to` positions) and `follow` (`object`, `offset`, `lag`). Add `handheld: 0.02` for life and `fov: [40, 30]` for a lens change. Missing values come from the scene camera.
- **Light and atmosphere:** scene `lights` (`point`, `spot`, `hemisphere`), `fog` (`near`/`far` or `density`), and `environment: "room"` for believable reflections on PBR materials. Key a light per shot with `"lights": {"spot": [{"at": 1, "intensity": 4}]}`, for example a lamp flicker or a reveal.
- **Look:** object `material: "toon"` (three-band cel shading) plus shot `outline` reads as 2D-friendly 3D. Use `standard` with `metalness`/`roughness` for realism. Objects can fade (`opacity`) and glow (`emissive_intensity`) per key.
- **Shapes and text:** `plane`, `cone`, `capsule` and `text` (a flat title plane in the scene) join `box`, `sphere`, `cylinder`, `torus` and `glb`.
- **Labels on 3D:** a top-level 2D layer with `"anchor3d": {"object": "ball", "offset3d": [0, 0.7, 0]}` follows that object on screen. Its own `x`/`y` are ignored; use `offset` for a screen nudge.
- Outline and bloom/focus don't combine; when `bloom` or `focus` is set, the outline is skipped.

## See and check the motion

- `make motion-report EPISODE=...` lists dead holds (nothing moves for 1 s or more), long `linear` moves, layers that start in lockstep, one-frame snaps and frozen rigs. It also writes `motion-report.png` with speed curves per shot. Fix every note or say why it is intentional.
- `make still EPISODE=... SHOT=... AT=1.2 ONION=3` overlays ghost poses, warm before and cool after, to check arcs, spacing and overlap at a key moment.

## Polish checklist

- Every big move has an ease other than `linear`, plus an anticipation or a settle.
- Things that land or hit get `impact` or `drop`, with a sound cue on the same frame.
- No character stands frozen: use `alive`, or at least a `wiggle` or `breathe`.
- Arcs, not straight lines, for anything thrown or flying.
- Stagger starts by 2–4 frames when several things move together.
- Check a `--sheet` still across the beat before rendering. Turn on `motion_blur` (0.3–0.6) for fast moves only after timing is locked.
