# Renderer parity fixture

This is the shared visual contract for the Python and browser renderers.

```sh
python video.py parity --renderers python,hyperframes
```

It renders a short 2D fixture with easings, blend modes, blur, camera, post and
a true luma-wipe, then writes renderer contact sheets, per-frame diffs and
`parity.json` under `output/parity/`.

The support matrix is the source of truth:

```sh
python video.py support --markdown --out docs/RENDERER-SUPPORT.md
```

Python is the raster-2D path. SVG, Three.js and browser-only finishing are
marked in the matrix instead of being approximated silently.
