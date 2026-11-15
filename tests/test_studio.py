"""Focused regression tests for the AI authoring controls."""

import copy
import json
import math
import unittest
from pathlib import Path

from studio.core import load, validate, validate_episode
from studio.design import pose_at, poses, resolve_color, text_tile
from studio.easing import ease
from studio.presets import apply_style, load_style
from studio.trails import expand as expand_trails

ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    def test_examples_validate(self):
        for episode in (ROOT / "examples").glob("*/episodes/*/episode.json"):
            channel = episode.parents[2] / "channel" / "channel.json"
            with self.subTest(episode=episode):
                load(episode, "episode")
                load(channel, "channel")

    def test_metadata_is_allowed(self):
        episode = json.loads(next((ROOT / "examples").glob("*/episodes/*/episode.json"))
                             .read_text(encoding="utf-8"))
        episode["$schema"] = "../schema/episode.schema.json"
        episode["meta"] = {"status": "draft", "notes": "AI handoff"}
        validate(episode, "episode")

    def test_extra_palette_roles(self):
        channel = json.loads((ROOT / "examples/paper-crane/channel/channel.json").read_text(encoding="utf-8"))
        channel["palette"]["warm"] = "#F59E0B"
        validate(channel, "channel")
        self.assertEqual(resolve_color("warm", channel["palette"]), "#F59E0B")


class PresetTests(unittest.TestCase):
    def test_all_style_presets_validate(self):
        for path in (ROOT / "presets" / "styles").glob("*.json"):
            with self.subTest(preset=path.stem):
                data = load_style(path.stem)
                self.assertEqual(data["name"], data["name"])

    def test_unknown_preset_lists_names(self):
        with self.assertRaisesRegex(ValueError, "Available:"):
            load_style("does-not-exist")


class MotionTests(unittest.TestCase):
    def _layer(self, keyframes):
        return {"id": "test", "kind": "rect", "x": 0.5, "y": 0.5, "keyframes": keyframes}

    def test_non_uniform_scale_and_ease(self):
        layer = self._layer([
            {"at": 0, "scale_x": 1, "scale_y": 1},
            {"at": 1, "scale_x": 2, "scale_y": 0.5,
             "ease": {"type": "cubic-bezier", "points": [0, 0, 1, 1]}},
        ])
        state = pose_at(poses(layer), 0.5)
        self.assertAlmostEqual(state["scale_x"], 1.5, places=3)
        self.assertAlmostEqual(state["scale_y"], 0.75, places=3)

    def test_per_property_ease(self):
        layer = self._layer([
            {"at": 0, "opacity": 0, "scale": 1},
            {"at": 1, "opacity": 1, "scale": 2, "ease": "back", "ease_props": {"opacity": "linear"}},
        ])
        state = pose_at(poses(layer), 0.5)
        self.assertAlmostEqual(state["opacity"], 0.5, places=3)
        self.assertNotAlmostEqual(state["scale"], 1.5, places=3)

    def test_auto_smoothing(self):
        layer = self._layer([
            {"at": 0, "x": 0},
            {"at": 0.5, "x": 1, "ease": "auto"},
            {"at": 1, "x": 0, "ease": "auto"},
        ])
        points = poses(layer)
        self.assertGreater(pose_at(points, 0.5)["x"], 0.99)
        self.assertGreater(pose_at(points, 0.75)["x"], 0.5)
        self.assertTrue(math.isclose(pose_at(points, 1)["x"], 0, abs_tol=1e-6))

    def test_defs_expand_with_prefixed_parents(self):
        from studio.expand import expand as expand_defs

        episode = {
            "defs": {"arm": [
                {"id": "upper", "kind": "rect", "x": 0, "y": 0, "width": 0.1, "height": 0.1},
                {"id": "hand", "kind": "ellipse", "x": 0.05, "y": 0.05, "width": 0.05, "height": 0.05,
                 "parent": "upper", "variant_group": "grip"},
            ]},
            "scenes": [{"shots": [{"id": "A", "layers": [
                {"id": "left", "kind": "use", "ref": "arm", "x": 0.3, "y": 0.5},
                {"id": "right", "kind": "use", "ref": "arm", "x": 0.7, "y": 0.5},
            ]}]}],
        }
        expand_defs(episode)
        layers = episode["scenes"][0]["shots"][0]["layers"]
        ids = [layer["id"] for layer in layers]
        self.assertIn("left", ids)
        self.assertIn("left/upper", ids)
        self.assertIn("left/hand", ids)
        hand = next(layer for layer in layers if layer["id"] == "left/hand")
        self.assertEqual(hand["parent"], "left/upper")
        self.assertEqual(hand["variant_group"], "left/grip")

    def test_animated_tint_opacity(self):
        layer = self._layer([
            {"at": 0, "tint_opacity": 0},
            {"at": 1, "tint_opacity": 1, "ease": "sine"},
        ])
        self.assertAlmostEqual(pose_at(poses(layer), 0.5)["tint_opacity"], 0.5, places=3)

    def test_animated_blur(self):
        layer = self._layer([
            {"at": 0, "blur": 0},
            {"at": 1, "blur": 0.4, "ease": "sine"},
        ])
        self.assertAlmostEqual(pose_at(poses(layer), 0.5)["blur"], 0.2, places=3)

    def test_sprite_sheet_frame_step(self):
        layer = self._layer([
            {"at": 0, "frame": 0},
            {"at": 0.5, "frame": 1},
            {"at": 1, "frame": 2},
        ])
        points = poses(layer)
        self.assertEqual(pose_at(points, 0.25)["frame"], 0)
        self.assertEqual(pose_at(points, 0.5)["frame"], 1)
        self.assertEqual(pose_at(points, 1)["frame"], 2)

    def test_channel_rigs_merge_with_episode_defs(self):
        from studio.expand import expand as expand_defs

        episode = {
            "defs": {"local": [
                {"id": "box", "kind": "rect", "x": 0, "y": 0, "width": 0.1, "height": 0.1},
            ]},
            "scenes": [{"shots": [{"id": "A", "layers": [
                {"id": "a", "kind": "use", "ref": "shared", "x": 0.3, "y": 0.5},
                {"id": "b", "kind": "use", "ref": "local", "x": 0.7, "y": 0.5},
            ]}]}],
        }
        channel = {"shared": [
            {"id": "dot", "kind": "ellipse", "x": 0, "y": 0, "width": 0.05, "height": 0.05},
        ]}
        expand_defs(episode, channel)
        ids = [layer["id"] for layer in episode["scenes"][0]["shots"][0]["layers"]]
        self.assertIn("a/dot", ids)
        self.assertIn("b/box", ids)

    def test_trails_expand_to_layers(self):
        episode = {"scenes": [{"shots": [{
            "id": "A",
            "layers": [{
                "id": "dot", "kind": "ellipse", "x": 0.2, "y": 0.5,
                "trail": {"count": 2, "spacing": 0.05, "opacity": 0.5},
                "keyframes": [{"at": 0, "x": 0.2}, {"at": 1, "x": 0.8}],
            }],
        }]}]}
        expand_trails(episode)
        ids = [layer["id"] for layer in episode["scenes"][0]["shots"][0]["layers"]]
        self.assertEqual(ids, ["dot-trail-2", "dot-trail-1", "dot"])


class StyleTests(unittest.TestCase):
    def test_caption_highlight_color_is_not_limited_to_hex(self):
        palette = {"background": "#000000", "foreground": "#FFFFFF",
                   "accent": "#FF0000", "secondary": "#111111"}
        self.assertEqual(resolve_color("accent", palette), "#FF0000")

    def test_text_tile_accepts_gradient_and_stroke(self):
        tile = text_tile(
            "HELLO", (320, 120),
            {"type": "linear", "angle": 90,
             "stops": [{"at": 0, "color": "#FFFFFF"}, {"at": 1, "color": "#22D3EE"}]},
            None, stroke=0.04, stroke_color="#000000",
        )
        self.assertEqual(tile.mode, "RGBA")
        self.assertGreater(tile.getchannel("A").getbbox()[2], 0)

    def test_sheet_tiles_slice_cells(self):
        from tempfile import TemporaryDirectory
        from PIL import Image
        from studio.design import sheet_tiles

        with TemporaryDirectory() as temp:
            path = Path(temp) / "sheet.png"
            Image.new("RGBA", (40, 20), "#FFFFFF").save(path)
            layer = {"id": "sheet", "kind": "sheet", "file": "sheet.png",
                     "columns": 2, "rows": 2, "count": 4,
                     "x": 0.5, "y": 0.5, "width": 0.2, "height": 0.2}
            tiles = sheet_tiles(layer, (100, 100), Path(temp))
            self.assertEqual(len(tiles), 4)
            self.assertEqual(tiles[0].size, tiles[3].size)

    def test_cubic_bezier_endpoints(self):
        curve = {"type": "cubic-bezier", "points": [0.4, 0, 0.2, 1]}
        self.assertAlmostEqual(ease(0, curve), 0)
        self.assertAlmostEqual(ease(1, curve), 1)


class RevealTests(unittest.TestCase):
    def test_word_reveal_expands_to_pieces(self):
        from studio.reveal import expand as expand_reveal

        episode = {
            "width": 540, "height": 960,
            "scenes": [{"shots": [{"id": "A", "layers": [
                {"id": "title", "kind": "text", "x": 0.5, "y": 0.4,
                 "width": 0.8, "height": 0.2, "text": "ONE SMALL GUST",
                 "reveal": {"mode": "word", "start": 0.1, "stagger": 0.1}},
            ]}]}],
        }
        channel = {"palette": {"background": "#000000", "foreground": "#FFFFFF",
                               "accent": "#22D3EE", "secondary": "#334155"}}
        expand_reveal(episode, channel, ROOT)
        layers = episode["scenes"][0]["shots"][0]["layers"]
        self.assertEqual(len(layers), 3)
        self.assertTrue(all(layer["kind"] == "text" for layer in layers))
        self.assertGreater(layers[-1]["keyframes"][-1]["at"], layers[0]["keyframes"][-1]["at"])


