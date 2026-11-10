"""Encode video, verify output, and package an episode for review."""

from fractions import Fraction
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from .audio import prepare_audio
from .core import MAX_SECONDS, new_package, probe, require, run, write_json
from .design import Composition, draw_caption, resolve_font, thumbnail, transition_frame


def encoder(width, height, fps):
    entries = run("ffmpeg", "-hide_banner", "-encoders").decode()
    encoders = {fields[1] for line in entries.splitlines() if len(fields := line.split()) > 2}
    if "libx264" in encoders:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19"]
    if "libopenh264" in encoders:
        bitrate = max(1_000_000, round(width * height * fps * 0.15))
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
    path.write_text("".join(blocks), encoding="utf-8")


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
            if transition := resolved.get("transition"):
                rows.append(f"- {transition['type']} from {clock(transition['start'], fps)} to {clock(transition['end'], fps)}.")
            elif start:
                rows.append("- Cut at the shot boundary.")
            for layer in shot["layers"]:
                stage = (f"- {layer['id']} ({layer['kind']}, {layer.get('plane', 'foreground')}) at ({layer['x']}, {layer['y']}), "
                         f"box {layer.get('width', 0.55)} × {layer.get('height', 0.2)}, "
                         f"scale {layer.get('scale', 1)}, rotation {layer.get('rotate', 0)}°, "
                         f"opacity {layer.get('opacity', 1)}.")
                if "file" in layer:
                    stage += f" {layer.get('asset_scope', 'episode').capitalize()} asset `{layer['file']}`."
                else:
                    fill = layer.get("fill", "foreground")
                    stage += f" Fill {channel['palette'].get(fill, fill)}."
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
                rows.append(f"- {clock(cue['start'], fps)}–{clock(cue['end'], fps)} · {cue['speaker']}: {cue['text']} [{cue['source']}]")
            for cue in resolved["sfx"]:
                rows.append(f"- {clock(cue['start'], fps)}–{clock(cue['end'], fps)} · SFX {cue['source']} at gain {cue['gain']}.")
            rows.append("")
    rows.extend(["## Captions", ""])
    for cue in timeline["captions"]:
        text = cue["text"].replace("\n", " / ")
        rows.append(f"- {clock(cue['start'], fps)}–{clock(cue['end'], fps)} · {text}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_frames(pipe, episode, timeline, levels, canvas, channel, font, base, out, burn):
    previous = None
    cues = iter(timeline["captions"])
    cue = next(cues, None)
    for scene, scene_timing in zip(episode["scenes"], timeline["scenes"]):
        for shot, timing in zip(scene["shots"], scene_timing["shots"]):
            composition = Composition(shot, canvas, channel, font, base)
            frames = timing["end"] - timing["start"]
            transition = timing.get("transition")
            count = transition["end"] - transition["start"] if transition else 0
            cover = episode["thumbnail"]
            cover_frame = round(cover.get("at", 0.5) * (frames - 1)) if cover["shot"] == shot["id"] else None
            for frame in range(frames):
                progress = frame / max(1, frames - 1)
                speaking = {speaker: float(samples[frame - a])
                            for a, b, speaker, samples in levels[shot["id"]] if a <= frame < b}
                visual = composition.frame(progress, speaking)
                if frame == cover_frame:
                    clean = composition.frame(progress, {}, cover.get("hide_layers", []))
                    thumbnail(clean, cover["text"], channel, font).save(out / "thumbnail.png")
                image = visual
                if count and frame < count:
                    image = transition_frame(previous, visual, transition["type"], (frame + 1) / count)
                absolute = timing["start"] + frame
                while cue and absolute >= cue["end"]:
                    cue = next(cues, None)
                if burn and cue and cue["start"] <= absolute < cue["end"]:
                    image = image.copy()
                    draw_caption(image, cue["text"], channel, font)
                pipe.write(image.tobytes())
            previous = visual


def encode(episode, timeline, levels, canvas, channel, font, base, out, mix, burn):
    w, h = canvas
    fps = timeline["fps"]
    options = encoder(w, h, fps)
    dest = out / "video.mp4"
    with TemporaryDirectory() as temp:
        with (Path(temp) / "ffmpeg.log").open("w+b") as log:
            process = subprocess.Popen(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
                 "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0", "-i", str(mix),
                 *options, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                 "-movflags", "+faststart", str(dest)], stdin=subprocess.PIPE, stderr=log,
            )
            try:
                with process.stdin as pipe:
                    write_frames(pipe, episode, timeline, levels, canvas, channel, font, base, out, burn)
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


def render(episode, channel, episode_dir, channel_dir, target, preview, burn, *, backend="python", library=None):
    shots = [shot for scene in episode["scenes"] for shot in scene["shots"]]
    has_three = any("three" in shot for shot in shots)
    if backend == "python":
        if has_three:
            raise ValueError("Three.js shots require --renderer remotion or --renderer hyperframes")
        if any(layer["kind"] == "svg" for shot in shots for layer in shot["layers"]):
            raise ValueError("SVG layers require --renderer hyperframes or --renderer remotion")
    require("ffmpeg")
    require("ffprobe")
    canvas = episode["width"], episode["height"]
    if preview:
        canvas = tuple(max(2, size // 4 * 2) for size in canvas)
    font = resolve_font(channel, channel_dir)
    with new_package(target) as out, TemporaryDirectory() as temp:
        work = Path(temp)
        timeline, levels = prepare_audio(episode, episode_dir, work / "mix.wav", work)
        if backend == "python":
            encode(episode, timeline, levels, canvas, channel, font, episode_dir, out, work / "mix.wav", burn)
        else:
            from .browser import render_browser

            render_browser(backend, episode, channel, timeline, levels, canvas, font, episode_dir, channel_dir,
                           library, work, out, burn, preview)
        if has_three:
            timeline["scene_library"] = {"file": channel["scene_library"], "version": library[0]["version"]}
            for scene, resolved in zip(episode["scenes"], timeline["scenes"]):
                for shot, timing in zip(scene["shots"], resolved["shots"]):
                    if "three" in shot:
                        timing["three"] = shot["three"]
        report = verify(out / "video.mp4", timeline, canvas, episode.get("max_seconds", MAX_SECONDS))
        report.update({"renderer": backend, "preview": preview, "burned_captions": burn and bool(timeline["captions"])})
        if timeline["captions"]:
            export_srt(out / "captions.srt", timeline["captions"], timeline["fps"])
        write_json(out / "timeline.json", timeline)
        write_json(out / "qa.json", report)
        write_script(out / "timed-script.md", episode, channel, timeline)
        write_json(out / "publishing.json", {key: episode[key] for key in ("title", "description", "tags")})
    return report
