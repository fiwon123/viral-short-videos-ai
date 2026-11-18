"""Machine profile: tiers, budgets, overrides, and the places that honour them."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProfileTests(unittest.TestCase):
    def test_tiers_follow_cores_ram_and_gpu(self):
        from studio.machine import profile
        low = profile({"cores": 4, "ram_gb": 8, "gpu": None}, env={})
        self.assertEqual((low["tier"], low["threads"], low["jobs"], low["browser_workers"]), ("low", 2, 1, 1))
        small_ram = profile({"cores": 16, "ram_gb": 6, "gpu": None}, env={})
        self.assertEqual(small_ram["tier"], "low")
        mid = profile({"cores": 8, "ram_gb": 16, "gpu": None}, env={})
        self.assertEqual((mid["tier"], mid["threads"], mid["jobs"]), ("mid", 6, 2))
        gpu = profile({"cores": 8, "ram_gb": 16, "gpu": {"vram_gb": 12}}, env={})
        self.assertEqual((gpu["tier"], gpu["gpu_ai"]), ("high", True))
        workstation = profile({"cores": 16, "ram_gb": 64, "gpu": None}, env={})
        self.assertEqual((workstation["tier"], workstation["threads"], workstation["jobs"]), ("high", 15, 4))
        for budget in (low, mid, gpu, workstation):
            self.assertLess(budget["threads"], budget["cores"] + (budget["cores"] == 1))
            self.assertFalse(budget["cpu_ai"], "CPU image generation is opt-in")
            self.assertEqual(budget["nice"], 10)

    def test_overrides_win_and_bad_values_are_refused(self):
        from studio.machine import profile
        machine = {"cores": 8, "ram_gb": 16, "gpu": None}
        forced = profile(machine, env={"STUDIO_PROFILE": "low", "STUDIO_THREADS": "3", "STUDIO_JOBS": "2",
                                       "STUDIO_BROWSER_WORKERS": "1", "STUDIO_NICE": "0", "STUDIO_CPU_AI": "1"})
        self.assertEqual((forced["tier"], forced["threads"], forced["jobs"], forced["browser_workers"],
                          forced["nice"], forced["cpu_ai"]), ("low", 3, 2, 1, 0, True))
        self.assertEqual(len(forced["overrides"]), 6)
        with self.assertRaises(ValueError):
            profile(machine, env={"STUDIO_PROFILE": "turbo"})
        with self.assertRaises(ValueError):
            profile(machine, env={"STUDIO_THREADS": "lots"})

    def test_apply_lowers_priority_and_caps_threads_for_children(self):
        if not hasattr(os, "nice"):
            self.skipTest("niceness is POSIX only")
        code = ("import os; from studio.machine import apply; apply();"
                "print(os.nice(0), os.environ['OMP_NUM_THREADS'], os.environ['STUDIO_BROWSER_WORKERS'])")
        env = {key: value for key, value in os.environ.items() if not key.startswith(("STUDIO_", "OMP_"))}
        env.update({"STUDIO_THREADS": "3", "STUDIO_BROWSER_WORKERS": "1"})
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                             check=True).stdout.split()
        self.assertGreaterEqual(int(out[0]), 10)
        self.assertEqual(out[1:], ["3", "1"])


class BudgetUseTests(unittest.TestCase):
    def test_x264_gets_the_thread_cap(self):
        from unittest import mock
        from studio import machine
        from studio.render import encoder
        with mock.patch.object(machine, "_CACHED", {"threads": 3}):
            options = encoder(1080, 1920, 30)
        if "libx264" in options:
            self.assertEqual(options[options.index("-threads") + 1], "3")

    def test_browser_workers_come_from_the_environment(self):
        source = (ROOT / "browser" / "render.mjs").read_text()
        self.assertIn("STUDIO_BROWSER_WORKERS", source)
        self.assertNotIn('"--workers", "2"', source)
        self.assertNotIn("concurrency: 2", source)

    def test_batch_defaults_to_the_profile_jobs(self):
        import inspect
        from studio.batch import run
        self.assertIsNone(inspect.signature(run).parameters["jobs"].default)


if __name__ == "__main__":
    unittest.main()
