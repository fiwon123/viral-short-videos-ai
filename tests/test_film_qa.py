"""Film QA: pixel energy, dead runs, frozen endings, cuts and blank frames, on synthetic and encoded clips."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FPS = 24


def scene(seed, height=128, width=72):
    return np.random.default_rng(seed).integers(40, 200, (height, width)).astype(np.float32)


def moving(seconds, seed=1, speed=3):
    """A textured background with a bright square sliding down and back, a few pixels a frame."""
    base = scene(seed)
    frames = []
    for index in range(round(seconds * FPS)):
        frame = base.copy()
        top = (index * speed) % (base.shape[0] - 20)
        frame[top:top + 20, 20:44] = 250
        frames.append(frame)
    return frames


def held(frame, seconds):
    return [frame.copy() for _ in range(round(seconds * FPS))]


def kinds(notes):
    return {note["kind"]: note["severity"] for note in notes}


class AnalyseTests(unittest.TestCase):
    def test_a_moving_film_with_cuts_is_green(self):
        from studio.film_qa import analyse, verdict
        stack = np.stack(moving(2.5, 1) + moving(2.5, 2, 5) + moving(2.5, 3, 7))
        notes, metrics, _ = analyse(stack, FPS)
        self.assertEqual(notes, [])
        self.assertEqual(verdict(notes), "green")
        self.assertEqual(metrics["cuts"], [2.5, 5.0])
        self.assertAlmostEqual(metrics["longest_framing"], 2.5)
        self.assertTrue(all(value >= 1.0 for value in metrics["energy"]))

    def test_a_frozen_ending_is_red(self):
        from studio.film_qa import analyse, verdict
        start = moving(3)
        stack = np.stack(start + held(start[-1], 2.0))
        notes, _, dead = analyse(stack, FPS, shots=[{"id": "A", "start": 0, "end": 5}])
        self.assertEqual(kinds(notes)["frozen-end"], "high")
        self.assertEqual(verdict(notes), "red")
        frozen = next(note for note in notes if note["kind"] == "frozen-end")
        self.assertEqual(frozen["shot"], "A")
        self.assertAlmostEqual(frozen["seconds"], 2.0, places=1)
        self.assertEqual(len(dead), 1)

    def test_dead_runs_are_graded_and_a_declared_stop_is_allowed(self):
        from studio.film_qa import analyse
        first = moving(2)
        short = np.stack(first + held(first[-1], 1.0) + moving(2, 4))
        self.assertEqual(kinds(analyse(short, FPS)[0]).get("dead"), "medium")
        long = np.stack(first + held(first[-1], 1.8) + moving(2, 4))
        self.assertEqual(kinds(analyse(long, FPS)[0]).get("dead"), "high")
        planned = analyse(long, FPS, stops=[(2.0, 3.8)])[0]
        self.assertNotIn("dead", kinds(planned))

    def test_one_framing_depends_on_the_route(self):
        from studio.film_qa import analyse
        stack = np.stack(moving(13))
        self.assertEqual(kinds(analyse(stack, FPS)[0])["one-framing"], "high")
        self.assertEqual(kinds(analyse(stack, FPS, route="continuous")[0])["one-framing"], "low")  # planned
        self.assertNotIn("one-framing", kinds(analyse(np.stack(moving(5)), FPS)[0]))

    def test_flat_film_and_no_burst(self):
        from studio.film_qa import analyse
        base = scene(5)
        drift = [np.roll(base, index // 12, axis=0) for index in range(10 * FPS)]  # a nudge twice a second
        found = kinds(analyse(np.stack(drift), FPS)[0])
        self.assertEqual(found["flat"], "high")
        self.assertEqual(found["no-burst"], "medium")
        self.assertEqual(found["slow-open"], "medium")

    def test_blank_frames_mid_film(self):
        from studio.film_qa import analyse
        black = np.zeros((128, 72), dtype=np.float32)
        stack = np.stack(moving(2) + [black.copy() for _ in range(12)] + moving(2, 6))
        blank = next(note for note in analyse(stack, FPS)[0] if note["kind"] == "blank")
        self.assertEqual(blank["severity"], "high")
        self.assertAlmostEqual(blank["at"], 2.0, places=1)

    def test_a_colour_only_cut_is_a_cut(self):
        from studio.film_qa import analyse
        # Two grounds of nearly the same brightness: a grey diff misses this cut, a colour diff does not.
        blue, plum = np.full((64, 36, 3), (32, 48, 64), np.float32), np.full((64, 36, 3), (64, 32, 48), np.float32)
        stack = np.stack([blue.copy() for _ in range(FPS)] + [plum.copy() for _ in range(FPS)])
        self.assertEqual(analyse(stack, FPS)[1]["cuts"], [1.0])
        self.assertEqual(analyse(stack.mean(axis=3), FPS)[1]["cuts"], [])

    def test_a_single_frame_pop_is_a_glitch_not_two_cuts(self):
        from studio.film_qa import analyse
        frames = moving(3)
        frames[36] = scene(9)  # one frame of another picture, then back
        notes, metrics, _ = analyse(np.stack(frames), FPS)
        self.assertEqual(kinds(notes).get("pop"), "high")
        self.assertEqual(metrics["pops"], [1.5])
        self.assertEqual(metrics["cuts"], [])

    def test_frame_zero_that_jumps_is_flagged(self):
        from studio.film_qa import analyse
        frames = moving(3)
        frames[0] = scene(11)  # the poster is a different picture
        notes, metrics, _ = analyse(np.stack(frames), FPS)
        self.assertEqual(kinds(notes).get("first-frame"), "high")
        self.assertTrue(metrics["first_frame_jump"])
        self.assertEqual(metrics["cuts"], [])
        clean = analyse(np.stack(moving(1) + moving(2, 4)), FPS)
        self.assertNotIn("pop", kinds(clean[0]))
        self.assertNotIn("first-frame", kinds(clean[0]))
        self.assertEqual(clean[1]["cuts"], [1.0], "a real cut stays a cut")

    def test_treatment_meta_and_stop_parsing(self):
        from studio.film_qa import parse_stops, read_meta
        self.assertEqual(parse_stops(["8-8.6", "10.0 to 10.5; 12–12.4s"]), [(8.0, 8.6), (10.0, 10.5), (12.0, 12.4)])
        self.assertEqual(parse_stops(["bad", "3-2"]), [])
        with TemporaryDirectory() as temp:
            path = Path(temp) / "treatment.md"
            path.write_text("# Treatment\n\n- **Route:** hybrid (spine plus one burst)\nStop: 8.2-8.7\n",
                            encoding="utf-8")
            self.assertEqual(read_meta(path), {"route": "hybrid", "stops": [(8.2, 8.7)]})
            self.assertEqual(read_meta(Path(temp) / "missing.md"), {"route": None, "stops": []})


class EncodedClipTests(unittest.TestCase):
    """Through ffmpeg and the CLI, the way make film-qa runs it."""

    def encode(self, path, filters):
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=180x320:rate=24:duration=2", "-vf", filters, "-pix_fmt", "yuv420p",
                        str(path)], check=True)

    def test_cli_writes_the_report_and_gates_a_frozen_ending(self):
        with TemporaryDirectory() as temp:
            video = Path(temp) / "video.mp4"
            self.encode(video, "tpad=stop_mode=clone:stop_duration=2")
            (Path(temp) / "treatment.md").write_text("Route: montage\n", encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "studio.film_qa", str(video), "--episode",
                                     str(Path(temp) / "episode.json")], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["verdict"], "red")
            self.assertIn("frozen-end", kinds(report["notes"]))
            self.assertEqual(report["metrics"]["route"], "montage")
            for key in ("report", "energy_chart", "sheet"):
                self.assertTrue(Path(report[key]).is_file(), key)
            saved = json.loads((Path(temp) / "film-qa" / "report.json").read_text())
            self.assertEqual(saved["energy_chart"], "film-qa/energy.png")

    def test_render_hook_never_raises(self):
        from studio.render import film_check
        with TemporaryDirectory() as temp:
            missing = film_check(Path(temp) / "nothing.mp4", Path(temp))
            self.assertEqual(missing["verdict"], "unchecked")
            video = Path(temp) / "video.mp4"
            self.encode(video, "null")
            result = film_check(video, Path(temp))
            self.assertIn(result["verdict"], ("green", "amber", "red"))
            self.assertEqual(result["report"], "film-qa/report.json")


class ViralPacingTests(unittest.TestCase):
    def test_a_long_camera_or_3d_shot_is_no_longer_exempt(self):
        from studio.viral_check import check

        def episode(duration, **extra):
            shot = {"id": "A", "duration": duration, "layers": [], "speech": [{"at": 0.1, "text": "Go."}], **extra}
            return {"title": "Go", "fps": 24, "thumbnail": {"text": "GO NOW"}, "scenes": [{"shots": [shot]}]}

        def pacing(item):
            return [note["severity"] for note in check(item, item)["notes"] if note["kind"] == "pacing"
                    and "one" in note["note"]]

        self.assertEqual(pacing(episode(14, camera={"preset": "push-in"})), ["medium"])
        self.assertEqual(pacing(episode(14, three={"scene": "garden"})), ["medium"])
        self.assertEqual(pacing(episode(8, camera={"preset": "push-in"})), ["low"])
        self.assertEqual(pacing(episode(5, camera={"preset": "push-in"})), [])


if __name__ == "__main__":
    unittest.main()
