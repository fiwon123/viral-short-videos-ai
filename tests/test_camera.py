"""Camera zoom runs in log space: an even visual rate for pushes and pulls, in every interpolator."""

import math
import unittest


def track(*keys):
    from studio.design import camera_points
    return camera_points({"camera": {"keyframes": list(keys)}})


class LogZoomTests(unittest.TestCase):
    def test_a_linear_zoom_key_passes_the_geometric_mean(self):
        from studio.design import pose_at
        points = track({"at": 0, "zoom": 1.0}, {"at": 1, "zoom": 4.0, "ease": "linear"})
        self.assertAlmostEqual(pose_at(points, 0.5)["zoom"], 2.0)

    def test_the_relative_rate_is_even_along_a_linear_key(self):
        from studio.design import pose_at
        points = track({"at": 0, "zoom": 1.3}, {"at": 1, "zoom": 2.95, "ease": "linear"})
        logs = [math.log(pose_at(points, step / 8)["zoom"]) for step in range(9)]
        steps = [b - a for a, b in zip(logs, logs[1:])]
        for step in steps:
            self.assertAlmostEqual(step, steps[0], places=9)

    def test_eases_and_end_values_are_kept(self):
        from studio.design import pose_at
        points = track({"at": 0, "zoom": 1.0}, {"at": 0.5, "zoom": 2.0, "ease": "smooth"},
                       {"at": 1, "zoom": 1.2, "ease": "back"})
        self.assertAlmostEqual(pose_at(points, 0.5)["zoom"], 2.0)
        self.assertAlmostEqual(pose_at(points, 1.0)["zoom"], 1.2)
        self.assertAlmostEqual(pose_at(points, 0.25)["zoom"], math.sqrt(2.0))  # smooth(0.5) = 0.5
        self.assertGreater(min(pose_at(points, step / 100)["zoom"] for step in range(101)), 0)

    def test_pan_and_layer_scale_stay_linear(self):
        from studio.design import pose_at, poses
        points = track({"at": 0, "x": 0.0, "zoom": 1.0}, {"at": 1, "x": 0.4, "zoom": 4.0, "ease": "linear"})
        self.assertAlmostEqual(pose_at(points, 0.5)["x"], 0.2)
        layer = {"id": "a", "kind": "rect", "x": 0.5, "y": 0.5, "scale": 1.0,
                 "keyframes": [{"at": 1, "scale": 4.0, "ease": "linear"}]}
        self.assertAlmostEqual(pose_at(poses(layer), 0.5)["scale"], 2.5)

    def test_the_shake_bake_follows_the_same_path(self):
        from studio.camera import resolve_camera
        from studio.design import pose_at
        shot = {"duration": 4.0, "camera": {"keyframes": [{"at": 0, "zoom": 1.0}, {"at": 1, "zoom": 4.0, "ease": "linear"}],
                                            "shakes": [{"at": 0.9, "duration": 0.1, "amplitude": 0.01}]}}
        baked = resolve_camera(shot, seconds=4.0)
        self.assertGreater(len(baked["keyframes"]), 100, "the shake must bake the track into dense keys")
        middle = min(baked["keyframes"], key=lambda key: abs(key["at"] - 0.5))
        self.assertAlmostEqual(middle["zoom"], 4.0 ** middle["at"], places=4)
        self.assertAlmostEqual(pose_at(track(*baked["keyframes"]), 0.5)["zoom"], 2.0, places=3)


if __name__ == "__main__":
    unittest.main()
