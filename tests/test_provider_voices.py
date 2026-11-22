"""Voices that bring their own word timings: ElevenLabs (mocked, never called) and a command
engine that writes ``{words}``. Captions and lip sync follow the voice's timings."""

import base64
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import numpy as np

RATE = 44100
SILENCE = 0.5  # leading silence the studio trims off every take


def pcm(seconds=1.6):
    """Silence, then a tone: the trim moves every word earlier by about SILENCE."""
    t = np.arange(int(seconds * RATE)) / RATE
    tone = 0.4 * np.sin(2 * np.pi * 220 * t)
    tone[: int(SILENCE * RATE)] = 0
    return (tone * 32767).astype("<i2").tobytes()


def alignment(text, start=0.6, step=0.08):
    chars = list(text)
    starts = [round(start + index * step, 3) for index in range(len(chars))]
    return {"characters": chars, "character_start_times_seconds": starts,
            "character_end_times_seconds": [round(value + step, 3) for value in starts]}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class Opener:
    def __init__(self):
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        body = json.loads(request.data)
        return FakeResponse({"audio_base64": base64.b64encode(pcm()).decode(), "alignment": alignment(body["text"])})


PROFILE = {"engine": "elevenlabs", "voice_id": "VoiceAbc12345", "direction": "warm narrator",
           "voice_settings": {"stability": 0.4}}


class CharactersToWordsTests(unittest.TestCase):
    def test_a_word_runs_from_its_first_character_to_its_last(self):
        from studio.voices import words_from_characters
        words = words_from_characters(**{k: v for k, v in zip(("characters", "starts", "ends"),
                                                                alignment("Hi  there!").values())})
        self.assertEqual([word["text"] for word in words], ["Hi", "there!"])
        self.assertEqual(words[0]["start"], 0.6)
        self.assertEqual(words[0]["end"], 0.76)  # "i" starts at 0.68, ends 0.08 later
        self.assertEqual(words[1]["start"], 0.92)


class ElevenLabsTests(unittest.TestCase):
    def test_the_take_and_its_timings_are_cached_and_the_key_is_never_written(self):
        from studio.voices import ElevenLabsTakes, read_words
        opener = Opener()
        with TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "sk-secret-test"}):
            takes = ElevenLabsTakes(Path(folder), opener=opener)
            path, detail = takes.take("Hello there", PROFILE)
            again, _ = takes.take("Hello there", PROFILE)
            self.assertEqual(path, again)
            self.assertEqual(len(opener.requests), 1, "the second render reuses the cached take")
            request = opener.requests[0]
            self.assertIn("/text-to-speech/VoiceAbc12345/with-timestamps", request.full_url)
            self.assertEqual(request.get_header("Xi-api-key"), "sk-secret-test")
            self.assertEqual(json.loads(request.data)["voice_settings"], {"stability": 0.4})
            self.assertEqual([word["text"] for word in read_words(path)], ["Hello", "there"])
            self.assertEqual(detail["engine"], "elevenlabs")
            for written in Path(folder).rglob("*"):
                if written.is_file():
                    self.assertNotIn(b"sk-secret-test", written.read_bytes(), written.name)
            self.assertNotIn("sk-secret-test", json.dumps(detail))

    def test_without_the_key_a_new_line_is_a_clear_error_and_a_cached_one_still_plays(self):
        from studio.voices import ElevenLabsTakes
        with TemporaryDirectory() as folder:
            with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k"}):
                ElevenLabsTakes(Path(folder), opener=Opener()).take("Cached line", PROFILE)
            with mock.patch.dict(os.environ, {}, clear=True):
                ElevenLabsTakes(Path(folder), opener=Opener()).take("Cached line", PROFILE)
                with self.assertRaisesRegex(ValueError, "ELEVENLABS_API_KEY is not set"):
                    ElevenLabsTakes(Path(folder), opener=Opener()).take("A new line", PROFILE)

    def test_spoken_take_moves_the_timings_onto_the_trimmed_clip(self):
        from studio.audio import spoken_take
        from studio.voices import ElevenLabsTakes
        with TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k"}):
            hosted = ElevenLabsTakes(Path(folder), opener=Opener())
            line = {"speaker": "N", "text": "Hello there"}
            clip, source, detail = spoken_take(line, {}, Path(folder), Path(folder), PROFILE, None, hosted=hosted)
            words = detail["provider_words"]
            self.assertIn("ElevenLabs", source)
            # Trimmed to 50 ms before the tone at 0.5 s: "Hello" at 0.6 s lands near 0.15 s.
            self.assertAlmostEqual(words[0]["start"], 0.15, delta=0.02)
            _, _, slow = spoken_take({**line, "pace": 0.8}, {}, Path(folder), Path(folder), PROFILE, None,
                                     hosted=hosted)
            # At pace 0.8 the take is 1.25x longer, so are its timings (trim moves too); atempo smears
            # the onset a little, so allow one frame at 24 fps.
            self.assertAlmostEqual(slow["provider_words"][0]["start"], 0.6 * 1.25 - (SILENCE * 1.25 - 0.05),
                                   delta=1 / 24)
            self.assertGreater(slow["provider_words"][1]["start"] - slow["provider_words"][0]["start"],
                               1.2 * (words[1]["start"] - words[0]["start"]))