class BatchTests(unittest.TestCase):
    def test_season_selection_and_dry_run(self):
        from tempfile import TemporaryDirectory
        from studio.batch import run

        with TemporaryDirectory() as temp:
            season = Path(temp) / "season.json"
            season.write_text(json.dumps({
                "title": "Test Season",
                "channel": str((ROOT / "tests/parity/channel.json").resolve()),
                "episodes": [
                    {"id": "one", "path": str((ROOT / "tests/parity/episode.json").resolve()),
                     "status": "planned"},
                    {"id": "two", "path": str((ROOT / "tests/parity/episode.json").resolve()),
                     "status": "done"},
                ],
            }), encoding="utf-8")
            report = run(season, status="planned", dry_run=True)
            self.assertTrue(report["dry_run"])
            self.assertEqual([item["id"] for item in report["episodes"]], ["one"])
            report = run(season, only=["two"], dry_run=True, preview=True)
            self.assertEqual([item["id"] for item in report["episodes"]], ["two"])


class StillTests(unittest.TestCase):
    def test_python_still(self):
        from tempfile import TemporaryDirectory
        from studio.audio_library import load_audio_library
        from studio.markers import expand as expand_markers
        from studio.particles import expand as expand_particles
        from studio.still import render_still

        episode_path = ROOT / "tests" / "parity" / "episode.json"
        channel_path = ROOT / "tests" / "parity" / "channel.json"
        channel = load(channel_path, "channel")
        episode = load(episode_path, "episode")
        episode = apply_style(episode, channel, channel_path.parent)
        episode = expand_particles(expand_trails(expand_markers(episode, channel_path.parent)))
        validate_episode(episode, episode_path.parent, channel_path.parent)
        with TemporaryDirectory() as temp:
            target = Path(temp) / "still.png"
            report = render_still(episode, channel, episode_path.parent, channel_path.parent, target,
                                  shot_id=episode["thumbnail"]["shot"], progress=0.5,
                                  renderer="python", audio=False,
                                  audio_library=load_audio_library(channel, channel_path.parent))
            self.assertTrue(target.is_file())
            self.assertEqual(report["renderer"], "python")


class CaptionTests(unittest.TestCase):
    def cue(self, text):
        words = [{"text": word, "start": index * 10, "end": index * 10 + 9}
                 for index, word in enumerate(text.split())]
        return {"start": 0, "end": len(words) * 10 + 5, "words": words}

    def test_pages_break_at_punctuation_without_orphans(self):
        from studio.captions import pages
        result = pages(self.cue("This is *really* not fine, okay go"), {"words_per_page": 3})
        texts = [[word["text"] for word in page["words"]] for page in result]
        self.assertEqual(texts, [["THIS", "IS", "REALLY"], ["NOT", "FINE,"], ["OKAY", "GO"]])
        self.assertTrue(result[0]["words"][2]["emphasis"])
        self.assertEqual(result[1]["start"], result[0]["end"])

    def test_keyword_emphasis_and_word_reveal(self):
        from studio.captions import pages, settings, word_state
        config = settings({"emphasis": ["moon"], "reveal": "word"})
        page = pages(self.cue("That was the moon."), config)[-1]
        moon = page["words"][-1]
        self.assertTrue(moon["emphasis"])
        self.assertIsNone(word_state(moon, 3, page, moon["start"] - 1, 30, 80, config))
        state = word_state(moon, 3, page, moon["start"] + 6, 30, 80, config)
        self.assertEqual(state["state"], "emphasis")
        self.assertGreater(state["scale"], 1.2)

    def test_kinetic_draw_python(self):
        from PIL import Image
        from studio.design import draw_caption
        image = Image.new("RGB", (360, 640), "#203040")
        draw_caption(image, self.cue("Small *signal* again"), {"palette": {"accent": "#FFBD54"}}, None,
                     config={"style": "kinetic", "fps": 30}, frame=25)
        self.assertNotEqual(image.getbbox(), None)
        self.assertGreater(len(image.getcolors(1 << 20)), 10)

    def test_caption_hold_never_overlaps_next(self):
        from studio.audio import hold_captions
        cues = [{"start": 0, "end": 30}, {"start": 35, "end": 60}]
        hold_captions(cues, 100, 30, 0.5)
        self.assertEqual(cues[0]["end"], 35)
        self.assertEqual(cues[1]["end"], 75)


class WordTimingTests(unittest.TestCase):
    def test_energy_pins_punctuation_to_pause(self):
        import numpy as np
        from studio.wordtiming import energy
        rate = 24000

        def burst(seconds):
            return 0.5 * np.sin(np.arange(int(seconds * rate)) * 0.05) * np.hanning(int(seconds * rate))
        clip = np.concatenate([burst(0.5), np.zeros(int(0.4 * rate)), burst(0.5)])
        words = energy(clip, rate, ["Hello", "there,", "small", "world."])
        self.assertLessEqual(words[1]["end"], 0.56)
        self.assertGreaterEqual(words[2]["start"], 0.85)
        self.assertEqual([word["text"] for word in words], ["Hello", "there,", "small", "world."])

    def test_recognised_words_map_onto_script(self):
        from studio.wordtiming import map_recognised
        heard = [{"text": "I", "start": 0, "end": 0.1}, {"text": "very", "start": 0.3, "end": 0.6}]
        mapped = map_recognised(["I", "am", "very"], heard)
        self.assertAlmostEqual(mapped[1]["start"], 0.1)
        self.assertAlmostEqual(mapped[2]["start"], 0.3)


class SoundDesignTests(unittest.TestCase):
    def test_sample_classification(self):
        from studio.samples import classify
        self.assertEqual(classify(Path("Kenney/Impacts/impactWood_heavy_002.ogg")), "thud")
        self.assertEqual(classify(Path("Whooshes/fast whoosh 3.wav")), "whoosh")
        self.assertEqual(classify(Path("UI/click_soft.wav")), "click")
        self.assertEqual(classify(Path("Cinematic/riser_long.wav")), "riser")
        self.assertIsNone(classify(Path("misc/untitled.wav")))

    def test_spotting_hits_fast_move_and_stop(self):
        from studio.spotting import propose
        shot = {"id": "A", "duration": 2.0, "layers": [{
            "id": "ball", "kind": "ellipse", "x": 0.1, "y": 0.5,
            "keyframes": [{"at": 0.2, "x": 0.1}, {"at": 0.45, "x": 0.9, "ease": "in"}]}]}
        cues = propose(shot, 30, {"whoosh", "thud", "pop"})
        kinds = [cue["sound"] for cue in cues]
        self.assertIn("whoosh", kinds)
        self.assertIn("thud", kinds)
        self.assertTrue(all(cue["spotted"] for cue in cues))
        shot["sfx"] = [{"at": cue["at"], "sound": "pop"} for cue in cues]
        self.assertEqual(propose(shot, 30, {"whoosh", "thud", "pop"}), [])

    def test_glue_reduces_only_loud_material(self):
        import numpy as np
        from studio.audio import glue
        track = np.zeros((48000, 2), dtype=np.float32)
        track[1000:6000] = 0.9
        track[20000:24000] = 0.05
        out = glue(track)
        self.assertLess(out[5000, 0], 0.8)
        self.assertAlmostEqual(float(out[23000, 0]), 0.05, places=3)


class CharacterTests(unittest.TestCase):
    def test_character_parts_and_rig(self):
        from studio.character import build_parts, rig_layers
        spec, parts = build_parts({"id": "t", "ears": "pointy", "antenna": True, "head": {"shape": "egg"}})
        names = {part.name for part in parts}
        self.assertTrue({"body", "head", "eye-l", "pupil-r", "mouth-rest", "mouth-open", "arm-l", "leg-r",
                         "ear-l", "antenna", "shadow"} <= names)
        layers = rig_layers(spec, parts, "art/characters/t")
        by_id = {layer["id"]: layer for layer in layers}
        self.assertEqual(by_id["pupil-l"]["parent"], "eye-l")
        self.assertEqual(by_id["eye-l"]["parent"], "head")
        self.assertFalse(by_id["mouth-open"]["visible"])
        self.assertLess(by_id["eye-l"]["x"], 0)
        for part in parts:
            self.assertTrue(part.svg().startswith("<svg"))

    def test_alive_adds_blink_breath_and_talk(self):
        from studio.character import build_parts, rig_layers
        from studio.expand import expand as expand_defs
        from studio.life import expand as expand_life
        spec, parts = build_parts({"id": "t"})
        rig = rig_layers(spec, parts, "art/characters/t")
        episode = {"defs": {"t": rig}, "scenes": [{"shots": [{"id": "A", "duration": 6.0, "layers": [
            {"id": "hero", "kind": "use", "ref": "t", "x": 0.5, "y": 0.8, "alive": {"talk": "Hero"}}]}]}]}
        episode = expand_life(expand_defs(episode))
        layers = {layer["id"]: layer for layer in episode["scenes"][0]["shots"][0]["layers"]}
        self.assertNotIn("alive", layers["hero"])
        eye_scale = [key.get("scale_y", 1) for key in layers["hero/eye-l"]["keyframes"]]
        self.assertLess(min(eye_scale), 0.2)
        body_scale = [key["scale_y"] for key in layers["hero/body"]["keyframes"]]
        self.assertGreater(max(body_scale) - min(body_scale), 0.02)
        self.assertEqual(layers["hero/mouth-rest"]["viseme_for"], "Hero")  # Viseme set: lip sync.
        self.assertEqual(layers["hero/mouth-mbp"]["viseme"], "mbp")
        ats = [key["at"] for key in layers["hero/body"]["keyframes"]]
        self.assertEqual(ats, sorted(ats))
        episode = {"defs": {"t": rig}, "scenes": [{"shots": [{"id": "A", "duration": 6.0, "layers": [
            {"id": "hero", "kind": "use", "ref": "t", "x": 0.5, "y": 0.8,
             "alive": {"talk": "Hero", "lipsync": False}}]}]}]}
        layers = {layer["id"]: layer for layer in expand_life(expand_defs(episode))["scenes"][0]["shots"][0]["layers"]}
        self.assertEqual(layers["hero/mouth-rest"]["quiet_for"], "Hero")
        self.assertTrue(layers["hero/mouth-open"]["talk_only"])


