"""Local AI character art: backend planning, cutout, part split, rig output and the ComfyUI client."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageDraw


def figure():
    """A flat cartoon figure on white: head, neck, body, arms held away, legs apart, white eyes."""
    image = Image.new("RGB", (400, 600), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    line, skin = (30, 30, 50), (240, 180, 120)
    draw.polygon([(130, 200), (90, 330), (110, 336), (150, 215)], fill=skin, outline=line, width=4)
    draw.polygon([(270, 200), (310, 330), (290, 336), (250, 215)], fill=skin, outline=line, width=4)
    draw.rectangle([165, 360, 195, 540], fill=(60, 80, 160), outline=line, width=4)
    draw.rectangle([205, 360, 235, 540], fill=(60, 80, 160), outline=line, width=4)
    draw.rounded_rectangle([150, 180, 250, 370], 20, fill=(220, 60, 70), outline=line, width=4)
    draw.rectangle([188, 160, 212, 185], fill=skin)
    draw.ellipse([140, 50, 260, 170], fill=skin, outline=line, width=4)
    draw.ellipse([175, 95, 190, 110], fill=(255, 255, 255), outline=line, width=3)
    draw.ellipse([210, 95, 225, 110], fill=(255, 255, 255), outline=line, width=3)
    draw.ellipse([179, 99, 186, 106], fill=line)
    draw.ellipse([214, 99, 221, 106], fill=line)
    draw.arc([180, 120, 220, 150], 20, 160, fill=line, width=4)
    return image


def channel(folder):
    folder = Path(folder)
    (folder / "channel.json").write_text(json.dumps({"name": "Art Lab"}))
    (folder / "tess.json").write_text(json.dumps({"id": "tess", "description": "a cheerful courier",
                                                  "style": "flat cartoon", "seed": 7, "height": 0.35,
                                                  "cutout": "key"}))
    return folder


class PlanTests(unittest.TestCase):
    def test_nothing_available_falls_back_to_the_procedural_generator(self):
        from studio.aiart import plan
        choice = plan({"gpu": None, "comfyui": None, "diffusers": False}, {})
        self.assertEqual(choice["backend"], "procedural")
        with self.assertRaises(ValueError):
            plan({"gpu": None, "comfyui": None, "diffusers": False}, {"backend": "comfyui"})

    def test_comfyui_model_follows_vram_and_skips_noncommercial_weights(self):
        from studio.aiart import plan
        checkpoints = ["flux1-dev-fp8.safetensors", "flux1-schnell-fp8.safetensors", "sd_xl_base_1.0.safetensors",
                       "sd_xl_turbo_1.0_fp16.safetensors"]
        comfy = {"url": "http://x", "checkpoints": checkpoints}
        big = plan({"gpu": {"vram_gb": 16}, "comfyui": comfy}, {})
        self.assertEqual((big["model"], big["checkpoint"]), ("flux-schnell", "flux1-schnell-fp8.safetensors"))
        small = plan({"gpu": {"vram_gb": 8}, "comfyui": comfy}, {})
        self.assertEqual((small["model"], small["checkpoint"]), ("sdxl", "sd_xl_base_1.0.safetensors"))
        only_dev = plan({"gpu": {"vram_gb": 24}, "comfyui": {"url": "http://x", "checkpoints": checkpoints[:1]},
                         "diffusers": False}, {})
        self.assertEqual(only_dev["backend"], "procedural")
        with self.assertRaises(ValueError):
            plan({"comfyui": comfy}, {"checkpoint": "flux1-dev-fp8.safetensors"})
        allowed = plan({"comfyui": comfy}, {"checkpoint": "flux1-dev-fp8.safetensors", "allow_noncommercial": True})
        self.assertEqual(allowed["checkpoint"], "flux1-dev-fp8.safetensors")

    def test_diffusers_picks_device_and_warns_on_cpu(self):
        from studio.aiart import plan
        cpu = plan({"gpu": None, "comfyui": None, "diffusers": True}, {})
        self.assertEqual((cpu["device"], cpu["model"]), ("cpu", "sd15"))
        self.assertIn("warning", cpu)
        mac = plan({"gpu": {"vendor": "apple", "vram_gb": 21}, "comfyui": None, "diffusers": True}, {})
        self.assertEqual((mac["device"], mac["model"]), ("mps", "flux-schnell"))
        self.assertEqual(plan({"gpu": None, "diffusers": True}, {"image": "a.png"})["backend"], "image")


class CutoutTests(unittest.TestCase):
    def test_key_removes_only_border_connected_background(self):
        from studio.cutout import key_background
        alpha = np.asarray(key_background(figure(), feather=0)) > 127
        self.assertFalse(alpha[5, 5])
        self.assertTrue(alpha[102, 182], "white eyes inside the outline must stay opaque")
        self.assertTrue(alpha[250, 200])


class OnnxCutoutTests(unittest.TestCase):
    def test_model_family_sets_size_and_normalisation(self):
        import sys
        import types
        from unittest import mock
        from studio.cutout import onnx_alpha
        seen = {}

        class Session:
            def __init__(self, path, providers=None):
                pass

            def get_inputs(self):
                return [types.SimpleNamespace(name="x", shape=[1, 3, "h", "w"])]

            def run(self, outputs, feed):
                batch = feed["x"]
                seen["size"], seen["low"] = batch.shape[-1], float(batch.min())
                return [np.zeros((1, 1, batch.shape[-2], batch.shape[-1]), dtype=np.float32)]
        fake = types.SimpleNamespace(InferenceSession=Session, get_available_providers=lambda: ["CPUExecutionProvider"])
        black = Image.new("RGB", (40, 60))
        with mock.patch.dict(sys.modules, {"onnxruntime": fake}):
            onnx_alpha(black, Path("isnet-anime.onnx"))
            self.assertEqual(seen["size"], 1024)
            self.assertAlmostEqual(seen["low"], -0.485, places=3)  # mean only
            onnx_alpha(black, Path("u2netp.onnx"))
            self.assertEqual(seen["size"], 320)
            self.assertAlmostEqual(seen["low"], -0.485 / 0.229, places=3)  # ImageNet mean and std


class SplitTests(unittest.TestCase):
    def test_split_finds_head_arms_legs_and_rigs_them(self):
        from studio.aiart import build_rig, split
        from studio.cutout import cut
        cutout, method = cut(figure(), "key")
        self.assertEqual(method, "key")
        alpha = np.asarray(cutout)[..., 3] > 127
        ys, xs = np.nonzero(alpha)
        cutout = cutout.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        masks, marks = split(np.asarray(cutout)[..., 3] > 127)
        self.assertEqual(set(masks), {"body", "head", "arm-l", "arm-r", "leg-l", "leg-r"})
        with TemporaryDirectory() as folder:
            layers = build_rig(cutout, masks, marks, {"height": 0.35}, "art/characters/tess", Path(folder))
            self.assertEqual(len(list(Path(folder).glob("*.png"))), 6)
        by_id = {layer["id"]: layer for layer in layers}
        self.assertEqual([layer["id"] for layer in layers][-2:], ["arm-l", "arm-r"], "arms draw last")
        self.assertEqual(by_id["head"]["parent"], "body")
        self.assertNotIn("parent", by_id["leg-l"])
        self.assertLess(by_id["arm-l"]["tip"][0], -0.03, "left arm reaches out to the left")
        self.assertGreater(by_id["arm-r"]["tip"][0], 0.03)
        self.assertLess(by_id["head"]["y"], 0, "head sits above the body pivot")
        self.assertAlmostEqual(by_id["leg-l"]["x"], -by_id["leg-r"]["x"], places=3)

    def test_manual_boxes_override_the_automatic_split(self):
        from studio.aiart import split
        alpha = np.ones((100, 50), dtype=bool)
        masks, _ = split(alpha, {"head": [0, 0, 1, 0.3]})
        self.assertEqual(masks["head"].sum(), 30 * 50)
        self.assertEqual(masks["body"].sum(), 70 * 50)


class FakeComfy:
    """A minimal ComfyUI: /system_stats, /object_info, /prompt, /history, /view."""

    def __init__(self, png):
        self.prompts = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _json(self, data):
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/system_stats":
                    self._json({"devices": [{"name": "cuda:0 Test GPU", "type": "cuda", "vram_total": 8 * 2**30}]})
                elif self.path == "/object_info/CheckpointLoaderSimple":
                    self._json({"CheckpointLoaderSimple": {"input": {"required": {
                        "ckpt_name": [["sd_xl_base_1.0.safetensors"]]}}}})
                elif self.path.startswith("/object_info/"):
                    self._json({})
                elif self.path.startswith("/history/"):
                    self._json({"p1": {"status": {"status_str": "success"}, "outputs": {
                        "8": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]}}}})
                elif self.path.startswith("/view"):
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(png)))
                    self.end_headers()
                    self.wfile.write(png)

            def do_POST(self):
                length = int(self.headers["Content-Length"])
                owner.prompts.append(json.loads(self.rfile.read(length)))
                self._json({"prompt_id": "p1"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class GenerateTests(unittest.TestCase):
    def test_comfyui_generation_is_rigged_recorded_and_cached(self):
        from studio.aiart import generate
        from studio.hardware import probe_comfyui
        buffer = BytesIO()
        figure().save(buffer, "PNG")
        comfy = FakeComfy(buffer.getvalue())
        try:
            info = probe_comfyui(comfy.url)
            self.assertEqual(info["devices"][0]["vram_gb"], 8.0)
            report = {"gpu": None, "comfyui": info, "diffusers": False}
            with TemporaryDirectory() as folder:
                base = channel(folder)
                result = generate(base, "tess.json", report=report)
                self.assertEqual(result["plan"]["checkpoint"], "sd_xl_base_1.0.safetensors")
                graph = comfy.prompts[0]["prompt"]
                self.assertEqual(graph["6"]["inputs"]["seed"], 7)
                self.assertIn("a cheerful courier", graph["3"]["inputs"]["text"])
                self.assertIn("plain flat white background", graph["3"]["inputs"]["text"])
                art = json.loads((base / "art/characters/tess/art.json").read_text())
                self.assertEqual((art["model"], art["license"], art["cutout"]),
                                 ("sdxl", "CreativeML Open RAIL++-M", "key"))
                library = json.loads((base / "rigs.json").read_text())
                self.assertEqual(len(library["rigs"]["tess"]), 6 + 2 + 13, "body parts, lifted eyes, mouth set")
                self.assertIn("wave", library["poses"]["tess"])
                self.assertEqual(json.loads((base / "channel.json").read_text())["rig_library"], "rigs.json")
                from studio.core import load
                load(base / "rigs.json", "rig_library")
                generate(base, "tess.json", report=report)
                self.assertEqual(len(comfy.prompts), 1, "same prompt, seed and model reuse the cached source")
                generate(base, "tess.json", report=report, seed=8)
                self.assertEqual(len(comfy.prompts), 2)
        finally:
            comfy.close()

    def test_supplied_layers_and_procedural_fallback(self):
        from studio.aiart import generate
        none = {"gpu": None, "comfyui": None, "diffusers": False}
        with TemporaryDirectory() as folder:
            base = channel(folder)
            parts = base / "layers"
            parts.mkdir()
            for name, box in {"body": (40, 40, 60, 80), "head": (35, 10, 65, 40), "leg-l": (42, 80, 48, 100),
                              "leg-r": (52, 80, 58, 100)}.items():
                layer = Image.new("RGBA", (100, 110), (0, 0, 0, 0))
                ImageDraw.Draw(layer).rectangle(box, fill=(200, 80, 80, 255))
                layer.save(parts / f"{name}.png")
            result = generate(base, "tess.json", parts_dir="layers", report=none)
            self.assertEqual(result["plan"]["backend"], "image")
            self.assertEqual(result["parts"], ["leg-l", "leg-r", "body", "head"])
            fallback = generate(base, "tess.json", report=none)
            self.assertEqual(fallback["plan"]["backend"], "procedural")
            self.assertTrue((base / "art/characters/tess/body.svg").is_file())


class FaceTests(unittest.TestCase):
    def test_finds_the_eyes_and_mouth_inside_the_head(self):
        from studio.aiart import _crop, split
        from studio.aiface import find_face
        from studio.cutout import cut
        cutout = _crop(cut(figure(), "key")[0])
        rgba = np.asarray(cutout)
        masks, _ = split(rgba[..., 3] > 127)
        face = find_face(rgba[..., :3].astype(float), masks["head"])
        self.assertEqual(len(face["eyes"]), 2)
        left, right = sorted(face["eyes"])
        self.assertLess(left[2], right[0], "two separate eyes")
        self.assertGreater(face["mouth"][1], left[3], "mouth below the eyes")
        self.assertEqual(face["skin"], "#F0B478")
        override = find_face(rgba[..., :3].astype(float), masks["head"], {"mouth": [0.4, 0.7, 0.6, 0.8]})
        self.assertIsNone(override["eyes"])
        self.assertIsNotNone(override["mouth"])

    def test_generated_rig_blinks_and_lip_syncs(self):
        from studio.aiart import generate
        from studio.pipeline import prepare_episode
        with TemporaryDirectory() as folder:
            base = channel(folder)
            figure().save(Path(folder, "art.png"))
            result = generate(base, "tess.json", image="art.png", report={"gpu": None, "comfyui": None})
            parts = result["parts"]
            self.assertIn("eye-l", parts)
            self.assertEqual(sum(part.startswith("mouth-") for part in parts), 13)
            self.assertLess(parts.index("mouth-rest"), parts.index("arm-l"), "mouths draw under the arms")
            head = np.asarray(Image.open(base / "art/characters/tess/head.png").convert("RGB")).astype(int)
            library = json.loads((base / "rigs.json").read_text())
            head_layer = next(layer for layer in library["rigs"]["tess"] if layer["id"] == "head")
            self.assertEqual(head_layer["role"], "head")
            # The painted mouth is gone: the lower face is skin now, only the outline stays dark.
            dark = head.sum(axis=2) < 200
            interior = dark[int(head.shape[0] * 0.6):int(head.shape[0] * 0.85), int(head.shape[1] * 0.3):int(head.shape[1] * 0.7)]
            self.assertFalse(interior.any(), "no dark mouth pixels left inside the face")
            channel_data = json.loads((base / "channel.json").read_text())
            episode = {"title": "t", "width": 540, "height": 960, "fps": 12, "scenes": [{"id": "S", "shots": [{
                "id": "A", "duration": 3.0, "speech": [{"speaker": "Tess", "text": "Hi there"}],
                "layers": [{"id": "tess", "kind": "use", "ref": "tess", "x": 0.5, "y": 0.8,
                            "alive": {"talk": "Tess"}}]}]}]}
            expanded = prepare_episode(episode, channel_data, base, style=False)
            layers = {layer["id"]: layer for layer in expanded["scenes"][0]["shots"][0]["layers"]}
            self.assertEqual(layers["tess/mouth-e"].get("viseme_for"), "Tess")
            self.assertTrue(any("scale_y" in key for key in layers["tess/eye-l"].get("keyframes", [])),
                            "eyes blink")


def blob():
    """A head-less character: an antenna on a wide body with eyes, a mouth on a light belly patch, and feet."""
    image = Image.new("RGB", (300, 420), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    line, skin = (26, 22, 56), (255, 201, 77)
    draw.line([(150, 30), (150, 90)], fill=line, width=4)
    draw.ellipse([138, 18, 162, 42], fill=(255, 120, 90), outline=line, width=3)  # antenna ball
    draw.ellipse([90, 340, 140, 375], fill=(255, 140, 100), outline=line, width=3)  # feet
    draw.ellipse([160, 340, 210, 375], fill=(255, 140, 100), outline=line, width=3)
    draw.ellipse([50, 80, 250, 350], fill=skin, outline=line, width=5)  # body
    draw.ellipse([90, 220, 210, 340], fill=(250, 222, 150))  # light belly patch
    for x in (95, 165):
        draw.ellipse([x, 140, x + 40, 185], fill=(255, 255, 255), outline=line, width=3)
        draw.ellipse([x + 12, 152, x + 28, 172], fill=line)
    draw.arc([125, 210, 175, 240], 20, 160, fill=line, width=4)  # mouth at the top of the belly
    return image


class BlobFaceTests(unittest.TestCase):
    def test_flat_background_uses_the_exact_key(self):
        from studio.cutout import choose
        self.assertEqual(choose("auto", blob()), "key")
        busy = Image.fromarray((np.random.default_rng(1).random((60, 40, 3)) * 255).astype(np.uint8))
        self.assertEqual(choose("auto", busy), choose("auto"))

    def test_an_antenna_is_not_a_head_and_the_body_carries_the_face(self):
        from studio.aiart import generate
        with TemporaryDirectory() as folder:
            base = channel(folder)
            blob().save(Path(folder) / "blob.png")
            spec = json.loads((base / "tess.json").read_text())
            spec.pop("cutout")
            (base / "tess.json").write_text(json.dumps(spec))
            result = generate(base, "tess.json", image="blob.png", report={"gpu": None, "comfyui": None})
            parts = result["parts"]
            self.assertNotIn("head", parts, "the antenna ball on a stem is not a head")
            self.assertIn("eye-l", parts)
            self.assertEqual(sum(part.startswith("mouth-") for part in parts), 13, "mouth found on the belly patch")
            art = json.loads((base / "art/characters/tess/art.json").read_text())
            self.assertEqual(art["cutout"], "key")
            self.assertIsNotNone(art["face"]["mouth"])
            rig = {layer["id"]: layer for layer in json.loads((base / "rigs.json").read_text())["rigs"]["tess"]}
            self.assertEqual(rig["mouth-rest"]["parent"], "body")
            self.assertEqual(rig["eye-l"]["parent"], "body")
            cutout = np.asarray(Image.open(base / "art/characters/tess/cutout.png"))
            self.assertTrue((cutout[..., 3] > 127)[:30].any(), "the key keeps the antenna ball")


if __name__ == "__main__":
    unittest.main()
