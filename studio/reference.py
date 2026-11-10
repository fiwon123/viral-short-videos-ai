"""Extract local reference evidence for a human or AI editorial breakdown."""

from io import BytesIO
import math
import re

from PIL import Image, ImageDraw

from .core import ffmpeg, new_package, probe, require, run, write_json
from .design import get_font


def reference(path, target, threshold):
    require("ffmpeg")
    require("ffprobe")
    data = probe(path)
    video = next((stream for stream in data["streams"] if stream["codec_type"] == "video"
                  and not stream.get("disposition", {}).get("attached_pic")), None)
    if not video:
        raise ValueError("Reference needs a video stream")
    duration = float(video.get("duration") or data["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Could not determine reference duration")

    # Metadata is sent to stdout so the candidates are available without parsing a progress log.
    filters = f"scale=320:-2,select=gt(scene\\,{threshold}),metadata=print:key=lavfi.scene_score:file=-"
    candidates = run("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
                     "-map", f"0:{video['index']}", "-an", "-vf", filters, "-f", "null", "-").decode()
    cuts = [float(value) for value in re.findall(r"pts_time:([-\d.eE+]+)", candidates)]
    cuts = [seconds for seconds in cuts if 0 < seconds < duration]
    uniform = [max(0, (duration - 0.15) * fraction / 10) for fraction in range(11)]
    selected = cuts if len(cuts) <= 13 else [cuts[i * (len(cuts) - 1) // 12] for i in range(13)]
    times = sorted({round(time, 3) for time in uniform + selected})
    with new_package(target) as out:
        frames = out / "frames"
        frames.mkdir()
        sheet = Image.new("RGB", (960, math.ceil(len(times) / 4) * 170), "#101828")
        draw = ImageDraw.Draw(sheet)
        thumbs = []
        for index, seconds in enumerate(times):
            raw = ffmpeg("-ss", str(seconds), "-i", str(path), "-map", f"0:{video['index']}", "-frames:v", "1",
                         "-vf", "scale=480:-2", "-c:v", "mjpeg", "-threads", "1", "-f", "image2pipe", "-")
            if not raw:
                continue
            filename = f"{index + 1:02d}.jpg"
            (frames / filename).write_bytes(raw)
            with Image.open(BytesIO(raw)) as image:
                image.thumbnail((232, 142), Image.Resampling.LANCZOS)
                x, y = index % 4 * 240, index // 4 * 170
                sheet.paste(image, (x + (240 - image.width) // 2, y + (142 - image.height) // 2))
            draw.text((x + 8, y + 145), f"{filename[:2]}  {seconds:.3f}s", font=get_font(None, 14), fill="white")
            thumbs.append({"file": f"frames/{filename}", "seek_seconds": seconds})
        sheet.save(out / "contact-sheet.jpg", quality=90)
        has_audio = any(stream["codec_type"] == "audio" for stream in data["streams"])
        if has_audio:
            ffmpeg("-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "16000", str(out / "audio.wav"))
        text_codecs = {"subrip", "ass", "ssa", "webvtt", "mov_text", "text"}
        captions = []
        for stream in data["streams"]:
            if stream["codec_type"] == "subtitle" and stream.get("codec_name") in text_codecs:
                name = f"source-captions-{stream['index']}.srt"
                ffmpeg("-i", str(path), "-map", f"0:{stream['index']}", str(out / name))
                captions.append(name)
        report = {"source": path.name, "duration_seconds": duration, "video": video,
                  "candidate_cuts_seconds": cuts, "candidate_cut_threshold": threshold,
                  "frames": thumbs, "audio_extracted": has_audio, "embedded_text_captions": captions,
                  "method": "Uniform and scene-change samples. Seek times and scene changes are candidates for review."}
        write_json(out / "reference.json", report)
    return {"frames": len(thumbs), "candidate_cuts": len(cuts), "audio_extracted": has_audio}
