"""Authoring lint: a camera that drifts there and back inside one setup (studio.lint.wander_warnings)."""

import unittest


def shot(keys, duration=3.0, **camera):
    return {"id": "A", "duration": duration, "layers": [], "camera": {"keyframes": keys, **camera}}


class WanderTests(unittest.TestCase):
    def test_a_push_that_eases_back_out_is_a_wobble(self):
        from studio.lint import wander_warnings
        keys = [{"at": 0, "zoom": 1.0}, {"at": 0.3, "zoom": 1.2, "ease": "smooth"}, {"at": 0.6, "zoom": 1.05, "ease": "smooth"}]
        warnings = wander_warnings(shot(keys))
        self.assertEqual(len(warnings), 1)
        self.assertIn("pushes one way", warnings[0])
        self.assertIn("73% of the way back", warnings[0])  # in log zoom: ln(1.2 / 1.05) / ln(1.2)

    def test_a_pan_across_and_back_is_a_wobble(self):
        from studio.lint import wander_warnings
        keys = [{"at": 0, "x": 0.0}, {"at": 0.4, "x": 0.2}, {"at": 0.7, "x": 0.02}]
        self.assertIn("pans one way", wander_warnings(shot(keys))[0])

    def test_a_move_that_lands_or_cuts_is_fine(self):
        from studio.lint import wander_warnings
        lands = [{"at": 0, "zoom": 1.0}, {"at": 0.5, "zoom": 1.3, "ease": "out"}, {"at": 1, "zoom": 1.3}]
        self.assertEqual(wander_warnings(shot(lands)), [])
        cut = [{"at": 0, "zoom": 1.0}, {"at": 0.4, "zoom": 1.3}, {"at": 0.41, "zoom": 1.0, "ease": "hold"},
               {"at": 1, "zoom": 1.1}]
        self.assertEqual(wander_warnings(shot(cut)), [], "a hold key is a cut to a new setup, not a drift back")
        small = [{"at": 0, "zoom": 1.0}, {"at": 0.3, "zoom": 1.02}, {"at": 0.6, "zoom": 1.0}]
        self.assertEqual(wander_warnings(shot(small)), [], "under 3% is a breath, not a move")

    def test_a_slow_return_long_after_is_not_a_wobble(self):
        from studio.lint import wander_warnings
        keys = [{"at": 0, "zoom": 1.0}, {"at": 0.05, "zoom": 1.2}, {"at": 0.5, "zoom": 1.2}, {"at": 0.55, "zoom": 1.0}]
        self.assertEqual(wander_warnings(shot(keys, duration=10)), [], "a 4.5 s hold between two quick moves")

    def test_presets_and_3d_are_left_out(self):
        from studio.lint import wander_warnings
        keys = [{"at": 0, "zoom": 1.0}, {"at": 0.3, "zoom": 1.2}, {"at": 0.6, "zoom": 1.05}]
        self.assertEqual(wander_warnings(shot(keys, preset="crash-zoom")), [])
        self.assertEqual(wander_warnings({**shot(keys), "three": {"scene": "x"}}), [])

    def test_lint_reports_it(self):
        from studio.lint import lint
        keys = [{"at": 0, "zoom": 1.0}, {"at": 0.3, "zoom": 1.2}, {"at": 0.6, "zoom": 1.05}]
        episode = {"fps": 24, "scenes": [{"id": "S", "shots": [shot(keys)]}]}
        self.assertTrue(any("wobble" in warning for warning in lint(episode, episode)))


if __name__ == "__main__":
    unittest.main()
