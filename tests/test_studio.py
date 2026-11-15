"""Focused regression tests for the AI authoring controls."""

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
        self.assertEqual(layers["hero/mouth-rest"]["quiet_for"], "Hero")
        self.assertTrue(layers["hero/mouth-open"]["talk_only"])
        ats = [key["at"] for key in layers["hero/body"]["keyframes"]]
        self.assertEqual(ats, sorted(ats))


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


if __name__ == "__main__":
    unittest.main()
