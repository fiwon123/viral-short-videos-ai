"""Prepare one frame-accurate visual plan for the optional browser renderers."""

from pathlib import Path
import shutil

from PIL import Image

from .core import asset, ffmpeg, require, run, svg_asset, write_json
from .design import draw_caption, poses, sprite, thumbnail

ENTRY = Path(__file__).resolve().parents[1] / "browser" / "render.mjs"


def stage_visuals(episode, channel, timeline, levels, canvas, font, base, channel_base, library, work, burn):
    assets = work / "assets"
    assets.mkdir()
    shots, scenes = [], {}
    width, height = canvas
    cover = episode["thumbnail"]
    data = {"width": width, "height": height, "fps": timeline["fps"],
            "frames": timeline["duration_frames"], "shots": shots, "scenes": scenes,
            "captions": [], "cover": {"hide": cover.get("hide_layers", [])}}
    models, vectors, caption_sprites = {}, {}, {}

    for source_scene, resolved_scene in zip(episode["scenes"], timeline["scenes"]):
        for shot, resolved in zip(source_scene["shots"], resolved_scene["shots"]):
            start, end = resolved["start"], resolved["end"]
            if shot["id"] == cover["shot"]:
                data["cover"]["frame"] = start + round(cover.get("at", 0.5) * (end - start - 1))
            prepared = {"start": start, "end": end, "transition": resolved.get("transition"),
                        "background": shot.get("background", channel["palette"]["background"]),
                        "layers": [], "speech": [(a, b, speaker, values.tolist())
                                                 for a, b, speaker, values in levels[shot["id"]]]}
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
                prepared["three"] = three
            for index, layer in enumerate(shot["layers"]):
                visual = {"id": layer["id"], "poses": poses(layer), "mouth": layer.get("mouth_for"),
                          "plane": layer.get("plane", "foreground")}
                if layer["kind"] == "svg":
                    path = svg_asset(layer, base, channel_base)
                    if path not in vectors:
                        vectors[path] = f"vector-{len(vectors)}.svg"
                        shutil.copyfile(path, assets / vectors[path])
                    visual["sprite"] = vectors[path]
                    visual["box"] = [max(1, round(layer.get("width", 0.55) * width)),
                                     max(1, round(layer.get("height", 0.2) * height))]
                else:
                    name = f"shot-{len(shots)}-layer-{index}.png"
                    sprite(layer, canvas, channel["palette"], font, base).save(assets / name)
                    visual["sprite"] = name
                prepared["layers"].append(visual)
            shots.append(prepared)

    if burn:
        for cue in timeline["captions"]:
            text = cue["text"]
            if text not in caption_sprites:
                tile = Image.new("RGBA", canvas)
                draw_caption(tile, text, channel, font)
                x, y, right, bottom = tile.getbbox()
                name = f"caption-{len(caption_sprites)}.png"
                tile.crop((x, y, right, bottom)).save(assets / name)
                caption_sprites[text] = {"sprite": name, "x": x, "y": y}
            data["captions"].append({"start": cue["start"], "end": cue["end"], **caption_sprites[text]})
    write_json(work / "visual-plan.json", data)


def render_browser(backend, episode, channel, timeline, levels, canvas, font, base, channel_base,
                   library, work, out, burn, preview):
    from .render import encoder

    require("node")
    modules = ENTRY.parent.parent / "node_modules"
    required = "@remotion/renderer" if backend == "remotion" else "hyperframes"
    if not (modules / required).is_dir():
        raise ValueError("Install browser renderer dependencies with npm ci from the repository root")
    stage_visuals(episode, channel, timeline, levels, canvas, font, base, channel_base, library, work, burn)
    video_options = ["-c:v", "copy"]
    picture_format = "mp4"
    if backend == "hyperframes":
        available_encoder = encoder(*canvas, timeline["fps"])
        if "libx264" not in available_encoder:
            picture_format = "webm"
            video_options = [*available_encoder, "-pix_fmt", "yuv420p"]
    run("node", str(ENTRY), backend, str(work), picture_format, "preview" if preview else "final")
    with Image.open(work / "cover.png") as cover:
        thumbnail(cover.convert("RGB"), episode["thumbnail"]["text"], channel, font).save(out / "thumbnail.png")
    ffmpeg("-i", str(work / f"picture.{picture_format}"), "-i", str(work / "mix.wav"), "-map", "0:v:0", "-map", "1:a:0",
           *video_options, "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out / "video.mp4"))
