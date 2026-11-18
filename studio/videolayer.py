"""Video layers: play a clip (an AI hero clip, your own footage) inside a shot.

    {"id": "clip", "kind": "video", "file": "art/hero/a/clip.mp4", "x": 0.5, "y": 0.5,
     "width": 1, "height": 1, "fit": "cover", "clip_start": 0.0, "clip_speed": 1.0, "loop": false}

``fit`` is ``contain`` (default, the whole clip inside the box, like image layers) or
``cover`` (fill the box and crop the overflow, for full-frame clips).

The clip is muted; put its sound in ``sfx`` if you need it. ``expand`` turns the
clip settings into ``frame`` keys, one per change of frame (unless you key ``frame`` yourself): the clip
plays from ``clip_start`` at ``clip_speed`` and then holds its last frame, or
wraps when ``loop`` is true. ``tiles`` decodes the frames once with ffmpeg, at
the layer's pixel size and the episode's frame rate, into a ``.video-frames``
cache beside the episode (``make archive`` clears it), and returns a lazy
sequence, so a long clip is never held in memory whole. Both renderers read it
like a sprite sheet.
"""

import hashlib
import math
from collections import OrderedDict
from pathlib import Path

from PIL import Image

from .core import probe, run, scoped_asset

CACHE = ".video-frames"


def clip_seconds(path):
    data = probe(path)
    duration = float((data.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        duration = float(video.get("duration") or 0)
    if duration <= 0:
        raise ValueError(f"Could not read the length of {Path(path).name}")
    return duration


def frame_keys(shot_seconds, clip_length, fps, start=0.0, speed=1.0, loop=False):
    """``frame`` keys (progress 0-1) that play ``clip_length`` seconds of video at ``fps`` over the shot.

    Renderers hold ``frame`` between keys (it is a sprite index, not interpolated), so there
    is one key per episode frame where the index changes. The clip holds its last frame at
    the end, or wraps when ``loop`` is set.
    """
    count = max(1, math.floor(clip_length * fps + 1e-6))
    speed = max(1e-3, float(speed))
    keys, previous = [], None
    for step in range(max(1, math.ceil(shot_seconds * fps - 1e-9)) + 1):
        seconds = min(shot_seconds, step / fps)
        index = math.floor((start + seconds * speed) * fps + 1e-6)
        index = index % count if loop else min(count - 1, index)
        if index != previous:
            keys.append({"at": round(seconds / shot_seconds, 6), "frame": index})
            previous = index
    return keys


def expand(episode, base, channel_base=None):
    """Give every video layer its frame count, rate and (unless authored) frame keys."""
    fps = float(episode["fps"])
    for scene in episode.get("scenes", []):
        for shot in scene.get("shots", []):
            for layer in shot.get("layers", []):
                if layer.get("kind") != "video":
                    continue
                length = clip_seconds(scoped_asset(layer, base, channel_base))
                layer["video_fps"] = fps
                layer["video_frames"] = max(1, math.floor(length * fps + 1e-6))
                if not any("frame" in key for key in layer.get("keyframes", [])):
                    keys = frame_keys(float(shot["duration"]), length, fps, float(layer.get("clip_start", 0)),
                                      float(layer.get("clip_speed", 1)), bool(layer.get("loop")))
                    layer["keyframes"] = merge_keys(layer.get("keyframes", []), keys)
    return episode


def merge_keys(existing, frames):
    """Add frame values to authored keys at the same times, and new keys elsewhere."""
    by_at = {key["at"]: dict(key) for key in existing}
    for key in frames:
        if key["at"] in by_at:
            by_at[key["at"]]["frame"] = key["frame"]
        else:
            by_at[key["at"]] = key
    return [by_at[at] for at in sorted(by_at)]


class Frames:
    """A lazy, indexable list of decoded frames with a small cache."""

    def __init__(self, paths, keep=6):
        self.paths, self.keep, self.cache = list(paths), keep, OrderedDict()

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        path = self.paths[index]
        if path in self.cache:
            self.cache.move_to_end(path)
            return self.cache[path]
        with Image.open(path) as source:
            image = source.convert("RGBA")
        self.cache[path] = image
        if len(self.cache) > self.keep:
            self.cache.popitem(last=False)
        return image

    def __iter__(self):
        for index in range(len(self)):
            yield self[index]

    def __bool__(self):
        return bool(self.paths)


def tiles(layer, canvas, base, channel_base=None):
    """Decoded frames of a video layer, fitted inside the layer box (like a sprite sheet)."""
    source = scoped_asset(layer, base, channel_base)
    width = max(2, round(layer.get("width", 1.0) * canvas[0]))
    height = max(2, round(layer.get("height", 1.0) * canvas[1]))
    fps = float(layer.get("video_fps", 24))
    stat = source.stat()
    cover = layer.get("fit") == "cover"
    key = hashlib.sha256(f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{width}x{height}|{fps}|{cover}"
                         .encode()).hexdigest()[:16]
    folder = Path(base) / CACHE / key
    done = folder / "done"
    if not done.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.png"):
            old.unlink()
        run("ffmpeg", "-y", "-v", "error", "-i", str(source), "-an",
            "-vf", (f"fps={fps:g},scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
                    f"crop={width}:{height}") if cover else
            f"fps={fps:g},scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos",
            str(folder / "f%05d.png"))
        done.write_text("ok\n", encoding="utf-8")
    paths = sorted(folder.glob("f*.png"))
    if not paths:
        raise ValueError(f"No frames decoded from {layer['file']}")
    expected = layer.get("video_frames")
    if expected:
        paths = (paths + [paths[-1]] * expected)[:expected]  # ffmpeg can drop or add one frame at the end.
    return Frames(paths)
