import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from studio import audio
from studio.voice_import import align, run, write_clip
from studio.voices import read_words


def word(text, start, end):
    return {"word": text, "start": start, "end": end}


def line(text, speaker="host", **extra):
    return {"text": text, "speaker": speaker, **extra}


def episode(*lines):
    return {"scenes": [{"shots": [{"id": "hook", "duration": 2, "speech": list(lines)}]}]}


class VoiceAlignmentTests(unittest.TestCase):
    def test_an_omitted_repeat_is_ambiguous(self):
        lines = [("A.1", line("Start now")), ("A.2", line("Ready set")), ("A.3", line("Start now"))]
        heard = [word("Start", .1, .3), word("now", .3, .5), word("Ready", .7, .9), word("set", 1, 1.2)]
        self.assertEqual([row["status"] for row in align(lines, heard, "en")], ["missing", "found", "missing"])

    def test_words_inserted_into_a_line_are_partial(self):
        heard = [word("Start", .1, .3), word("right", .3, .5), word("now", .5, .7)]
        row = align([("A.1", line("Start now"))], heard, "en")[0]
        self.assertEqual(row["coverage"], 1)
        self.assertEqual(row["status"], "partial")

    def test_uncertain_edges_and_middle_are_reported_differently(self):
        rows = align([("A.1", line("Minha ideia muda tudo")), ("A.2", line("Aqui vamos"))],
                     [word("Minha", .1, .3), word("ideia", .3, .5), word("tudo", .6, .8),
                      word("vamos", 1, 1.2)], "pt")
        self.assertEqual([row["status"] for row in rows], ["partial", "missing"])
        self.assertEqual([part["text"] for part in rows[0]["words"]], ["Minha", "ideia", "muda", "tudo"])
        self.assertEqual(rows[0]["words"][2], {"text": "muda", "start": .5, "end": .6})

    def test_inference_requires_one_line_between_confirmed_neighbors(self):
        lines = [("A.1", line("Start now")), ("A.2", line("Gustavo")), ("A.3", line("Then move"))]
        heard = [word("Start", .1, .3), word("now", .3, .5), word("August", .7, .9),
                 word("Then", 1, 1.2), word("move", 1.3, 1.5)]
        rows = align(lines, heard, "en")
        self.assertEqual(rows[1]["status"], "inferred")
        self.assertEqual(rows[1]["words"], [{"text": "Gustavo", "start": .7, "end": .9}])
        lines.insert(2, ("A.4", line("Another line")))
        self.assertEqual([row["status"] for row in align(lines, heard, "en")],
                         ["found", "missing", "missing", "found"])


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
class VoiceImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "episode.json"
        self.recording = self.root / "whole take.wav"
        t = np.arange(4 * audio.SAMPLE_RATE) / audio.SAMPLE_RATE
        write_clip(self.recording, (0.2 * np.sin(2 * np.pi * 210 * t)).astype(np.float32))

    def test_speaker_import_reaches_caption_and_mouth_timing(self):
        original = episode(line("Start now", words=[{"text": "old", "start": .1, "end": .2}]),
                           line("Try again", "guest"), line("Then move"))
        self.manifest.write_text(json.dumps(original))
        heard = [word("Start", .2, .4), word("now", .45, .65), word("Then", 1.8, 2.1), word("move", 2.2, 2.45)]
        result = run(self.manifest, self.recording, "host", transcribe=lambda *_: (heard, "en"))
        self.assertEqual(result["found"], 2)
        revised = json.loads(self.manifest.read_text())
        shot = revised["scenes"][0]["shots"][0]
        first, middle, last = shot["speech"]
        self.assertEqual(middle, original["scenes"][0]["shots"][0]["speech"][1])
        self.assertNotIn("words", first)
        self.assertNotEqual(first["file"], last["file"])
        self.assertEqual(read_words(self.root / first["file"])[0]["start"], .06)
        clean_shot = {**shot, "speech": [first, last]}
        _, takes, _ = audio.plan_shot(clean_shot, 24, {}, self.root, self.root, {}, None, None)
        _, _, timed, clip, _, _ = takes[0]
        self.assertEqual(audio.measured_words(timed, "Start now", clip, self.root)[0]["method"], "provider")
        with patch("studio.lipsync.visemes", return_value=[]) as visemes:
            audio.line_visemes(timed, clip, 24, self.root, {"host": {"rest", "open"}}, "en")
        self.assertEqual(visemes.call_args.args[1], timed["_provider_words"])

    def test_respelled_line_uses_asr_words_and_warns_about_acting(self):
        self.manifest.write_text(json.dumps(episode(line("Read SQL", spoken_text="Read sequel", pitch=2, pace=.9))))
        heard = [word("Read", .2, .4), word("sequel", .45, .65)]
        result = run(self.manifest, self.recording, transcribe=lambda *_: (heard, "en"))
        row = result["lines"][0]
        self.assertEqual(row["status"], "found")
        self.assertIn("pace or pitch", row["warning"])
        self.assertEqual([item["text"] for item in read_words(self.root / row["file"])], ["Read", "sequel"])

    def test_missing_line_keeps_previous_take(self):
        self.manifest.write_text(json.dumps(episode(line("Start now", file="previous.wav"))))
        original = self.manifest.read_bytes()
        result = run(self.manifest, self.recording, transcribe=lambda *_: ([], "en"))
        self.assertEqual(result["missing"], 1)
        self.assertEqual(self.manifest.read_bytes(), original)
        self.assertTrue((self.root / "voice-import.json").is_file())

    def test_manifest_edit_during_recognition_is_preserved(self):
        self.manifest.write_text(json.dumps(episode(line("Start now"))))

        def transcribe(*_):
            self.manifest.write_text("new edit")
            return [word("Start", .2, .4), word("now", .5, .7)], "en"

        with self.assertRaisesRegex(ValueError, "episode changed"):
            run(self.manifest, self.recording, transcribe=transcribe)
        self.assertEqual(self.manifest.read_text(), "new edit")
        self.assertFalse((self.root / "audio").exists())

    @unittest.skipUnless(shutil.which("make"), "make is required")
    def test_make_import_reports_uncertainty_and_publishes_timed_takes(self):
        # Substitute only the recognizer; run Make, CLI parsing, decoding and
        # publishing as the user does, including filenames containing spaces.
        (self.root / "faster_whisper.py").write_text(
            "from types import SimpleNamespace as S\n"
            "class WhisperModel:\n"
            "    def __init__(self, *args, **kwargs): pass\n"
            "    def transcribe(self, *args, **kwargs):\n"
            "        words = [S(word='Start', start=.2, end=.4), S(word='now', start=.45, end=.65)]\n"
            "        return iter([S(words=words)]), S(language='en')\n"
        )
        environment = {**os.environ, "STUDIO_ASR": "on", "PYTHONPATH": str(self.root)}
        project = Path(__file__).resolve().parents[1]
        for text, expected_code, expected_status in (("Start now", 0, "found"), ("Start right now", 1, "partial")):
            with self.subTest(text=text):
                self.manifest.write_text(json.dumps(episode(line(text), line("Guest line", "guest"))))
                result = subprocess.run(
                    ["make", "--no-print-directory", "voice-import", f"PYTHON={sys.executable}",
                     f"EPISODE={self.manifest}", f"FILE={self.recording}", "SPEAKER=host", "LANGUAGE=en"],
                    cwd=project, env=environment, text=True, capture_output=True,
                )
                # Make maps any recipe error to exit 2.
                self.assertEqual(result.returncode, 0 if expected_code == 0 else 2, result.stderr)
                report = json.loads((self.root / "voice-import.json").read_text())
                self.assertEqual(report["lines"][0]["status"], expected_status)
                self.assertIn(expected_status, result.stdout)
                take = self.root / report["lines"][0]["file"]
                self.assertTrue(take.is_file())
                self.assertEqual(len(read_words(take)), len(text.split()))
                saved = json.loads(self.manifest.read_text())["scenes"][0]["shots"][0]["speech"]
                self.assertEqual(saved[1], line("Guest line", "guest"))