class LintTests(unittest.TestCase):
    def test_lint_flags_snaps_particles_and_fov(self):
        from studio.lint import lint
        shot = {"id": "A", "duration": 1.0, "camera": {"keyframes": [{"at": 0.5, "fov": 40}]}, "layers": [
            {"id": "a", "kind": "rect", "x": 0.5, "y": 0.5, "keyframes": [{"at": 0.5}, {"at": 0.51}]},
            {"id": "p", "kind": "particles", "x": 0.5, "y": 0.5, "rate": 900, "file": "x.svg"}]}
        episode = {"fps": 30, "scenes": [{"shots": [shot]}]}
        warnings = lint(episode, episode)
        self.assertEqual(len(warnings), 3)


class MovesTests(unittest.TestCase):
    def shot(self, **layer):
        base = {"id": "a", "kind": "rect", "x": 0.5, "y": 0.8}
        return {"width": 1080, "height": 1920, "fps": 24,
                "scenes": [{"shots": [{"id": "A", "duration": 2.0, "layers": [{**base, **layer}]}]}]}

    def keys(self, episode, layer_id="a"):
        from studio.design import pose_at, poses
        layer = next(item for item in episode["scenes"][0]["shots"][0]["layers"] if item["id"] == layer_id)
        points = poses(layer)
        return lambda seconds: pose_at(points, seconds / 2.0)

    def test_path_hits_endpoints_and_orients(self):
        from studio.moves import expand
        episode = expand(self.shot(path={"points": [[0.1, 0.5], [0.9, 0.5]], "orient": True, "ease": "linear"}))
        pose = self.keys(episode)
        self.assertAlmostEqual(pose(0)["x"], 0.1, places=3)
        self.assertAlmostEqual(pose(2.0)["x"], 0.9, places=3)
        self.assertAlmostEqual(pose(1.0)["rotate"], 0, places=1)

    def test_jump_rises_and_lands(self):
        from studio.moves import expand
        episode = expand(self.shot(motion=[{"recipe": "jump", "t": 0.5, "d": 0.6, "height": 0.1}]))
        pose = self.keys(episode)
        self.assertLess(pose(0.5 + 0.6 * 0.49)["y"], 0.72)
        self.assertAlmostEqual(pose(1.5)["y"], 0.8, places=3)
        self.assertGreater(pose(0.5 + 0.6 * 0.12)["scale_x"], 1.05)

    def test_pop_hides_before_start(self):
        from studio.moves import expand
        pose = self.keys(expand(self.shot(motion=[{"recipe": "pop", "t": 1.0}])))
        self.assertEqual(pose(0.5)["opacity"], 0)
        self.assertAlmostEqual(pose(1.9)["scale_x"], 1.0, places=2)

    def test_wiggle_is_deterministic(self):
        from studio.moves import expand
        a = self.keys(expand(self.shot(wiggle=[{"prop": "rotate", "amp": 5}])))
        b = self.keys(expand(self.shot(wiggle=[{"prop": "rotate", "amp": 5}])))
        self.assertEqual(a(1.3)["rotate"], b(1.3)["rotate"])
        self.assertNotEqual(a(1.3)["rotate"], 0)

    def test_follow_lags_behind_target(self):
        from studio.moves import expand
        episode = self.shot(keyframes=[{"at": 0.2, "x": 0.1}, {"at": 0.4, "x": 0.9}])
        episode["scenes"][0]["shots"][0]["layers"].append(
            {"id": "b", "kind": "rect", "x": 0.1, "y": 0.5, "follow": {"target": "a", "lag": 0.1}})
        episode = expand(episode)
        lead, chase = self.keys(episode, "a"), self.keys(episode, "b")
        self.assertLess(chase(0.8)["x"], lead(0.8)["x"])
        self.assertAlmostEqual(chase(2.0)["x"], 0.9, places=2)


class PoseTests(unittest.TestCase):
    def test_pose_keys_blend_parts_and_mouth(self):
        from studio.character import POSES, build_parts, rig_layers
        from studio.design import pose_at, poses
        from studio.expand import expand as expand_defs
        from studio.poses import expand as expand_poses
        spec, parts = build_parts({"id": "t"})
        episode = {"defs": {"t": rig_layers(spec, parts, "art/characters/t")}, "scenes": [{"shots": [{
            "id": "A", "duration": 3.0, "layers": [{"id": "hero", "kind": "use", "ref": "t", "x": 0.5, "y": 0.8,
                                                    "pose_keys": [{"t": 1.0, "pose": "wave", "d": 0.2}]}]}]}]}
        episode = expand_poses(expand_defs(episode), {"t": POSES})
        layers = {item["id"]: item for item in episode["scenes"][0]["shots"][0]["layers"]}
        arm = poses(layers["hero/arm-r"])
        self.assertAlmostEqual(pose_at(arm, 0.1)["rotate"], -18, places=3)
        self.assertAlmostEqual(pose_at(arm, 0.9)["rotate"], -150, places=3)
        smile, rest = poses(layers["hero/mouth-smile"]), poses(layers["hero/mouth-rest"])
        self.assertTrue(pose_at(smile, 0.9)["visible"])
        self.assertFalse(pose_at(rest, 0.9)["visible"])


class MotionReportTests(unittest.TestCase):
    def test_report_flags_dead_hold_linear_and_lockstep(self):
        from studio.motion_report import report
        moves = [{"id": f"m{i}", "kind": "rect", "x": 0.2, "y": 0.2 + i * 0.1,
                  "keyframes": [{"at": 0.1, "x": 0.2}, {"at": 0.3, "x": 0.8}]} for i in range(3)]
        shot = {"id": "A", "duration": 4.0, "layers": moves}
        episode = {"fps": 24, "scenes": [{"shots": [shot]}]}
        data, charts = report(episode, episode)
        kinds = {note["kind"] for note in data["shots"][0]["notes"]}
        self.assertEqual(kinds, {"dead-hold", "linear", "lockstep"})
        self.assertIn("m0", charts["A"])

    def test_contrast_flags_text_matching_background(self):
        from studio.motion_report import contrast_notes
        palette = {"background": "#131B30", "foreground": "#FFF3D8", "accent": "#FFBD54", "muted": "#1A2440"}
        shot = {"id": "A", "duration": 2.0, "layers": [
            {"id": "dim", "kind": "text", "text": "HI", "x": 0.5, "y": 0.2, "width": 0.5, "height": 0.1, "fill": "muted"},
            {"id": "saved", "kind": "text", "text": "HI", "x": 0.5, "y": 0.3, "width": 0.5, "height": 0.1,
             "fill": "muted", "stroke": {"width": 0.08, "color": "foreground"}},
            {"id": "card", "kind": "rect", "x": 0.5, "y": 0.7, "width": 0.8, "height": 0.2, "fill": "foreground"},
            {"id": "on-card", "kind": "text", "text": "HI", "x": 0.5, "y": 0.7, "width": 0.5, "height": 0.1,
             "fill": "#FFFFFF"},
            {"id": "ok", "kind": "text", "text": "HI", "x": 0.5, "y": 0.45, "width": 0.5, "height": 0.1,
             "fill": "accent"}]}
        flagged = {note["layer"] for note in contrast_notes(shot, palette)}
        self.assertEqual(flagged, {"dim", "on-card"})

    def test_onion_skin_composites(self):
        from tempfile import TemporaryDirectory
        from PIL import Image, ImageDraw
        from studio.still import onion_skin
        with TemporaryDirectory() as temp:
            frames = {}
            for offset in (-1, 0, 1):
                image = Image.new("RGB", (80, 40), "#101020")
                ImageDraw.Draw(image).rectangle((30 + offset * 20, 10, 40 + offset * 20, 20), fill="#FFFFFF")
                frames[offset] = Path(temp) / f"{offset}.png"
                image.save(frames[offset])
            out = onion_skin(frames, Path(temp) / "onion.png")
            with Image.open(out) as result:
                self.assertEqual(result.getpixel((35, 15)), (255, 255, 255))
                past = result.getpixel((15, 15))
                self.assertGreater(past[0], past[2])


