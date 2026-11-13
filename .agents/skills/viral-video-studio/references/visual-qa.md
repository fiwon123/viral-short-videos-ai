# Stage and check the animation

## Lock the design before animating

Open an approved turnaround, model preview, or representative frame for each character. Record silhouette, proportions, scale relative to props, palette, materials, neutral and reaction poses, and the movement that distinguishes the character. Reuse the same versioned artwork and model IDs. Match a new set and its lighting to a frame the channel has already approved. Keep a body, its expression variants, and separate mouth or effects layers identifiable.

## Block layers, motion, and light

- Write each shot's stack from back to front. Use the flat background plane for environment art, the Three.js stage for objects that occlude each other in depth, and the flat foreground plane for titles and screen-space effects. Keep captions above the picture. Assign stable IDs and record the intended overlap, such as a table hiding feet or a held prop crossing a character's body. Check those deliberate occlusions in the actual render.
- Block start, contact, and end poses before easing. Record the floor height, object scale and pivot, who holds or supports each prop, where a hit lands, and when it separates. Keep planted feet and held props anchored during holds. Give a falling object a clear acceleration, impact, and recovery. Carry direction and velocity through matched cuts. For chains of impacts or complex physics, simulate at a fixed step in a physics-capable tool, bake the resulting transforms into the shot, and review the baked motion at output fps.
- Define named `lighting_rigs` in the versioned scene library and reference them with `lighting_rig` on each set. Keep key direction, color, ambient fill, and floor contact shadows consistent across a continuous scene. Plan a motivated light change when the location or story calls for it. Use `shadows: true` in the rig and tag the relevant objects with `cast_shadow` or `receive_shadow`. Size the shadow area to cover the action. Match flat artwork to the same light direction and contrast in mixed shots. [Three.js directional shadows](https://threejs.org/docs/pages/DirectionalLightShadow.html)
- For replaceable 3D poses, use a shared `variant_group` and set each object's default `visible` state. Keyframe `visible` for a clean switch. The visibility change steps on its keyframe. Groups allow at most one visible object at a time. Keep variants at their actual staging coordinates so their poses and contacts can be checked.
- Use `pivot` and `parent` for 2D rigs. Put the pivot at the joint that should stay planted, keep the parent layer first, and check that a rotating head, arm or prop keeps its contact point. A child's `x` and `y` are offsets from the parent's pivot. Check every rig at the extremes of its motion, not only the neutral pose.
- Treat a shot `camera` as a deliberate move. Check that the push-in keeps faces and the payoff inside the safe area, that background `parallax` does not expose an edge, and that camera shake lands on the impact instead of floating.
- Review `post` and `motion_blur` at the final size. Grain and bloom can hide a weak silhouette, and motion blur can smear a contact frame. Compare a clean and finished frame at the same moment.

## Declare the checks that matter

Use the [manifest schema](../../../../studio/schema.json). A 3D `hitbox` is a local box with `size` and optional `center`, in scene units. The check transforms it with the object's authored position, rotation, and scale. Fit the box to the relevant solid area. A 2D `hitbox` is a centered `[width, height]` in canvas fractions before scale and rotation. Omit it to use the layer's declared layout box. For assets with padding or transparency, specify a tighter box.

This is a shot fragment. IDs refer to its layers or the objects in its scene library.

```json
{
  "checks": {
    "keep_in_frame": ["headline"],
    "avoid_2d": [["headline", "badge"]],
    "avoid_3d": [["character", "moving-prop"]],
    "floor": {"y": 0, "objects": ["character", "moving-prop"], "tolerance": 0.02},
    "contacts": [{"at": 0.55, "objects": ["moving-prop", "table"], "tolerance": 0.03}],
    "continuity": {"lighting": true, "objects": ["table"]}
  }
}
```

Use `continuity` only where the previous shot is also 3D. It compares the preceding shot's final rendered pose to the new shot's opening pose. Lock `camera` for a matched camera cut, `lighting` for a continuous lighting setup, and specific object IDs for matched props or actors. Use a contact rule for objects meant to touch. Reserve avoid rules for pairs that should stay apart. Contact times are normalized across the resolved shot and snap to its nearest frame. [Three.js oriented bounding boxes](https://threejs.org/docs/pages/OBB.html)

## Check and review

```sh
python video.py check-visual episodes/my-episode/episode.json \
  --channel channels/my-channel/channel.json
```

The command resolves the speech and effect durations, then checks the authored boxes at output frames. It also checks 3D camera position against its target. The report uses zero-based episode frames and names the shot and objects for each issue. Rendering runs the declared rules and variant checks before encoding. A successful checked export includes `visual-qa.json`.

Compare preview frames with the approved designs and step through every impact, pose switch, and cut. Watch the full preview with sound and muted. Check small silhouettes, eyelines, mouth shapes, frame margins, the contact patch, shadows, and foreground occlusion. The checks cover authored bounds at sampled frames. Review silhouette clipping, mesh deformation, motion between frames, 2D-to-3D occlusion, and the physical feel in the preview.
