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


def sounding(path, *, audio="sine=frequency=440:duration=3", filters="afade=t=out:st=2.2:d=0.8", silent=False):
    """A 3 s clip with a tone (faded out by default) or no audio at all."""
    path.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=90x160:rate=24:duration=3"]
    if not silent:
        command += ["-f", "lavfi", "-i", audio, "-af", filters, "-c:a", "aac", "-shortest"]
    subprocess.run(command + ["-pix_fmt", "yuv420p", str(path)], check=True)
    return path


class AudioGateTests(unittest.TestCase):
    """The delivered file's sound, through deliver() the way make deliver runs it."""

    def deliver(self, layout, video):
        from studio.episode_state import deliver

        def no_speech(where, folder):
            return {"verdict": "no-speech", "notes": []}
        return deliver(layout.episode, video=video, viral=viral_stub, narration=no_speech)

    def test_a_faded_tone_passes_and_the_facts_record_it(self):
        from studio.episode_state import audio_gate
        with TemporaryDirectory() as temp:
            video = sounding(Path(temp) / "v.mp4", filters="volume=0.3,afade=t=out:st=2.2:d=0.8")
            facts, notes = audio_gate(video, target=-14)
            self.assertTrue(facts["decodes"])
            self.assertGreater(facts["tail_under_loudest_db"], 12)
            self.assertNotIn("audio-cut", [note["kind"] for note in notes])
            self.assertNotIn("true-peak", [note["kind"] for note in notes])
            _, notes = audio_gate(video, target=facts["integrated_lufs"] + 5)
            self.assertIn("loudness", [note["kind"] for note in notes])

    def test_cut_clipping_and_silence_are_amber_in_delivery(self):
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            (layout.folder / "treatment.md").write_text(GOOD, encoding="utf-8")
            layout.age_episode()
            cases = (("ep-v1", dict(filters="volume=0.3"), "audio `audio-cut`"),
                     ("ep-v2", dict(audio="sine=frequency=440:duration=3", filters="volume=8,afade=t=out:st=2.2:d=0.8"),  # lavfi sine is 1/8 scale
                      "audio `true-peak`"),
                     ("ep-v3", dict(silent=True), "audio `silent`"))
            for name, options, expected in cases:
                video = sounding(layout.renders / name / "video.mp4", **options)
                report, code = self.deliver(layout, video)
                self.assertEqual(code, 0, report)
                self.assertIn(expected, report["amber"], name)
                self.assertIn("- Delivered sound:", (video.parent / "delivery.md").read_text(encoding="utf-8"))

    def test_a_damaged_file_is_refused(self):
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            (layout.folder / "treatment.md").write_text(GOOD, encoding="utf-8")
            layout.age_episode()
            video = sounding(layout.renders / "ep-v1" / "video.mp4")
            data = bytearray(video.read_bytes())
            data[len(data) // 3:len(data) // 3 + 3000] = b"\x00" * 1500 + b"\xff" * 1500
            video.write_bytes(bytes(data))
            report, code = self.deliver(layout, video)
            self.assertEqual(code, 2, report)
            self.assertTrue(any("does not decode cleanly" in reason for reason in report["reasons"]))
            self.assertFalse((video.parent / "delivery.md").exists())


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

    def cut_clip(self, path):
        """Two seconds: a test pattern, then a hard cut at 1.0 s to a different one, with a tone and a hit."""
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc2=size=90x160:rate=24:duration=1",
                        "-f", "lavfi", "-i", "smptebars=size=90x160:rate=24:duration=1",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                        "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-map", "2:a",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
        timeline = {"fps": 24, "captions": [], "scenes": [{"id": "S", "shots": [
            {"id": "A", "start": 0, "end": 24, "sfx": [{"start": 6, "sound": "pop", "gain": 0.5}]},
            {"id": "B", "start": 24, "end": 48, "sfx": [{"start": 30, "sound": "thud"}]}]}]}
        (path.parent / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
        return path

    def test_sound_and_continuity_reviewers_get_their_evidence(self):
        from PIL import Image
        from studio.episode_state import review_pack
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            (layout.folder / "treatment.md").write_text(GOOD + KEY_STILLS, encoding="utf-8")
            (layout.folder / "review").mkdir()
            (layout.folder / "review" / "director-ep-v1.md").write_text("P0: the hook\n", encoding="utf-8")
            layout.age_episode()
            video = self.cut_clip(layout.renders / "ep-preview" / "video.mp4")
            result = review_pack(layout.episode)
            pack = Path(result["pack"])
            self.assertEqual(set(result["lenses"]), {"director", "sound", "continuity"})
            for name in ("prompt.md", "prompt-sound.md", "prompt-continuity.md", "sound.png", "sound-cues.json",
                         "cuts.png"):
                self.assertTrue((pack / name).is_file(), name)
            cues = json.loads((pack / "sound-cues.json").read_text(encoding="utf-8"))
            self.assertEqual([(cue["at"], cue["sound"], cue["shot"]) for cue in cues],
                             [(0.25, "pop", "A"), (1.25, "thud", "B")])
            report = json.loads((video.parent / "film-qa" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["metrics"]["cuts"], [1.0])
            with Image.open(pack / "cuts.png") as sheet:  # one cut: one row of two frames
                self.assertGreaterEqual(sheet.width, 2 * 270)
                self.assertLess(sheet.height, 2 * (480 + 22))
                import numpy as np
                pixels = np.asarray(sheet.convert("L"), dtype=np.float32)[30:]
                before, after = pixels[:, :270], pixels[:, 282:552]
                self.assertGreater(float(np.abs(before - after).mean()), 20, "both sides of the cut, not one frame twice")
            sound = (pack / "prompt-sound.md").read_text(encoding="utf-8")
            continuity = (pack / "prompt-continuity.md").read_text(encoding="utf-8")
            self.assertIn("episodes/ep/review/sound-ep-preview.md", sound)
            self.assertIn("sound.png", sound)
            self.assertIn("episodes/ep/review/continuity-ep-preview.md", continuity)
            self.assertIn("cuts.png", continuity)
            for prompt in (sound, continuity, (pack / "prompt.md").read_text(encoding="utf-8")):
                self.assertIn("review/director-ep-v1.md", prompt)

    def test_cue_table_carries_film_qa_sync_rows(self):
        from studio.episode_state import cue_table
        with TemporaryDirectory() as temp:
            timeline = Path(temp) / "timeline.json"
            timeline.write_text(json.dumps({"fps": 24, "scenes": [{"id": "S", "shots": [
                {"id": "A", "sfx": [{"start": 6, "sound": "pop"}, {"start": 12, "source": "sfx/thud-2.wav"}]}]}]}),
                encoding="utf-8")
            report = {"metrics": {"sync": [{"cue": 0.5, "status": "late", "offset_ms": 210, "picture": 0.29}]}}
            cues = cue_table(timeline, report)
            self.assertEqual(cues[0]["sound"], "pop")
            self.assertNotIn("status", cues[0])
            self.assertEqual((cues[1]["sound"], cues[1]["status"], cues[1]["offset_ms"]), ("thud-2", "late", 210))

    def test_cli_lens_picks_one_reviewer(self):
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            layout.age_episode()
            self.cut_clip(layout.renders / "ep-preview" / "video.mp4")
            result = subprocess.run([sys.executable, "-m", "studio.episode_state", "review-pack", str(layout.episode),
                                     "--lens", "sound"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            pack = Path(json.loads(result.stdout)["pack"])
            self.assertTrue((pack / "prompt-sound.md").is_file())
            self.assertFalse((pack / "prompt-continuity.md").exists())
            self.assertFalse((pack / "prompt.md").exists())
            bad = subprocess.run([sys.executable, "-m", "studio.episode_state", "review-pack", str(layout.episode),
                                  "--lens", "lighting"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("Unknown lens lighting", bad.stderr)

    def test_no_fresh_render_is_an_error(self):
        from studio.episode_state import review_pack
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            with self.assertRaisesRegex(ValueError, "render one first"):
                review_pack(layout.episode)


if __name__ == "__main__":
    unittest.main()
