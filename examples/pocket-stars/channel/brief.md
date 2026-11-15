# Pocket Stars — example channel

A feature showcase for the newer studio tools, told as one tiny story: Pip
catches a falling star.

- **Shot A:** a gradient sky keyed from dusk to night (`fill` keys), hills at
  three `z` depths under a drifting camera (parallax), twinkling stars
  (`wiggle`), and a generated character with `alive` idle motion and antenna
  follow-through.
- **Shot B:** the star falls on a curved `path`, spins like a coin
  (`turn_y`), carries an SVG `finish` (cel shade, rim, grain), and Pip's arm
  tracks it with `ik`.
- **Shot C:** the catch. A glow ring's `stroke_width` and `fill` swell.
- **Shot D:** a 3D end card. A `camera_rig` orbits extruded 3D text
  (`depth`, `bevel`), an emissive star, particles and fog.

Pip is generated with `make character` from `art/characters/pip.json`. Copy the
structure, not the artwork, when you make a real channel.