class DepthTests(unittest.TestCase):
    def width(self, z, camera, parent=None):
        from studio.transform import apply, layer_matrix
        matrix = layer_matrix({"x": 0.6, "y": 0.5, "z": z}, 1080, 1920, [0.5, 0.5], camera=camera, box=(100, 100))
        return apply(matrix, 100, 0)[0] - apply(matrix, 0, 0)[0], apply(matrix, 50, 50)

    def test_rest_camera_keeps_authored_layout(self):
        for z in (0, 2, 8):
            width, centre = self.width(z, {"x": 0, "y": 0, "zoom": 1, "rotate": 0})
            self.assertAlmostEqual(width, 100)
            self.assertAlmostEqual(centre[0], 648)

    def test_dolly_zoom_holds_subject_and_shrinks_background(self):
        camera = {"x": 0, "y": 0, "zoom": 0.627, "rotate": 0, "z": 0.4}
        self.assertAlmostEqual(self.width(0, camera)[0], 100, delta=0.3)
        self.assertLess(self.width(4, camera)[0], 75)

    def test_far_layers_pan_less(self):
        camera = {"x": 0.1, "y": 0, "zoom": 1, "rotate": 0}
        near, far = self.width(0, camera)[1][0], self.width(5, camera)[1][0]
        self.assertAlmostEqual(near - 648, 108)
        self.assertLess(far - 648, 30)

    def test_children_get_the_camera_once(self):
        from studio.transform import apply, layer_matrix
        camera = {"x": 0, "y": 0, "zoom": 2.0, "rotate": 0}
        parent = layer_matrix({"x": 0.5, "y": 0.5}, 1080, 1920, [0.5, 0.5], camera=camera, box=(100, 100))
        child = layer_matrix({"x": 0.1, "y": 0}, 1080, 1920, [0.5, 0.5], parent=parent, parent_origin=(50, 50),
                             camera=camera, box=(10, 10))
        self.assertAlmostEqual(apply(child, 5, 5)[0] - apply(parent, 50, 50)[0], 216)

    def test_depth_order_far_to_near(self):
        from studio.design import depth_order
        layers = [{"id": "near", "z": -0.2}, {"id": "far", "z": 5}, {"id": "kid", "parent": "far"}, {"id": "mid"}]
        self.assertEqual([layer["id"] for layer in depth_order(layers)], ["far", "kid", "mid", "near"])


class CameraRigTests(unittest.TestCase):
    scene = {"camera": {"position": [0, 1, 4], "target": [0, 0, 0]},
             "objects": [{"id": "hero", "kind": "box", "position": [0, 0, 0]}]}

    def test_orbit_keeps_radius_and_height(self):
        import math
        from studio.rig3d import camera_keys
        keys = camera_keys({"kind": "orbit", "from": -30, "to": 60}, self.scene, {}, 2.0)
        for key in keys:
            x, y, z = key["position"]
            self.assertAlmostEqual(math.hypot(x, z), 4, places=3)
            self.assertAlmostEqual(y, 1, places=3)
        self.assertAlmostEqual(math.degrees(math.atan2(keys[-1]["position"][0], keys[-1]["position"][2])), 60, places=2)

    def test_dolly_moves_toward_target(self):
        from studio.rig3d import camera_keys
        keys = camera_keys({"kind": "dolly", "to": 2.0}, self.scene, {}, 1.0)
        self.assertAlmostEqual(sum(v * v for v in keys[-1]["position"]) ** 0.5, 2.0, places=3)

    def test_follow_tracks_object_keys(self):
        from studio.rig3d import camera_keys
        three = {"objects": {"hero": [{"at": 1, "position": [4, 0, 0]}]}}
        keys = camera_keys({"kind": "follow", "object": "hero", "offset": [0, 1, 3], "lag": 0}, self.scene, three, 2.0)
        self.assertEqual(keys[-1]["target"], [4, 0, 0])
        self.assertEqual(keys[-1]["position"], [4, 1, 3])


class PaintKeyTests(unittest.TestCase):
    def test_tint_color_interpolates(self):
        layer = {"id": "a", "kind": "rect", "x": 0.5, "y": 0.5, "tint_color": "#000000",
                 "keyframes": [{"at": 1, "tint_color": "#FF8000"}]}
        middle = pose_at(poses(layer), 0.5)["tint_color"]
        self.assertAlmostEqual(middle[0], 127.5)
        self.assertAlmostEqual(middle[1], 64)

    def test_wipe_tile_reveals_from_edge(self):
        from PIL import Image
        from studio.design import wipe_tile
        tile = Image.new("RGBA", (100, 20), (255, 255, 255, 255))
        half = wipe_tile(tile, 0.5, "left")
        self.assertEqual(half.getpixel((10, 10))[3], 255)
        self.assertEqual(half.getpixel((90, 10))[3], 0)
        right = wipe_tile(tile, 0.25, "right")
        self.assertEqual(right.getpixel((90, 10))[3], 255)
        self.assertEqual(right.getpixel((10, 10))[3], 0)

    def test_turn_point_projects_card_flip(self):
        from studio.design import turn_point
        self.assertEqual(turn_point(10, 5, 0, 0, 100), (10, 5))
        x, y = turn_point(10, 0, 0, 90, 100)
        self.assertAlmostEqual(x, 0, places=6)
        x, y = turn_point(10, 0, 0, 180, 100)
        self.assertAlmostEqual(x, -10, places=6)
        # Positive turn_y swings the left edge away: it shrinks, the right edge grows.
        far, _ = turn_point(-10, 0, 0, 30, 100)
        near, _ = turn_point(10, 0, 0, 30, 100)
        self.assertGreater(abs(near), abs(far))

    def test_turn_tile_keeps_pivot_and_narrows(self):
        from PIL import Image
        from studio.design import turn_tile
        tile = Image.new("RGBA", (100, 50), (255, 255, 255, 255))
        flat, pivot = turn_tile(tile, 0, 0, [0.5, 0.5])
        self.assertEqual(flat.size, (160, 110))
        self.assertEqual(pivot, [0.5, 0.5])
        self.assertEqual(flat.getpixel((80, 55))[3], 255)
        turned, _ = turn_tile(tile, 0, 60, [0.5, 0.5])
        box = turned.getchannel("A").point(lambda a: 255 if a > 128 else 0).getbbox()
        self.assertLess(box[2] - box[0], 70)
        self.assertGreater(box[2] - box[0], 40)

    def test_turn_is_keyable(self):
        layer = {"id": "a", "kind": "rect", "x": 0.5, "y": 0.5,
                 "keyframes": [{"at": 1, "turn_y": 180}]}
        self.assertAlmostEqual(pose_at(poses(layer), 0.5)["turn_y"], 90)

    def test_compose_keeps_tint_color_hex(self):
        from studio.keys import compose
        layer = {"id": "a", "kind": "rect", "x": 0.5, "y": 0.5, "tint_color": "#000000",
                 "keyframes": [{"at": 1, "tint_color": "#FFFFFF"}]}
        compose(layer, 1.0, [lambda t: {"x": ("add", 0.1)}])
        self.assertTrue(all(key["tint_color"].startswith("#") for key in layer["keyframes"]))


class CaptionPlacementTests(unittest.TestCase):
    def test_kinetic_caption_moves_off_face(self):
        from studio.caption_place import place
        shot = {"id": "A", "duration": 2.0, "layers": [
            {"id": "hero", "kind": "group", "x": 0.5, "y": 0.62},
            {"id": "hero/head", "kind": "svg", "role": "head", "parent": "hero", "x": 0, "y": 0,
             "width": 0.4, "height": 0.2, "pivot": [0.5, 0.5]}]}
        episode = {"scenes": [{"shots": [shot]}]}
        timeline = {"scenes": [{"shots": [{"id": "A", "start": 0, "end": 48}]}],
                    "captions": [{"start": 5, "end": 30, "words": []}]}
        place(timeline, episode, {"style": "kinetic", "position": "center", "offset": 0.12})
        self.assertEqual(timeline["captions"][0]["placement"]["position"], "top")

    def test_clear_caption_keeps_its_position(self):
        from studio.caption_place import place
        shot = {"id": "A", "duration": 2.0, "layers": [
            {"id": "sign", "kind": "rect", "caption_avoid": True, "x": 0.5, "y": 0.2, "width": 0.3, "height": 0.1}]}
        timeline = {"scenes": [{"shots": [{"id": "A", "start": 0, "end": 48}]}],
                    "captions": [{"start": 5, "end": 30, "words": []}]}
        place(timeline, {"scenes": [{"shots": [shot]}]}, {"style": "kinetic", "position": "bottom"})
        self.assertNotIn("placement", timeline["captions"][0])


class BoilTests(unittest.TestCase):
    def test_variants_jitter_geometry_deterministically(self):
        from studio.boil import variants
        svg = '<svg viewBox="0 0 100 100"><path d="M10 10 C20 20 30 30 40 40" fill="#FFF"/><circle cx="50" cy="50" r="5"/></svg>'
        first, second = variants(svg, 1.0), variants(svg, 1.0)
        self.assertEqual(first, second)
        self.assertEqual(len(set(first)), 3)
        self.assertIn('r="5"', first[0])
        self.assertIn('fill="#FFF"', first[0])


class CaptionAuditTests(unittest.TestCase):
    def test_audit_flags_speed_flicker_and_ui_zone(self):
        from studio.captions import audit
        words = [{"text": w, "start": i, "end": i + 1} for i, w in enumerate("one two three four five six".split())]
        timeline = {"fps": 24, "captions": [{"start": 0, "end": 12, "words": words, "text": "x"}]}
        kinds = {note["kind"] for note in audit(timeline, {"style": "kinetic", "position": "bottom", "offset": 0.1})}
        self.assertEqual(kinds, {"fast", "short", "flicker", "ui-zone"})


