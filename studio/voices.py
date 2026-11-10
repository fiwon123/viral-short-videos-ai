"""Render local neural takes once and reuse the exact WAV on subsequent renders."""

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
