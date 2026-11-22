"""Authoring lint: the 2D camera's view against the shot's backdrop (studio.lint.coverage_warnings)."""

import unittest


def shot(camera_keys, **backdrop):
    layer = {"id": "set", "kind": "svg", "file": "art/set.svg", "x": 0.5, "y": 0.5, "width": 1.0, "height": 1.0,
             "plane": "background", **backdrop}
    return {"id": "A", "duration": 4.0, "layers": [layer, {"id": "duck", "kind": "rect", "x": 0.5, "y": 0.7}],
            "camera": {"keyframes": camera_keys}}


PULL_OUT = [{"at": 0, "zoom": 1.5, "x": -0.23, "y": -0.27}, {"at": 1, "zoom": 1.3, "x": -0.23, "y": -0.27, "ease": "linear"}]


class CoverageTests(unittest.TestCase):
    def test_a_pull_out_past_a_frame_sized_set_warns_with_the_amount_and_time(self):
        from studio.lint import coverage_warnings
        warnings = coverage_warnings(shot(PULL_OUT))
        self.assertEqual(len(warnings), 1)
        self.assertIn("A/set", warnings[0])
        self.assertIn("9.2% of the frame", warnings[0])  # 0.5 + (0.5 + 0.27) / 1.3 - 1 at the end
        self.assertIn("-4.00s", warnings[0])

    def test_bleed_parallax_zero_and_an_inside_camera_are_quiet(self):
        from studio.lint import coverage_warnings
        self.assertEqual(coverage_warnings(shot(PULL_OUT, width=1.41, height=1.23)), [], "bled like the fix")
        self.assertEqual(coverage_warnings(shot(PULL_OUT, parallax=0)), [], "a pinned set never leaves the frame")
        push = [{"at": 0, "zoom": 1.0}, {"at": 1, "zoom": 2.0, "x": 0.3, "ease": "linear"}]
        self.assertEqual(coverage_warnings(shot(push)), [], "|x| <= (zoom - 1) / 2 stays inside")

    def test_half_parallax_moves_the_set_half_as_much(self):
        from studio.lint import coverage_warnings
        # At parallax 0.5 the pull-out ends at zoom 1.15 and y offset -0.135: 0.5 + 0.635 / 1.15 - 1 = 5.2%.
        self.assertIn("5.2% of the frame", coverage_warnings(shot(PULL_OUT, parallax=0.5))[0])

    def test_layers_the_check_cannot_model_are_left_out(self):
        from studio.lint import coverage_warnings
        self.assertEqual(coverage_warnings(shot(PULL_OUT, keyframes=[{"at": 1, "x": 0.4}])), [])
        self.assertEqual(coverage_warnings(shot(PULL_OUT, z=2)), [])
        self.assertEqual(coverage_warnings({**shot(PULL_OUT), "three": {"scene": "x"}}), [])

    def test_lint_reports_it_on_the_expanded_episode(self):
        from studio.lint import lint
        episode = {"fps": 24, "scenes": [{"id": "S", "shots": [shot(PULL_OUT)]}]}
        self.assertTrue(any("leaves this backdrop" in warning for warning in lint(episode, episode)))


if __name__ == "__main__":
    unittest.main()
