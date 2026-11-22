"""The production script for voice and visual AI (studio.script)."""

import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def build(root, speech=True):
    """workspace/demo with a channel, a cast, a style lock and one two-shot episode."""
    channel = root / "workspace" / "demo" / "channel"
    episode = root / "workspace" / "demo" / "episodes" / "pilot"
    channel.mkdir(parents=True)
    episode.mkdir(parents=True)
    (channel / "channel.json").write_text(json.dumps({"name": "Demo", "audio_library": "audio/cast.json"}))
    (channel / "audio").mkdir()
    (channel / "audio" / "cast.json").write_text(json.dumps({"version": 1, "voices": {
        "Ana": {"engine": "elevenlabs", "voice_id": "VoiceAbc12345", "direction": "Bright,\nquick host."}}}))
    (channel / "style-lock.json").write_text(json.dumps({"summary": "Flat ink comedy, thick outlines.",
                                                         "never": ["photoreal faces"]}))
    lines = [{"speaker": "Ana", "text": "Wait, my SSD quit?", "spoken_text": "Wait, my S S D quit?",
              "delivery": "Shocked,\nloud."},
             {"speaker": "Ana", "text": "It left a note."}] if speech else []
    data = {"title": "Pilot", "fps": 24, "scenes": [{"id": "S1", "purpose": "Setup", "shots": [
        {"id": "A", "duration": 2.0, "direction": "Ana opens the case;\nthe drive is gone.", "background": "#112233",
         "speech": lines[:1], "sfx": [{"at": 0.5, "sound": "thud"}], "layers": []},
        {"id": "B", "duration": 3.0, "direction": "Close on the note.", "background": "paper",
         "speech": [{**lines[1], "at": 0.4}] if speech else [], "sfx": [], "layers": []}]}]}
    path = episode / "episode.json"
    path.write_text(json.dumps(data))
    return path


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.cwd)

    def test_estimated_script_lists_voices_shots_lines_and_prompts(self):
        from studio.script import write
        with TemporaryDirectory() as folder:
            os.chdir(folder)
            episode = build(Path(folder))
            report = write(episode)
            self.assertEqual(report["times"], "estimated")
            self.assertEqual((report["shots"], report["lines"], report["speakers"]), (2, 2, ["Ana"]))
            script = (episode.parent / "script.md").read_text()
            self.assertIn("| Ana | elevenlabs | Bright, quick host. |", script)
            # The spoken form has six words: 2.3 s at 2.6 per second, so the line holds shot A open.
            self.assertIn("### A · 00:00.0–00:02.4", script)
            self.assertIn("**Picture:** Ana opens the case; the drive is gone.", script)
            self.assertIn("**Sound:** thud at 00:00.5.", script)
            self.assertIn("| A.1 | 00:00.0–00:02.3 | Ana | Wait, my SSD quit? (say: Wait, my S S D quit?) "
                          "| Shocked, loud. |", script)
            self.assertIn("| B.1 | 00:02.8–", script)  # shot B starts at 2.4, the line at 0.4 into it
            self.assertIn("Look: Flat ink comedy, thick outlines.", script)
            self.assertIn("Avoid: photoreal faces.", script)
            self.assertIn("Background #112233.", script)
            self.assertNotIn("Background paper", script, "palette token names are not colours")
            self.assertIn("make voice-import EPISODE=workspace/demo/episodes/pilot/episode.json", script)

    def test_voice_script_is_ready_to_paste(self):
        from studio.script import write
        with TemporaryDirectory() as folder:
            os.chdir(folder)
            episode = build(Path(folder))
            write(episode)
            voice = (episode.parent / "voice-script.txt").read_text()
            self.assertIn("Ana: Bright, quick host.", voice)
            self.assertIn("\nWait, my S S D quit?\n\nIt left a note.\n", voice)
            self.assertIn("[shocked, loud] Wait, my S S D quit?", voice)
            self.assertIn("A.1        00:00.0  Wait, my S S D quit?  (written: Wait, my SSD quit?)", voice)
            self.assertIn("make voice-import EPISODE=workspace/demo/episodes/pilot/episode.json FILE=", voice)

    def test_times_come_from_a_newer_audio_pass(self):
        from studio.script import write
        with TemporaryDirectory() as folder:
            os.chdir(folder)
            episode = build(Path(folder))
            render = Path(folder) / "workspace" / "demo" / "renders" / "pilot-preview"
            render.mkdir(parents=True)
            timeline = {"fps": 24, "scenes": [{"shots": [
                {"id": "A", "start": 0, "end": 60, "speech": [{"start": 6, "end": 42}]},
                {"id": "B", "start": 60, "end": 132, "speech": [{"start": 72, "end": 96}]}]}]}
            time.sleep(0.01)
            (render / "timeline.json").write_text(json.dumps(timeline))
            report = write(episode)
            self.assertEqual(report["times"], "measured from pilot-preview")
            script = (episode.parent / "script.md").read_text()
            self.assertIn("| A.1 | 00:00.2–00:01.8 |", script)
            self.assertIn("### B · 00:02.5–00:05.5", script)
            # An edit after the audio pass makes those times stale again.
            later = time.time() + 5
            os.utime(episode, (later, later))
            self.assertEqual(write(episode)["times"], "estimated")

    def test_a_wordless_episode_still_gets_picture_sound_and_prompts(self):
        from studio.script import write
        with TemporaryDirectory() as folder:
            os.chdir(folder)
            episode = build(Path(folder), speech=False)
            report = write(episode)
            self.assertEqual(report["lines"], 0)
            self.assertIn("Wordless", (episode.parent / "script.md").read_text())
            self.assertIn("Visual AI prompt", (episode.parent / "script.md").read_text())
            self.assertIn("No spoken lines", (episode.parent / "voice-script.txt").read_text())


if __name__ == "__main__":
    unittest.main()
