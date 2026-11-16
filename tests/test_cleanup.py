"""Cleanup and archive planning across workspace channels."""

import io
import json
import tempfile
import unittest
from pathlib import Path

from studio.cleanup import ensure_old_folders, mark_published, plan_channel, run
from studio.memory import create as create_memory


def package(folder, video=b"v" * 100):
    folder.mkdir(parents=True)
    (folder / "video.mp4").write_bytes(video)
    (folder / "thumbnail.png").write_bytes(b"t")
    (folder / "publishing.md").write_text("# copy")
    (folder / "mix.wav").write_bytes(b"m" * 500)
    (folder / "qa.json").write_text("{}")


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        root = self.root = self.workspace / "demo"
        (root / "channel").mkdir(parents=True)
        (root / "channel" / "channel.json").write_text("{}")
        (root / "channel" / "style-lock.json").write_text(json.dumps(
            {"references": [{"path": "../renders/locked-v1/video.mp4"}]}))
        for name in ("shipped", "fresh", "locked", "marked"):
            ep = root / "episodes" / name
            ep.mkdir(parents=True)
            (ep / "episode.json").write_text("{}")
        (root / "episodes" / "fresh" / ".audio-takes").mkdir()
        renders = root / "renders"
        package(renders / "fresh-v1")
        package(renders / "fresh-v2")
        package(renders / "marked-v1")
        package(renders / "_old" / "shipped-v1")
        package(renders / "_old" / "locked-v1")
        (renders / "_old" / "batch-publishing.md").write_text("copy")
        (renders / "fresh-v2-preview").mkdir()
        ensure_old_folders(root)
        retired = root / "episodes" / "_old" / "retired"
        retired.mkdir()
        (retired / "episode.json").write_text("{}")
        mark_published(root / "episodes" / "marked", url="https://example.com/short")

    def tearDown(self):
        self.tmp.cleanup()

    def actions(self):
        items, notes = plan_channel(self.root)
        return {str(i.path.relative_to(self.root)): i.action for i in items}, notes

    def test_plan_tiers(self):
        actions, notes = self.actions()
        self.assertEqual(actions["renders/fresh-v1"], "delete")
        self.assertEqual(actions["renders/fresh-v2"], "keep")
        self.assertEqual(actions["renders/fresh-v2-preview"], "delete")
        self.assertEqual(actions["renders/marked-v1"], "archive")
        self.assertEqual(actions["renders/_old/shipped-v1"], "delete")
        self.assertEqual(actions["renders/_old/batch-publishing.md"], "delete")
        self.assertEqual(actions["episodes/_old/retired"], "delete")
        self.assertNotIn("renders/_old/README.md", actions)
        self.assertNotIn("episodes/_old/README.md", actions)
        self.assertEqual(actions["renders/_old/locked-v1"], "keep")
        self.assertEqual(actions["episodes/fresh/.audio-takes"], "delete")
        self.assertNotIn("channel/style-lock.json", actions)
        self.assertTrue(any("locked-v1" in n for n in notes))

    def test_dry_run_changes_nothing(self):
        before = sorted(p for p in self.root.rglob("*"))
        run(self.workspace, apply=False, out=io.StringIO())
        self.assertEqual(before, sorted(p for p in self.root.rglob("*")))

    def test_apply_archives_upload_files(self):
        run(self.workspace, apply=True, out=io.StringIO())
        archive = self.root / "archive" / "marked-v1"
        self.assertTrue((archive / "video.mp4").exists())
        self.assertTrue((archive / "publishing.md").exists())
        self.assertFalse((archive / "mix.wav").exists())
        self.assertFalse((self.root / "renders" / "marked-v1").exists())
        self.assertFalse((self.root / "renders" / "_old" / "shipped-v1").exists())
        self.assertFalse((self.root / "episodes" / "_old" / "retired").exists())
        self.assertTrue((self.root / "renders" / "_old" / "README.md").exists())
        self.assertTrue((self.root / "episodes" / "_old" / "README.md").exists())
        self.assertFalse((self.root / "renders" / "fresh-v1").exists())
        self.assertTrue((self.root / "renders" / "fresh-v2" / "video.mp4").exists())
        self.assertTrue((self.root / "renders" / "_old" / "locked-v1" / "video.mp4").exists())
        self.assertTrue((self.root / "episodes" / "fresh" / "episode.json").exists())

    def test_no_video_keeps_only_copy(self):
        run(self.workspace, apply=True, keep_video=False, out=io.StringIO())
        archive = self.root / "archive" / "marked-v1"
        self.assertTrue((archive / "publishing.md").exists())
        self.assertFalse((archive / "video.mp4").exists())

    def test_new_channel_gets_old_folders(self):
        create_memory("brand-new", root=self.workspace)
        self.assertTrue((self.workspace / "brand-new" / "renders" / "_old" / "README.md").exists())
        self.assertTrue((self.workspace / "brand-new" / "episodes" / "_old" / "README.md").exists())

    def test_marker_records_url_once(self):
        marker = mark_published(self.root / "episodes" / "marked" / "episode.json",
                                url="https://example.com/short")
        self.assertEqual(json.loads(marker.read_text())["urls"], ["https://example.com/short"])


if __name__ == "__main__":
    unittest.main()
