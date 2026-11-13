"""Prepare one frame-accurate visual plan for the optional browser renderers."""

from pathlib import Path
import shutil

from PIL import Image, ImageDraw

from .camera import resolve_camera
from .core import asset, ffmpeg, require, run, svg_asset, write_json
from .design import (_draw_tracked, caption_layout, color_alpha, draw_caption, layer_order, poses,
                     resolve_color, resolve_font, sheet_tiles, sprite, thumbnail)

ENTRY = Path(__file__).resolve().parents[1] / "browser" / "render.mjs"


def _caption_config(channel, episode):
    return {**(channel.get("captions") or {}), **(episode.get("captions") or {})}


def _caption_offset(rows, height, position, extra=0.0):
    top = rows[0][0]["box"][1] if rows else 0
    base = {"top": 0.09, "center": 0.46, "bottom": 0.80}.get(position, 0.80)
    return round(height * (base + float(extra or 0))) - top


def _save_caption_tile(tile, assets, name):
    box = tile.getbbox()
    if not box:
        box = (0, 0, 1, 1)
    tile.crop(box).save(assets / name)
    return {"sprite": name, "x": box[0], "y": box[1]}


def stage_visuals(episode, channel, timeline, levels, canvas, font, base, channel_base, library, work, burn,
                  config=None):
    assets = work / "assets"
    assets.mkdir()
    shots, scenes = [], {}
    width, height = canvas
    cover = episode["thumbnail"]
    caption_config = _caption_config(channel, episode)
    data = {"width": width, "height": height, "fps": timeline["fps"],
            "frames": timeline["duration_frames"], "shots": shots, "scenes": scenes,
            "captions": [], "cover": {"hide": cover.get("hide_layers", [])},
            "caption_style": caption_config.get("style", "box"),
            "palette": channel.get("palette", {})}
    models, vectors = {}, {}

    for source_scene, resolved_scene in zip(episode["scenes"], timeline["scenes"]):
        for shot, resolved in zip(source_scene["shots"], resolved_scene["shots"]):
            start, end = resolved["start"], resolved["end"]
            duration = (end - start) / timeline["fps"]
            if shot["id"] == cover["shot"]:
                data["cover"]["frame"] = start + round(cover.get("at", 0.5) * (end - start - 1))
            transition = dict(resolved.get("transition") or {})
            if transition.get("type") == "mask" and transition.get("mask"):
                mask_base = channel_base if transition.get("mask_scope") == "channel" else base
                mask_path = asset(mask_base, transition["mask"])
                mask_name = f"transition-{len(shots)}-{mask_path.name}"
                shutil.copyfile(mask_path, assets / mask_name)
                transition["mask_sprite"] = mask_name
            prepared = {"start": start, "end": end, "duration": duration,
                        "transition": transition,
                        "background": shot.get("background", channel["palette"]["background"]),
                        "camera": resolve_camera(shot) if shot.get("camera") else None,
                        "post": {**(channel.get("post") or {}), **(episode.get("post") or {}),
                                 **(shot.get("post") or {})},
                        "motion_blur": shot.get("motion_blur",
                                                (config or {}).get("motion_blur", episode.get("motion_blur", 0))),
                        "layers": [], "visemes": [],
                        "speech": [(a, b, speaker, values.tolist())
                                   for a, b, speaker, values in levels.get(shot["id"], [])]}
            prepared["visemes"] = [
                {"start": cue["start"], "end": cue["end"], "speaker": cue.get("speaker"),
                 "shape": item["shape"], "at": item["at"]}
                for cue in timeline["captions"] for item in cue.get("visemes", [])
                if start <= item["at"] < end
            ]
            if three := shot.get("three"):
                scene_id = three["scene"]
                if scene_id not in scenes:
                    scene = library[0]["scenes"][scene_id]
                    objects = []
                    for obj in scene["objects"]:
                        if obj["kind"] == "glb":
                            path = asset(library[1], obj["file"])
                            if path not in models:
                                models[path] = f"model-{len(models)}.glb"
                                shutil.copyfile(path, assets / models[path])
                            obj = {**obj, "file": models[path]}
                        objects.append(obj)
                    scenes[scene_id] = {**scene, "objects": objects}
                prepared["three"] = {**three, "duration": duration}
            ordered = sorted(layer_order(shot["layers"]),
                             key=lambda item: item.get("plane") != "background")
            for index, layer in enumerate(ordered):
                mask = layer.get("mask")
                if mask and not str(mask.get("source", "")).startswith("layer:"):
                    mask_base = channel_base if mask.get("scope") == "channel" else base
                    mask_path = asset(mask_base, mask["source"])
                    mask_name = f"mask-{len(shots)}-{index}-{mask_path.name}"
                    shutil.copyfile(mask_path, assets / mask_name)
                    mask = {**mask, "sprite": mask_name}
                visual = {"id": layer["id"], "kind": layer["kind"], "poses": poses(layer),
                          "mouth": layer.get("mouth_for"),
                          "plane": layer.get("plane", "foreground"),
                          "parent": layer.get("parent"), "variant_group": layer.get("variant_group"),
                          "pivot": layer.get("pivot", [0.5, 0.5]),
                          "blend": layer.get("blend", "normal"), "blur": layer.get("blur", 0),
                          "motion_blur": layer.get("motion_blur", 0),
                          "parallax": layer.get("parallax", 1), "mask": mask,
                          "shadow": layer.get("shadow"), "glow": layer.get("glow"),
                          "tint": layer.get("tint"),
                          "viseme_for": layer.get("viseme_for"), "viseme": layer.get("viseme")}
                if layer["kind"] == "svg":
                    path = svg_asset(layer, base, channel_base)
                    if path not in vectors:
                        vectors[path] = f"vector-{len(vectors)}.svg"
                        shutil.copyfile(path, assets / vectors[path])
                    visual["sprite"] = vectors[path]
                    visual["box"] = [max(1, round(layer.get("width", 0.55) * width)),
                                     max(1, round(layer.get("height", 0.2) * height))]
                elif layer["kind"] == "sheet":
                    frames = []
                    for frame_index, tile in enumerate(sheet_tiles(layer, canvas, base, channel_base)):
                        name = f"shot-{len(shots)}-layer-{index}-frame-{frame_index}.png"
                        tile.save(assets / name)
                        frames.append(name)
                    if not frames:
                        raise ValueError(f"Sprite sheet has no frames: {layer['id']}")
                    visual["frames"] = frames
                    visual["sprite"] = frames[0]
                else:
                    name = f"shot-{len(shots)}-layer-{index}.png"
                    sprite(layer, canvas, channel, font, base, channel_base).save(assets / name)
                    visual["sprite"] = name
                prepared["layers"].append(visual)
            shots.append(prepared)

    if burn:
        style = caption_config.get("style", "box")
        for cue in timeline["captions"]:
            if style == "karaoke":
                text = cue["text"]
                if caption_config.get("uppercase"):
                    text = text.upper()
                blank = Image.new("RGBA", canvas)
                caption_font, rows, size = caption_layout(blank, text, font, caption_config)
                offset = _caption_offset(rows, height, caption_config.get("position", "bottom"),
                                         caption_config.get("offset", 0))
                background = Image.new("RGBA", canvas)
                draw = ImageDraw.Draw(background)
                pad_x = round(width * float(caption_config.get("padding_x", 0.04)))
                pad_y = round(height * float(caption_config.get("padding_y", 0.02)))
                left = round(width * float(caption_config.get("padding_x", 0.09))) - pad_x
                right = width - left
                top = rows[0][0]["box"][1] + offset - pad_y if rows else 0
                bottom = rows[-1][0]["box"][3] + offset + pad_y if rows else 0
                palette = channel["palette"]
                draw.rounded_rectangle((left, top, right, bottom),
                                       radius=max(2, round(size * float(caption_config.get("radius", 0.45)))),
                                       fill=color_alpha(caption_config.get("background", "background"),
                                                        palette, float(caption_config.get("background_opacity", 1))))
                background = _save_caption_tile(background, assets, f"caption-{len(data['captions'])}-bg.png")
                words = []
                index = 0
                for row in rows:
                    for word in row:
                        box = (word["box"][0], word["box"][1] + offset,
                               word["box"][2], word["box"][3] + offset)
                        normal = Image.new("RGBA", canvas)
                        active = Image.new("RGBA", canvas)
                        tracking = float(caption_config.get("letter_spacing", 0))
                        outline = max(0, round(size * float(caption_config.get("stroke", 0))))
                        stroke_color = color_alpha(caption_config.get("background", "background"),
                                                   palette, float(caption_config.get("background_opacity", 1)))
                        normal_draw, active_draw = ImageDraw.Draw(normal), ImageDraw.Draw(active)
                        _draw_tracked(normal_draw, (box[0], box[1]), word["text"], caption_font,
                                      resolve_color(caption_config.get("foreground", "foreground"), palette),
                                      tracking, stroke_width=outline,
                                      stroke_fill=stroke_color)
                        _draw_tracked(active_draw, (box[0], box[1]), word["text"], caption_font,
                                      resolve_color(caption_config.get("highlight_text", "background"), palette),
                                      tracking, stroke_width=outline,
                                      stroke_fill=stroke_color)
                        normal = _save_caption_tile(normal, assets, f"caption-{len(data['captions'])}-w{index}.png")
                        active = _save_caption_tile(active, assets, f"caption-{len(data['captions'])}-a{index}.png")
                        timing = cue.get("words", [])
                        words.append({
                            "start": timing[index]["start"] if index < len(timing) else cue["start"],
                            "end": timing[index]["end"] if index < len(timing) else cue["end"],
                            "normal": normal, "active": active,
                            "box": [round(box[0]), round(box[1]), round(box[2]), round(box[3])],
                        })
                        index += 1
                data["captions"].append({
                    "start": cue["start"], "end": cue["end"],
                    "background": background, "words": words, "karaoke": True,
                    "highlight": resolve_color(caption_config.get("highlight", "accent"), palette),
                    "highlight_pad": round(size * 0.04),
                    "highlight_radius": round(size * 0.20),
                    "animation": caption_config.get("animation", "none"),
                })
            else:
                text = cue["text"]
                if caption_config.get("uppercase"):
                    text = text.upper()
                tile = Image.new("RGBA", canvas)
                draw_caption(tile, {**cue, "text": text}, channel, font, config=caption_config)
                caption_sprite = _save_caption_tile(tile, assets, f"caption-{len(data['captions'])}.png")
                data["captions"].append({"start": cue["start"], "end": cue["end"], **caption_sprite,
                                         "animation": caption_config.get("animation", "none")})
    write_json(work / "visual-plan.json", data)


