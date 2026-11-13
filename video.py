#!/usr/bin/env python3
"""Run the local animated-video studio."""

import argparse
from importlib.util import find_spec
import json
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory


def options():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check local dependencies")
    for name, help_text in (("validate", "check episode and channel inputs"),
                            ("audio", "audition the cast and mix without rendering video"),
                            ("check-visual", "check protected layers, contacts, and continuity on the resolved timeline"),
                            ("render", "render a production package")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("episode", type=Path)
        command.add_argument("--channel", type=Path,
                             help="channel manifest; discovered under channels/ when omitted")
        if name in {"audio", "render"}:
            command.add_argument("--out", type=Path, help="package directory (defaults to output/<channel>/<episode>-<suffix>)")
        if name == "render":
            preview = command.add_mutually_exclusive_group()
            preview.add_argument("--preview", action="store_true", help="export a half-size preview")
            preview.add_argument("--full-size-preview", action="store_true", help="export a preview at full resolution")
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
    reference.add_argument("--focus-shorts", action="store_true",
                           help="sample the first and last two seconds more closely")
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
    model_dir = Path(__file__).resolve().parent / "audio-models"
    result["neural_audio"] = {
        "kokoro_installed": find_spec("kokoro_onnx") is not None,
        "model_present": Path(os.environ.get("STUDIO_KOKORO_MODEL", model_dir / "kokoro-v1.0.int8.onnx")).is_file(),
        "voices_present": Path(os.environ.get("STUDIO_KOKORO_VOICES", model_dir / "voices-v1.0.bin")).is_file(),
    }
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
        return reference(args.video.resolve(), args.out, args.threshold, focus_shorts=args.focus_shorts), 0

    from studio.core import load, new_package, validate_channel, validate_episode, write_json

    if args.channel is None:
        from studio.project import resolve_channel

        args.channel = resolve_channel(Path(__file__).resolve().parent)
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

    from studio.audio_library import load_audio_library, validate_audio
    episode = load(args.episode, "episode")
    validate_episode(episode, args.episode.parent, args.channel.parent, check_visual_assets=args.command != "audio")
    audio_library = load_audio_library(channel, args.channel.parent)
    validate_audio(episode, audio_library)
    if args.command in {"audio", "render"} and args.out is None:
        suffix = "audio" if args.command == "audio" else "v1"
        if args.command == "render" and (args.preview or args.full_size_preview):
            suffix = "preview"
        channel_dir = Path(os.path.abspath(args.channel)).parent.name or args.channel.stem
        episode_dir = Path(os.path.abspath(args.episode)).parent.name or args.episode.stem
        args.out = Path("output") / channel_dir / f"{episode_dir}-{suffix}"
    if args.command == "audio":
        from studio.audio import audio_summary, prepare_audio
        from studio.render import export_srt

        with new_package(args.out) as out, TemporaryDirectory() as temp:
            timeline, _ = prepare_audio(episode, args.episode.parent, out / "mix.wav", Path(temp), audio_library, channel=channel)
            report = {"duration_seconds": timeline["duration_frames"] / timeline["fps"], **audio_summary(timeline)}
            write_json(out / "timeline.json", timeline)
            write_json(out / "audio-qa.json", report)
            if timeline["captions"]:
                export_srt(out / "captions.srt", timeline["captions"], timeline["fps"])
        return {**report, "package": str(args.out.resolve())}, 0

    from studio.scenes import load_library, validate_three
    from studio.visual import validate_visual

    library = load_library(channel, args.channel.parent)
    for scene in episode["scenes"]:
        for shot in scene["shots"]:
            validate_three(shot, library)
    validate_visual(episode, library)
    if args.command == "validate":
        return {"valid": True, "episode": episode["title"], "channel": channel["name"]}, 0
    if args.command == "check-visual":
        from studio.audio import prepare_audio
        from studio.visual import audit_visual

        with TemporaryDirectory() as temp:
            work = Path(temp)
            timeline, _ = prepare_audio(episode, args.episode.parent, work / "mix.wav", work, audio_library, channel=channel)
            report = audit_visual(episode, library, timeline, include_cameras=True)
        return report, int(bool(report["issues"]))
    from studio.render import render

    report = render(episode, channel, args.episode.parent, args.channel.parent, args.out, args.preview, not args.no_burn,
                    backend=args.renderer, library=library, audio_library=audio_library)
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