class CueShapeTests(unittest.TestCase):
    def test_punch_and_highpass(self):
        import numpy as np
        from studio.audio import shape_tone
        rate = 48000
        t = np.arange(rate // 4) / rate
        clip = (0.3 * np.sin(2 * np.pi * 60 * t) + 0.3 * np.sin(2 * np.pi * 3000 * t)).astype(np.float32)
        filtered = shape_tone(clip, {"highpass": 800})
        low = np.abs(np.fft.rfft(filtered))[15]
        self.assertLess(low, np.abs(np.fft.rfft(clip))[15] * 0.3)
        punched = shape_tone(clip, {"punch": 1.0})
        self.assertLessEqual(float(np.max(np.abs(punched))), float(np.max(np.abs(clip))) + 1e-6)

    def test_sfx_density_note(self):
        from studio.captions import sfx_density
        cues = [{"start": i * 3} for i in range(8)]
        timeline = {"fps": 24, "scenes": [{"shots": [{"sfx": cues}]}]}
        self.assertEqual(sfx_density(timeline)[0]["kind"], "sfx-dense")


class GradeTests(unittest.TestCase):
    def test_identity_cube_is_identity_and_looks_change_colour(self):
        import numpy as np
        from tempfile import TemporaryDirectory
        from studio.grade import apply, bake, load_cube
        with TemporaryDirectory() as temp:
            path = Path(temp) / "identity.cube"
            axis = [i / 3 for i in range(4)]
            rows = [f"{r} {g} {b}" for b in axis for g in axis for r in axis]
            path.write_text("LUT_3D_SIZE 4\n" + "\n".join(rows), encoding="utf-8")
            size, lut = load_cube(str(path))
        colours = np.array([[[0.2, 0.5, 0.9], [0.8, 0.3, 0.1]]], dtype=np.float32)
        self.assertTrue(np.allclose(apply(colours, size, lut), colours, atol=1e-5))
        size, teal = bake("teal-orange")
        graded = apply(np.array([[[0.1, 0.1, 0.1]]], dtype=np.float32), size, teal)[0, 0]
        self.assertGreater(graded[2], graded[0])  # Shadows lean teal.


class FinishPassTests(unittest.TestCase):
    SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
           '<defs><linearGradient id="g"><stop offset="0"/></linearGradient></defs>'
           '<circle cx="50" cy="50" r="40"/><g><rect x="100" y="10" width="80" height="80"/></g></svg>')

    def test_silhouette_wraps_whole_drawing(self):
        import xml.etree.ElementTree as ET
        from studio.stylepass import apply
        out = apply(self.SVG, {"shade": 0.4, "rim": 0.3, "texture": 0.2, "outline": 0.02}, uid="f")
        root = ET.fromstring(out)
        self.assertEqual(out.count('filter="url(#f)"'), 1)
        names = {child.tag.split("}")[1] for child in root.iter()}
        self.assertTrue({"feOffset", "feTurbulence", "feMorphology"} <= names)
        # Light from the top left: the shade band offsets toward the light.
        offset = next(node for node in root.iter() if node.tag.endswith("feOffset"))
        self.assertLess(float(offset.get("dx")), 0)

    def test_shapes_mode_wraps_each_top_level_element(self):
        import xml.etree.ElementTree as ET
        from studio.stylepass import apply
        out = apply(self.SVG, {"per": "shapes"}, uid="f")
        ET.fromstring(out)
        self.assertEqual(out.count('filter="url(#f)"'), 2)
        self.assertNotIn('<g filter="url(#f)"><defs>', out)

    def test_finish_is_valid_layer_field(self):
        schema = json.loads((ROOT / "studio" / "schema.json").read_text())
        finish = schema["$defs"]["layer"]["properties"]["finish"]
        self.assertIn("outline", finish["properties"])


class PaintTests(unittest.TestCase):
    PALETTE = {"background": "#000000", "foreground": "#FFFFFF", "accent": "#FF0000"}

    def test_fill_and_stroke_interpolate(self):
        from studio.paint import look, paint_at, track
        layer = {"id": "a", "kind": "rect", "x": 0.5, "y": 0.5, "fill": "background",
                 "keyframes": [{"at": 1, "fill": "foreground", "stroke_width": 0.2, "stroke_color": "accent"}]}
        middle = look(paint_at(track(layer, self.PALETTE), 0.5))
        self.assertEqual(middle["fill"], "#808080")
        self.assertEqual(middle["stroke"]["width"], 0.1)

    def test_solid_blends_into_gradient(self):
        from studio.paint import look, paint_at, track
        gradient = {"type": "linear", "angle": 0, "stops": [{"at": 0, "color": "#FF0000"}, {"at": 1, "color": "#0000FF"}]}
        layer = {"id": "a", "kind": "rect", "x": 0.5, "y": 0.5, "fill": "#000000",
                 "keyframes": [{"at": 1, "fill": gradient}]}
        fill = look(paint_at(track(layer, self.PALETTE), 0.5))["fill"]
        self.assertEqual([stop["color"] for stop in fill["stops"]], ["#800000", "#000080"])

    def test_expand_keeps_motion_and_steps_frames(self):
        from studio.paint import expand
        layer = {"id": "a", "kind": "ellipse", "x": 0.2, "y": 0.5, "fill": "background",
                 "keyframes": [{"at": 1, "x": 0.8, "fill": "foreground", "ease": "smooth"}]}
        episode = {"fps": 24, "scenes": [{"shots": [{"id": "A", "duration": 1.0, "layers": [layer]}]}]}
        expand(episode, {"palette": self.PALETTE})
        self.assertGreater(len(layer["paint_frames"]), 10)
        self.assertEqual(layer["paint_frames"][-1]["fill"], "#FFFFFF")
        points = poses(layer)
        self.assertAlmostEqual(pose_at(points, 0.5)["x"], 0.5, places=2)
        self.assertEqual(pose_at(points, 1.0)["frame"], len(layer["paint_frames"]) - 1)

    def test_gradient_past_ninety_degrees_is_not_clipped(self):
        from studio.design import gradient_image
        image = gradient_image((10, 4), {"angle": 180, "stops": [{"at": 0, "color": "#FF0000"},
                                                                  {"at": 1, "color": "#0000FF"}]}, self.PALETTE)
        self.assertGreater(image.getpixel((9, 1))[0], 200)
        self.assertGreater(image.getpixel((0, 1))[2], 200)


class DiscoverTests(unittest.TestCase):
    def fake(self, views):
        from datetime import datetime, timezone
        published = {"a": "2026-11-14T12:00:00Z", "b": "2026-11-10T12:00:00Z", "c": "2026-11-14T00:00:00Z"}
        lengths = {"a": "PT45S", "b": "PT58S", "c": "PT9M"}
        channel = {"a": "UC1", "b": "UC2", "c": "UC3"}

        def request(endpoint, key, **params):
            if endpoint == "search":
                return [{"id": {"videoId": vid}} for vid in "abc"]
            if endpoint == "videoCategories":
                return [{"id": "1", "snippet": {"title": "Film & Animation"}}]
            if endpoint == "videos":
                return [{"id": vid, "snippet": {"title": vid, "channelTitle": channel[vid], "channelId": channel[vid],
                                                "publishedAt": published[vid], "categoryId": "1",
                                                "liveBroadcastContent": "none"},
                         "contentDetails": {"duration": lengths[vid]},
                         "statistics": {"viewCount": str(views[vid])}} for vid in params["id"].split(",")]
            if endpoint == "channels":
                return [{"id": "UC1", "statistics": {"subscriberCount": "1000"}},
                        {"id": "UC2", "statistics": {"subscriberCount": "2000000"}}]
            return []
        return request, datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

    def test_velocity_outlier_shorts_and_snapshot_growth(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"YOUTUBE_API_KEY": "test"}):
            self.check_discover()

    def check_discover(self):
        import os
        from tempfile import TemporaryDirectory
        from datetime import timedelta
        from studio.research import discover
        request, now = self.fake({"a": 240000, "b": 900000, "c": 5000000})
        by_views = discover(["q"], "US", None, 5, request, now, shorts=True)
        self.assertEqual([c["channel"] for c in by_views["channels"]], ["UC2", "UC1"])  # 9-minute video dropped.
        by_speed = discover(["q"], "US", None, 5, request, now, shorts=True, rank="velocity")
        self.assertEqual(by_speed["channels"][0]["channel"], "UC1")  # 240k in 24h beats 900k in 5 days.
        self.assertEqual(by_speed["channels"][0]["videos"][0]["views_per_hour"], 10000.0)
        by_outlier = discover(["q"], "US", None, 5, request, now, shorts=True, rank="outlier")
        self.assertEqual(by_outlier["channels"][0]["videos"][0]["views_per_subscriber"], 240.0)
        with TemporaryDirectory() as folder:
            discover(["q"], "US", None, 5, request, now, shorts=True, snapshots=folder)
            later_request, _ = self.fake({"a": 300000, "b": 910000, "c": 5000000})
            later = discover(["q"], "US", None, 5, later_request, now + timedelta(hours=6), shorts=True,
                             rank="velocity", snapshots=folder)
            video = later["channels"][0]["videos"][0]
            self.assertEqual(video["views_gained"], 60000)
            self.assertEqual(video["views_per_hour_since_last"], 10000.0)
            self.assertEqual(len(os.listdir(folder)), 2)


