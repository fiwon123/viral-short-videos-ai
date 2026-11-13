"""Encode video, verify output, and package an episode for review."""

from fractions import Fraction
import math
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image

from .audio import audio_summary, prepare_audio
from .core import MAX_SECONDS, asset, new_package, probe, require, run, write_json
from .design import Composition, apply_post, draw_caption, resolve_font, thumbnail, transition_frame
from .publishing import publishing_guide
from .visual import audit_visual


def render_config(channel, episode):
    config = {}
    for source in ((channel or {}).get("render"), (episode or {}).get("render")):
        config.update(source or {})
    config.setdefault("supersample", (channel or {}).get("render", {}).get("supersample",
                                                                          (episode or {}).get("supersample", 1)))
    config.setdefault("motion_blur", (channel or {}).get("motion_blur",
                                                         (episode or {}).get("motion_blur", 0)))
    return config


def encoder(width, height, fps, config=None):
    config = config or {}
    entries = run("ffmpeg", "-hide_banner", "-encoders").decode()
    encoders = {fields[1] for line in entries.splitlines() if len(fields := line.split()) > 2}
    crf = int(config.get("crf", 17))
    preset = config.get("preset", "medium")
    tune = config.get("tune", "animation")
    if "libx264" in encoders:
        options = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
        if tune != "none":
            options.extend(["-tune", tune])
        return options
    if "libopenh264" in encoders:
        factor = max(0.08, min(0.4, 0.30 - (crf - 17) * 0.015))
        bitrate = max(1_000_000, round(width * height * fps * factor))
        return ["-c:v", "libopenh264", "-b:v", str(bitrate)]
    raise ValueError("Install an FFmpeg build with libx264 or libopenh264 for H.264 export")


