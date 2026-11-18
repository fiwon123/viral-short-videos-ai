"""Hero clips: video backend planning, the ComfyUI client, sheet packing and shot insertion."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

WAN_FILES = {"unets": ["wan2.2_ti2v_5B_fp16.safetensors"], "clips": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
             "vaes": ["wan2.2_vae.safetensors"], "wan_node": True}


def episode(folder):
    path = Path(folder) / "episode.json"
    path.write_text(json.dumps({"title": "t", "description": "d", "tags": ["t"], "thumbnail": {"shot": "A", "text": "T"},
                                "width": 360, "height": 640, "fps": 12, "scenes": [{"id": "S", "purpose": "p", "shots": [
        {"id": "A", "duration": 2.0, "layers": [
            {"id": "bg", "kind": "rect", "x": 0.5, "y": 0.5, "width": 1, "height": 1, "fill": "#223344"},
            {"id": "title", "kind": "text", "text": "HOOK", "x": 0.5, "y": 0.2}]}]}]}))
    return path


class HeroPlanTests(unittest.TestCase):
    def test_backend_follows_what_the_machine_has(self):
        from studio.heroclip import plan
        none = {"gpu": None, "comfyui": None, "diffusers": False}
        self.assertEqual(plan(none, {})["backend"], "parallax")
        wan = plan({"comfyui": {"url": "http://x", "video": WAN_FILES}}, {})
        self.assertEqual((wan["graph"], wan["files"]["vae"]), ("wan22-5b", "wan2.2_vae.safetensors"))
        workflow = plan({"comfyui": {"url": "http://x", "video": {}}}, {"workflow": "ltx.json"})
        self.assertEqual(workflow["graph"], "workflow")
        self.assertEqual(plan({"comfyui": {"url": "http://x", "video": {}}}, {})["backend"], "parallax")
        with self.assertRaises(ValueError):
            plan({"comfyui": {"url": "http://x", "video": {}}}, {"backend": "comfyui"})
        small = {"gpu": {"vendor": "nvidia", "name": "g", "vram_gb": 8}, "diffusers": True}
        self.assertEqual(plan(small, {})["backend"], "parallax")
        big = {"gpu": {"vendor": "nvidia", "name": "g", "vram_gb": 16}, "diffusers": True}
        self.assertEqual(plan(big, {})["model"], "ltx-video")

    def test_frame_counts_and_sizes_match_the_model(self):
        from studio.heroclip import clip_size, frame_count
        self.assertEqual(frame_count(4, {"fps": 24, "step": 4, "max_seconds": 5}), 97)
        self.assertEqual(frame_count(9, {"fps": 24, "step": 8, "max_seconds": 5}), 121)
        self.assertEqual(frame_count(2, {"fps": 12, "step": 1}), 24)
        self.assertEqual(clip_size((1080, 1920)), (480, 832))

    def test_workflow_placeholders(self):
        from studio.heroclip import fill_workflow
        graph = {"1": {"inputs": {"image": "{{image}}", "length": "{{frames}}", "text": "a {{prompt}}!"}}}
        values = {"image": "x.png", "prompt": "leap", "negative": "", "seed": 1, "frames": 49, "width": 1,
                  "height": 1, "fps": 24}
        self.assertEqual(fill_workflow(graph, values)["1"]["inputs"], {"image": "x.png", "length": 49, "text": "a leap!"})


class HeroSheetTests(unittest.TestCase):
    def test_pack_fits_the_limit_and_keeps_order(self):
        from studio.heroclip import pack
        frames = [Image.new("RGB", (480, 832), (index * 5, 0, 0)) for index in range(49)]
        sheet, columns, rows = pack(frames, limit=4096)
        self.assertLessEqual(max(sheet.size), 4096)
        self.assertGreaterEqual(columns * rows, 49)
        cell = (sheet.width // columns, sheet.height // rows)
        last = sheet.getpixel(((48 % columns) * cell[0] + 2, (48 // columns) * cell[1] + 2))
        self.assertEqual(last[0], 240)

    def test_place_keeps_named_layers_above(self):
        from studio.heroclip import place
        layers = [{"id": "bg"}, {"id": "title"}, {"id": "label"}]
        ours = [{"id": "clip"}]
        self.assertEqual([item["id"] for item in place(layers, ours, True, {"title"})], ["bg", "label", "clip", "title"])
        self.assertEqual([item["id"] for item in place(layers, ours, False)], ["clip", "bg", "title", "label"])


class FakeVideoComfy:
    def __init__(self, frames):
        self.prompts, self.uploads = [], 0
        owner = self
        pngs = []
        for frame in frames:
            buffer = BytesIO()
            frame.save(buffer, "PNG")
            pngs.append(buffer.getvalue())

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _json(self, data):
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.startswith("/history/"):
                    self._json({"p": {"status": {"status_str": "success", "completed": True}, "outputs": {"11": {
                        "images": [{"filename": f"{i}.png", "type": "output"} for i in range(len(pngs))]}}}})
                elif self.path.startswith("/view"):
                    index = int(self.path.split("filename=")[1].split(".png")[0])
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(pngs[index])))
                    self.end_headers()
                    self.wfile.write(pngs[index])

            def do_POST(self):
                data = self.rfile.read(int(self.headers["Content-Length"]))
                if self.path == "/upload/image":
                    owner.uploads += 1
                    self._json({"name": "start.png", "subfolder": "", "type": "input"})
                else:
                    owner.prompts.append(json.loads(data))
                    self._json({"prompt_id": "p"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class HeroRunTests(unittest.TestCase):
    def test_comfyui_clip_becomes_a_frame_keyed_sheet_under_the_shot(self):
        from studio.core import load
        from studio.heroclip import run
        frames = [Image.new("RGB", (96, 160), (index * 20, 40, 60)) for index in range(9)]
        comfy = FakeVideoComfy(frames)
        try:
            with TemporaryDirectory() as folder:
                path = episode(folder)
                Image.new("RGB", (90, 160), "white").save(Path(folder) / "plate.png")
                report = {"comfyui": {"url": comfy.url, "video": WAN_FILES}}
                result = run(path, "A", image=Path(folder) / "plate.png", prompt="clouds drift", seed=3,
                             seconds=1.0, report=report)
                self.assertEqual((result["frames"], result["placed"]), (9, "under the shot"))
                graph = comfy.prompts[0]["prompt"]
                self.assertEqual(graph["7"]["inputs"]["length"], 25)
                self.assertEqual(graph["4"]["inputs"]["image"], "start.png")
                self.assertEqual(graph["9"]["inputs"]["seed"], 3)
                shot = json.loads(path.read_text())["scenes"][0]["shots"][0]
                layer = shot["layers"][0]
                self.assertEqual((layer["kind"], layer["count"], layer["hero_clip"]), ("sheet", 9, "a"))
                self.assertEqual(layer["keyframes"][-1], {"at": 0.1875, "frame": 8, "ease": "linear"})
                load(path, "episode")
                run(path, "A", image=Path(folder) / "plate.png", prompt="clouds drift", seed=3, seconds=1.0,
                    report=report)
                self.assertEqual(len(comfy.prompts), 1, "cached clip is reused")
                self.assertEqual(sum(item.get("hero_clip") == "a" for item in
                                     json.loads(path.read_text())["scenes"][0]["shots"][0]["layers"]), 1)
        finally:
            comfy.close()

    def test_parallax_fallback_pushes_depth_layers_without_a_camera(self):
        from studio.heroclip import run
        with TemporaryDirectory() as folder:
            path = episode(folder)
            image = Image.new("RGB", (180, 320), (30, 60, 90))
            image.paste((200, 180, 60), (40, 200, 140, 300))
            image.save(Path(folder) / "start.png")
            result = run(path, "A", image=Path(folder) / "start.png", report={"gpu": None, "comfyui": None})
            self.assertEqual(result["backend"], "parallax")
            shot = json.loads(path.read_text())["scenes"][0]["shots"][0]
            self.assertNotIn("camera", shot)
            ours = [layer for layer in shot["layers"] if layer.get("depth_photo") == "hero-a"]
            growth = [layer["keyframes"][-1]["scale"] for layer in ours]
            self.assertEqual(growth, sorted(growth), "nearer layers push in more")
            self.assertEqual(shot["layers"][0]["id"], ours[0]["id"], "a supplied image is a background plate")
            with self.assertRaises(ValueError):
                run(path, "A", image=Path(folder) / "start.png", keep=["nope"], report={"gpu": None, "comfyui": None})

    def test_shot_first_frame_is_replaced_and_kept_layers_stay_above(self):
        from studio.heroclip import run
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as folder:
            path = episode(folder)
            channel = Path(folder) / "channel.json"
            channel.write_text((root / "tests" / "parity" / "channel.json").read_text())
            run(path, "A", channel=channel, keep=["title"], report={"gpu": None, "comfyui": None})
            self.assertTrue((Path(folder) / "art/hero/a/start.png").is_file())
            layers = json.loads(path.read_text())["scenes"][0]["shots"][0]["layers"]
            self.assertEqual(layers[0]["id"], "bg")
            self.assertEqual(layers[-1]["id"], "title", "kept layers stay above the clip")
            ours = [layer for layer in layers if layer.get("depth_photo") == "hero-a"]
            self.assertTrue(ours)
            self.assertFalse(any("z" in layer for layer in ours),
                             "z would sort the plate behind the shot it replaces")
            self.assertFalse(list(Path(folder).glob(".hero-start-*.json")), "temporary episode removed")


if __name__ == "__main__":
    unittest.main()
