"""Narration check: what was heard against what was meant (studio.narration). No model is ever loaded here."""

import json
import os
import subprocess
import sys
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_episode_state import GOOD, Layout, clip, viral_stub  # noqa: E402


def kinds(notes):
    return {note["kind"]: note["severity"] for note in notes}


class TokenTests(unittest.TestCase):
    def test_numbers_letters_and_contractions_normalise(self):
        from studio.narration import tokens
        self.assertEqual(tokens("Ten *centimeters*.", "en-us"), ["10", "centimeters"])
        self.assertEqual(tokens("twenty-one", "en-us"), ["21"])
        self.assertEqual(tokens("O GTA sete chega", "pt-br"), tokens("o gta 7 chega", "pt-br"))
        self.assertEqual(tokens("Vai sair GTA6!", "pt-br"), ["vai", "sair", "gta", "6"])
        self.assertEqual(tokens("isso pros outros", "pt-br"), tokens("isso para os outros", "pt-br"))
        self.assertEqual(tokens("Carry-on rabbit", "en-us"), tokens("Carry on rabbit", "en-us"))
        self.assertEqual(tokens("猫が来た。", "ja"), ["猫", "が", "来", "た"])

    def test_numbers_spoken_as_several_words_become_one(self):
        from studio.narration import tokens
        for spoken, digits, lang in (("vinte e um gatos", "21 gatos", "pt-br"), ("twenty one dogs", "21 dogs", "en-us"),
                                     ("two hundred and five", "205", "en-us"), ("trente et un", "31", "fr-fr"),
                                     ("treinta y cinco", "35", "es"), ("cem e vinte", "120", "pt-br")):
            self.assertEqual(tokens(spoken, lang), tokens(digits, lang), spoken)
        self.assertEqual(tokens("dois e três", "pt-br"), ["2", "e", "3"], "only a round value takes a smaller one")
        for written, digits, lang in (("40 thousand", "40,000", "en-us"), ("two hundred thousand", "200000", "en-us"),
                                      ("vinte mil", "20.000", "pt-br")):
            self.assertEqual(tokens(written, lang), tokens(digits, lang), written)
        self.assertEqual(tokens("3.5", "en-us"), ["3", "5"], "a decimal is not a digit group")
        self.assertEqual(tokens("o gato e o cão", "pt-br"), ["o", "gato", "e", "o", "cão"])


class JudgeTests(unittest.TestCase):
    line = {"speaker": "N", "at": 1.0, "language": "en-us", "text": "The duck lifts the heavy barbell now."}

    def judge(self, heard, **extra):
        from studio.narration import judge
        return judge({**self.line, **extra}, heard)

    def test_a_faithful_line_has_no_notes(self):
        notes, row = self.judge("the duck lifts the heavy barbell now")
        self.assertEqual(notes, [])
        self.assertEqual(row["wer"], 0.0)

    def test_a_dropped_key_word_is_misread(self):
        notes, row = self.judge("the duck lifts the heavy now")
        self.assertEqual(kinds(notes), {"misread": "medium"})
        self.assertIn("barbell", row["missing"])

    def test_a_repeat_and_a_wrong_number_are_flagged(self):
        notes, _ = self.judge("the duck duck lifts the heavy barbell now")
        self.assertEqual(kinds(notes), {"repeat": "medium"})
        from studio.narration import judge
        notes, _ = judge({"speaker": "N", "at": 0, "language": "en-us", "text": "Seven dogs and three cats."},
                         "seven dogs and four cats")
        self.assertIn("number", kinds(notes))

    def test_the_respelling_for_the_voice_counts_as_correct(self):
        from studio.narration import judge
        line = {"speaker": "SSD", "at": 0, "language": "pt-br", "text": "Meu SSD pediu demissão.",
                "spoken_text": "Meu ésse ésse dê pediu demissão."}
        notes, row = judge(line, "Meu ésse ésse dê pediu demissão")
        self.assertEqual(notes, [])
        self.assertEqual(row["meant"], line["spoken_text"])

    def test_silence_and_mush_are_unheard_but_a_short_slip_is_not(self):
        notes, _ = self.judge("")
        self.assertEqual(kinds(notes), {"unheard": "high"})
        notes, _ = self.judge("a bird sings over the sea")
        self.assertEqual(kinds(notes)["unheard"], "high")
        from studio.narration import judge
        notes, _ = judge({"speaker": "H", "at": 0, "language": "pt-br", "text": "Só... um... minuto..."},
                         "Sol honges minuto.")
        self.assertEqual(kinds(notes), {"misread": "medium"}, "one word in three, and the article 'um' is no number")


