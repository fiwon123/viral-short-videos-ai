"""Render voice takes once and reuse the exact WAV on subsequent renders.

Engines: Kokoro (local), any local TTS ``command``, and ElevenLabs (hosted). A take may come
with word timings from the voice itself, saved beside it as ``<take>.words.json``
(``[{"text", "start", "end"}]`` in seconds); captions and lip sync then use them instead of
listening to the take.
"""

from functools import cached_property
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import os
from tempfile import TemporaryDirectory
import wave

import numpy as np

MODEL_DIR = Path(__file__).resolve().parents[1] / "audio-models"


def checksum(path):
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class KokoroTakes:
    def __init__(self, episode_dir):
        self.cache = episode_dir / ".audio-takes"
        self.model = Path(os.environ.get("STUDIO_KOKORO_MODEL", MODEL_DIR / "kokoro-v1.0.int8.onnx"))
        self.voices = Path(os.environ.get("STUDIO_KOKORO_VOICES", MODEL_DIR / "voices-v1.0.bin"))

    @cached_property
    def model_identity(self):
        if not self.model.is_file() or not self.voices.is_file():
            raise ValueError("Install the local Kokoro model and voice files as described in the audio guide")
        try:
            package = version("kokoro-onnx")
        except ImportError as error:
            raise ValueError("Install requirements-voice.txt with a Python 3.10–3.13 environment") from error
        return {"runtime": package, "model_sha256": checksum(self.model), "voices_sha256": checksum(self.voices)}

    @cached_property
    def engine(self):
        # Keep model I/O local and load the session only when a take needs synthesis.
        from kokoro_onnx import Kokoro
        from onnxruntime import disable_telemetry_events

        disable_telemetry_events()
        return Kokoro(str(self.model), str(self.voices))

    def take(self, text, profile):
        parts = sorted(profile["blend"].items())
        speed = profile.get("speed", 1.0)
        settings = {"engine": "kokoro", **self.model_identity, "blend": dict(parts),
                    "speed": speed, "language": profile["language"]}
        payload = json.dumps([text, settings], ensure_ascii=False, sort_keys=True).encode()
        name = sha256(payload).hexdigest() + ".wav"
        target = self.cache / name
        if not target.is_file():
            self.cache.mkdir(exist_ok=True)
            weights = sum(weight for _, weight in parts)
            try:
                blend = sum(self.engine.get_voice_style(voice) * (weight / weights) for voice, weight in parts)
                language = "cmn" if profile["language"] == "zh" else profile["language"]
                samples, rate = self.engine.create(text, voice=blend, speed=speed, lang=language)
            except KeyError as error:
                raise ValueError(f"Kokoro voice is missing from the configured voice file: {error}") from error
            if not len(samples) or not np.all(np.isfinite(samples)) or np.max(np.abs(samples)) < 0.002:
                raise ValueError("Kokoro did not produce an audible take")
            pcm = np.rint(np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
            with TemporaryDirectory(prefix=".take-", dir=self.cache) as folder:
                staged = Path(folder) / "take.wav"
                with wave.open(str(staged), "wb") as output:
                    output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
                    output.writeframes(pcm)
                try:
                    os.link(staged, target)
                except FileExistsError:
                    pass
        return target, {**settings, "take": str(target.relative_to(self.cache.parent))}


def words_file(take):
    """Where a take's provider word timings live."""
    return Path(take).with_suffix(".words.json")


def read_words(take):
    """The provider word timings saved beside a take, or None."""
    path = words_file(take)
    if not path.is_file():
        return None
    try:
        words = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    valid = [item for item in words if isinstance(item, dict) and {"text", "start", "end"} <= set(item)]
    return valid or None


def words_from_characters(characters, starts, ends):
    """Word timings from a per-character alignment (ElevenLabs and similar): a word runs from its first
    character's start to its last character's end; whitespace separates words."""
    words, current, first, last = [], "", None, None
    for char, start, end in zip(characters, starts, ends):
        if char.isspace():
            if current:
                words.append({"text": current, "start": round(first, 3), "end": round(last, 3)})
            current, first, last = "", None, None
            continue
        if not current:
            first = float(start)
        current += char
        last = float(end)
    if current:
        words.append({"text": current, "start": round(first, 3), "end": round(last, 3)})
    return words


class CommandTakes:
    """Any local TTS program as a voice engine, cached like Kokoro takes.

    Profile: ``{"engine": "command", "command": ["piper", "--model", "voice.onnx",
    "--output_file", "{out}"], "input": "stdin"}``. ``{out}`` is the WAV to write and
    ``{text}`` (with ``"input": "arg"``) is the line. Works with Piper, eSpeak,
    Coqui, F5-TTS, Chatterbox or any script that writes a WAV. A program that knows when
    each word is spoken (a hosted voice's timestamps, a forced aligner) writes them as JSON
    ``[{"text", "start", "end"}]`` to ``{words}``; captions and lip sync then follow them.
    """

    def __init__(self, episode_dir):
        self.cache = episode_dir / ".audio-takes"

    def take(self, text, profile):
        import subprocess
        command = [str(part) for part in profile["command"]]
        settings = {"engine": "command", "command": command, "input": profile.get("input", "stdin"),
                    "speed": profile.get("speed", 1.0)}
        name = sha256(json.dumps([text, settings], ensure_ascii=False, sort_keys=True).encode()).hexdigest() + ".wav"
        target = self.cache / name
        if not target.is_file():
            self.cache.mkdir(exist_ok=True)
            with TemporaryDirectory(prefix=".take-", dir=self.cache) as folder:
                staged = Path(folder) / "take.wav"
                timings = Path(folder) / "take.words.json"
                args = [part.replace("{out}", str(staged)).replace("{text}", text).replace("{words}", str(timings))
                        for part in command]
                stdin = text.encode("utf-8") if settings["input"] == "stdin" else None
                try:
                    result = subprocess.run(args, input=stdin, capture_output=True, timeout=600)
                except FileNotFoundError as error:
                    raise ValueError(f"Voice command not found: {command[0]}. Install it or fix the cast profile.") from error
                if result.returncode or not staged.is_file():
                    detail = result.stderr.decode("utf-8", errors="replace")[-800:]
                    raise ValueError(f"Voice command failed ({command[0]}): {detail}")
                if timings.is_file():
                    os.replace(timings, words_file(target))
                try:
                    os.link(staged, target)
                except FileExistsError:
                    pass
        return target, {**settings, "take": str(target.relative_to(self.cache.parent))}


ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=pcm_44100"


class ElevenLabsTakes:
    """ElevenLabs voices, with the word timings the API returns alongside the audio.

    Profile: ``{"engine": "elevenlabs", "voice_id": "...", "model": "eleven_multilingual_v2",
    "voice_settings": {"stability": 0.4, "similarity_boost": 0.8, "style": 0.3}}``. The key comes
    only from ``ELEVENLABS_API_KEY`` and is never written anywhere. Takes are cached by text and
    settings, so a render without the key (the Docker sandbox) reuses takes made on the host.
    """

    RATE = 44100

    def __init__(self, episode_dir, opener=None):
        self.cache = episode_dir / ".audio-takes"
        self.opener = opener

    def take(self, text, profile):
        settings = {"engine": "elevenlabs", "voice_id": profile["voice_id"],
                    "model": profile.get("model", "eleven_multilingual_v2"),
                    "voice_settings": profile.get("voice_settings") or {}}
        name = sha256(json.dumps([text, settings], ensure_ascii=False, sort_keys=True).encode()).hexdigest() + ".wav"
        target = self.cache / name
        if not target.is_file():
            key = os.environ.get("ELEVENLABS_API_KEY")
            if not key:
                raise ValueError("ELEVENLABS_API_KEY is not set: render this line once on the host with the key "
                                 "(the take is cached and reused everywhere after), or use another engine.")
            body = {"text": text, "model_id": settings["model"]}
            if settings["voice_settings"]:
                body["voice_settings"] = settings["voice_settings"]
            data = self._post(ELEVENLABS_URL.format(voice=settings["voice_id"]), body, key)
            import base64
            pcm = base64.b64decode(data["audio_base64"])
            alignment = data.get("alignment") or {}
            self.cache.mkdir(exist_ok=True)
            with TemporaryDirectory(prefix=".take-", dir=self.cache) as folder:
                staged = Path(folder) / "take.wav"
                with wave.open(str(staged), "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(self.RATE)
                    handle.writeframes(pcm)
                if alignment.get("characters"):
                    words = words_from_characters(alignment["characters"], alignment["character_start_times_seconds"],
                                                  alignment["character_end_times_seconds"])
                    words_file(target).write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
                try:
                    os.link(staged, target)
                except FileExistsError:
                    pass
        return target, {**settings, "take": str(target.relative_to(self.cache.parent))}

    def _post(self, url, body, key):
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen
        request = Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                          headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with (self.opener or urlopen)(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:300]
            raise ValueError(f"ElevenLabs refused the request ({error.code}): {detail}") from error
        except URLError as error:
            raise ValueError(f"ElevenLabs is unreachable: {error.reason}") from error