def clock(frame, fps, separator="."):
    seconds, ms = divmod(round(Fraction(1000 * frame, fps)), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{ms:03}"


def export_srt(path, cues, fps):
    blocks = [
        f"{i}\n{clock(cue['start'], fps, ',')} --> {clock(cue['end'], fps, ',')}\n{cue['text']}\n\n"
        for i, cue in enumerate(cues, 1)
    ]
    path.write_text("".join(blocks).rstrip() + "\n", encoding="utf-8")


def write_script(path, episode, channel, timeline):
    fps = timeline["fps"]
    rows = [f"# {episode['title']}", "", f"{episode['width']} × {episode['height']} · {fps} fps",
            f"Runtime {clock(timeline['duration_frames'], fps)}", "",
            "Layer coordinates and box sizes are canvas fractions with the origin at the top left. "
            "Positions refer to layer centers. Background layers sit behind the 3D stage and foreground layers sit above it. "
            "Layers within each plane are drawn back to front.", ""]
    if episode.get("music"):
        music = episode["music"]
        rows.extend([f"Music bed: {music.get('file', music.get('preset'))}, gain {music.get('gain', 0.10)}, ducked under speech.", ""])
    for scene, timing in zip(episode["scenes"], timeline["scenes"]):
        rows.extend([f"## {scene['id']} · {clock(timing['start'], fps)}–{clock(timing['end'], fps)}", "", scene["purpose"], ""])
        for shot, resolved in zip(scene["shots"], timing["shots"]):
            start, end = resolved["start"], resolved["end"]
            rows.extend([f"### {shot['id']} · {clock(start, fps)}–{clock(end, fps)}", "",
                         shot.get("direction", "Use the composition and motion cues below."), ""])
            if three := shot.get("three"):
                rows.append(f"- 3D scene `{three['scene']}` from `{channel['scene_library']}`.")
                for subject, keys in [("Camera", three.get("camera", [])), *three.get("objects", {}).items()]:
                    for key in keys:
                        frame = start + round(key["at"] * (end - start - 1))
                        pose = ", ".join(f"{name}={value}" for name, value in key.items() if name != "at")
                        rows.append(f"  - {clock(frame, fps)} · {subject} · {pose}")
            background = shot.get("background", channel["palette"]["background"])
            rows.append(f"- Background {background}.")
            if camera := shot.get("camera"):
                keys = ", ".join(f"{key['at']}:x={key.get('x', 0)},y={key.get('y', 0)},"
                                 f"zoom={key.get('zoom', 1)},rotate={key.get('rotate', 0)}"
                                 for key in camera.get("keyframes", []))
                rows.append(f"- Camera {camera.get('x', 0)}, {camera.get('y', 0)}, zoom {camera.get('zoom', 1)}, "
                            f"rotate {camera.get('rotate', 0)}" + (f"; keys {keys}." if keys else "."))
            if post := shot.get("post"):
                rows.append("- Post: " + ", ".join(f"{key}={value}" for key, value in post.items()) + ".")
            if blur := shot.get("motion_blur"):
                rows.append(f"- Motion blur {blur}.")
            if transition := resolved.get("transition"):
                rows.append(f"- {transition['type']} from {clock(transition['start'], fps)} to {clock(transition['end'], fps)}.")
            elif start:
                rows.append("- Cut at the shot boundary.")
            for layer in shot["layers"]:
                scale = layer.get("scale", 1)
                scale_x = layer.get("scale_x", scale)
                scale_y = layer.get("scale_y", scale)
                stage = (f"- {layer['id']} ({layer['kind']}, {layer.get('plane', 'foreground')}) at ({layer['x']}, {layer['y']}), "
                         f"box {layer.get('width', 0.55)} × {layer.get('height', 0.2)}, "
                         f"scale {scale_x} × {scale_y}, rotation {layer.get('rotate', 0)}°, "
                         f"opacity {layer.get('opacity', 1)}.")
                if "file" in layer:
                    stage += f" {layer.get('asset_scope', 'episode').capitalize()} asset `{layer['file']}`."
                else:
                    fill = layer.get("fill", "foreground")
                    fill = "gradient" if isinstance(fill, dict) else channel["palette"].get(fill, fill)
                    stage += f" Fill {fill}."
                if "text" in layer:
                    stage += f" Screen text: {layer['text']}"
                if "mouth_for" in layer:
                    stage += f" Mouth movement follows {layer['mouth_for']}."
                rows.append(stage)
                for key in layer.get("keyframes", []):
                    frame = start + round(key["at"] * (end - start - 1))
                    pose = ", ".join(f"{name}={value}" for name, value in key.items() if name != "at")
                    rows.append(f"  - {clock(frame, fps)} · {pose}")
            for cue in resolved["speech"]:
                direction = f" Delivery: {cue['delivery']}." if "delivery" in cue else ""
                rows.append(f"- {clock(cue['start'], fps)}–{clock(cue['end'], fps)} · {cue['speaker']}: "
                            f"{cue['text']} [{cue['source']}].{direction}")
            for cue in resolved["sfx"]:
                rows.append(f"- {clock(cue['start'], fps)}–{clock(cue['end'], fps)} · SFX {cue['source']} at gain {cue['gain']}.")
            rows.append("")
    rows.extend(["## Captions", ""])
    for cue in timeline["captions"]:
        text = cue["text"].replace("\n", " / ")
        rows.append(f"- {clock(cue['start'], fps)}–{clock(cue['end'], fps)} · {text}")
    path.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")


def write_frames(pipe, episode, timeline, levels, canvas, channel, font, base, out, burn,
                 config=None, make_thumbnail=True, channel_base=None):
    import numpy as np

    config = config or render_config(channel, episode)
    previous = None
    cues = iter(timeline["captions"])
    cue = next(cues, None)
    supersample = max(1, int(config.get("supersample", 1)))
    render_canvas = (canvas[0] * supersample, canvas[1] * supersample)
    caption_config = {**(channel.get("captions") or {}), **(episode.get("captions") or {})}
    thumbnail_font = resolve_font(channel, channel_base or base)
    primary_at = episode["thumbnail"].get("at", 0.5)
    covers = [{**cover, "at": cover.get("at", primary_at)}
              for cover in [episode["thumbnail"], *episode.get("thumbnails", [])]]
    for scene, scene_timing in zip(episode["scenes"], timeline["scenes"]):
        for shot, timing in zip(scene["shots"], scene_timing["shots"]):
            composition = Composition(shot, render_canvas, channel, font, base,
                                      episode_post=episode.get("post"),
                                      motion_blur=config.get("motion_blur", 0),
                                      channel_base=channel_base)
            frames = timing["end"] - timing["start"]
            transition = timing.get("transition")
            count = transition["end"] - transition["start"] if transition else 0
            cover_frames = {}
            for index, cover in enumerate(covers):
                if cover["shot"] == shot["id"]:
                    cover_frames.setdefault(round(cover.get("at", 0.5) * (frames - 1)),
                                            []).append((index, cover))
            blur = float(shot.get("motion_blur", config.get("motion_blur", 0)) or 0)
            subframes = 5 if blur >= 0.55 else 3 if blur >= 0.18 else 1
            post = {**(channel.get("post") or {}), **(episode.get("post") or {}), **(shot.get("post") or {})}
            transition_mask = None
            if transition and transition.get("type") == "mask" and transition.get("mask"):
                mask_base = channel_base if transition.get("mask_scope") == "channel" else base
                with Image.open(asset(mask_base, transition["mask"])) as source:
                    transition_mask = source.convert("L").copy()
            for frame in range(frames):
                absolute = timing["start"] + frame
                progress = frame / max(1, frames - 1)
                speaking = {speaker: float(samples[frame - a])
                            for a, b, speaker, samples in levels[shot["id"]] if a <= frame < b}
                visemes = {}
                for caption in timeline["captions"]:
                    if caption.get("start", 0) <= absolute < caption.get("end", 0):
                        for item in caption.get("visemes", []):
                            if item.get("at", 0) <= absolute:
                                visemes[caption["speaker"]] = item["shape"]
                if subframes > 1:
                    shutter = blur / max(frames, 1)
                    stack = []
                    for index in range(subframes):
                        offset = (index - (subframes - 1) / 2) * shutter
                        stack.append(np.asarray(composition.frame(
                            max(0.0, min(1.0, progress + offset)), speaking,
                            post=False, seed=absolute * 11 + index, visemes=visemes)))
                    visual = Image.fromarray(np.uint8(np.mean(stack, axis=0)))
                else:
                    visual = composition.frame(progress, speaking, post=False, seed=absolute,
                                               visemes=visemes)
                visual = apply_post(visual, post, seed=absolute, palette=channel["palette"])
                if make_thumbnail:
                    for cover_index, cover in cover_frames.get(frame, []):
                        clean = composition.frame(progress, {}, cover.get("hide_layers", []),
                                                  post=False, seed=absolute)
                        image_cover = thumbnail(apply_post(clean, post, seed=absolute,
                                                           palette=channel["palette"]),
                                                cover["text"], channel, thumbnail_font, cover,
                                                channel_base or base)
                        if cover_index == 0:
                            image_cover.save(out / "thumbnail.png")
                        else:
                            name = "".join(character if character.isalnum() or character in "-_" else "-"
                                           for character in str(cover.get("name", cover_index))).strip("-")
                            image_cover.save(out / f"thumbnail-{name or cover_index}.png")
                image = visual
                if count and frame < count:
                    image = transition_frame(previous, visual, transition["type"], (frame + 1) / count,
                                             transition.get("ease", "smooth"),
                                             softness=transition.get("softness", 0.08),
                                             invert=transition.get("invert", False),
                                             seed=transition.get("seed", 17),
                                             mask_image=transition_mask,
                                             mask_mode=transition.get("mask_mode", "luma"))
                while cue and absolute >= cue["end"]:
                    cue = next(cues, None)
                if burn and cue and cue["start"] <= absolute < cue["end"]:
                    image = image.copy()
                    draw_caption(image, cue, channel, font, config=caption_config, frame=absolute)
                if supersample > 1:
                    image = image.resize(canvas, Image.Resampling.LANCZOS)
                pipe.write(image.tobytes())
            previous = visual


def encode(episode, timeline, levels, canvas, channel, font, base, out, mix, burn, *,
           config=None, make_thumbnail=True, channel_base=None):
    w, h = canvas
    fps = timeline["fps"]
    config = config or render_config(channel, episode)
    options = encoder(w, h, fps, config)
    audio_bitrate = int(config.get("audio_bitrate", 192))
    dest = out / "video.mp4"
    with TemporaryDirectory() as temp:
        with (Path(temp) / "ffmpeg.log").open("w+b") as log:
            process = subprocess.Popen(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
                 "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0", "-i", str(mix),
                 *options, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", f"{audio_bitrate}k", "-ac", "2",
                 "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                 "-movflags", "+faststart", str(dest)], stdin=subprocess.PIPE, stderr=log,
            )
            try:
                with process.stdin as pipe:
                    write_frames(pipe, episode, timeline, levels, canvas, channel, font, base, out, burn,
                                 config=config, make_thumbnail=make_thumbnail,
                                 channel_base=channel_base)
            except BrokenPipeError:
                pass
            except BaseException:
                process.kill()
                process.wait()
                raise
            if process.wait():
                log.seek(0)
                raise ValueError(f"Video encode failed\n{log.read().decode(errors='replace')[-2500:]}")


def verify(path, timeline, canvas, limit):
    data = probe(path, count_frames=True)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), {})
    duration = float(data["format"]["duration"])
    fps = timeline["fps"]
    frames = timeline["duration_frames"]
    if (video.get("width"), video.get("height")) != canvas or video.get("codec_name") != "h264":
        raise ValueError("Encoded video is missing or has an unexpected format")
    if int(video.get("nb_read_frames", 0)) != frames or Fraction(video["avg_frame_rate"]) != fps:
        raise ValueError("Encoded video has unexpected frame count or frame rate")
    audio_duration = float(audio.get("duration", 0))
    if not audio or abs(audio_duration - frames / fps) > 0.06:
        raise ValueError("Encoded audio length does not match the timeline")
    if not math.isfinite(duration) or abs(duration - frames / fps) > 0.06 or duration > limit + 0.000001:
        raise ValueError(f"Encoded container duration failed the timeline or {limit:g}-second limit check")
    return {"duration_seconds": duration, "frames": frames, "fps": fps,
            "width": canvas[0], "height": canvas[1], "video_codec": video["codec_name"],
            "audio_codec": audio["codec_name"], "audio_seconds": audio_duration,
            "caption_cues": len(timeline["captions"])}


