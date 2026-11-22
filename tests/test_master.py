"""The master stage reaches the loudness target under the true-peak ceiling (studio.audio.master_audio)."""

import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np


def write(path, samples, rate=48000):
    stereo = np.stack([samples, samples], axis=1)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((np.clip(stereo, -1, 1) * 32767).astype("<i2").tobytes())
    return path


def sparse_hits(seconds=8.0, rate=48000):
    """Short decaying noise hits every 0.4 s over a faint bed: a wordless mix of thuds and pops (the real
    channel mixes that missed the target needed 1-6 dB more than linear normalisation gave)."""
    audio = np.random.default_rng(1).normal(0, 0.002, int(seconds * rate))
    for at in np.arange(0.2, seconds - 0.3, 0.4):
        start = int(at * rate)
        length = int(0.12 * rate)
        burst = np.random.default_rng(int(at * 10)).uniform(-1, 1, length) * np.exp(-np.arange(length) / (rate * 0.06))
        audio[start:start + length] += 0.9 * burst
    return audio


def dense_tone(seconds=8.0, rate=48000):
    t = np.arange(int(seconds * rate)) / rate
    return 0.1 * np.sin(2 * np.pi * 220 * t) + 0.05 * np.sin(2 * np.pi * 330 * t)


class MasterTests(unittest.TestCase):
    def master(self, samples):
        from studio.audio import master_audio, measure_loudness
        with TemporaryDirectory() as temp:
            path = write(Path(temp) / "mix.wav", samples)
            master_audio(path, {"loudness": -14, "true_peak": -1.5})
            found = measure_loudness(path)
            return float(found["integrated_lufs"]), float(found["true_peak_db"])

    def test_a_sparse_mix_reaches_the_target_under_the_ceiling(self):
        level, peak = self.master(sparse_hits())
        self.assertAlmostEqual(level, -14, delta=1.0)
        self.assertLessEqual(peak, -1.4)

    def test_a_dense_mix_reaches_the_target_too(self):
        level, peak = self.master(dense_tone())
        self.assertAlmostEqual(level, -14, delta=1.0)
        self.assertLessEqual(peak, -1.4)


if __name__ == "__main__":
    unittest.main()
