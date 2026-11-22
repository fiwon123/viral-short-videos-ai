"""Anchors: keys and cues timed to spoken words and the music's beat grid."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def episode(**extra):
    """Two shots: A has two lines, B has none. Shot-level extras merge into A."""
    shot_a = {"id": "A", "duration": 2.0, "speech": [
        {"speaker": "N", "text": "The duck lifts the *barbell* now.", "at": 0.2},
        {"speaker": "N", "text": "The barbell waves back.", "pause_after": 0.3}],
        "layers": [{"id": "bar", "kind": "rect", "x": 0.5, "y": 0.5, "keyframes": [
            {"at": 0, "scale": 1}, {"at_word": "barbell", "scale": 1.2}]}],
        "sfx": [{"cue": "pop", "at_word": {"word": "waves", "edge": "end"}}]}
    shot_a.update(extra)
    shot_b = {"id": "B", "duration": 3.0, "layers": []}
    return {"title": "t", "description": "d", "tags": ["x"], "width": 360, "height": 640, "fps": 24,
            "thumbnail": {"shot": "A", "text": "LIFT"}, "scenes": [{"id": "S", "purpose": "p", "shots": [shot_a, shot_b]}]}


class ClockTests(unittest.TestCase):
    def test_estimate_lays_lines_out_like_the_audio_pass(self):
        from studio.anchors import GAP, estimate_clock
        clock = estimate_clock(episode())
        first, second = clock["shots"]["A"]["lines"]
        self.assertAlmostEqual(first["start"], 0.2)
        self.assertAlmostEqual(second["start"], first["end"] + GAP)
        self.assertGreater(clock["shots"]["A"]["duration"], 2.0, "the speech overruns the authored 2 s")
        self.assertAlmostEqual(clock["shots"]["B"]["start"], clock["shots"]["A"]["duration"])

    def test_word_matching(self):
        from studio.anchors import estimate_clock, word_time
        timing = estimate_clock(episode())["shots"]["A"]
        words = [line["words"] for line in timing["lines"]]
        self.assertAlmostEqual(word_time("barbell", "A", timing), words[0][4]["start"])  # *emphasis* ignored
        self.assertAlmostEqual(word_time({"word": "barbell", "occurrence": 2}, "A", timing), words[1][1]["start"])
        self.assertAlmostEqual(word_time({"line": 1, "word": "barbell"}, "A", timing), words[1][1]["start"])
        self.assertAlmostEqual(word_time({"word": "barbell waves", "edge": "end"}, "A", timing), words[1][2]["end"])
        self.assertAlmostEqual(word_time({"word": "duck", "offset": -0.1}, "A", timing), words[0][1]["start"] - 0.1)
        self.assertAlmostEqual(word_time({"line": -1, "word": 0}, "A", timing), words[1][0]["start"])
        with self.assertRaisesRegex(ValueError, "no word 'kettlebell'"):
            word_time("kettlebell", "A", timing)
        with self.assertRaisesRegex(ValueError, "has 2 line"):
            word_time({"line": 2, "word": "the"}, "A", timing)
        with self.assertRaisesRegex(ValueError, "no speech"):
            word_time("x", "B", {"lines": []})

    def test_measured_clock_from_a_timeline(self):
        from studio.anchors import clock_from_timeline, word_time
        timeline = {"fps": 24, "captions": [
            {"words": [{"text": "Hi", "start": 30, "end": 36}, {"text": "there.", "start": 38, "end": 48}]}],
            "scenes": [{"shots": [{"id": "A", "start": 24, "end": 96, "speech": [{"start": 30, "end": 48}]}]}]}
        timing = clock_from_timeline({}, timeline)["shots"]["A"]
        self.assertEqual((timing["start"], timing["duration"]), (1.0, 3.0))
        self.assertAlmostEqual(word_time("there", "A", timing), (38 - 24) / 24)


class ResolveTests(unittest.TestCase):
    def test_keys_recipes_and_cues_get_numbers(self):
        from studio.anchors import estimate_clock, resolve, word_time
        source = episode(motion=None)
        source["scenes"][0]["shots"][0]["layers"][0]["motion"] = [{"recipe": "pop", "at_word": "now"}]
        source["scenes"][0]["shots"][0]["camera"] = {"keyframes": [{"at_word": "waves", "zoom": 1.2}]}
        source["scenes"][0]["shots"][0].pop("motion")
        timing = estimate_clock(source)["shots"]["A"]
        resolved = resolve(source)
        shot = resolved["scenes"][0]["shots"][0]
        key = shot["layers"][0]["keyframes"][1]
        self.assertNotIn("at_word", key)
        self.assertAlmostEqual(key["at"], word_time("barbell", "A", timing) / timing["duration"], places=5)
        # A recipe's t is seconds of the authored shot, which the renderer stretches to the resolved one.
        self.assertAlmostEqual(shot["layers"][0]["motion"][0]["t"],
                               word_time("now", "A", timing) / timing["duration"] * 2.0, places=5)
        self.assertAlmostEqual(shot["sfx"][0]["at"], word_time({"word": "waves", "edge": "end"}, "A", timing), places=3)
        self.assertIn("at", shot["camera"]["keyframes"][0])
        self.assertIn("at_word", source["scenes"][0]["shots"][0]["layers"][0]["keyframes"][1], "source untouched")

    def test_keys_are_reordered_after_resolution(self):
        from studio.anchors import resolve
        source = episode()
        source["scenes"][0]["shots"][0]["layers"][0]["keyframes"] = [
            {"at_word": "back", "opacity": 0}, {"at": 0.1, "opacity": 1}]
        keys = resolve(source)["scenes"][0]["shots"][0]["layers"][0]["keyframes"]
        self.assertEqual([key.get("opacity") for key in keys], [1, 0])

    def test_beats_and_snap(self):
        from studio.anchors import estimate_clock, resolve
        grid = {"bpm": 120, "offset": 0.1, "per_bar": 4}
        source = episode(snap="beat")
        source["scenes"][0]["shots"][1]["layers"] = [{"id": "dot", "kind": "ellipse", "x": 0.5, "y": 0.5,
                                                     "keyframes": [{"at_beat": {"bar": 3, "beat": 2}, "x": 0.6}]}]
        source["scenes"][0]["shots"][1]["sfx"] = [{"cue": "pop", "at_beat": 9}]
        resolved = resolve(source, None, grid)
        shot_a, shot_b = resolved["scenes"][0]["shots"]
        estimated = estimate_clock(source)["shots"]["A"]["duration"]
        self.assertGreaterEqual(shot_a["duration"], estimated)
        self.assertAlmostEqual((shot_a["duration"] - 0.1) / 0.5 % 1, 0, places=4, msg="A ends on a beat")
        self.assertNotIn("snap", shot_a)
        start_b = shot_a["duration"]
        self.assertAlmostEqual(shot_b["sfx"][0]["at"], 0.1 + 9 * 0.5 - start_b, places=3)
        bar_three_beat_two = 0.1 + (2 * 4 + 1) * 0.5
        self.assertAlmostEqual(shot_b["layers"][0]["keyframes"][0]["at"], (bar_three_beat_two - start_b) / 3.0,
                               places=5)
        bar = resolve(episode(snap="bar"), None, grid)["scenes"][0]["shots"][0]["duration"]
        self.assertAlmostEqual((bar - 0.1) / 2.0 % 1, 0, places=4, msg="snap: bar lands on a downbeat")

    def test_snap_holds_on_a_measured_clock(self):
        from studio.anchors import resolve
        grid = {"bpm": 120, "offset": 0.0}
        clock = {"fps": 24, "shots": {"A": {"start": 0, "duration": 4.0, "lines": [], "measured": True},
                                      "B": {"start": 4.0, "duration": 3.0, "lines": [], "measured": True}}}
        source = episode(snap="beat", speech=[], sfx=[])
        source["scenes"][0]["shots"][0]["layers"][0]["keyframes"] = [{"at": 0, "scale": 1}]
        shot = resolve(source, clock, grid)["scenes"][0]["shots"][0]
        self.assertEqual(shot["duration"], 4.0, "an end already on the beat is written into the authored length")

    def test_errors(self):
        from studio.anchors import resolve
        late = episode()
        late["scenes"][0]["shots"][1]["sfx"] = [{"cue": "pop", "at_beat": 400}]
        with self.assertRaisesRegex(ValueError, "outside the shot"):
            resolve(late, None, {"bpm": 120})
        with self.assertRaisesRegex(ValueError, "needs a tempo"):
            resolve(late, None, lambda: None)


class MusicGridTests(unittest.TestCase):
    def test_first_beat_and_tempo_of_a_click_track(self):
        from studio.music import RATE, first_beat, tempo
        samples = np.zeros(RATE * 12)
        for at in np.arange(0.3, 12, 0.5):  # 120 bpm, first click at 0.3 s
            start = int(at * RATE)
            samples[start:start + 400] = np.hanning(800)[400:] * 0.8
        bpm = tempo(samples)
        self.assertAlmostEqual(bpm, 120, delta=2)
        self.assertAlmostEqual(first_beat(samples, bpm), 0.3, delta=0.03)

    def test_a_syncopated_figure_names_the_beat_as_an_alternative(self):
        # A 3-3-2 kick at 125 bpm repeats every one and a half beats and reads as about 83 (seen on a real
        # music Short); the beat must at least be named beside it. A plain click track names nothing else.
        from studio.music import RATE, tempo, tempo_alternatives
        rng, beat = np.random.default_rng(0), 60 / 125
        samples = rng.normal(0, .003, RATE * 15)

        def hit(at, amp, tone):
            start = int(at * RATE)
            t = np.arange(min(int(.12 * RATE), len(samples) - start)) / RATE
            body = np.sin(2 * np.pi * 55 * t) if tone else rng.normal(0, 1, len(t))
            samples[start:start + len(t)] += amp * np.exp(-t / .03) * body

        for bar in range(8):
            origin = 0.2 + bar * 4 * beat
            for position, amp, tone in ((0, .8, 1), (1.5, .8, 1), (3, .6, 1), (1, .5, 0), (3, .5, 0)):
                hit(origin + position * beat, amp, tone)
            for half in range(8):
                hit(origin + half * beat / 2, .12, 0)
        bpm = tempo(samples)
        self.assertTrue(any(abs(value - 125) < 3 for value in [bpm, *tempo_alternatives(samples, bpm)]), bpm)
        clicks = np.zeros(RATE * 12)
        for at in np.arange(0.3, 12, 0.5):
            clicks[int(at * RATE):int(at * RATE) + 400] = np.hanning(800)[400:] * 0.8
        self.assertEqual(tempo_alternatives(clicks, tempo(clicks)), [])

    def test_music_grid_sources(self):
        from studio.anchors import music_grid
        self.assertEqual(music_grid({"preset": "pulse"})["bpm"], 120.0)
        self.assertEqual(music_grid({"file": "x.wav", "beat": {"bpm": 96}}), {"per_bar": 4, "offset": 0.0, "bpm": 96})
        self.assertIsNone(music_grid({"file": "missing.wav"}, "/nowhere"))
        self.assertIsNone(music_grid(None))


class CutsOnBeatTests(unittest.TestCase):
    def test_share_of_cuts_on_the_grid(self):
        from studio.film_qa import on_beat
        beat = {"bpm": 120, "offset": 0.1}
        self.assertEqual(on_beat([0.6, 1.1, 1.6, 2.0], beat, 24), 0.75)  # 2.0 is 0.1 s off
        self.assertIsNone(on_beat([], beat, 24))
        self.assertIsNone(on_beat([1.0], None, 24))

    def test_montage_with_off_beat_cuts_gets_a_note(self):
        from studio.film_qa import analyse
        rng = np.random.default_rng(3)
        scenes = [rng.integers(0, 255, (32, 18)).astype(np.float32) for _ in range(5)]
        stack = np.stack([scenes[min(4, index // 17)] + (index % 2) for index in range(85)])  # cuts every 17 frames
        notes, metrics, _ = analyse(stack, 24, route="montage", beat={"bpm": 120, "offset": 0.0})
        self.assertEqual(metrics["bpm"], 120)
        self.assertLess(metrics["cuts_on_beat"], 0.5)
        self.assertIn("off-beat", {note["kind"] for note in notes})

    def test_timeline_records_the_pulse_grid(self):
        from studio import audio
        from studio.core import SAMPLE_RATE

        def take(line, *args):
            return np.zeros(SAMPLE_RATE // 2, dtype=np.float32), "test", {}
        source = episode()
        source["music"] = {"preset": "pulse", "gain": 0.05}
        source["scenes"][0]["shots"][0].update({"speech": [], "sfx": []})
        source["scenes"][0]["shots"][0]["layers"][0]["keyframes"] = [{"at": 0, "scale": 1}]
        with TemporaryDirectory() as folder, mock.patch.object(audio, "spoken_take", take):
            timeline, _ = audio.prepare_audio(source, Path(folder), Path(folder) / "mix.wav", Path(folder))
        self.assertEqual(timeline["music"]["beat"]["bpm"], 120.0)


class PipelineTests(unittest.TestCase):
    def test_schema_and_prepare_episode(self):
        from studio.core import validate
        from studio.pipeline import prepare_episode
        source = validate(episode(), "episode")
        expanded = prepare_episode(source, {"name": "c"}, ROOT, style=False)
        key = expanded["scenes"][0]["shots"][0]["layers"][0]["keyframes"][1]
        self.assertTrue(0 < key["at"] < 1)
        broken = episode()
        broken["scenes"][0]["shots"][0]["layers"][0]["keyframes"][1].pop("at_word")
        with self.assertRaises(ValueError):
            validate(broken, "episode")
        with self.assertRaises(ValueError):
            validate(episode(snap="sometimes"), "episode")

    def test_measured_pass_uses_the_takes(self):
        from studio import audio
        from studio.core import SAMPLE_RATE
        from studio.pipeline import prepare_measured

        def take(line, *args):  # a 1.5 s take per line: longer than the text estimate for "Hi."
            return np.zeros(int(SAMPLE_RATE * 1.5), dtype=np.float32), "test", {}
        source = episode()
        shot = source["scenes"][0]["shots"][0]
        shot["speech"] = [{"speaker": "N", "text": "Hi.", "at": 0.2}, {"speaker": "N", "text": "Bye now."}]
        shot["layers"][0]["keyframes"][1] = {"at_word": "bye", "scale": 1.2}
        shot["sfx"] = [{"cue": "pop", "at_word": "bye"}]
        with TemporaryDirectory() as folder, mock.patch.object(audio, "spoken_take", take):
            expanded = prepare_measured(source, {"name": "c"}, ROOT, Path(folder))
        cue = expanded["scenes"][0]["shots"][0]["sfx"][0]
        # The second line starts after the first 1.5 s take plus the 0.18 s gap, not after an estimate.
        self.assertAlmostEqual(cue["at"], 0.2 + 1.5 + 0.18, delta=1 / 24 + 1e-6)


if __name__ == "__main__":
    unittest.main()
