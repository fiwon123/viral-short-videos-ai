#!/usr/bin/env python3
"""Run the local animated-video studio."""

import argparse
from importlib.util import find_spec
import json
from pathlib import Path
import re
import shutil
import sys


def options():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check local dependencies")
    for name, help_text in (("validate", "check episode and channel inputs"), ("render", "render a production package")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("episode", type=Path)
        command.add_argument("--channel", required=True, type=Path)
        if name == "render":
            command.add_argument("--out", required=True, type=Path)
            command.add_argument("--preview", action="store_true", help="use half-size resolution")
            command.add_argument("--renderer", choices=("python", "remotion", "hyperframes"), default="python",
                                 help="select the visual renderer")
            command.add_argument("--no-burn", action="store_true", help="export captions as a separate SRT only")
    brand = commands.add_parser("brand", help="generate a logo, banner, and channel metadata")
    brand.add_argument("channel", type=Path)
    brand.add_argument("--out", required=True, type=Path)
    reference = commands.add_parser("analyze", help="extract local reference frames, cuts, and audio")
    reference.add_argument("video", type=Path)
    reference.add_argument("--out", required=True, type=Path)
    reference.add_argument("--threshold", type=float, default=0.34, help="scene change threshold from 0 to 1")
    discover = commands.add_parser("discover", help="sample top recent YouTube videos using YOUTUBE_API_KEY")
    discover.add_argument("--query", action="append", required=True, help="repeat for distinct search terms")
    discover.add_argument("--region", required=True, help="two-letter country code")
    discover.add_argument("--language", help="YouTube relevance language hint")
    discover.add_argument("--limit", type=int, default=8)
    return parser.parse_args()


def doctor():
    binaries = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe", "espeak-ng")}
    modules = {name: bool(find_spec(name)) for name in ("PIL", "numpy", "jsonschema")}
    npm_modules = Path(__file__).resolve().parent / "node_modules"
    result = {"binaries": binaries, "python_modules": modules, "browser_renderers": {
        "node": shutil.which("node"),
        "remotion_installed": (npm_modules / "@remotion" / "renderer").is_dir(),
        "hyperframes_installed": (npm_modules / "hyperframes").is_dir(),
        "three_installed": (npm_modules / "three").is_dir(),
    }}
    if binaries["ffmpeg"] and modules["jsonschema"]:
        from studio.core import run

        codecs = run("ffmpeg", "-hide_banner", "-encoders").decode()
        result["h264_encoder"] = next((name for name in ("libx264", "libopenh264") if re.search(rf"\b{name}\b", codecs)), None)
    ok = all(modules.values()) and binaries["ffmpeg"] and binaries["ffprobe"] and result.get("h264_encoder")
    return result, 0 if ok else 1


def execute(args):
    if args.command == "doctor":
        return doctor()
    if args.command == "discover":
        from studio.research import discover

        if not re.fullmatch(r"[A-Za-z]{2}", args.region) or not 5 <= args.limit <= 25 or len(args.query) > 8:
            raise ValueError("Use a two-letter region, a limit from 5 to 25, and up to eight queries")
        return discover(args.query, args.region.upper(), args.language, args.limit), 0
    if args.command == "analyze":
        from studio.reference import reference

        if not 0 < args.threshold < 1:
            raise ValueError("Threshold must be between 0 and 1")
        if not args.video.is_file():
            raise ValueError("Provide a local reference video file")
        return reference(args.video.resolve(), args.out, args.threshold), 0

    from studio.core import load, new_package, validate_channel, validate_episode, write_json

    channel = load(args.channel, "channel")
    validate_channel(channel, args.channel.parent)
    if args.command == "brand":
        from studio.design import make_brand

        with new_package(args.out) as out:
            make_brand(channel, args.channel.parent, out)
            write_json(out / "channel-publishing.json", {
                key: channel[key] for key in ("name", "handle", "tagline", "description", "tags") if key in channel
            })
        return {"brand": channel["name"], "package": str(args.out.resolve())}, 0

    from studio.scenes import load_library, validate_three

    episode = load(args.episode, "episode")
    validate_episode(episode, args.episode.parent, args.channel.parent)
    library = load_library(channel, args.channel.parent)
    for scene in episode["scenes"]:
        for shot in scene["shots"]:
            validate_three(shot, library)
    if args.command == "validate":
        return {"valid": True, "episode": episode["title"], "channel": channel["name"]}, 0
    from studio.render import render

    report = render(episode, channel, args.episode.parent, args.channel.parent, args.out, args.preview, not args.no_burn,
                    backend=args.renderer, library=library)
    return {**report, "package": str(args.out.resolve())}, 0


def main():
    try:
        result, status = execute(options())
    except ModuleNotFoundError as error:
        print(f"studio: {error}. Install requirements.txt in your Python environment.", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as error:
        print(f"studio: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main())
