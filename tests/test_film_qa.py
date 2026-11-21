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

    def test_a_cut_in_on_the_same_set_is_a_cut_but_a_fast_move_is_not(self):
        from studio.film_qa import analyse
        def framed(size, top=40):
            frame = np.full((128, 72), 100.0, dtype=np.float32)
            frame[top:top + size, 36 - size // 2:36 + size // 2] = 160  # one subject on a flat set
            return frame
        wide, medium = framed(24), framed(48, top=30)
        self.assertLess(float(np.abs(medium - wide).mean()), 18, "under the hard-cut threshold")
        notes, metrics, _ = analyse(np.stack(held(wide, 1) + held(medium, 1)), FPS)
        self.assertEqual(metrics["cuts"], [1.0])
        # The same change spread over a burst of frames is motion (a crash zoom), not a cut.
        burst = [framed(24 + step * 3, top=40 - step) for step in range(9)]
        _, metrics, _ = analyse(np.stack(held(wide, 1) + burst + held(burst[-1], 1)), FPS)
        self.assertEqual(metrics["cuts"], [])

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


def starts_moving(at_frame, total=96, seed=3):
    """A still textured frame where a bright square starts sliding at ``at_frame``."""
    base = scene(seed)
    frames = []
    for index in range(total):
        frame = base.copy()
        top = 10 + max(0, index - at_frame + 1) * 4  # frame ``at_frame`` is the first that differs
        frame[top:top + 20, 20:44] = 250
        frames.append(frame)
    return np.stack(frames)


def level_with(seconds, hits=(), swells=()):
    """A dB level track (5 ms steps) at the silence floor, with decaying hits and held swells."""
    from studio.film_qa import LEVEL_HOP
    level = np.full(round(seconds / LEVEL_HOP), -60.0)
    for at in hits:
        start = round(at / LEVEL_HOP)
        decay = np.arange(len(level) - start) * LEVEL_HOP
        level[start:] = np.maximum(level[start:], -8.0 - decay * 300)  # -38 dB 0.1 s later
    for at in swells:
        level[round(at / LEVEL_HOP):] = np.maximum(level[round(at / LEVEL_HOP):], -12.0)
    return level


def write_hits(path, times, seconds=0.6, rate=22050):
    """A WAV with a short decaying burst at each of ``times`` (seconds)."""
    import wave
    audio = np.zeros(int(seconds * rate))
    for at in times:
        start = int(at * rate)
        burst = np.random.default_rng(7).uniform(-1, 1, rate // 20) * np.exp(-np.arange(rate // 20) / (rate * 0.008))
        audio[start:start + len(burst)] += 0.7 * burst[:len(audio) - start]
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return path


class SoundSyncTests(unittest.TestCase):
    """Each sound effect against the picture event it lands on (film_qa.sync)."""

    def test_a_cue_finds_its_own_sample_and_a_rattle_is_not_judged(self):
        from studio.film_qa import attacks, cues_from_timeline
        with TemporaryDirectory() as temp:
            root = Path(temp) / "workspace" / "demo"
            (root / "channel").mkdir(parents=True)
            (root / "channel" / "channel.json").write_text(json.dumps({"audio_library": "audio/cast.json"}))
            write_hits(root / "channel" / "audio" / "sfx" / "thud-1.wav", [0.0])
            write_hits(root / "channel" / "audio" / "sfx" / "rattle-1.wav", [0.0, 0.09, 0.18])
            write_hits(root / "episodes" / "ep" / "audio" / "boing.wav", [0.0])
            render = root / "renders" / "ep-v1"
            render.mkdir(parents=True)
            (render / "timeline.json").write_text(json.dumps({"fps": 24, "scenes": [{"id": "S", "shots": [
                {"id": "A", "start": 0, "end": 96, "sfx": [
                    {"start": 24, "sound": "thud", "source": "sfx/thud-1.wav"},
                    {"start": 48, "sound": "rattle", "source": "sfx/rattle-1.wav"},
                    {"start": 60, "kind": "file", "source": "audio/boing.wav"},
                    {"start": 72, "sound": "gone", "source": "sfx/missing.wav"}]}]}]}))
            cues = cues_from_timeline(render / "timeline.json")
            self.assertEqual([Path(cue["sample"]).name if "sample" in cue else None for cue in cues],
                             ["thud-1.wav", "rattle-1.wav", "boing.wav", None])
            self.assertEqual(attacks(cues[0]["sample"]), 1)
            self.assertEqual(attacks(cues[1]["sample"]), 3)
            # Off the picture by 250 ms: a single hit is flagged, a rattle is not judged.
            for cue, expected in ((cues[0], "late"), (cues[1], "repeated")):
                _, rows = self.check(starts_moving(48), [{**cue, "at": 2.25}], level_with(4, hits=[2.25]))
                self.assertEqual(rows[0]["status"], expected, cue["sound"])

    def check(self, stack, cues, level, captions=()):
        from studio.film_qa import analyse
        notes, metrics, _ = analyse(stack, FPS, route="hybrid", cues=cues, level=level, captions=captions)
        return [note for note in notes if note["kind"].startswith("sound-")], metrics["sync"]

    def test_a_hit_on_the_frame_that_starts_moving_is_synced(self):
        notes, rows = self.check(starts_moving(48), [{"sound": "thud", "at": 2.0}], level_with(4, hits=[2.0]))
        self.assertEqual(notes, [])
        self.assertEqual(rows[0]["status"], "synced")
        self.assertAlmostEqual(rows[0]["picture"], 2.0, places=2)

    def test_late_and_early_hits_are_flagged_with_the_offset(self):
        late, rows = self.check(starts_moving(48), [{"sound": "thud", "at": 2.25}], level_with(4, hits=[2.25]))
        self.assertEqual([note["kind"] for note in late], ["sound-late"])
        self.assertEqual(late[0]["severity"], "medium")
        self.assertEqual(rows[0]["offset_ms"], 250)
        early, rows = self.check(starts_moving(48), [{"sound": "thud", "at": 1.875}], level_with(4, hits=[1.875]))
        self.assertEqual([note["kind"] for note in early], ["sound-early"])
        self.assertEqual(rows[0]["offset_ms"], -125)

    def test_within_tolerance_is_synced(self):
        # Two frames late (83 ms) is inside the 125 ms window; one frame early (42 ms) inside 45 ms.
        for at in (2.0 + 2 / FPS, 2.0 - 1 / FPS):
            notes, rows = self.check(starts_moving(48), [{"sound": "tap", "at": at}], level_with(4, hits=[at]))
            self.assertEqual(notes, [], at)
            self.assertEqual(rows[0]["status"], "synced", at)

    def test_a_hit_on_a_cut_is_on_the_cut(self):
        stack = np.stack(held(scene(1), 2) + held(scene(2), 2))
        notes, rows = self.check(stack, [{"sound": "hit", "at": 2.0}], level_with(4, hits=[2.0]))
        self.assertEqual(notes, [])
        self.assertEqual(rows[0]["status"], "on-cut")

    def test_a_sustained_sound_is_not_judged(self):
        notes, rows = self.check(starts_moving(48), [{"sound": "creak", "at": 2.3}], level_with(4, swells=[2.3]))
        self.assertEqual(notes, [])
        self.assertEqual(rows[0]["status"], "sustained")

    def test_a_caption_change_is_not_a_picture_event(self):
        notes, rows = self.check(starts_moving(48), [{"sound": "click", "at": 2.3}], level_with(4, hits=[2.3]),
                                 captions=[2.0])
        self.assertEqual(notes, [])
        self.assertEqual(rows[0]["status"], "unmatched")

    def test_an_event_belongs_to_the_nearest_cue(self):
        cues = [{"sound": "click", "at": 1.75}, {"sound": "pop", "at": 2.0}]
        notes, rows = self.check(starts_moving(48), cues, level_with(4, hits=[1.75, 2.0]))
        self.assertEqual(notes, [])
        self.assertEqual([row["status"] for row in rows], ["unmatched", "synced"])

    def test_cli_measures_the_rendered_audio_against_the_timeline(self):
        import wave
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            rate, seconds, hit = 22050, 4, 2.25  # the square starts moving at 2.0 s; the thud is 250 ms late
            audio = np.zeros(rate * seconds)
            start = int(hit * rate)
            burst = np.random.default_rng(5).uniform(-1, 1, rate // 5) * np.exp(-np.arange(rate // 5) / (rate * 0.02))
            audio[start:start + len(burst)] = 0.8 * burst
            with wave.open(str(folder / "hit.wav"), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(rate)
                handle.writeframes((audio * 32767).astype("<i2").tobytes())
            frames = starts_moving(48, total=FPS * seconds)
            rgb = np.repeat(np.repeat(np.repeat(frames[..., None], 3, axis=3), 2, axis=1), 2, axis=2)
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                            f"{rgb.shape[2]}x{rgb.shape[1]}", "-r", str(FPS), "-i", "-", "-i", str(folder / "hit.wav"),
                            "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                            str(folder / "video.mp4")], input=rgb.clip(0, 255).astype(np.uint8).tobytes(), check=True)
            timeline = {"fps": FPS, "captions": [], "scenes": [{"id": "S", "shots": [
                {"id": "A", "start": 0, "end": FPS * seconds,
                 "sfx": [{"start": round(hit * FPS), "sound": "thud", "source": "sfx/thud-1.wav"}]}]}]}
            (folder / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "studio.film_qa", str(folder / "video.mp4")], cwd=ROOT,
                                    capture_output=True, text=True)
            report = json.loads(result.stdout)
            notes = [note for note in report["notes"] if note["kind"].startswith("sound-")]
            self.assertEqual([note["kind"] for note in notes], ["sound-late"], report["metrics"]["sync"])
            self.assertEqual(notes[0]["shot"], "A")
            self.assertAlmostEqual(report["metrics"]["sync"][0]["picture"], 2.0, places=2)
            self.assertGreater(report["metrics"]["sync"][0]["offset_ms"], 200)


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
