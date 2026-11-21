"""Episode state from evidence, the delivery gate, and the review pack."""

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_treatment import GOOD  # noqa: E402  a treatment that lints green

KEY_STILLS = "\n## Key stills\n\n- Hook: 0.5 s (A)\n- Hero: 1.5 s (D)\n"


def clip(path, *, frozen=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    filters = "tpad=stop_mode=clone:stop_duration=3" if frozen else "null"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=90x160:rate=24:duration=3", "-vf", filters, "-pix_fmt", "yuv420p", str(path)],
                   check=True)
    return path


def ok_validator(where):
    return True, "validated (stub)"


def viral_stub(where, video):
    return {"score": 81, "notes": [{"severity": "low", "kind": "loop", "note": "Loop match 60%."}]}


class Layout:
    def __init__(self, temp):
        self.root = Path(temp) / "workspace" / "demo"
        self.folder = self.root / "episodes" / "ep"
        self.folder.mkdir(parents=True)
        self.episode = self.folder / "episode.json"
        self.episode.write_text(json.dumps({"scenes": []}), encoding="utf-8")
        self.renders = self.root / "renders"

    def age_episode(self, seconds=60):
        """Make episode.json older than anything written after it."""
        past = time.time() - seconds
        os.utime(self.episode, (past, past))

    def render(self, name, verdict="green", frozen=False):
        video = clip(self.renders / name / "video.mp4", frozen=frozen)
        (video.parent / "film-qa").mkdir(exist_ok=True)
        (video.parent / "film-qa" / "report.json").write_text(json.dumps({"verdict": verdict, "notes": []}))
        return video


def state(layout):
    from studio.episode_state import state as compute
    return compute(layout.episode, validator=ok_validator)


class StateTests(unittest.TestCase):
    def test_each_piece_of_evidence_advances_the_stage(self):
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            first = state(layout)
            self.assertEqual(first["state"], "concept")
            self.assertIn("make channel-memory SLUG=demo EPISODE=ep", first["next"])
            (layout.folder / "treatment.md").write_text(GOOD, encoding="utf-8")
            self.assertEqual(state(layout)["state"], "built")
            stills = layout.renders / "ep-stills"
            stills.mkdir(parents=True)
            (stills / "A-0.1.png").write_bytes(b"png")
            self.assertEqual(state(layout)["state"], "stills")
            layout.age_episode()
            layout.render("ep-preview")
            self.assertEqual(state(layout)["state"], "previewed")
            (layout.folder / "review").mkdir()
            (layout.folder / "review" / "director.md").write_text("P0: none.\n")
            self.assertEqual(state(layout)["state"], "reviewed")
            layout.render("ep-v1", verdict="red")
            red = state(layout)
            self.assertEqual(red["state"], "reviewed")
            self.assertIn("film-qa is red", red["missing"][0])
            layout.render("ep-v2", verdict="amber")
            self.assertEqual(state(layout)["state"], "mastered")

    def test_stale_renders_do_not_count(self):
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            (layout.folder / "treatment.md").write_text(GOOD, encoding="utf-8")
            (layout.renders / "ep-stills").mkdir(parents=True)
            (layout.renders / "ep-stills" / "a.png").write_bytes(b"png")
            layout.render("ep-preview")
            future = time.time() + 60
            os.utime(layout.episode, (future, future))  # edited after the preview was rendered
            result = state(layout)
            self.assertEqual(result["state"], "stills")
            self.assertTrue(any("stale: ep-preview" in line for line in result["missing"]))

    def test_write_puts_the_stage_on_the_status_line(self):
        from studio.episode_state import write_status
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            notes = layout.folder / "NOTES.md"
            notes.write_text("# Ep\n\nStatus: delivered (claimed)\n\n## Next step\n", encoding="utf-8")
            write_status(layout.episode, {"state": "built"})
            text = notes.read_text(encoding="utf-8")
            self.assertIn("Status: built (from evidence", text)
            self.assertNotIn("claimed", text)
            self.assertIn("## Next step", text)


