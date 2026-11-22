"""Comments on a rendered frame: you point at the spot, the agent looks at it, changes that, and replies.

    python -m studio.comments serve EPISODE [--video renders/<ep>-preview/video.mp4] [--port 8765]
    python -m studio.comments list EPISODE           open comments, each with its frame and a close-up
    python -m studio.comments done EPISODE ID --reply "what changed"

``serve`` (``make review``) opens a local page that plays the newest preview or
master. Pause, press C or click the picture, and type the note: it is saved to
``episodes/<episode>/review/comments.json`` with the time, the frame, the shot,
the progress within the shot (the number a keyframe's ``at`` uses) and the
clicked point. The page lists every comment with its status and reply.

``list`` (``make comments``) is the agent's side. For each open comment it
writes ``review/comments/<id>-frame.png`` (the frame, the spot ringed) and
``<id>-spot.png`` (a close-up of the spot at 2x). Look at both before changing
anything, change only what the note is about, re-render, then ``done`` with a
one-line reply, which the page shows.

Adapted from huashu-motion's point-at-the-frame review (MIT): a note that
carries its moment and its place, and a one-line answer. Built here on the
rendered MP4 and a JSON file, so it works for every renderer.
"""

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlparse
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "editor"
SPOT = 0.3      # the close-up is this share of the frame's width around the point
_LOCK = threading.Lock()


def _where(episode):
    from .episode_state import paths
    return paths(episode)


def store(episode):
    return _where(episode)["folder"] / "review" / "comments.json"