def render(episode, channel, episode_dir, channel_dir, target, preview, burn, *, backend="python", library=None,
           audio_library=None, options=None):
    config = render_config(channel, episode)
    if options:
        config.update({key: value for key, value in options.items() if value is not None})
    make_thumbnail = bool(config.get("thumbnail", True))
    make_publishing = bool(config.get("publishing", True))
    burn = bool(burn and config.get("captions", True))
    if config.get("stems"):
        episode["render"] = {**(episode.get("render") or {}), "stems": True}
    shots = [shot for scene in episode["scenes"] for shot in scene["shots"]]
    has_three = any("three" in shot for shot in shots)
    if backend == "python":
        if has_three:
            raise ValueError("Three.js shots require --renderer remotion or --renderer hyperframes")
        if any(layer["kind"] == "svg" for shot in shots for layer in shot["layers"]):
            raise ValueError("SVG layers require --renderer hyperframes or --renderer remotion")
    require("ffmpeg")
    require("ffprobe")
    scale = float(config.get("scale", 1) or 1)
    if preview:
        scale *= 0.25
    canvas = tuple(max(2, round(size * scale) // 2 * 2) for size in (episode["width"], episode["height"]))
    font = resolve_font(channel, channel_dir)
    caption_font = (episode.get("captions") or {}).get("font") or (channel.get("captions") or {}).get("font")
    if caption_font:
        font = resolve_font(channel, channel_dir, caption_font)
    with new_package(target) as out, TemporaryDirectory() as temp:
        work = Path(temp)
        timeline, levels = prepare_audio(episode, episode_dir, work / "mix.wav", work, audio_library, channel=channel)
        if (work / "mix.wav").is_file():
            shutil.copyfile(work / "mix.wav", out / "mix.wav")
        if config.get("stems"):
            for stem in work.glob("stem-*.wav"):
                shutil.copyfile(stem, out / stem.name)
        visual_report = audit_visual(episode, library, timeline)
        if visual_report["issues"]:
            issues = []
            for item in visual_report["issues"][:5]:
                subjects = f" ({', '.join(item['ids'])})" if item["ids"] else ""
                issues.append(f"{item['shot']} frame {item['frame']}: {item['message']}{subjects}")
            raise ValueError("Visual checks failed. Run check-visual for the full report. " + " | ".join(issues))
        if backend == "python":
            encode(episode, timeline, levels, canvas, channel, font, episode_dir, out, work / "mix.wav", burn,
                   config=config, make_thumbnail=make_thumbnail, channel_base=channel_dir)
        else:
            from .browser import render_browser

            render_browser(backend, episode, channel, timeline, levels, canvas, font, episode_dir, channel_dir,
                           library, work, out, burn, preview, config=config)
        if has_three:
            timeline["scene_library"] = {"file": channel["scene_library"], "version": library[0]["version"]}
            for scene, resolved in zip(episode["scenes"], timeline["scenes"]):
                for shot, timing in zip(scene["shots"], resolved["shots"]):
                    if "three" in shot:
                        timing["three"] = shot["three"]
        report = verify(out / "video.mp4", timeline, canvas, episode.get("max_seconds", MAX_SECONDS))
        report.update({"renderer": backend, "preview": preview, "burned_captions": burn and bool(timeline["captions"]),
                       "audio": audio_summary(timeline)})
        if timeline["captions"] and config.get("captions", True):
            export_srt(out / "captions.srt", timeline["captions"], timeline["fps"])
        if visual_report["checked_shots"]:
            write_json(out / "visual-qa.json", visual_report)
        write_json(out / "timeline.json", timeline)
        write_script(out / "timed-script.md", episode, channel, timeline)
        if make_publishing:
            write_json(out / "publishing.json", {key: episode[key] for key in ("title", "description", "tags")})
            guide, warnings = publishing_guide(episode, channel, timeline, out, target)
            (out / "publishing.md").write_text(guide, encoding="utf-8")
            if warnings:
                report["publishing_warnings"] = warnings
        report["render"] = {key: config[key] for key in ("crf", "preset", "tune", "supersample", "motion_blur",
                                                         "audio_bitrate", "captions", "thumbnail", "publishing")
                            if key in config}
        write_json(out / "qa.json", report)
    return report