def write_wav(path, seconds, rate=24000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        tone = 0.2 * np.sin(2 * np.pi * 220 * np.arange(int(seconds * rate)) / rate)
        handle.writeframes((tone * 32767).astype("<i2").tobytes())


class Heard:
    """A transcriber that answers in order and records the length of what it was given."""

    def __init__(self, *answers):
        self.answers, self.lengths, self.model = list(answers), [], "fake"

    def __call__(self, audio, language):
        self.lengths.append(len(audio) / 16000)
        return self.answers.pop(0)


def render(layout, lines):
    """A render folder with a timeline holding ``lines`` (dicts with start/end frames and optional take)."""
    folder = layout.renders / "ep-v1"
    folder.mkdir(parents=True, exist_ok=True)
    timeline = {"fps": 24, "scenes": [{"id": "S", "shots": [{"id": "A", "start": 0, "end": 96, "speech": lines}]}]}
    (folder / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    return folder


class CheckTests(unittest.TestCase):
    def test_each_line_is_heard_from_its_take_or_from_the_mix(self):
        from studio.narration import PAD, check
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            write_wav(layout.folder / ".audio-takes" / "a.wav", 1.5)
            folder = render(layout, [
                {"speaker": "N", "text": "It works nights.", "language": "en-us", "start": 0, "end": 36,
                 "take": ".audio-takes/a.wav"},
                {"speaker": "N", "text": "Carry on rabbit.", "language": "en-us", "start": 48, "end": 72,
                 "take": ".audio-takes/gone.wav"},
                {"speaker": "Bee", "text": "Bzz bzz.", "language": "en-us", "start": 80, "end": 90,
                 "narration": False}])
            write_wav(folder / "mix.wav", 4.0)
            heard = Heard("it works nights", "carry carry on rabbit")
            report = check(folder / "timeline.json", layout.folder, heard)
            self.assertEqual(len(report["lines"]), 2, "narration: false is left out")
            self.assertAlmostEqual(heard.lengths[0], 1.5, places=2)  # the take itself
            self.assertAlmostEqual(heard.lengths[1], 1.0 + 2 * PAD, places=2)  # the mix around the line
            self.assertEqual(report["verdict"], "amber")
            self.assertEqual(kinds(report["notes"]), {"repeat": "medium"})

    def test_without_a_recogniser_it_is_unchecked_not_green(self):
        from studio import narration
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            folder = render(layout, [{"speaker": "N", "text": "Hi.", "start": 0, "end": 10}])
            with mock.patch.object(narration, "whisper", return_value=None):
                report = narration.check(folder / "timeline.json", layout.folder)
            self.assertEqual(report["verdict"], "unchecked")
            empty = render(layout, [])
            self.assertEqual(narration.check(empty / "timeline.json", layout.folder)["verdict"], "no-speech")

    def test_asr_off_wins_even_when_faster_whisper_is_installed(self):
        import types
        from studio import narration
        loaded = []
        fake = types.SimpleNamespace(WhisperModel=lambda name, **options: loaded.append(name) or object())
        with mock.patch.dict(sys.modules, {"faster_whisper": fake}):
            with mock.patch.dict(os.environ, {"STUDIO_ASR": "off"}):
                self.assertIsNone(narration.whisper())
            self.assertEqual(loaded, [], "no model is loaded when ASR is off")
            with mock.patch.dict(os.environ, {"STUDIO_ASR": "", "STUDIO_ASR_MODEL": "tiny"}):
                self.assertIsNotNone(narration.whisper())
            self.assertEqual(loaded, ["tiny"])

    def test_cli_with_asr_off_writes_an_unchecked_report(self):
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            folder = render(layout, [{"speaker": "N", "text": "Hi.", "start": 0, "end": 10}])
            clip(folder / "video.mp4")
            result = subprocess.run([sys.executable, "-m", "studio.narration", str(layout.episode)], cwd=ROOT,
                                    capture_output=True, text=True, env={**os.environ, "STUDIO_ASR": "off"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["verdict"], "unchecked")
            self.assertEqual(json.loads((folder / "narration.json").read_text())["verdict"], "unchecked")
            # An audio pass (timeline and mix, no video yet) newer than the render is the one checked.
            import time
            time.sleep(0.05)
            audio = layout.renders / "ep-audio-v2"
            audio.mkdir()
            (audio / "timeline.json").write_text((folder / "timeline.json").read_text(), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "studio.narration", str(layout.episode)], cwd=ROOT,
                                    capture_output=True, text=True, env={**os.environ, "STUDIO_ASR": "off"})
            self.assertEqual(json.loads(result.stdout)["render"], "ep-audio-v2")


class DeliverTests(unittest.TestCase):
    def test_narration_goes_into_the_sealed_facts_and_the_amber_list(self):
        from studio.episode_state import deliver, verify

        def misread(where, folder):
            return {"verdict": "amber", "model": "base", "lines": [{}, {}],
                    "notes": [{"kind": "misread", "severity": "medium", "note": "N at 1.00 s: 40% differ."}]}

        def unchecked(where, folder):
            return {"verdict": "unchecked", "reason": "faster-whisper is not installed", "notes": []}
        with TemporaryDirectory() as temp:
            layout = Layout(temp)
            (layout.folder / "treatment.md").write_text(GOOD, encoding="utf-8")
            layout.age_episode()
            video = clip(layout.renders / "ep-v1" / "video.mp4")
            report, code = deliver(layout.episode, video=video, viral=viral_stub, narration=misread)
            self.assertEqual(code, 0, report)
            self.assertEqual(report["narration"], "amber")
            self.assertIn("narration `misread`", report["amber"])
            text = (video.parent / "delivery.md").read_text(encoding="utf-8")
            self.assertIn("- Narration: **amber** (2 line(s) heard back with faster-whisper base)", text)
            self.assertIn("medium `misread`: N at 1.00 s", text)
            self.assertTrue(verify(video.parent / "delivery.md")["ok"])
            deliver(layout.episode, video=video, viral=viral_stub, narration=unchecked)
            self.assertIn("- Narration: **not checked** (faster-whisper is not installed)",
                          (video.parent / "delivery.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