def load(episode):
    path = store(episode)
    if not path.is_file():
        return {"comments": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(episode, data):
    path = store(episode)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def newest_render(episode):
    """The newest fresh preview or master of the episode (what the user is reviewing)."""
    from .episode_state import renders
    found = [item for item in renders(_where(episode)) if item["kind"] in ("preview", "master")]
    fresh = [item for item in found if item["fresh"]] or found
    if not fresh:
        raise ValueError("No preview or master to review; run make preview first.")
    return fresh[0]["video"]


def locate(video, seconds):
    """(frame, shot id, progress within the shot) for a time in a render, from its timeline.json."""
    timeline = Path(video).parent / "timeline.json"
    if not timeline.is_file():
        return int(round(seconds * 24)), None, None
    data = json.loads(timeline.read_text(encoding="utf-8"))
    fps = float(data.get("fps", 24))
    frame = int(seconds * fps + 1e-6)
    for scene in data.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot["start"] <= frame < shot["end"]:
                return frame, shot["id"], round((frame - shot["start"]) / max(1, shot["end"] - shot["start"]), 4)
    return frame, None, None


def add(episode, video, seconds, x, y, text):
    """Record a comment at ``seconds`` and the point (x, y), 0-1 from the top left of the picture."""
    text = str(text or "").strip()
    if not text:
        raise ValueError("A comment needs words.")
    seconds, x, y = float(seconds), float(x), float(y)
    if not (0 <= x <= 1 and 0 <= y <= 1) or seconds < 0:
        raise ValueError("The point must be inside the picture (x and y from 0 to 1) and the time positive.")
    frame, shot, progress = locate(video, seconds)
    with _LOCK:
        data = load(episode)
        number = 1 + max((int(re.sub(r"\D", "", item["id"]) or 0) for item in data["comments"]), default=0)
        comment = {"id": f"c{number}", "render": Path(video).parent.name, "time": round(seconds, 3), "frame": frame,
                   "shot": shot, "shot_progress": progress, "x": round(x, 4), "y": round(y, 4), "text": text[:2000],
                   "status": "open", "created": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
        data["comments"].append(comment)
        _save(episode, data)
    return comment


def resolve(episode, comment_id, reply):
    reply = str(reply or "").strip()
    if not reply:
        raise ValueError("Say in one line what changed (--reply).")
    with _LOCK:
        data = load(episode)
        comment = next((item for item in data["comments"] if item["id"] == comment_id), None)
        if comment is None:
            raise ValueError(f"No comment {comment_id}.")
        comment.update(status="done", reply=reply[:500],
                       resolved=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        _save(episode, data)
    return comment


def look(episode, comment, video=None):
    """Write the comment's frame with the spot ringed and a 2x close-up of the spot; return their paths."""
    from PIL import Image, ImageDraw
    where = _where(episode)
    video = Path(video) if video else where["renders"] / comment["render"] / "video.mp4"
    if not video.is_file():
        return {}
    out = where["folder"] / "review" / "comments"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        grab = Path(temp) / "frame.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                        f"select=eq(n\\,{int(comment['frame'])})", "-frames:v", "1", str(grab)],
                       capture_output=True, check=False)
        if not grab.is_file():
            return {}
        frame = Image.open(grab).convert("RGB")
    width, height = frame.size
    cx, cy = comment["x"] * width, comment["y"] * height
    half = SPOT * width / 2
    box = (int(max(0, cx - half)), int(max(0, cy - half)), int(min(width, cx + half)), int(min(height, cy + half)))
    spot = frame.crop(box)
    spot = spot.resize((spot.width * 2, spot.height * 2), Image.LANCZOS)
    ring = ImageDraw.Draw(spot)
    px, py, small = (cx - box[0]) * 2, (cy - box[1]) * 2, max(10, spot.width * 0.04)
    ring.ellipse((px - small, py - small, px + small, py + small), outline="#FF3B3B", width=3)
    marked = frame.copy()
    draw = ImageDraw.Draw(marked)
    radius = max(12, width * 0.04)
    for grow, colour in ((3, "#000000"), (0, "#FF3B3B")):
        draw.ellipse((cx - radius - grow, cy - radius - grow, cx + radius + grow, cy + radius + grow),
                     outline=colour, width=max(3, int(width / 200)))
    paths = {"frame_image": out / f"{comment['id']}-frame.png", "spot_image": out / f"{comment['id']}-spot.png"}
    marked.save(paths["frame_image"])
    spot.save(paths["spot_image"])
    return {key: str(path) for key, path in paths.items()}


def open_comments(episode):
    """Open comments for the agent, each with its frame and close-up written to look at first."""
    result = []
    for comment in load(episode)["comments"]:
        if comment["status"] == "open":
            result.append({**comment, **look(episode, comment)})
    return result


class Handler(BaseHTTPRequestHandler):
    episode = None
    video = None

    def log_message(self, fmt, *args):
        pass

    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, content_type):
        body = Path(path).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _video(self):
        """Serve the MP4 with HTTP range requests, which browsers need to seek."""
        size = self.video.stat().st_size
        start, end = 0, size - 1
        ranged = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        if ranged and (ranged.group(1) or ranged.group(2)):
            if ranged.group(1):
                start = int(ranged.group(1))
                end = min(int(ranged.group(2)), size - 1) if ranged.group(2) else size - 1
            else:
                start = max(0, size - int(ranged.group(2)))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        self.send_response(206 if ranged else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if ranged:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(self.video, "rb") as handle:
            handle.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = handle.read(min(1 << 16, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._file(PAGE / "review.html", "text/html; charset=utf-8")
        elif path == "/review.js":
            self._file(PAGE / "review.js", "text/javascript; charset=utf-8")
        elif path == "/style.css":
            self._file(PAGE / "style.css", "text/css; charset=utf-8")
        elif path == "/api/review":
            timeline = self.video.parent / "timeline.json"
            fps = json.loads(timeline.read_text(encoding="utf-8")).get("fps", 24) if timeline.is_file() else 24
            self._json(200, {"episode": _where(self.episode)["slug"], "render": self.video.parent.name, "fps": fps,
                             "comments": load(self.episode)["comments"]})
        elif path == "/api/comments":
            self._json(200, load(self.episode))
        elif path == "/video.mp4":
            self._video()
        else:
            self._json(404, {"error": "Not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/comments":
            return self._json(404, {"error": "Not found"})
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 64 * 1024)
            payload = json.loads(self.rfile.read(length) or b"{}")
            comment = add(self.episode, self.video, payload.get("time"), payload.get("x"), payload.get("y"),
                          payload.get("text"))
        except (TypeError, ValueError) as error:
            return self._json(400, {"error": str(error)})
        self._json(201, comment)


def server(episode, video=None, port=8765, tries=10):
    """A review server for ``episode`` (not started). When ``port`` is taken (``make editor`` is running)
    the next free one is used; ``server_address`` says which."""
    handler = type("ReviewHandler", (Handler,), {"episode": Path(episode).resolve(),
                                                 "video": Path(video).resolve() if video else newest_render(episode)})
    # The dev sandbox sets STUDIO_EDITOR_HOST=0.0.0.0 so the published port reaches the server.
    host = os.environ.get("STUDIO_EDITOR_HOST", "127.0.0.1")
    for offset in range(tries if port else 1):
        try:
            return ThreadingHTTPServer((host, port + offset if port else 0), handler)
        except OSError:
            if offset == tries - 1:
                raise
    raise OSError(f"No free port from {port}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("episode", type=Path)
    serve.add_argument("--video", type=Path)
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    listing = commands.add_parser("list")
    listing.add_argument("episode", type=Path)
    done = commands.add_parser("done")
    done.add_argument("episode", type=Path)
    done.add_argument("id")
    done.add_argument("--reply", required=True)
    args = parser.parse_args()
    try:
        if args.command == "list":
            print(json.dumps(open_comments(args.episode), indent=2, ensure_ascii=False))
        elif args.command == "done":
            print(json.dumps(resolve(args.episode, args.id, args.reply), indent=2, ensure_ascii=False))
        else:
            running = server(args.episode, args.video, args.port)
            port = running.server_address[1]
            url = f"http://127.0.0.1:{port}/"
            print(f"review: {url} ({running.RequestHandlerClass.video.parent.name})")
            if port != args.port:
                print(f"review: port {args.port} is busy (make editor?), using {port}. In the dev sandbox only the "
                      f"published port reaches the browser: stop the other server or run on the host.")
            if not args.no_browser:
                webbrowser.open(url)
            try:
                running.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                running.server_close()
    except ValueError as error:
        print(f"studio: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
