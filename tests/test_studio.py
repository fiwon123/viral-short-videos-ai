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


if __name__ == "__main__":
    unittest.main()
