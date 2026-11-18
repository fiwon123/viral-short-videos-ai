"""Video layers: frame keys from clip settings, decoding, and playback through a real still render."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def colour_clip(path, count=12, fps=12):
    """A clip whose frame i is a flat grey of value 20 * i (so a still shows which frame played)."""
    from studio.heroclip import write_clip
    write_clip([Image.new("RGB", (64, 112), (20 * index,) * 3) for index in range(count)], fps, path)


class FrameKeyTests(unittest.TestCase):
    def test_plays_once_then_holds(self):
        from studio.videolayer import frame_keys
        keys = frame_keys(2.0, 1.0, 12)
        self.assertEqual(keys[0], {"at": 0.0, "frame": 0})
        self.assertEqual(keys[-1]["frame"], 11)
        self.assertAlmostEqual(keys[-1]["at"], 11 / 12 / 2, places=4)
        self.assertEqual([key["frame"] for key in keys], list(range(12)))

    def test_loop_speed_and_start(self):
        from studio.videolayer import frame_keys
        looped = [key["frame"] for key in frame_keys(2.0, 1.0, 12, loop=True)]
        self.assertEqual(looped[:13], list(range(12)) + [0])
        fast = [key["frame"] for key in frame_keys(1.0, 2.0, 12, speed=2.0)]
        self.assertEqual(fast[:3], [0, 2, 4])
        late = frame_keys(1.0, 2.0, 12, start=1.5)
        self.assertEqual((late[0]["frame"], late[-1]["frame"]), (18, 23))


class VideoPlaybackTests(unittest.TestCase):
    def test_still_shows_the_frame_for_its_time(self):
        with TemporaryDirectory() as folder:
            folder = Path(folder)
            colour_clip(folder / "clip.mp4")
            (folder / "channel.json").write_text((ROOT / "tests" / "parity" / "channel.json").read_text())
            (folder / "episode.json").write_text(json.dumps({
                "title": "V", "description": "d", "tags": ["t"], "width": 270, "height": 480, "fps": 12,
                "thumbnail": {"shot": "A", "text": "T"}, "scenes": [{"id": "S", "purpose": "p", "shots": [
                    {"id": "A", "duration": 2.0, "layers": [{"id": "clip", "kind": "video", "file": "clip.mp4",
                                                             "x": 0.5, "y": 0.5, "width": 1, "height": 1}]}]}]}))
            for at, frame in ((0.5, 6), (1.5, 11)):
                out = folder / f"still-{at}.png"
                result = subprocess.run([sys.executable, str(ROOT / "video.py"), "still", str(folder / "episode.json"),
                                         "--channel", str(folder / "channel.json"), "--shot", "A", "--at", str(at),
                                         "--no-audio", "--renderer", "python", "--out", str(out)],
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                grey = Image.open(out).convert("L").getpixel((135, 240))
                self.assertAlmostEqual(grey, 20 * frame, delta=6, msg=f"at {at}s expected clip frame {frame}")
            self.assertTrue(list((folder / ".video-frames").glob("*/f00001.png")), "frames cached")

    def test_cover_fills_the_box_and_contain_fits_inside(self):
        from studio.videolayer import tiles
        with TemporaryDirectory() as folder:
            folder = Path(folder)
            colour_clip(folder / "clip.mp4", count=3)  # 64 x 112: narrower than 9:16
            layer = {"id": "c", "kind": "video", "file": "clip.mp4", "width": 1, "height": 1, "video_fps": 12}
            contain = tiles(layer, (270, 480), folder)
            cover = tiles({**layer, "fit": "cover"}, (270, 480), folder)
            self.assertEqual(cover[0].size, (270, 480))
            self.assertLess(contain[0].size[1], 480 + 1)
            self.assertNotEqual(contain[0].size, cover[0].size)

    def test_frames_are_lazy_and_bounded(self):
        from studio.videolayer import Frames
        with TemporaryDirectory() as folder:
            paths = []
            for index in range(10):
                path = Path(folder) / f"f{index:05d}.png"
                Image.new("RGB", (4, 4), (index, 0, 0)).save(path)
                paths.append(path)
            frames = Frames(paths, keep=3)
            self.assertEqual(len(frames), 10)
            self.assertEqual(frames[7].getpixel((0, 0))[0], 7)
            list(frames)
            self.assertLessEqual(len(frames.cache), 3)


if __name__ == "__main__":
    unittest.main()
