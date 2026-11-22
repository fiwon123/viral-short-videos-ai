"""Whisper word timing picks a model for the line's language (studio.wordtiming), with a fake model."""

import os
import sys
import types
import unittest
from unittest import mock

import numpy as np


class FakeModel:
    loaded = []

    def __init__(self, name, **options):
        self.name = name
        FakeModel.loaded.append((name, options))
        self.calls = []

    def transcribe(self, audio, **options):
        self.calls.append(options)
        words = [types.SimpleNamespace(word=f" {word}", start=index * 0.3, end=index * 0.3 + 0.25)
                 for index, word in enumerate(options["initial_prompt"].split())]
        return [types.SimpleNamespace(words=words)], None


class LanguageModelTests(unittest.TestCase):
    def setUp(self):
        from studio import wordtiming
        self.wordtiming = wordtiming
        wordtiming._MODEL.clear()
        FakeModel.loaded = []
        self.modules = mock.patch.dict(sys.modules, {"faster_whisper": types.SimpleNamespace(WhisperModel=FakeModel)})
        self.modules.start()
        self.env = mock.patch.dict(os.environ, {"STUDIO_WHISPER_MODEL": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.modules.stop()
        self.wordtiming._MODEL.clear()

    def test_portuguese_uses_the_multilingual_model_and_says_so(self):
        clip = np.zeros(16000, dtype=np.float32)
        words, method = self.wordtiming.measure(clip, 16000, "o gato chega", method="auto", language="pt-br")
        self.assertEqual(method, "whisper")
        self.assertEqual([word["text"] for word in words], ["o", "gato", "chega"])
        name, options = FakeModel.loaded[-1]
        self.assertEqual(name, "base")
        self.assertTrue(options["download_root"].endswith(os.path.join("audio-models", "whisper")))
        self.assertEqual(self.wordtiming._MODEL["base"].calls[-1]["language"], "pt")

    def test_english_keeps_the_english_model(self):
        self.wordtiming.measure(np.zeros(16000, dtype=np.float32), 16000, "the duck lifts", method="auto",
                                language="en-us")
        self.assertEqual(FakeModel.loaded[-1][0], "base.en")
        self.assertIsNone(self.wordtiming._MODEL["base.en"].calls[-1]["language"])
        self.assertEqual(self.wordtiming.model_name(None), "base.en")

    def test_the_environment_still_overrides(self):
        with mock.patch.dict(os.environ, {"STUDIO_WHISPER_MODEL": "small"}):
            self.assertEqual(self.wordtiming.model_name("pt-br"), "small")


if __name__ == "__main__":
    unittest.main()
