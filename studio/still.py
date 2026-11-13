"""Render one frame for fast composition and motion review.

The still command reuses the same resolved episode, preset, audio clock and
caption config as a full render. It is intentionally small: one shot, one
frame, one PNG. A contact sheet is a thin wrapper around it.
"""

import math
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from .audio import prepare_audio
from .design import Composition, apply_post, draw_caption, resolve_font
from .render import render_config
from .browser import stage_visuals
from .core import require, run

ENTRY = Path(__file__).resolve().parents[1] / "browser" / "still.mjs"


def _simple_timeline(episode):
    fps = episode["fps"]
    cursor = 0
    scenes = []
    for scene in episode["scenes"]:
        timing = {"id": scene["id"], "purpose": scene.get("purpose", ""), "start": cursor, "shots": []}
        for shot in scene["shots"]:
            frames = max(1, math.ceil(float(shot["duration"]) * fps - 1e-9))
            timing["shots"].append({"id": shot["id"], "start": cursor, "end": cursor + frames,
                                    "speech": [], "sfx": []})
            cursor += frames
        timing["end"] = cursor
        scenes.append(timing)
    return {"fps": fps, "duration_frames": cursor, "scenes": scenes, "captions": []}


def _locate(episode, timeline, shot_id):
    shots = [shot for scene in episode["scenes"] for shot in scene["shots"]]
    target = next((shot for shot in shots if shot["id"] == shot_id), None)
    if target is None:
        names = ", ".join(shot["id"] for shot in shots)
        raise ValueError(f"Unknown shot: {shot_id}. Available: {names}")
    for scene, scene_timing in zip(episode["scenes"], timeline["scenes"]):
        for shot, timing in zip(scene["shots"], scene_timing["shots"]):
            if shot is target:
                return shot, timing
    raise ValueError(f"Shot is not present in the resolved timeline: {shot_id}")


def _speaking(levels, shot_id, frame):
    return {speaker: float(samples[frame - start])
            for start, end, speaker, samples in levels.get(shot_id, [])
            if start <= frame < end}


def _visemes(timeline, absolute):
    found = {}
    for caption in timeline.get("captions", []):
        if caption.get("start", 0) <= absolute < caption.get("end", 0):
            for item in caption.get("visemes", []):
                if item.get("at", 0) <= absolute:
                    found[caption["speaker"]] = item["shape"]
    return found


def _caption_at(timeline, absolute):
    return next((caption for caption in timeline.get("captions", [])
                 if caption.get("start", 0) <= absolute < caption.get("end", 0)), None)


def render_still(episode, channel, episode_dir, channel_dir, target, *, shot_id=None,
                 at=0.0, progress=None, scale=1.0, renderer="python", burn=True, audio=True,
                 library=None, audio_library=None):
    target = Path(target).resolve()
    if shot_id is None:
        shot_id = episode["thumbnail"]["shot"]
    config = render_config(channel, episode)
    supersample = max(1, int(config.get("supersample", 1))) if renderer == "python" else 1
    canvas = tuple(max(2, round(size * float(scale) * supersample) // 2 * 2)
                   for size in (episode["width"], episode["height"]))
    font = resolve_font(channel, channel_dir)
    caption_font = (episode.get("captions") or {}).get("font") or (channel.get("captions") or {}).get("font")
    if caption_font:
        font = resolve_font(channel, channel_dir, caption_font)
    caption_config = {**(channel.get("captions") or {}), **(episode.get("captions") or {})}

    with TemporaryDirectory(prefix=".still-") as temp:
        work = Path(temp)
        if audio:
            timeline, levels = prepare_audio(episode, episode_dir, work / "mix.wav", work,
                                             audio_library, channel=channel)
        else:
            timeline, levels = _simple_timeline(episode), {}
        shot, timing = _locate(episode, timeline, shot_id)
        frames = timing["end"] - timing["start"]
        if progress is not None:
            ratio = max(0.0, min(1.0, float(progress)))
        else:
            ratio = max(0.0, min(0.99, float(at) * timeline["fps"] / max(1, frames)))
        local = round(ratio * max(0, frames - 1))
        absolute = timing["start"] + local
        speaking = _speaking(levels, shot_id, local) if audio else {}
        visemes = _visemes(timeline, absolute) if audio else {}
        caption = _caption_at(timeline, absolute) if (burn and audio) else None

        if renderer == "python":
            composition = Composition(shot, canvas, channel, font, episode_dir,
                                      episode_post=episode.get("post"),
                                      channel_base=channel_dir)
            image = composition.frame(local / max(1, frames - 1), speaking, post=False,
                                      seed=absolute, visemes=visemes)
            image = apply_post(image, composition.post, seed=absolute, palette=channel["palette"])
            if caption:
                draw_caption(image, caption, channel, font, config=caption_config, frame=absolute)
            if supersample > 1:
                image = image.resize((canvas[0] // supersample, canvas[1] // supersample),
                                     Image.Resampling.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target)
            return {"still": str(target), "shot": shot_id, "frame": absolute,
                    "at": round(local / timeline["fps"], 3), "renderer": "python"}

        from .renderers import get

        require("node")
        modules = ENTRY.parent.parent / "node_modules"
        required = get(renderer).package
        if not (modules / required).is_dir():
            raise ValueError("Install browser renderer dependencies with npm ci from the repository root")
        stage_visuals(episode, channel, timeline, levels, canvas, font, episode_dir, channel_dir,
                      library, work, bool(caption), config=config)
        target.parent.mkdir(parents=True, exist_ok=True)
        run("node", str(ENTRY), renderer, str(work), str(target), str(absolute))
        return {"still": str(target), "shot": shot_id, "frame": absolute,
                "at": round(local / timeline["fps"], 3), "renderer": renderer}


def contact_sheet(paths, target, *, labels=None, tile=(270, 480)):
    """Write a labelled grid of stills for motion review."""
    images = []
    for path in paths:
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail(tile, Image.Resampling.LANCZOS)
            images.append(image)
    if not images:
        raise ValueError("A contact sheet needs at least one still")
    padding = 12
    header = 24
    width = max(image.width for image in images) + padding * 2
    height = max(image.height for image in images) + padding * 2 + header
    columns = min(len(images), 4)
    rows = math.ceil(len(images) / columns)
    sheet = Image.new("RGB", (width * columns, height * rows), "#0B1020")
    from PIL import ImageDraw

    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(images):
        column, row = index % columns, index // columns
        x = column * width + (width - image.width) // 2
        y = row * height + header + (height - header - image.height) // 2
        sheet.paste(image, (x, y))
        if labels:
            draw.text((column * width + padding, row * height + 5), labels[index], fill="#F8FAFC")
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)
    return target