class MorphShapeTests(unittest.TestCase):
    def test_svg_blend_interpolates_numbers_and_colours(self):
        from studio.morph import blend, compatible
        a = '<svg viewBox="0 0 10 10"><path d="M0 0 L10 0" fill="#000000"/></svg>'
        b = '<svg viewBox="0 0 10 10"><path d="M0 4 L10 8" fill="#FF8000"/></svg>'
        self.assertIsNone(compatible(a, b))
        self.assertEqual(blend(a, b, 0.5), '<svg viewBox="0 0 10 10"><path d="M0 2 L10 4" fill="#804000"/></svg>')
        self.assertIn("structure", compatible(a, a.replace("L10 0", "C1 1 2 2 10 0")))

    def test_svg_morph_keys_frames(self):
        from studio.morph import MORPH_LEVELS, expand
        layer = {"id": "m", "kind": "svg", "file": "a.svg", "morph_to": "b.svg", "x": 0.5, "y": 0.5,
                 "keyframes": [{"at": 1, "morph": 1}]}
        expand({"fps": 24, "scenes": [{"shots": [{"id": "A", "duration": 1.0, "layers": [layer]}]}]})
        points = poses(layer)
        self.assertEqual(pose_at(points, 1.0)["frame"], MORPH_LEVELS - 1)
        self.assertEqual(pose_at(points, 0.5)["frame"], (MORPH_LEVELS - 1) // 2)

    def test_polygon_morph_keeps_corners(self):
        from studio.paint import look, paint_at, track
        star = [[0.5, 0], [0.62, 0.35], [1, 0.38], [0.7, 0.6], [0.8, 1], [0.5, 0.78], [0.2, 1], [0.3, 0.6],
                [0, 0.38], [0.38, 0.35]]
        layer = {"id": "p", "kind": "polygon", "x": 0.5, "y": 0.5, "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
                 "keyframes": [{"at": 1, "points": star}]}
        end = look(paint_at(track(layer, {}), 1.0))["points"]
        for corner in star:
            self.assertIn(corner, end)
        self.assertEqual(len(end), len(look(paint_at(track(layer, {}), 0.0))["points"]))


class BendTests(unittest.TestCase):
    def test_bend_point_follows_an_arc(self):
        import math
        from studio.design import bend_point
        length = 100
        k = math.radians(90) / length
        x, y, turn = bend_point(0, length, k, length)
        self.assertAlmostEqual(x, 200 / math.pi, places=4)  # Quarter circle of radius 2L/pi, swinging right.
        self.assertAlmostEqual(y, 200 / math.pi, places=4)
        self.assertAlmostEqual(turn, 90)
        self.assertEqual(bend_point(3, -5, k, length), (3, -5, 0.0))  # Above the pivot stays rigid.

    def test_bent_tile_keeps_coverage_and_children_ride_the_tip(self):
        from PIL import Image
        from studio.design import bend_child, bend_tile
        tile = Image.new("RGBA", (20, 120), (255, 0, 0, 255))
        bent, pivot = bend_tile(tile, 90, [0.5, 1 / 6])
        area = sum(1 for value in bent.getchannel("A").getdata() if value > 128)
        self.assertAlmostEqual(area / (20 * 120), 1.0, delta=0.06)
        child = bend_child({"x": 0, "y": 100 / 1000, "rotate": 0}, 90, (20, 120), [0.5, 1 / 6], 1000, 1000)
        self.assertAlmostEqual(child["rotate"], 90)
        self.assertGreater(child["x"], 0.05)


class CharacterArchetypeTests(unittest.TestCase):
    def test_archetypes_build_their_signature_parts(self):
        from studio.character import ARCHETYPES, build_parts
        expected = {"human": {"head", "hair", "hair-back", "nose"}, "cat": {"tail", "nose", "ear-l"},
                    "dog": {"tail", "nose", "ear-r"}, "bird": {"nose", "tail"}, "robot": {"antenna"}, "blob": set()}
        for name in ARCHETYPES:
            spec, parts = build_parts({"id": name, "archetype": name})
            names = {part.name for part in parts}
            self.assertTrue(expected[name] <= names, (name, expected[name] - names))
            order = [part.name for part in parts]
            if "tail" in names:  # Behind the body: drawn first and parented to the rig root.
                self.assertLess(order.index("tail"), order.index("body"))
                self.assertIsNone(next(p for p in parts if p.name == "tail").parent)

    def test_spec_overrides_archetype_and_unknown_is_rejected(self):
        from studio.character import build_parts
        spec, parts = build_parts({"id": "x", "archetype": "cat", "tail": "none", "palette": {"body": "#123456"}})
        self.assertNotIn("tail", {part.name for part in parts})
        self.assertEqual(spec["palette"]["body"], "#123456")
        with self.assertRaises(ValueError):
            build_parts({"id": "x", "archetype": "dragon"})

    def test_alive_wags_tails(self):
        from studio.life import expand as expand_life
        shot = {"id": "A", "duration": 2.0, "layers": [
            {"id": "c", "kind": "group", "x": 0.5, "y": 0.8, "alive": True},
            {"id": "c/tail", "kind": "svg", "role": "tail", "parent": "c", "x": 0.05, "y": -0.05, "rotate": 120}]}
        expand_life({"scenes": [{"shots": [shot]}]})
        tail = shot["layers"][1]
        bends = {round(key.get("bend", 0), 2) for key in tail.get("keyframes", [])}
        self.assertGreater(len(bends), 5)


class Physics3DTests(unittest.TestCase):
    def test_bodies_fall_bounce_collide_and_settle(self):
        import math
        from studio.physics3d import expand, simulate
        objects = [{"id": "ball", "kind": "sphere", "position": [0, 3, -3], "scale": [0.5, 0.5, 0.5]},
                   {"id": "roller", "kind": "sphere", "position": [-1.5, 0.25, 0], "scale": [0.5, 0.5, 0.5]},
                   {"id": "target", "kind": "sphere", "position": [1.0, 0.25, 0], "scale": [0.5, 0.5, 0.5]},
                   {"id": "crate", "kind": "box", "position": [-2, 2, 0], "scale": [0.6, 0.6, 0.6]}]
        keys = simulate(objects, {"bodies": {"ball": {"bounce": 0.5}, "roller": {"velocity": [3, 0, 0]}, "target": {},
                                             "crate": {"spin": [0, 0, 200]}}}, 4.0)
        ball_heights = [key["position"][1] for key in keys["ball"]]
        self.assertAlmostEqual(min(ball_heights), 0.25, places=3)  # Rests on its radius, never sinks.
        self.assertGreater(keys["target"][-1]["position"][0], 1.3)  # Knocked along by the roller.
        turn = keys["crate"][-1]["rotation"][2] / (math.pi / 2)
        self.assertAlmostEqual(turn, round(turn), places=2)  # Settled on a face.
        episode = {"scenes": [{"shots": [{"id": "A", "duration": 1.0, "three": {
            "scene": "s", "physics": {"bodies": {"ball": {}}}, "objects": {"ball": [{"at": 1, "visible": False}]}}}]}]}
        expand(episode, ({"scenes": {"s": {"objects": objects}}}, None))
        baked = episode["scenes"][0]["shots"][0]["three"]["objects"]["ball"]
        self.assertTrue(all("position" in key for key in baked))
        self.assertFalse(baked[-1]["visible"])


class Rig3DTests(unittest.TestCase):
    def test_generated_character_is_a_valid_skinned_glb(self):
        from tempfile import TemporaryDirectory
        from studio.glbcharacter import write_glb
        from studio.scenes import check_glb, node_names
        with TemporaryDirectory() as folder:
            result = write_glb(Path(folder) / "hero.glb", {"shirt": "#FF0000"})
            model = check_glb(Path(folder) / "hero.glb")
        self.assertEqual(len(model["skins"][0]["joints"]), len(result["bones"]))
        names = node_names(model)
        self.assertTrue({"Hips", "Head", "UpperArm.L", "LowerArm.R", "Foot.L", "UpperArmL"} <= names)
        self.assertEqual(result["vertices"] % 3, 0)

    def test_unknown_bones_and_ik_targets_are_rejected(self):
        from studio.scenes import validate_three
        scene = {"objects": [{"id": "hero", "kind": "glb", "_nodes": ["Hips", "UpperArm.R", "LowerArm.R", "Hand.R"]},
                             {"id": "ball", "kind": "sphere"}]}
        library = ({"scenes": {"s": scene}}, None)
        ok = {"id": "A", "three": {"scene": "s", "objects": {"hero": [{"at": 1, "bones": {"Hips": [0, 10, 0]}}]},
                                   "ik": {"hero": [{"chain": ["UpperArm.R", "LowerArm.R", "Hand.R"],
                                                    "keys": [{"at": 0.5, "object": "ball"}]}]}}}
        validate_three(ok, library)
        bad = {"id": "A", "three": {"scene": "s", "objects": {"hero": [{"at": 1, "bones": {"Spine": [0, 1, 0]}}]}}}
        with self.assertRaisesRegex(ValueError, "Spine"):
            validate_three(bad, library)
        missing = {"id": "A", "three": {"scene": "s", "ik": {"hero": [{"chain": ["UpperArm.R", "Hand.R"],
                                                                        "keys": [{"at": 0.5, "object": "moon"}]}]}}}
        with self.assertRaisesRegex(ValueError, "moon"):
            validate_three(missing, library)


class VoiceActingTests(unittest.TestCase):
    def test_pitch_pace_and_intensity_change_the_take(self):
        import numpy as np
        from studio.audio import act
        from studio.core import SAMPLE_RATE
        t = np.arange(SAMPLE_RATE) / SAMPLE_RATE
        tone = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

        def peak(signal):
            spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
            return np.argmax(spectrum) * SAMPLE_RATE / len(signal)
        self.assertAlmostEqual(peak(act(tone, {"pitch": 12})), 440, delta=3)
        self.assertAlmostEqual(len(act(tone, {"pace": 1.25})) / SAMPLE_RATE, 0.8, delta=0.03)
        self.assertIs(act(tone, {}), tone)

    def test_command_engine_runs_a_local_tts_program(self):
        import sys
        from tempfile import TemporaryDirectory
        from studio.audio import spoken_take
        script = ("import sys, wave, math\n"
                  "text = sys.stdin.read()\n"
                  "w = wave.open(sys.argv[1], 'wb'); w.setparams((1, 2, 24000, 0, 'NONE', 'none'))\n"
                  "w.writeframes(b''.join(int(12000 * math.sin(i / 8)).to_bytes(2, 'little', signed=True)"
                  " for i in range(2400 * max(1, len(text) // 5))))\n")
        with TemporaryDirectory() as folder:
            tts = Path(folder) / "tts.py"
            tts.write_text(script)
            profile = {"engine": "command", "command": [sys.executable, str(tts), "{out}"], "direction": "test"}
            clip, source, detail = spoken_take({"speaker": "N", "text": "Hello there friend"}, {}, Path(folder),
                                               Path(folder), profile, None)
            self.assertIn("Local TTS", source)
            self.assertGreater(len(clip), 1000)
            cached = list((Path(folder) / ".audio-takes").glob("*.wav"))
            self.assertEqual(len(cached), 1)


class MusicLibraryTests(unittest.TestCase):
    def test_import_tags_moods_and_episode_mood_picks_a_track(self):
        import subprocess
        from tempfile import TemporaryDirectory
        from studio.music import expand, import_music
        from studio.core import validate
        with TemporaryDirectory() as folder:
            source, channel_dir = Path(folder) / "pack", Path(folder) / "channel"
            (source / "Calm Piano").mkdir(parents=True)
            (source / "Hype").mkdir()
            channel_dir.mkdir()
            for path, freq in ((source / "Calm Piano" / "soft_morning.wav", 220), (source / "Hype" / "drive_fast.wav", 440)):
                subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                                f"sine=frequency={freq}:duration=8", str(path)], check=True)
            result = import_music(channel_dir, source)
            self.assertEqual(len(result["added"]), 2)
            self.assertEqual(import_music(channel_dir, source)["added"], [])  # Deduplicated by hash.
            channel = {"music_library": "audio/music/index.json"}
            episode = {"title": "Test", "music": {"mood": "action", "gain": 0.05},
                       "scenes": [{"shots": [{"duration": 6}]}]}
            picked = expand(episode, channel, channel_dir)["music"]
            self.assertTrue(picked["library_file"].endswith(".wav"))
            self.assertIn("drive", picked["library_file"])
            self.assertEqual(picked["gain"], 0.05)
            self.assertNotIn("mood", picked)
            validate({"mood": "calm", "energy": "low", "bpm": [70, 90]}, "music")
            with self.assertRaises(Exception):
                validate({"preset": "pulse", "file": "a.wav"}, "music")