def render_browser(backend, episode, channel, timeline, levels, canvas, font, base, channel_base,
                   library, work, out, burn, preview, config=None):
    from .render import encoder

    require("node")
    from .renderers import get

    modules = ENTRY.parent.parent / "node_modules"
    required = get(backend).package
    if not (modules / required).is_dir():
        raise ValueError("Install browser renderer dependencies with npm ci from the repository root")
    config = config or {}
    caption_font = (episode.get("captions") or {}).get("font") or (channel.get("captions") or {}).get("font")
    if caption_font:
        font = resolve_font(channel, channel_base, caption_font)
    scale = max(1, int(config.get("supersample", episode.get("supersample", 1))))
    visual_canvas = (canvas[0] * scale, canvas[1] * scale)
    stage_visuals(episode, channel, timeline, levels, visual_canvas, font, base, channel_base, library, work, burn,
                  config=config)
    video_options = ["-c:v", "copy"]
    if scale > 1:
        video_options = [*encoder(canvas[0], canvas[1], timeline["fps"], config), "-pix_fmt", "yuv420p"]
    picture_format = "mp4"
    if backend == "hyperframes":
        available_encoder = encoder(*canvas, timeline["fps"], config)
        if "libx264" not in available_encoder:
            picture_format = "webm"
            video_options = [*available_encoder, "-pix_fmt", "yuv420p"]
    run("node", str(ENTRY), backend, str(work), picture_format, "preview" if preview else "final")
    if config.get("thumbnail", True):
        thumbnail_font = resolve_font(channel, channel_base)
        with Image.open(work / "cover.png") as cover:
            for index, item in enumerate([episode["thumbnail"], *episode.get("thumbnails", [])]):
                image = thumbnail(cover.convert("RGB"), item["text"], channel, thumbnail_font, item,
                                  channel_base)
                if index == 0:
                    image.save(out / "thumbnail.png")
                else:
                    name = "".join(character if character.isalnum() or character in "-_" else "-"
                                   for character in str(item.get("name", index))).strip("-")
                    image.save(out / f"thumbnail-{name or index}.png")
    picture_filter = (["-vf", f"scale={canvas[0]}:{canvas[1]}:flags=lanczos"] if scale > 1 else [])
    audio_bitrate = int(config.get("audio_bitrate", 192))
    ffmpeg("-i", str(work / f"picture.{picture_format}"), "-i", str(work / "mix.wav"), "-map", "0:v:0", "-map", "1:a:0",
           *picture_filter, *video_options, "-c:a", "aac", "-b:a", f"{audio_bitrate}k", "-ac", "2",
           "-movflags", "+faststart", str(out / "video.mp4"))
