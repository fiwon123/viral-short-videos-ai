# 📘 Manifest Reference

The full JSON Schema is in [`studio/schema.json`](https://github.com/fiwon123/viral-short-videos-ai/blob/main/studio/schema.json). This page is the practical guide.

## 🏷️ Channel

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | text | Channel name |
| `handle` | text | `@handle` |
| `tagline` | text | Short promise |
| `description` | text | Long channel description |
| `tags` | text[] | Channel tags |
| `mark` | text | 1–6 characters for the logo |
| `palette` | object | `background`, `foreground`, `accent`, `secondary` |
| `font` | path | Optional brand font |
| `scene_library` | path | Optional 3D scene library |
| `audio_library` | path | Optional voice and Foley library |
| `banner` | object | Width, height and safe area |
| `captions` | object | Channel caption defaults |
| `style` | object | Channel style preset |
| `audio` | object | Channel audio defaults |
| `render` | object | Channel render defaults |
| `post` | object | Channel finishing defaults |
| `motion_blur` | 0–1 | Channel motion-blur default |

## 🎞️ Episode

| Field | Type | Meaning |
| --- | --- | --- |
| `title` | text | Publishing title |
| `description` | text | Publishing description |
| `tags` | text[] | YouTube tags |
| `width`, `height` | even integer | Canvas size |
| `fps` | enum | 12, 15, 24, 25, 30, 48, 50, 60 |
| `max_seconds` | number | Hard runtime limit |
| `supersample` | 1–2 | Render at 2× and downsample |
| `motion_blur` | 0–1 | Subframe motion blur |
| `post` | object | Grade and finishing |
| `captions` | object | Caption style |
| `audio` | object | Master, reverb and room tone |
| `render` | object | Codec/quality/output switches |
| `style` | object | Style preset |
| `music` | object | Music bed |
| `voice` | object | eSpeak fallback voice |
| `tiktok` | object | Caption and hashtags |
| `thumbnail` | object | Shot, text, time and hidden layers |
| `scenes` | array | Story scenes |

## 🎥 Shot

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | text | Unique shot ID |
| `duration` | number | Requested seconds |
| `direction` | text | Direction note for the timed script |
| `layers` | array | 2D layer stack |
| `three` | object | 3D scene and keys |
| `camera` | object | 2D camera |
| `speech` | array | Voice lines |
| `sfx` | array | Sound cues |
| `transition` | object | Incoming transition |
| `post` | object | Shot finishing |
| `motion_blur` | 0–1 | Shot motion blur |
| `checks` | object | Visual QA rules |
| `background` | color | Shot background |

## 🧱 Layer

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | text | Unique within the shot |
| `kind` | enum | `rect`, `ellipse`, `polygon`, `text`, `image`, `svg` |
| `x`, `y` | number | Centre or parent-relative offset |
| `width`, `height` | number | Box size in canvas fractions |
| `scale`, `rotate`, `opacity` | number | Base pose |
| `visible` | boolean | Base visibility |
| `parent` | text | Parent layer ID |
| `pivot` | `[x,y]` | Pivot inside the layer box |
| `variant_group` | text | At most one visible layer in the group |
| `plane` | enum | `background` or `foreground` |
| `asset_scope` | enum | `episode` or `channel` |
| `fill` | color/name | Palette role or hex |
| `radius` | 0–1 | Rounded rectangle radius |
| `text` | text | Text content |
| `file` | path | Image or SVG |
| `mouth_for` | text | Speaker whose audio drives mouth height |
| `blend` | enum | `normal`, `add`, `screen`, `multiply`, `overlay`, `soft-light` |
| `blur` | 0–1 | Layer blur |
| `parallax` | 0–2 | Camera parallax amount |
| `hitbox` | `[w,h]` | 2D QA box |
| `points` | array | Polygon points |
| `keyframes` | array | Pose keys |

## 🎥 Camera

| Field | Type | Meaning |
| --- | --- | --- |
| `x`, `y` | number | Canvas-fraction offset |
| `zoom` | number | Zoom multiplier |
| `rotate` | number | Degrees |
| `preset` | enum | `push-in`, `pull-out`, `crash-zoom`, `whip-pan`, `dolly`, `float`, `orbit`, `handheld` |
| `shake` | object | `amplitude`, `frequency`, `decay`, `seed` |
| `handheld` | object | `amplitude`, `frequency`, `seed` |
| `keyframes` | array | Normalized camera keys |

## 🔁 Transition

| Field | Type | Meaning |
| --- | --- | --- |
| `type` | enum | 17 types: dissolve, wipes, slides, whips, zoom, iris, flash, dip-to-black, luma-wipe |
| `duration` | number | Seconds, shorter than the shot |
| `ease` | enum | Easing for the transition |

## 🎨 Post

| Field | Range | Meaning |
| --- | --- | --- |
| `brightness` | 0–2 | Exposure |
| `contrast` | 0–2 | Contrast |
| `saturation` | 0–2 | Saturation |
| `hue` | −180–180 | Hue rotation |
| `tint` | color | Warm/cool tint |
| `bloom` | 0–1 | Highlight bloom |
| `blur` | 0–1 | Soft focus |
| `chromatic` | 0–1 | RGB split |
| `grain` | 0–1 | Film grain |
| `vignette` | 0–1 | Edge darkening |
| `letterbox` | 0–1 | Black bars |

## 🗣️ Speech

| Field | Type | Meaning |
| --- | --- | --- |
| `speaker` | text | Cast profile name |
| `text` | text | Displayed caption |
| `spoken_text` | text | Optional spoken variant |
| `caption` | text | Optional caption override |
| `delivery` | text | Acting note |
| `at` | seconds | Start offset |
| `file` | path | Recorded take |
| `pan` | −1–1 | Stereo position |
| `reverb` | 0–1 | Wet send |
| `gain` | 0–1 | Level |

## 🔊 SFX

| Field | Type | Meaning |
| --- | --- | --- |
| `at` | seconds | Start |
| `sound` | text | Channel library sound |
| `variant` | integer | Lock a take |
| `file` | path | Episode-local sound |
| `cue` | enum | Legacy `pop`, `whoosh`, `chime` |
| `gain` | 0–1 | Level |
| `rate` | 0.5–1.8 | Pitch/duration |
| `pan` | −1–1 | Stereo position |
| `reverb` | 0–1 | Wet send |
| `pitch_variance` | 0–0.5 | Deterministic variation |
| `fade_in`, `fade_out` | seconds | Edge fades |
| `loop` | boolean | Loop playback |
| `duration` | seconds | Loop length |
| `layers` | array | Stacked cues with `offset` |

## 🎵 Music

| Field | Type | Meaning |
| --- | --- | --- |
| `preset` | `pulse` | Built-in scratch bed |
| `file` | path | Imported music |
| `gain` | 0–1 | Level |
| `fade_in`, `fade_out` | seconds | Music fades |
| `duck` | object | `amount`, `attack`, `release` |

## 🎚️ Audio

| Field | Type | Meaning |
| --- | --- | --- |
| `master.enabled` | boolean | Run the mastering chain |
| `master.loudness` | −40–0 | Integrated LUFS target |
| `master.true_peak` | −9–0 | True-peak ceiling |
| `master.compress` | boolean | Bus compression |
| `master.stereo_width` | 0–2 | Stereo width |
| `reverb.mix` | 0–1 | Shared wet send |
| `reverb.size` | 0–1 | Shared reverb size |
| `room_tone.file/sound` | path/text | Continuous room bed |
| `room_tone.gain` | 0–1 | Room level |

## 🖼️ Render

| Field | Type | Meaning |
| --- | --- | --- |
| `crf` | 0–51 | H.264 quality |
| `preset` | enum | x264 preset |
| `tune` | enum | `animation`, `film`, `grain`, `stillimage`, `fastdecode`, `zerolatency`, `none` |
| `audio_bitrate` | 64–512 | kbps |
| `captions` | boolean | Burned captions and SRT |
| `thumbnail` | boolean | Thumbnail export |
| `publishing` | boolean | Publishing files |
| `supersample` | 1–2 | 2× supersampling |
| `motion_blur` | 0–1 | Motion blur |
| `master` | boolean | Enable audio mastering |

## 🧊 3D

| Field | Type | Meaning |
| --- | --- | --- |
| `three.scene` | text | Scene library name |
| `three.camera` | array | Camera position/target keys |
| `three.objects` | object | Per-object transform keys |
| `three.animations` | object | GLB clip playback |
| `three_object.kind` | enum | `box`, `sphere`, `cylinder`, `torus`, `glb` |
| `metalness`, `roughness` | 0–1 | PBR finish |
| `emissive`, `emissive_intensity` | color/number | Glow |
| `cast_shadow`, `receive_shadow` | boolean | Shadows |
| `variant_group`, `visible` | text/boolean | Pose swaps |

## 🧪 Advanced additions

| Field | Type | Meaning |
| --- | --- | --- |
| `layer.kind: "group"` | enum | Container that inherits transforms and masks to children |
| `layer.mask` | object | `source`, `mode` alpha/luma, `invert`, `feather`, `scope` |
| `layer.kind: "particles"` | enum | Expands into deterministic particle layers |
| `particles.count/rate/life` | numbers | Total count, rate-based count, lifespan |
| `particles.velocity/gravity/spread/size/area/seed` | numbers | Motion and look |
| `layer.viseme_for/viseme` | text | Mouth-shape switching from measured visemes |
| `camera.track` | object | Keep a layer at a screen point |
| `camera.shakes` | array | Timed camera shakes |
| `three.camera[].fov` | number | Keyframeable 3D field of view |
| `three.focus[]` | array | 3D focus distance and aperture |
| `three.animations[].weight` | 0–1 | Blend multiple GLB clips |
| `speech.lead` | seconds | Start dialogue before the picture cut |
| `speech.words` | arrays | Measured word timings |
| `speech.visemes` | arrays | Measured viseme timings |
| `sfx.lead` | seconds | Start a sound before the cut |
| `episode.ambience` | array | Room, wind or city bed across shots |
| `episode.markers` | array | Named SFX, shake and effect bundles |
| `render.stems` | boolean | Write dialogue/music/ambience/SFX stems |
| `transition.mask` | path | Custom luma or alpha matte |
| `transition.mask_mode` | enum | `luma` or `alpha` |
| `transition.softness` | 0–1 | Matte edge feather |

Full examples: [Advanced Controls](Advanced-Controls).

## 🔗 Related guides

- [Creative Controls](Creative-Controls)
- [Audio and Sound Design](Audio-and-Sound-Design)
- [Motion, Camera and Rigs](Motion-Camera-and-Rigs)