class LipSyncTests(unittest.TestCase):
    def test_words_become_held_visemes_with_closures_and_rests(self):
        from studio.lipsync import visemes
        words = [{"start": 0.0, "end": 0.4}, {"start": 0.45, "end": 0.9}, {"start": 1.5, "end": 1.9}]
        keys = visemes("Bob made pies", words, None, 30)
        shapes = [key["shape"] for key in keys]
        self.assertIn("mbp", shapes)
        self.assertEqual(shapes[-1], "rest")
        rest_at = [key["at"] for key in keys if key["shape"] == "rest"]
        self.assertTrue(any(0.85 <= at <= 0.95 for at in rest_at))  # Pause between "made" and "pies".
        frames = [round(key["at"] * 30) for key in keys]
        self.assertTrue(all(b - a >= 2 for a, b in zip(frames, frames[1:])))  # No one-frame flicker.
        self.assertEqual(frames, sorted(frames))

    def test_silence_closes_the_mouth_and_spelling_fallback_works(self):
        from studio.lipsync import spelling_shapes, visemes
        levels = [0.5] * 10 + [0.0] * 8 + [0.5] * 10
        keys = visemes("aaaa", [{"start": 0, "end": 28 / 30}], levels, 30)
        self.assertIn("rest", [key["shape"] for key in keys[:-1]])
        self.assertEqual(spelling_shapes("phone"), ["fv", "o", "etc"])

    def test_resolve_maps_to_the_characters_mouths(self):
        from studio.lipsync import resolve
        basic = {"rest", "open", "o"}
        self.assertEqual(resolve("mbp", basic), "rest")
        self.assertEqual(resolve("ai", basic), "open")
        self.assertEqual(resolve("u", basic), "o")
        self.assertEqual(resolve("D", {"ai", "rest"}), "ai")  # Rhubarb letters.

    def test_active_viseme_overrides_variant_visibility(self):
        from studio.design import Composition, resolve_font
        channel = {"palette": {"background": "#000000", "foreground": "#FFFFFF", "accent": "#FF0000",
                               "secondary": "#0000FF"}}
        layers = [{"id": name, "kind": "rect", "x": 0.5, "y": 0.5, "width": 0.5, "height": 0.5, "fill": fill,
                   "variant_group": "m", "viseme_for": "Hero", "viseme": name, "visible": name == "rest"}
                  for name, fill in (("rest", "accent"), ("o", "secondary"))]
        design = Composition({"id": "A", "duration": 1, "layers": layers}, (40, 40), channel,
                             resolve_font(channel, Path(".")), Path("."))
        self.assertEqual(design.frame(0.5, {}, post=False, visemes={}).getpixel((20, 20))[:3], (255, 0, 0))
        self.assertEqual(design.frame(0.5, {}, post=False, visemes={"Hero": "o"}).getpixel((20, 20))[:3], (0, 0, 255))


class ViralCheckTests(unittest.TestCase):
    def test_flags_a_slow_silent_opening(self):
        from studio.viral_check import check
        slow = {"title": "The Longest Wait Ever Recorded On Any Hill Anywhere At All Tonight Friends",
                "fps": 24, "thumbnail": {"shot": "A"},
                "scenes": [{"shots": [{"id": "A", "duration": 7.0, "layers": [
                    {"id": "bg", "kind": "rect", "x": 0.5, "y": 0.5}]}]}]}
        kinds = {note["kind"] for note in check(slow, slow)["notes"]}
        self.assertTrue({"hook-motion", "hook-text", "first-shot", "pacing", "packaging"} <= kinds)
        snappy = {"title": "Pip catches a star", "fps": 24, "thumbnail": {"shot": "A", "text": "CAUGHT IT"},
                  "scenes": [{"shots": [{"id": "A", "duration": 2.5, "speech": [{"at": 0.2, "text": "Pip catches a star."}],
                                         "layers": [{"id": "s", "kind": "ellipse", "x": 0.2, "y": 0.5,
                                                     "keyframes": [{"at": 0.3, "x": 0.8}]}]},
                                        {"id": "B", "duration": 4.0, "camera": {"preset": "push-in"}, "layers": []}, {"id": "C", "duration": 3.5, "camera": {"preset": "float"}, "layers": []}, {"id": "D", "duration": 4.0, "camera": {"preset": "push-in"}, "layers": []}]}]}
        result = check(snappy, snappy)
        self.assertEqual(result["notes"], [])
        self.assertEqual(result["score"], 100)


class ChannelMemoryTests(unittest.TestCase):
    def test_creates_missing_files_and_keeps_existing(self):
        from datetime import date
        from tempfile import TemporaryDirectory
        from studio.memory import create
        with TemporaryDirectory() as root:
            created = create("demo", "ep01", root, date(2026, 1, 2))
            names = sorted(Path(path).relative_to(Path(root) / "demo").as_posix() for path in created)
            self.assertEqual(names, ["MEMORY.md", "channel/AGENTS.md", "channel/episode-ledger.md",
                                     "channel/ideas.md", "channel/series.md", "episodes/ep01/NOTES.md"])
            memory = (Path(root) / "demo" / "MEMORY.md").read_text()
            self.assertIn("Updated: 2026-01-02", memory)
            self.assertIn("## Direction history", memory)
            self.assertTrue((Path(root) / "demo/channel/AGENTS.md").read_text().startswith("# Channel rules"))
            (Path(root) / "demo" / "MEMORY.md").write_text("kept")
            self.assertEqual(create("demo", None, root), [])
            self.assertEqual((Path(root) / "demo" / "MEMORY.md").read_text(), "kept")


class RotationConventionTests(unittest.TestCase):
    def test_positive_rotate_turns_counter_clockwise_like_the_browser(self):
        # browser/painter.mjs layerMatrix uses rotate(-degrees) with the canvas [cos, sin, -sin, cos] form.
        from studio.transform import apply, layer_matrix
        matrix = layer_matrix({"x": 0, "y": 0, "rotate": 90}, 100, 100, [0, 0], box=(10, 10))
        x, y = apply(matrix, 1, 0)
        self.assertAlmostEqual(x, 0, places=6)
        self.assertAlmostEqual(y, -1, places=6)  # Screen up: counter-clockwise.

    def test_path_orient_follows_the_convention(self):
        from studio.moves import expand
        layer = {"id": "a", "kind": "rect", "x": 0.1, "y": 0.1,
                 "path": {"points": [[0.1, 0.1], [0.9, 0.9]], "orient": True, "ease": "linear"}}
        episode = {"width": 1000, "height": 1000, "scenes": [{"shots": [{"id": "A", "duration": 1.0, "layers": [layer]}]}]}
        expand(episode)
        middle = pose_at(poses(layer), 0.5)["rotate"]
        self.assertAlmostEqual(middle, -45, places=0)  # Heading down-right on screen is clockwise.


