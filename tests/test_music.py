"""Fitting a library track to an episode: bar-line joins, the track's own opening and ending, exact length."""

import json
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

BEAT = {"bpm": 120, "offset": 0.25}  # 2 s bars in 4/4, first beat at 0.25 s
BAR = 2.0


def track(seconds=31.0, rate=None, loud_from=None):
    """A sine track: a 330 Hz intro (two bars), a 220 Hz middle, and a 440 Hz ending that rings out."""
    from studio.music import RATE
    rate = rate or RATE
    t = np.arange(int(seconds * rate)) / rate
    samples = 0.3 * np.sin(2 * np.pi * 220 * t)
    intro = t < 4.25
    samples[intro] = 0.3 * np.sin(2 * np.pi * 330 * t[intro])
    ending = t >= seconds - 2.75
    samples[ending] = 0.3 * np.sin(2 * np.pi * 440 * t[ending]) * np.exp(-(t[ending] - t[ending][0]) / 1.0)
    if loud_from is not None:
        loud = (t >= loud_from) & ~ending
        samples[loud] *= 3.0
        samples[~loud & ~ending] *= 0.1
    return samples


def on_bar(seconds):
    position = (seconds - BEAT["offset"]) / BAR
    return abs(position - round(position)) < 1e-3


def length(plan):
    return sum(end - start for start, end in plan["segments"])


class ArrangeTests(unittest.TestCase):
    def test_a_long_track_keeps_its_opening_and_ending_and_cuts_bars_out_of_the_middle(self):
        from studio.music import arrange
        plan = arrange(track(), 14.0, BEAT)
        self.assertAlmostEqual(length(plan), 14.0, places=3)
        self.assertEqual(plan["segments"][0][0], 0.0, "the first downbeat is kept: the ring-out paid the remainder")
        self.assertEqual(len(plan["joins"]), 1)
        self.assertTrue(on_bar(plan["joins"][0]["from"]) and on_bar(plan["joins"][0]["to"]))
        self.assertGreater(plan["segments"][-1][1], 29.5, "the track's own ending plays")
        self.assertGreater(plan["end_trim"], 0)
        self.assertNotIn("warning", plan)

    def test_the_head_pays_what_the_ring_out_cannot_and_the_beat_follows(self):
        from studio.music import arrange
        plan = arrange(track(), 13.37, BEAT)
        self.assertAlmostEqual(length(plan), 13.37, places=3)
        self.assertAlmostEqual(plan["segments"][0][0], plan["head_trim"], places=3)
        self.assertGreater(plan["head_trim"], 0)
        # A beat at 0.25 s in the source is at 0.25 - head_trim in the film (modulo one beat).
        self.assertAlmostEqual(plan["offset"], (0.25 - plan["head_trim"]) % 0.5, places=3)

    def test_a_short_track_repeats_whole_bars_before_its_ending(self):
        from studio.music import arrange
        plan = arrange(track(), 45.5, BEAT)
        self.assertAlmostEqual(length(plan), 45.5, places=3)
        self.assertGreaterEqual(len(plan["segments"]), 3)
        for join in plan["joins"]:
            self.assertTrue(on_bar(join["from"]) and on_bar(join["to"]), join)
            self.assertLess(join["to"], join["from"], "a repeat jumps back")
        self.assertGreater(plan["segments"][-1][1], 29.5)

    def test_no_beat_or_no_loop_leaves_the_track_alone(self):
        from studio.music import arrange
        self.assertIsNone(arrange(track(), 14.0, None))
        self.assertIsNone(arrange(track(), 45.5, BEAT, loop=False))

    def test_a_join_across_a_loudness_change_is_flagged(self):
        from studio.music import arrange
        plan = arrange(track(loud_from=16.25), 10.0, BEAT)
        self.assertAlmostEqual(length(plan), 10.0, places=3)
        self.assertGreater(plan["joins"][0]["step_db"], 6)
        self.assertIn("warning", plan)


def write_wav(path, samples, rate):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


def dominant(samples, rate):
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    return float(np.fft.rfftfreq(len(samples), 1 / rate)[int(np.argmax(spectrum))])


class FitThroughThePipelineTests(unittest.TestCase):
    """From the episode's mood request to the mixed WAV, the way render runs it."""

    def channel(self, folder):
        from studio.music import RATE
        music = Path(folder) / "audio" / "music"
        music.mkdir(parents=True)
        write_wav(music / "song.wav", track(), RATE)
        index = {"tracks": [{"file": "audio/music/song.wav", "title": "Song", "moods": ["funny"], "energy": "medium",
                             "bpm": 120, "first_beat": 0.25, "duration": 31.0}]}
        (music / "index.json").write_text(json.dumps(index), encoding="utf-8")
        return {"music_library": "audio/music/index.json"}

    def episode(self, **music):
        return {"title": "t", "description": "d", "tags": ["x"], "width": 360, "height": 640, "fps": 24,
                "thumbnail": {"shot": "A", "text": "T"}, "music": {"mood": "funny", "gain": 0.5, **music},
                "scenes": [{"id": "S", "purpose": "p", "shots": [
                    {"id": "A", "duration": 14.0, "speech": [], "sfx": [], "layers": []}]}]}

    def test_the_mix_opens_on_the_intro_and_ends_on_the_tracks_own_ending(self):
        from studio import audio
        from studio.core import SAMPLE_RATE, validate
        from studio.music import expand
        with TemporaryDirectory() as folder:
            channel = self.channel(folder)
            expanded = expand(validate(self.episode(), "episode"), channel, folder)
            plan = expanded["music"]["arrangement"]
            self.assertAlmostEqual(length(plan), 14.0, places=3)
            self.assertEqual(expanded["music"]["beat"]["offset"], plan["offset"])
            timeline, _ = audio.prepare_audio(expanded, Path(folder), Path(folder) / "mix.wav", Path(folder))
            self.assertEqual(timeline["music"]["arrangement"]["segments"], plan["segments"])
            mix = audio.read_audio(Path(folder) / "mix.wav")
            self.assertAlmostEqual(len(mix) / SAMPLE_RATE, 14.0, delta=0.05)
            opening = mix[int(0.5 * SAMPLE_RATE):int(1.5 * SAMPLE_RATE)]
            ending = mix[int(12.6 * SAMPLE_RATE):int(13.4 * SAMPLE_RATE)]
            self.assertAlmostEqual(dominant(opening, SAMPLE_RATE), 330, delta=5)
            self.assertAlmostEqual(dominant(ending, SAMPLE_RATE), 440, delta=5)

    def test_fit_false_keeps_the_old_cut(self):
        from studio.core import validate
        from studio.music import expand
        with TemporaryDirectory() as folder:
            expanded = expand(validate(self.episode(fit=False), "episode"), self.channel(folder), folder)
            self.assertNotIn("arrangement", expanded["music"])

    def test_film_qa_reports_a_loud_join(self):
        from studio.film_qa import music_notes
        with TemporaryDirectory() as folder:
            path = Path(folder) / "timeline.json"
            path.write_text(json.dumps({"music": {"arrangement": {
                "warning": "listen", "joins": [{"from": 6.25, "to": 22.25, "step_db": 19.5}]}}}), encoding="utf-8")
            notes = music_notes(path)
            self.assertEqual([note["kind"] for note in notes], ["music-join"])
            self.assertEqual(notes[0]["severity"], "medium")
            path.write_text(json.dumps({"music": {"arrangement": {"joins": []}}}), encoding="utf-8")
            self.assertEqual(music_notes(path), [])


if __name__ == "__main__":
    unittest.main()
