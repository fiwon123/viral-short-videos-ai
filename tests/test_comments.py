"""Comments on a rendered frame: the store, the agent's look at the spot, the review server and the CLI."""

import json
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_episode_state import Layout, clip  # noqa: E402


def render(layout):
    """A 3 s preview at 24 fps with a timeline: shot A for the first second, B for the next two."""
    video = clip(layout.renders / "ep-preview" / "video.mp4")
    timeline = {"fps": 24, "scenes": [{"id": "S", "start": 0, "shots": [
        {"id": "A", "start": 0, "end": 24}, {"id": "B", "start": 24, "end": 72}]}]}
    (video.parent / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    layout.age_episode()
    return video


class StoreTests(unittest.TestCase):
    def test_a_comment_knows_its_frame_shot_and_progress(self):
        from studio.comments import add, load, store
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            video = render(layout)
            first = add(layout.episode, video, 1.5, 0.25, 0.75, "  The foot floats.  ")
            self.assertEqual((first["id"], first["frame"], first["shot"], first["shot_progress"]), ("c1", 36, "B", 0.25))
            self.assertEqual(first["text"], "The foot floats.")
            second = add(layout.episode, video, 0.2, 0.5, 0.5, "Hook too slow")
            self.assertEqual((second["id"], second["shot"]), ("c2", "A"))
            on_cut = add(layout.episode, video, 1.0, 0.5, 0.5, "The first frame of B")
            self.assertEqual((on_cut["frame"], on_cut["shot"], on_cut["shot_progress"]), (24, "B", 0.0))
            self.assertEqual(store(layout.episode), layout.folder / "review" / "comments.json")
            self.assertEqual([item["id"] for item in load(layout.episode)["comments"]], ["c1", "c2", "c3"])

    def test_bad_input_is_refused(self):
        from studio.comments import add
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            video = render(layout)
            for args in ((1.0, 0.5, 0.5, "  "), (1.0, 1.4, 0.5, "x"), (-1, 0.5, 0.5, "x"), ("soon", 0.5, 0.5, "x")):
                with self.assertRaises(ValueError, msg=args):
                    add(layout.episode, video, *args)

    def test_resolve_records_a_one_line_reply(self):
        from studio.comments import add, load, resolve
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            video = render(layout)
            add(layout.episode, video, 1.0, 0.5, 0.5, "Too dark")
            done = resolve(layout.episode, "c1", "Lifted the key light 20%.")
            self.assertEqual((done["status"], done["reply"]), ("done", "Lifted the key light 20%."))
            self.assertIn("resolved", load(layout.episode)["comments"][0])
            with self.assertRaises(ValueError):
                resolve(layout.episode, "c9", "x")
            with self.assertRaises(ValueError):
                resolve(layout.episode, "c1", " ")


class LookTests(unittest.TestCase):
    def test_the_agent_gets_the_frame_with_the_spot_ringed_and_a_close_up(self):
        from PIL import Image
        from studio.comments import SPOT, add, open_comments, resolve
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            video = render(layout)
            add(layout.episode, video, 2.0, 0.5, 0.5, "Ring here")
            add(layout.episode, video, 0.5, 0.2, 0.2, "Already fixed")
            resolve(layout.episode, "c2", "done")
            listed = open_comments(layout.episode)
            self.assertEqual([item["id"] for item in listed], ["c1"], "only open comments")
            item = listed[0]
            self.assertEqual(item["frame"], 48, "the frame number is kept")
            with Image.open(item["frame_image"]) as frame, Image.open(item["spot_image"]) as spot:
                self.assertEqual(frame.size, (90, 160))
                pixels = np.asarray(frame.convert("RGB")).astype(int)
                reds = np.all(pixels == (0xFF, 0x3B, 0x3B), axis=-1)  # the ring's exact colour (PNG is lossless)
                rows, cols = np.nonzero(reds)
                self.assertTrue(len(rows), "a red ring is drawn")
                self.assertAlmostEqual(cols.mean(), 45, delta=4)
                self.assertAlmostEqual(rows.mean(), 80, delta=4)
                self.assertEqual(spot.width, 2 * round(SPOT * 90))


class ServerTests(unittest.TestCase):
    def setUp(self):
        from studio.comments import server
        self.temp = TemporaryDirectory()
        self.layout = Layout(self.temp.name)
        self.video = render(self.layout)
        self.server = server(self.layout.episode, port=0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(self.base + path, data=body, headers=headers or {},
                                         method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def test_a_note_posted_from_the_page_is_stored_and_listed(self):
        status, _, body = self.request("/api/comments", {"time": 1.5, "x": 0.3, "y": 0.6, "text": "Foot floats"})
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["shot"], "B")
        status, _, body = self.request("/api/review")
        review = json.loads(body)
        self.assertEqual((review["episode"], review["render"], review["fps"]), ("ep", "ep-preview", 24))
        self.assertEqual([item["text"] for item in review["comments"]], ["Foot floats"])
        status, _, body = self.request("/api/comments", {"time": 1.5, "x": 3, "y": 0.6, "text": "off the picture"})
        self.assertEqual(status, 400)
        self.assertIn("inside the picture", json.loads(body)["error"])

    def test_the_video_is_served_in_ranges_so_the_page_can_seek(self):
        size = self.video.stat().st_size
        status, headers, body = self.request("/video.mp4", headers={"Range": "bytes=100-199"})
        self.assertEqual(status, 206)
        self.assertEqual(headers["Content-Range"], f"bytes 100-199/{size}")
        self.assertEqual(body, self.video.read_bytes()[100:200])
        status, headers, body = self.request("/video.mp4", headers={"Range": "bytes=-50"})
        self.assertEqual((status, len(body)), (206, 50))
        status, _, _ = self.request("/video.mp4", headers={"Range": f"bytes={size + 10}-"})
        self.assertEqual(status, 416)
        status, headers, body = self.request("/video.mp4")
        self.assertEqual((status, len(body), headers["Accept-Ranges"]), (200, size, "bytes"))

    def test_the_page_and_its_script_are_served(self):
        status, _, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Frame review", body)
        self.assertEqual(self.request("/review.js")[0], 200)
        self.assertEqual(self.request("/nothing")[0], 404)


class CliTests(unittest.TestCase):
    def test_list_and_done_through_the_command_line(self):
        from studio.comments import add
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            video = render(layout)
            add(layout.episode, video, 1.0, 0.5, 0.5, "Pip floats")
            command = [sys.executable, "-m", "studio.comments"]
            listed = subprocess.run(command + ["list", str(layout.episode)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(listed.returncode, 0, listed.stderr)
            item = json.loads(listed.stdout)[0]
            self.assertTrue(Path(item["spot_image"]).is_file())
            done = subprocess.run(command + ["done", str(layout.episode), "c1", "--reply", "Lifted 6 px."], cwd=ROOT,
                                  capture_output=True, text=True)
            self.assertEqual(json.loads(done.stdout)["status"], "done")
            self.assertEqual(json.loads(subprocess.run(command + ["list", str(layout.episode)], cwd=ROOT,
                                                       capture_output=True, text=True).stdout), [])
            missing = subprocess.run(command + ["done", str(layout.episode), "c7", "--reply", "x"], cwd=ROOT,
                                     capture_output=True, text=True)
            self.assertEqual(missing.returncode, 1)
            self.assertIn("No comment c7", missing.stderr)


if __name__ == "__main__":
    unittest.main()
