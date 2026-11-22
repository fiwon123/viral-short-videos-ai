import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from studio.core import ffmpeg
from studio.reference_study import display, source_url, study, top_shorts

FIRST = "ABCDEFGHIJK"
SECOND = "XYZXYZXYZ12"
THIRD = "MNOPQRSTUVW"


class ReferenceSelectionTests(unittest.TestCase):
    def test_only_direct_youtube_video_and_channel_urls_are_allowed(self):
        self.assertEqual(source_url(f"https://www.youtube.com/watch?v={FIRST}&list=abc"), FIRST)
        self.assertEqual(source_url(f"https://youtu.be/{FIRST}"), FIRST)
        self.assertEqual(source_url("https://www.youtube.com/@name/shorts", channel=True),
                         "https://www.youtube.com/@name/shorts")
        for url in ("file:///tmp/video", "https://www.youtube.com.example.org", "https://youtube.com/playlist?list=abc"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                source_url(url)

    def test_top_ranks_all_indexed_shorts_and_reports_incomplete_counts(self):
        def fetch(*args):
            if "--flat-playlist" in args:
                return json.dumps({"entries": [{"id": FIRST, "view_count": 17}, {"id": SECOND}, {"id": THIRD}]})
            if args[-1].endswith(THIRD):
                raise ValueError("video unavailable")
            return json.dumps({"view_count": 81})

        selected, report = top_shorts("https://www.youtube.com/@creator/shorts", 3, fetch)
        self.assertEqual([item["id"] for item in selected], [SECOND, FIRST])
        self.assertEqual((report["indexed"], report["with_views"], report["requested"]), (3, 2, 3))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe are required")
class BreakdownTextTests(unittest.TestCase):
    def test_apostrophes_stay_readable_and_table_syntax_stays_escaped(self):
        self.assertEqual(display("And that's \"cool\""), "And that's \"cool\"")
        self.assertEqual(display("a|b [x](y) <i> & c"), "a&#124;b &#91;x&#93;(y) &lt;i&gt; &amp; c")


class ReferenceStudyTests(unittest.TestCase):
    def test_local_media_evidence_and_notes_survive_a_rerun(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fetch(*args):
                video = Path(args[args.index("-o") + 1]).parent
                if "--skip-download" in args:
                    (video / "source.en.vtt").write_text("WEBVTT\n\n")
                    return b""
                self.assertNotIn("--write-subs", args, "captions must not ride on the media download")
                ffmpeg("-f", "lavfi", "-i", "color=black:s=160x256:r=24:d=2", "-f", "lavfi", "-i",
                       "sine=frequency=440:duration=2", "-vf", "drawbox=color=white:t=fill:enable='gte(t,1)'",
                       "-c:v", "mpeg4", "-c:a", "aac", str(video / "source.mp4"))
                (video / "source.info.json").write_text(json.dumps({
                    "title": "An example | title", "view_count": 70, "like_count": 3,
                    "upload_date": "20261121", "description": "description", "tags": ["original"],
                    "requested_subtitles": {"en": {}},
                }))
                return b""

            def recognize(*_):
                return ([SimpleNamespace(start=.2, end=.7, text="Let's go", words=[
                    SimpleNamespace(word="Let's", start=.2, end=.38), SimpleNamespace(word="go", start=.45, end=.7),
                ])], SimpleNamespace(language="en"))

            urls = [f"https://www.youtube.com/shorts/{FIRST}"]
            (folder,) = study(root, "my-channel", urls, fetch=fetch, recognizer=lambda **_: recognize)
            self.assertEqual(folder, root / "workspace" / "my-channel" / "research" / "references" / FIRST)
            metadata = json.loads((folder / "metadata.json").read_text())
            self.assertEqual(metadata["captions"], ["source.en.vtt"])
            self.assertEqual(metadata["view_count"], 70)
            self.assertTrue((root / "reference-media" / "youtube" / FIRST / "source.mp4").is_file())
            measured = json.loads((folder / "study.json").read_text())
            self.assertEqual(measured["timed_words"], 2)
            self.assertGreater(measured["cuts_per_second"], 0)
            self.assertGreater(measured["edge_frame_delta"], .8)
            breakdown = folder / "breakdown.md"
            self.assertIn("00:00.450", breakdown.read_text())
            self.assertIn("Candidate cut", breakdown.read_text())
            breakdown.write_text("Editorial notes")
            patterns = folder.parent / "patterns.md"
            patterns.write_text("A verified pattern")
            study(root, "my-channel", urls, fetch=lambda *_: self.fail("unexpected download"),
                  recognizer=lambda **_: self.fail("unexpected recognizer"))
            self.assertEqual(breakdown.read_text(), "Editorial notes")
            self.assertEqual(patterns.read_text(), "A verified pattern")

    def test_a_refused_caption_track_keeps_the_video(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fetch(*args):
                video = Path(args[args.index("-o") + 1]).parent
                if "--skip-download" in args:
                    (video / "source.pt-orig.vtt").write_text("WEBVTT\n\n")
                    raise ValueError("python failed\nERROR: Unable to download video subtitles for 'en': "
                                     "HTTP Error 429: Too Many Requests")
                ffmpeg("-f", "lavfi", "-i", "color=black:s=160x256:r=24:d=2", "-f", "lavfi", "-i",
                       "sine=frequency=440:duration=2", "-c:v", "mpeg4", "-c:a", "aac", str(video / "source.mp4"))
                (video / "source.info.json").write_text(json.dumps({"title": "Refused captions"}))
                return b""

            (folder,) = study(root, "my-channel", [f"https://www.youtube.com/shorts/{FIRST}"], fetch=fetch,
                              recognizer=lambda **_: None)
            metadata = json.loads((folder / "metadata.json").read_text())
            self.assertEqual(metadata["captions"], ["source.pt-orig.vtt"])
            self.assertIn("429", metadata["captions_error"])
            self.assertIn("Platform caption files", (folder / "breakdown.md").read_text())