COMMAND_TTS = """
import json, math, sys, wave
out, words = sys.argv[1], sys.argv[2]
rate = 24000
frames = bytearray()
for i in range(int(1.6 * rate)):
    value = 0 if i < rate // 2 else int(12000 * math.sin(i / 8))
    frames += value.to_bytes(2, "little", signed=True)
w = wave.open(out, "wb"); w.setparams((1, 2, rate, 0, "NONE", "none")); w.writeframes(bytes(frames)); w.close()
json.dump([{"text": "Hello", "start": 0.6, "end": 0.9}, {"text": "there", "start": 1.0, "end": 1.5}], open(words, "w"))
"""


def episode(caption=None):
    line = {"speaker": "N", "text": "Hello there"}
    if caption:
        line["caption"] = caption
    return {"fps": 24, "scenes": [{"id": "S", "purpose": "test", "shots": [
        {"id": "A", "duration": 2.5, "speech": [line], "sfx": [], "layers": []}]}]}


class CommandWordsTests(unittest.TestCase):
    def prepared(self, folder, source):
        from studio import audio
        tts = Path(folder) / "tts.py"
        tts.write_text(COMMAND_TTS)
        library = {"version": 1, "voices": {"N": {"engine": "command", "direction": "test",
                                                   "command": [sys.executable, str(tts), "{out}", "{words}"]}}}
        with mock.patch.dict(os.environ, {"STUDIO_WORD_TIMING": "energy", "STUDIO_ASR": "off"}):
            timeline, _ = audio.prepare_audio(source, Path(folder), Path(folder) / "mix.wav", Path(folder),
                                              audio_library=(library, Path(folder) / "audio.json"))
        return timeline

    def test_captions_follow_the_timings_the_command_wrote(self):
        with TemporaryDirectory() as folder:
            timeline = self.prepared(folder, episode())
            cue = timeline["captions"][0]
            speech = timeline["scenes"][0]["shots"][0]["speech"][0]
            self.assertEqual(speech["word_timing"], "provider")
            self.assertNotIn("provider_words", speech)
            first, second = cue["words"]
            # Trimmed 0.45 s: "Hello" 0.6 -> 0.15 s (frame 4), "there" 1.0 -> 0.55 s (frame 13).
            self.assertEqual(first["start"] - cue["start"], 4)
            self.assertEqual(second["start"] - cue["start"], 13)
            self.assertTrue(list((Path(folder) / ".audio-takes").glob("*.words.json")))

    def test_a_different_caption_is_spread_over_the_spoken_span(self):
        with TemporaryDirectory() as folder:
            cue = self.prepared(folder, episode(caption="Hi there, friend"))["captions"][0]
            self.assertEqual([word["text"] for word in cue["words"]], ["Hi", "there,", "friend"])
            self.assertEqual(cue["words"][0]["start"] - cue["start"], 4)
            self.assertEqual(cue["words"][-1]["end"] - cue["start"], 25)  # "there" ends at 1.05 s


class SchemaTests(unittest.TestCase):
    def test_an_elevenlabs_voice_needs_an_id_and_no_kokoro_fields(self):
        from studio.core import validate
        good = {"version": 1, "voices": {"N": PROFILE}}
        validate(good, "audio_library")
        for bad in ({k: v for k, v in PROFILE.items() if k != "voice_id"}, {**PROFILE, "blend": {"af_heart": 100}}):
            with self.assertRaises(Exception):
                validate({"version": 1, "voices": {"N": bad}}, "audio_library")
        with self.assertRaises(Exception):
            validate({"version": 1, "voices": {"N": {"engine": "recorded", "direction": "d", "identity": "i",
                                                     "voice_id": "VoiceAbc12345"}}}, "audio_library")


if __name__ == "__main__":
    unittest.main()