class IKTests(unittest.TestCase):
    W, H = 1080, 1920

    def shot(self, ik, flip=False, chain=2):
        layers = [{"id": "hero", "kind": "group", "x": 0.5, "y": 0.4, "ik": ik,
                   **({"scale_x": -1} if flip else {})},
                  {"id": "hero/upper", "kind": "rect", "parent": "hero", "x": 0.0, "y": 0.0, "width": 0.02,
                   "height": 0.1, "tip": [0, 0.1] if chain == 1 else None}]
        if chain == 2:
            layers.append({"id": "hero/lower", "kind": "rect", "parent": "hero/upper", "x": 0.0, "y": 0.05,
                           "width": 0.02, "height": 0.1, "tip": [0, 0.05]})
        for layer in layers:
            if layer.get("tip") is None:
                layer.pop("tip", None)
        return {"id": "A", "duration": 2.0, "layers": layers}

    def end(self, shot, seconds, chain=2):
        from studio.ik import Skeleton
        skeleton = Skeleton(shot, self.W, self.H)
        last = "hero/lower" if chain == 2 else "hero/upper"
        x, y = skeleton.point(last, seconds, skeleton.layers[last]["tip"])
        return x / self.W, y / self.H

    def run_ik(self, shot):
        from studio.ik import expand
        episode = {"width": self.W, "height": self.H, "scenes": [{"shots": [shot]}]}
        expand(episode)
        return shot

    def test_two_bone_reaches_target_and_releases(self):
        shot = self.run_ik(self.shot([{"chain": ["upper", "lower"], "keys": [
            {"t": 0.2, "x": 0.55, "y": 0.45, "d": 0.2}, {"t": 1.5, "release": True, "d": 0.2}]}]))
        x, y = self.end(shot, 1.0)
        self.assertAlmostEqual(x, 0.55, places=3)
        self.assertAlmostEqual(y, 0.45, places=3)
        # Released: back to the straight rest arm hanging down.
        x, y = self.end(shot, 2.0)
        self.assertAlmostEqual(x, 0.5, places=3)
        self.assertAlmostEqual(y, 0.5, places=3)

    def test_bend_flips_the_elbow(self):
        from studio.ik import Skeleton
        elbows = []
        for bend in (1, -1):
            shot = self.run_ik(self.shot([{"chain": ["upper", "lower"], "bend": bend,
                                           "keys": [{"t": 0, "x": 0.5, "y": 0.46, "d": 0}]}]))
            elbows.append(Skeleton(shot, self.W, self.H).world("hero/lower", 1.0)[0][0])
        # Shoulder and target share x = 540 px, so the two bends put the elbow on opposite sides.
        self.assertLess((elbows[0] - 540) * (elbows[1] - 540), -1)

    def test_one_bone_aims_on_a_mirrored_rig(self):
        shot = self.run_ik(self.shot([{"chain": ["upper"], "keys": [{"t": 0, "x": 0.6, "y": 0.4, "d": 0}]}],
                                     flip=True, chain=1))
        x, y = self.end(shot, 1.0, chain=1)
        self.assertAlmostEqual(y, 0.4, places=3)  # Aimed straight right, level with the shoulder.
        self.assertGreater(x, 0.5)

    def test_motion_report_flags_unreachable_target(self):
        from studio.motion_report import reach_notes
        ik = [{"chain": ["upper", "lower"], "keys": [{"t": 0, "x": 0.9, "y": 0.4, "d": 0}]}]
        far = self.shot(ik)
        notes = reach_notes(far, copy.deepcopy(far), self.W, self.H)
        self.assertEqual([note["kind"] for note in notes], ["reach"])
        near = self.shot([{**ik[0], "keys": [{"t": 0, "x": 0.55, "y": 0.45, "d": 0}]}])
        self.assertEqual(reach_notes(near, copy.deepcopy(near), self.W, self.H), [])

    def test_follows_a_moving_layer(self):
        shot = self.shot([{"chain": ["upper", "lower"], "keys": [{"t": 0, "layer": "ball", "d": 0}]}])
        shot["layers"].append({"id": "ball", "kind": "ellipse", "x": 0.45, "y": 0.42,
                               "keyframes": [{"at": 1, "x": 0.56, "y": 0.47}]})
        self.run_ik(shot)
        x, y = self.end(shot, 1.0)
        self.assertAlmostEqual(x, 0.505, places=2)
        self.assertAlmostEqual(y, 0.445, places=2)


class MorphTests(unittest.TestCase):
    MODEL = {"meshes": [{"primitives": [{"targets": [{}, {}]}], "extras": {"targetNames": ["smile", "blink"]}},
                        {"primitives": [{"targets": [{}]}]}]}

    def test_morph_names_include_labels_and_indices(self):
        from studio.scenes import morph_names
        self.assertEqual(morph_names(self.MODEL), {"smile", "blink", "0", "1"})

    def test_unknown_morph_key_is_rejected(self):
        from studio.scenes import validate_three
        scene = {"objects": [{"id": "face", "kind": "glb", "_morphs": ["smile"]}]}
        library = ({"scenes": {"s": scene}}, None)
        good = {"id": "A", "three": {"scene": "s", "objects": {"face": [{"at": 1, "morph": {"smile": 1}}]}}}
        validate_three(good, library)
        bad = {"id": "A", "three": {"scene": "s", "objects": {"face": [{"at": 1, "morph": {"frown": 1}}]}}}
        with self.assertRaisesRegex(ValueError, "frown"):
            validate_three(bad, library)


class TypefaceTests(unittest.TestCase):
    def test_outline_handles_implied_on_curve_points(self):
        from studio.typeface import outline
        # Square with straight edges, then a contour of only off-curve points (a TrueType circle).
        square = [(0, 0, True), (10, 0, True), (10, 10, True), (0, 10, True)]
        self.assertEqual(outline([square]), "m 0 0 l 10 0 l 10 10 l 0 10 l 0 0")
        circle = outline([[(0, 10, False), (10, 10, False), (10, 0, False), (0, 0, False)]])
        self.assertTrue(circle.startswith("m 5 10 q"))
        self.assertEqual(circle.count("q"), 4)

    def test_convert_reads_a_system_truetype_font(self):
        import glob
        from studio.typeface import convert
        fonts = [path for pattern in ("/usr/share/fonts/**/*Sans*Bold.ttf", "/usr/share/fonts/**/*.ttf",
                                      "/Library/Fonts/*.ttf", "C:/Windows/Fonts/*.ttf")
                 for path in glob.glob(pattern, recursive=True)]
        if not fonts:
            self.skipTest("no TrueType font installed")
        data = convert(fonts[0], "AO")
        self.assertIsNotNone(data)
        self.assertGreater(data["resolution"], 0)
        # "O" has an outer contour and a hole.
        self.assertEqual(data["glyphs"]["O"]["o"].count("m "), 2)
        self.assertGreater(data["glyphs"]["A"]["ha"], 0)

    def test_convert_rejects_non_truetype(self):
        from tempfile import NamedTemporaryFile
        from studio.typeface import convert
        with NamedTemporaryFile(suffix=".otf") as handle:
            handle.write(b"OTTO" + bytes(64))
            handle.flush()
            self.assertIsNone(convert(handle.name, "A"))


POSE_MODES = ["linear", "in", "out", "smooth", "sine", "expo", "circ", "quint", "back", "elastic",
              "bounce", "spring", "hold", "auto",
              {"type": "cubic-bezier", "points": [0.2, 0, 0, 1]},
              {"type": "spring", "stiffness": 180, "damping": 10}]


@unittest.skipUnless(__import__("shutil").which("node"), "node is not installed")
class BrowserPoseParityTests(unittest.TestCase):
    """browser/pose.mjs poseAt must match studio.design.pose_at for every ease."""

    def _layers(self):
        layers = []
        for index, mode in enumerate(POSE_MODES):
            layers.append({
                "id": f"l{index}", "kind": "rect", "x": 0.2, "y": 0.3, "tint_color": "#000000",
                "keyframes": [
                    {"at": 0.3, "x": 0.8, "rotate": 40, "tint_color": "#FF8000", "turn_y": 90, "ease": mode},
                    {"at": 0.6, "y": 0.9, "scale": 1.6, "visible": False, "frame": 2, "ease": mode,
                     "ease_props": {"y": "back", "scale": "auto"}},
                    {"at": 1.0, "x": 0.1, "y": 0.2, "visible": True, "tint_color": "#20C0FF", "ease": mode},
                ]})
        return layers

    def test_pose_at_matches_python(self):
        import subprocess
        samples = [index / 40 for index in range(41)]
        tracks = {layer["id"]: poses(layer) for layer in self._layers()}
        script = ("import {poseAt} from './browser/pose.mjs';"
                  "const {tracks, samples} = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
                  "const out = {};"
                  "for (const [id, points] of Object.entries(tracks)) out[id] = samples.map((p) => poseAt(points, p));"
                  "process.stdout.write(JSON.stringify(out));")
        script = "import {readFileSync} from 'fs';" + script.replace("require('fs').readFileSync", "readFileSync")
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                                input=json.dumps({"tracks": tracks, "samples": samples}),
                                capture_output=True, text=True, check=True)
        browser = json.loads(result.stdout)
        for layer_id, points in tracks.items():
            for progress, js in zip(samples, browser[layer_id]):
                py = pose_at(points, progress)
                self.assertEqual(set(py), set(js), layer_id)
                for name, value in py.items():
                    other = js[name]
                    if isinstance(value, (list, tuple)):
                        for a, b in zip(value, other):
                            self.assertAlmostEqual(a, b, places=6, msg=f"{layer_id}.{name}@{progress}")
                    elif isinstance(value, bool) or value is None:
                        self.assertEqual(value, other, f"{layer_id}.{name}@{progress}")
                    else:
                        self.assertAlmostEqual(value, other, places=6, msg=f"{layer_id}.{name}@{progress}")


if __name__ == "__main__":
    unittest.main()
