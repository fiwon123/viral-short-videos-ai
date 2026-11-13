# 🛠️ Contributing

The studio is a template. Keep the reusable engine and skill generic; keep channel-specific work local.

## 🧭 Principles

1. **Manifest first.** A creative control should be expressible in JSON before it becomes a Python special case.
2. **Backward compatible.** Existing episodes must keep rendering.
3. **Deterministic.** No hidden randomness without a seed.
4. **Small primitives.** Prefer a preset, recipe or helper over a large opaque feature.
5. **Reviewable.** Every render must be inspectable with `timeline.json`, `qa.json` and `visual-qa.json`.
6. **Original assets.** Do not commit third-party characters, music or footage without a licence.

## ➕ Add a style preset

1. Create `presets/styles/my-style.json`.
2. Use only supported episode keys: `post`, `captions`, `audio`, `render`, `music`, `camera`, `motion_blur`, `supersample`.
3. Test it with an example episode.
4. Document it in [Creative Controls](Creative-Controls).

## ➕ Add a camera preset

1. Add the preset to `studio/camera.py`.
2. Add the enum value to `studio/schema.json`.
3. Test both renderers.
4. Document the motion in [Motion, Camera and Rigs](Motion-Camera-and-Rigs).

## ➕ Add a Sound Lab layer

1. Extend `studio/soundlab.py` with a new layer type.
2. Keep it deterministic and normalize the result.
3. Add a recipe under `presets/audio/` or an example channel.
4. Test with `python video.py sound`.

## ➕ Add an Effect Lab base

1. Add a generator to `studio/effectlab.py`.
2. Use palette roles, not fixed channel colours.
3. Keep the SVG self-contained and static.
4. Test `python video.py effect` and a layer reference.

## ➕ Change the schema

1. Edit `studio/schema.json`.
2. Update the Python renderer.
3. Update `browser/painter.mjs` and/or `browser/three.mjs`.
4. Add a valid example.
5. Update [Manifest Reference](Manifest-Reference).
6. Run:

```sh
python -m py_compile studio/*.py video.py
node --check browser/painter.mjs
python video.py validate examples/paper-crane/episodes/one-letter-home/episode.json \
  --channel examples/paper-crane/channel/channel.json
```

## 📝 Documentation

- Lead the README with creator workflows, example outputs, and monetization. Keep installation and reference links below them.
- Deep detail belongs in `wiki/`.
- Use emoji section headings, tables, badges and callouts.
- Keep code blocks copy-ready.
- Update the wiki source when behavior changes.

## 🧪 Before a pull request

```sh
make doctor
make status
make validate EPISODE=... CHANNEL=...
make check EPISODE=... CHANNEL=...
make preview EPISODE=... CHANNEL=...
```

Include the rendered preview or a link to it when the change affects the picture.

## 🔗 Related guides

- [Manifest Reference](Manifest-Reference)
- [QA, Export and Publishing](QA-Export-and-Publishing)
