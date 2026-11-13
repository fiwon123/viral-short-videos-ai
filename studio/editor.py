"""A local-only storyboard and shot inspector for an episode.

The editor is deliberately narrow: it edits the same `episode.json` the AI
uses, saves through the schema validator, and previews 2D shots with the
Python compositor. SVG and Three.js shots should be reviewed with a normal
renderer preview.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import webbrowser

from PIL import Image

from .core import load, validate_episode
from .design import Composition, apply_post, resolve_font
from .expand import expand as expand_defs
from .markers import expand as expand_markers
from .particles import expand as expand_particles
from .presets import apply_style
from .trails import expand as expand_trails

EDITOR = Path(__file__).resolve().parents[1] / "editor"


class Handler(BaseHTTPRequestHandler):
    episode_path = None
    channel_path = None
    episode = None
    channel = None

    def log_message(self, fmt, *args):
        return

    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._file(EDITOR / "index.html", "text/html; charset=utf-8")
        elif parsed.path == "/app.js":
            self._file(EDITOR / "app.js", "text/javascript; charset=utf-8")
        elif parsed.path == "/style.css":
            self._file(EDITOR / "style.css", "text/css; charset=utf-8")
        elif parsed.path == "/api/episode":
            self._json(200, {"episode": self.episode, "channel": self.channel,
                             "path": str(self.episode_path), "channel_path": str(self.channel_path)})
        elif parsed.path == "/api/still":
            query = parse_qs(parsed.query)
            shot_id = (query.get("shot") or [""])[0]
            progress = float((query.get("at") or ["0.5"])[0])
            self._still(shot_id, progress)
        else:
            self._json(404, {"error": "Not found"})

    def _still(self, shot_id, progress):
        shots = [shot for scene in self.episode["scenes"] for shot in scene["shots"]]
        shot = next((item for item in shots if item["id"] == shot_id), None)
        if shot is None:
            return self._json(404, {"error": f"Unknown shot: {shot_id}"})
        if any(layer["kind"] == "svg" for layer in shot["layers"]) or "three" in shot:
            return self._json(415, {"error": "Use a renderer preview for SVG or 3D shots"})
        base = self.episode_path.parent
        channel_dir = self.channel_path.parent
        import copy

        episode = expand_defs(copy.deepcopy(self.episode))
        episode = apply_style(episode, self.channel, channel_dir)
        episode = expand_particles(expand_trails(expand_markers(episode, channel_dir)))
        styled = next((item for scene in episode["scenes"] for item in scene["shots"]
                       if item["id"] == shot_id), shot)
        font = resolve_font(self.channel, channel_dir)
        canvas = self.episode["width"], self.episode["height"]
        composition = Composition(styled, canvas, self.channel, font, base,
                                  episode_post=episode.get("post"),
                                  channel_base=channel_dir)
        image = composition.frame(max(0, min(1, progress)), {}, post=False)
        image = apply_post(image, composition.post, palette=self.channel["palette"])
        image.save("/tmp/viral-editor-still.png")
        self._file(Path("/tmp/viral-editor-still.png"), "image/png")

    def do_POST(self):
        if urlparse(self.path).path != "/api/save":
            return self._json(404, {"error": "Not found"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            episode = payload.get("episode")
            if not isinstance(episode, dict):
                raise ValueError("Expected an episode object")
            validate_episode(episode, self.episode_path.parent, self.channel_path.parent)
            self.episode_path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
            self.episode = episode
            self._json(200, {"saved": str(self.episode_path), "shots": len(
                [shot for scene in episode["scenes"] for shot in scene["shots"]])})
        except (OSError, ValueError, KeyError) as error:
            self._json(400, {"error": str(error)})


def serve(episode_path, channel_path, port=8765, open_browser=True):
    episode_path = Path(episode_path).resolve()
    channel_path = Path(channel_path).resolve()
    Handler.episode_path = episode_path
    Handler.channel_path = channel_path
    Handler.episode = load(episode_path, "episode")
    Handler.channel = load(channel_path, "channel")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"editor: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
