# 🧊 3D and Renderers

The studio supports Three.js scenes for shots where perspective, rotation, contact or a recurring set matters.

## 🎥 Choose a renderer

| Renderer | Use when |
| --- | --- |
| `python` | Simple raster 2D, fastest iteration |
| `hyperframes` | Vector 2D, 2.5D and Three.js; recommended default |
| `remotion` | Existing React/Remotion workflow |

```sh
python video.py render ... --renderer hyperframes --preview
```

SVG and Three.js shots require a browser renderer. The Python renderer rejects them with a clear error.

## 🗺️ Scene library

Point the channel at a scene library:

```json
{"scene_library": "scene-library/station-v1.json"}
```

```json
{
  "version": 1,
  "lighting_rigs": {
    "night": {"ambient": 0.18, "key": 1.7, "position": [-3, 6, 4],
              "target": [0, 0.8, 0], "color": "#BFD7FF",
              "shadows": true, "shadow_extent": 5}
  },
  "scenes": {
    "station": {
      "camera": {"position": [4.2, 3.0, 7.4], "target": [0, 1.8, 0], "fov": 38},
      "lighting_rig": "night",
      "objects": [
        {"id": "desk", "kind": "box", "position": [0, 0.15, 0],
         "scale": [2.6, 0.3, 1.5], "color": "#3B4A63",
         "cast_shadow": true, "receive_shadow": true}
      ]
    }
  }
}
```

Object kinds: `box`, `sphere`, `cylinder`, `torus`, `glb`.

## 🎨 Materials

```json
{"metalness": 0.4, "roughness": 0.3, "emissive": "#6EE7B7", "emissive_intensity": 2.4}
```

The renderer uses ACES tone mapping and sRGB output. Shadows are PCF with a 1024 map.

## 🎬 Animate a shot

```json
{
  "three": {
    "scene": "station",
    "camera": [
      {"at": 0, "position": [4.2, 3.0, 7.4], "target": [0, 1.8, 0]},
      {"at": 1, "position": [2.7, 2.6, 5.9], "target": [0, 1.8, 0], "ease": "sine"}
    ],
    "objects": {
      "signal": [{"at": 0.5, "scale": [0.24, 0.24, 0.24]},
                 {"at": 1, "scale": [0.18, 0.18, 0.18]}]
    }
  }
}
```

Optional GLB animation clips:

```json
{"animations": {"character": [{"clip": "idle", "at": 0, "rate": 1, "loop": true}]}}
```

## 🧱 Model rules

- Use self-contained, uncompressed GLB files.
- Embed buffers and textures.
- Keep object IDs and scale stable between episodes.
- Use `variant_group` and `visible` for pose swaps.
- Add `hitbox`, `floor`, `contacts` and `continuity` checks when staging matters.

## ✅ Review

- Check silhouette, lens and scale.
- Check contact frames and shadows.
- Check the camera target never equals its position.
- Check a 2D/3D cut for scale and light continuity.

## 🔗 Related guides

- [Motion, Camera and Rigs](Motion-Camera-and-Rigs)
- [VFX and Post](VFX-and-Post)
- [Manifest Reference](Manifest-Reference)