class DeliverTests(unittest.TestCase):
    def test_gate_writes_sealed_facts_and_verify_catches_edits(self):
        from studio.episode_state import deliver, state as compute, verify
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            (layout.folder / "treatment.md").write_text(GOOD, encoding="utf-8")
            layout.age_episode()
            video = clip(layout.renders / "ep-v1" / "video.mp4")
            report, code = deliver(layout.episode, video=video, viral=viral_stub)
            self.assertEqual(code, 0, report)
            delivery = video.parent / "delivery.md"
            text = delivery.read_text(encoding="utf-8")
            self.assertIn("Film QA: **", text)
            self.assertIn("Viral check: **81**/100", text)
            self.assertIn("Director's notes: **none**", text)
            self.assertIn("say why the director pass was skipped", text)
            self.assertTrue(verify(delivery)["ok"])
            (layout.renders / "ep-stills").mkdir()
            (layout.renders / "ep-stills" / "a.png").write_bytes(b"png")
            clip(layout.renders / "ep-preview" / "video.mp4")
            (layout.folder / "review").mkdir()
            (layout.folder / "review" / "director.md").write_text("ok\n")
            from studio.film_qa import run as film_qa
            film_qa(layout.renders / "ep-preview" / "video.mp4", images=False)
            self.assertEqual(compute(layout.episode, validator=ok_validator)["state"], "delivered")
            # The maker's notes survive a second delivery of the same render.
            delivery.write_text(text + "\nThe loop is intentional.\n", encoding="utf-8")
            deliver(layout.episode, video=video, viral=viral_stub)
            self.assertIn("The loop is intentional.", delivery.read_text(encoding="utf-8"))
            self.assertTrue(verify(delivery)["ok"])
            delivery.write_text(delivery.read_text(encoding="utf-8").replace("**81**", "**99**"), encoding="utf-8")
            self.assertIn("edited", verify(delivery)["reason"])
            deliver(layout.episode, video=video, viral=viral_stub)
            with open(video, "ab") as handle:
                handle.write(b"\0")
            self.assertIn("changed after delivery", verify(delivery)["reason"])

    def test_red_film_qa_is_refused(self):
        from studio.episode_state import deliver
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            (layout.folder / "treatment.md").write_text(GOOD, encoding="utf-8")
            video = clip(layout.renders / "ep-v1" / "video.mp4", frozen=True)
            report, code = deliver(layout.episode, video=video, viral=viral_stub)
            self.assertEqual(code, 2)
            self.assertFalse(report["delivered"])
            self.assertTrue(any("frozen" in reason for reason in report["reasons"]))
            self.assertFalse((video.parent / "delivery.md").exists())

    def test_verify_cli_exit_code(self):
        with TemporaryDirectory() as temp:
            fake = Path(temp) / "delivery.md"
            fake.write_text("# Delivery\n\nall good, trust me\n", encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "studio.episode_state", "verify", str(fake)], cwd=ROOT,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)["ok"])


class ReviewPackTests(unittest.TestCase):
    def test_pack_holds_what_a_cold_reviewer_needs(self):
        from studio.episode_state import key_stills, review_pack
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            treatment = layout.folder / "treatment.md"
            treatment.write_text(GOOD + KEY_STILLS, encoding="utf-8")
            self.assertEqual(key_stills(treatment), [("hook", 0.5), ("hero", 1.5)])
            layout.age_episode()
            clip(layout.renders / "ep-preview" / "video.mp4")
            result = review_pack(layout.episode)
            pack = Path(result["pack"])
            for name in ("sheet.png", "energy.png", "report.json", "treatment.md", "still-hook-0.5s.png",
                         "still-hero-1.5s.png", "prompt.md"):
                self.assertTrue((pack / name).is_file(), name)
            prompt = (pack / "prompt.md").read_text(encoding="utf-8")
            self.assertIn("episodes/ep/review/director-ep-preview.md", prompt)
            self.assertIn("Picture first", prompt)

    def test_no_fresh_render_is_an_error(self):
        from studio.episode_state import review_pack
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            with self.assertRaisesRegex(ValueError, "render one first"):
                review_pack(layout.episode)


if __name__ == "__main__":
    unittest.main()
