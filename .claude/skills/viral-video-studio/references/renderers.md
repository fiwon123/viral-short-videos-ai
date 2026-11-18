# Reuse the same look across episodes

Keep the approved palette, typography, logo, caption placement, characters, sets, and lighting with the channel brief. Store reusable 2D cast and props in `channel/rigs.json` and reference it with `channel.rig_library`. Store 3D assets and a versioned scene library next to the channel manifest. Point `channel.json` at that version with `scene_library`. Keep model filenames, object IDs, scale, materials, and default camera framing stable between episodes. Create a new library version for an intentional redesign. A render records the selected library and its version in `timeline.json`.

## Pick a renderer

- Start new vector-led 2D and 2.5D episodes with `--renderer hyperframes`. HyperFrames seeks a paused GSAP timeline. The browser draws SVG assets directly, and GSAP drives their layer motion from the same frame clock. [HyperFrames compositions](https://hyperframes.heygen.com/concepts/compositions)
- Use `--renderer remotion` for an established React workflow. It supports the same SVG layers, Three.js scenes, and timing rules. Keep the renderer and browser version consistent within a series when matching the exact appearance matters.
- Use the Python renderer for simple raster 2D work with fewer dependencies. SVG and Three.js shots need a browser renderer.

All three use the Python studio's resolved frame clock, measured speech, mix, captions, thumbnail copy, and export checks. Browser encoding can produce small pixel differences. Judge continuity with matched stills at the same shot and frame and keep the chosen renderer for an approved series look.

## Author vector 2D shots

Use a layer with `"kind": "svg"` and a `file` relative to the episode manifest. Use `"asset_scope": "channel"` to resolve it relative to the channel manifest and reuse approved artwork. Give each independently moving piece its own SVG layer. Use static, self-contained SVGs with a `viewBox`. Animate each layer's position, scale, rotation, or opacity with manifest keyframes. The browser renderer fits the art inside its layer box without stretching it. Keep embedded scripts, animations, and linked artwork out of the SVG file so the shot can be sought frame by frame.

## Combine 2D and 3D

Choose 3D for objects or shots where perspective, spatial motion, or a recurring set matters. A single episode can cut between flat and 3D shots or combine both in one shot. Mark any flat layer with `"plane": "background"` to place it behind the 3D stage. Other flat layers default to foreground. The order is shot color, 2D background, Three.js, 2D foreground, and captions. Within a plane, later layers draw in front. For a parallax look, keyframe the background more slowly than the foreground. Titles and captions can stay fixed in screen space.

A mixed shot can use a reusable backdrop, a 3D prop from the channel library, and an episode-specific graphic.

```json
{
  "three": {"scene": "workbench"},
  "layers": [
    {"id": "wall", "kind": "svg", "file": "art/wall.svg", "asset_scope": "channel",
     "plane": "background", "x": 0.5, "y": 0.5, "width": 1.2, "height": 1.2,
     "keyframes": [{"at": 1, "x": 0.46, "ease": "smooth"}]},
    {"id": "flash", "kind": "svg", "file": "art/flash.svg", "plane": "foreground",
     "x": 0.72, "y": 0.34, "opacity": 0,
     "keyframes": [{"at": 0.45, "opacity": 0}, {"at": 0.5, "opacity": 1}]}
  ]
}
```

Use the `library` and `three_shot` definitions in the [schema](../../../../studio/schema.json). The channel-relative library contains named scenes. Each scene defines a perspective camera, fixed lighting, and objects with stable IDs. Use unit box, sphere, cylinder, or torus geometry or a self-contained, uncompressed GLB file relative to the library. Embed model textures and buffers. Use the approved GLB for a recurring character.

Set the shot's `three.scene` to a library scene name. Optionally keyframe camera position and target and each object's position, rotation, or scale. Times are normalized over the resolved shot, and Three.js rotations use radians. A shot starts at the library's default poses. Specify a matching opening pose when continuity needs to carry across a cut. GLB objects support whole-model transforms. Complex skeletal animation needs an authored rig workflow.

Declare hitboxes, contacts, and continuity rules with the [staging and visual QA guide](visual-qa.md). Render a preview with the selected backend. Review representative shots from this episode next to approved frames from the series. Check faces, camera and prop scale, lighting, caption clearance, and transition continuity before rendering the full package.

## Stage effects and weight

Give a channel a reusable effects kit with `python -m studio.vfx channels/<slug>`. It writes palette-matched SVGs (flash, shockwave, impact stars, dust, smoke, splash, ripple, speed lines, sparkle) that episodes reference as channel-scoped layers. Start every effect at `opacity: 0` in the base pose, or it shows from frame one. Pop in over one or two frames, hold, then fade over the stated life.

Anchor screen-space effects to 3D contacts with `studio.lens.screen(point, camera)`, using the same shot camera and the canvas size. Recompute when the camera moves during the shot.

Keyframe 3D motion through `studio.physics`: `drop()` for falling props, `burst()` and `splash()` for debris and droplets, `spring()` for overshoot, `orbit()` for floating props, `pendulum()` for swings, and `shake()` for decaying camera jitter. The renderer interpolates linearly between keys, so sample the curve at the frame rate instead of trusting two distant keys. Contact frames should be exact; `drop()` places them on the floor and emits squash on the same object keys. Bias debris upward and keep speeds modest so pieces stay in frame. Hide one-off particles after their last key, or they hang in the air.

## Adjust type, colour and weight

Use a `sheet` layer for frame-by-frame animation. Set `columns`, `rows`, `count`, and keyframe `frame`; the cell holds until the next key. The sheet is sliced once, so Python, HyperFrames and Remotion choose the same frame. Use `reveal` on a static text layer to expand words, lines or characters into timed pieces before the renderers see them. Text is rasterized from the same font resolution in every renderer, so `font` roles, alignment, tracking, line height, stroke and shadow stay consistent. Use `channel.fonts` for a display/body pair and `channel.fonts` roles in captions. A layer `fill` can be a gradient, and `stroke`, `shadow` and `glow` are applied before the layer transform. For 2D weight, use `scale_x`/`scale_y` and `skew_x`/`skew_y`; `scale` remains the uniform fallback. `trail` expands into delayed layers at load time, so it works identically in Python, HyperFrames and Remotion.

## Finish the frame

Use layer `motion_blur` for a cheap directional smear on fast props or text; it samples the layer's own velocity and is separate from the shot-level motion blur. Use a shot `camera` for push-ins, pans and rotations instead of moving every layer by hand. Camera `x` and `y` are canvas-fraction offsets, `zoom` is a multiplier, and keyframes use the same easings as layers. Give background layers a lower `parallax` so they move less.

Use layer `pivot` at human joints and `parent` for cutout rigs. A child's `x` and `y` are offsets from the parent's pivot, and it inherits the parent's scale, rotation and opacity. Keep the parent first in the layer list or rely on the renderer's parent-first ordering.

Add `post` for finishing: `grain`, `vignette`, `bloom`, `blur`, `chromatic`, `letterbox`, and a grade through `brightness`, `contrast`, `saturation`, `hue` and `tint`. Use `blend` on a layer for `add`, `screen`, `multiply`, `overlay` or `soft-light`, and `blur` for depth. Set `motion_blur` on a shot or the episode to accumulate subframes; it costs more render time, so preview before the master. `supersample: 2` renders at twice the canvas and downsamples with Lanczos in both the Python and browser paths.

For 3D, `three.bloom` adds a seeded bloom pass with `bloom_radius` and `bloom_threshold`; it combines with `three.focus` depth of field. Scene libraries can declare `particles` emitters with `position`, `count`, `spread`, `velocity`, `gravity`, `life`, `size`, `color`, `emit` and `blending`. PBR objects accept `metalness`, `roughness`, `emissive` and `emissive_intensity`. A GLB with animation clips can play them through `three.animations` with an object ID, clip name, offset, rate and loop flag. The renderer uses ACES tone mapping with sRGB output.

Transitions include `dissolve`, four wipes, four slides, `whip-left`/`whip-right`, `zoom-in`/`zoom-out`, `iris`, `flash`, `dip-to-black` and `luma-wipe`. Keep the transition shorter than the shot and check the cut with sound. Camera presets include `push-in`, `pull-out`, `crash-zoom`, `whip-pan`, `dolly`, `float`, `orbit` and `handheld`; add `shake` or `handheld` for procedural movement.

Use `style.preset` for a coherent first pass, `render` for CRF/preset/tune/audio bitrate and output switches, and `visible`/`variant_group` for 2D expression or pose swaps. If the channel needs a new SVG, write an Effect Lab recipe and run `python video.py effect`; keep the generated file inside the channel.
