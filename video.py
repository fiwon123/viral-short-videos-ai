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
            command.add_argument("--out", type=Path,
                                 help="package directory (defaults to the channel workspace or output/)")
        if name == "render":
            preview = command.add_mutually_exclusive_group()
            preview.add_argument("--preview", action="store_true", help="export a half-size preview")
            preview.add_argument("--full-size-preview", action="store_true", help="export a preview at full resolution")
            command.add_argument("--renderer", choices=("python", "remotion", "hyperframes"), default="python",
                                 help="select the visual renderer")
            captions = command.add_mutually_exclusive_group()
            captions.add_argument("--no-burn", action="store_true", help="export captions as a separate SRT only")
            captions.add_argument("--no-captions", action="store_true", help="disable burned captions and SRT")
            command.add_argument("--no-thumbnail", action="store_true", help="skip thumbnail.png")
            command.add_argument("--no-publishing", action="store_true", help="skip publishing.md and publishing.json")
            command.add_argument("--stems", action="store_true", help="write dialogue/music/ambience/sfx stems")
            command.add_argument("--crf", type=int, help="override the H.264 CRF quality")
            command.add_argument("--preset", help="override the x264 preset")
            command.add_argument("--audio-bitrate", type=int, help="override the AAC bitrate in kbps")
            command.add_argument("--scale", type=float, help="scale the output canvas, for example 0.5")
    still = commands.add_parser("still", help="render one frame or a contact sheet for fast review")
    still.add_argument("episode", type=Path)
    still.add_argument("--channel", type=Path)
    still.add_argument("--shot", help="shot ID; defaults to the thumbnail shot")
    still.add_argument("--at", type=float, default=0.0, help="seconds from the shot start")
    still.add_argument("--progress", type=float, help="0 to 1 through the shot")
    still.add_argument("--scale", type=float, default=1.0)
    still.add_argument("--renderer", choices=("auto", "python", "remotion", "hyperframes"), default="auto")
    still.add_argument("--out", type=Path)
    still.add_argument("--sheet", type=int, help="render this many evenly spaced frames as a contact sheet")
    still.add_argument("--times", help="comma separated seconds for a contact sheet")
    still.add_argument("--no-captions", action="store_true")
    still.add_argument("--no-audio", action="store_true")
    presets = commands.add_parser("presets", help="list style presets")
    presets.add_argument("--channel", type=Path)
    presets.add_argument("--json", action="store_true")
    templates = commands.add_parser("templates", help="list shot templates")
    templates.add_argument("--channel", type=Path)
    templates.add_argument("--json", action="store_true")
    motion = commands.add_parser("motion", help="list or emit manifest-ready motion recipes")
    motion.add_argument("recipe", nargs="?")
    motion.add_argument("--list", action="store_true")
    motion.add_argument("--duration", type=float, default=1.0)
    motion.add_argument("--t0", type=float, default=0.0)
    motion.add_argument("--amount", type=float)
    brand = commands.add_parser("brand", help="generate a logo, banner, and channel metadata")
    brand.add_argument("channel", type=Path)
    brand.add_argument("--out", required=True, type=Path)
    doc = commands.add_parser("channel-doc", help="write channel.md from the channel manifest")
    doc.add_argument("channel", type=Path)
    resolve = commands.add_parser("resolve", help="show the effective preset, render and audio settings")
    resolve.add_argument("episode", type=Path)
    resolve.add_argument("--channel", type=Path)
    resolve.add_argument("--json", action="store_true")
    align = commands.add_parser("align", help="import measured word timings into an episode")
    align.add_argument("episode", type=Path)
    align.add_argument("--json", required=True, type=Path)
    safearea = commands.add_parser("safearea", help="write a platform safe-area guide image")
    safearea.add_argument("--platform", choices=("youtube-shorts", "tiktok", "generic"), default="youtube-shorts")
    safearea.add_argument("--out", required=True, type=Path)
    shot_template = commands.add_parser("shot-template", help="emit a parameterised reusable shot")
    shot_template.add_argument("template", help="template name under presets/shots")
    shot_template.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    shot_template.add_argument("--channel", type=Path)
    shot_template.add_argument("--out", type=Path)
    editor = commands.add_parser("editor", help="open the local shot inspector")
    editor.add_argument("episode", type=Path)
    editor.add_argument("--channel", type=Path)
    editor.add_argument("--port", type=int, default=8765)
    editor.add_argument("--no-open", action="store_true")
    batch = commands.add_parser("batch", help="validate or render a season manifest")
    batch.add_argument("season", type=Path)
    batch.add_argument("--only", action="append", default=[], help="episode ID; repeatable")
    batch.add_argument("--status", help="only entries with this status")
    batch.add_argument("--renderer", choices=("python", "hyperframes", "remotion"))
    batch.add_argument("--preview", action="store_true", default=None)
    batch.add_argument("--jobs", type=int, default=1)
    batch.add_argument("--validate-only", action="store_true")
    batch.add_argument("--dry-run", action="store_true")
    batch.add_argument("--out-root", type=Path)
    schema = commands.add_parser("schema", help="write per-manifest schema wrappers for editors")
    schema.add_argument("--out", type=Path, default=Path("schema"))
    support = commands.add_parser("support", help="show the renderer support matrix")
    support.add_argument("--markdown", action="store_true")
    support.add_argument("--out", type=Path)
    parity = commands.add_parser("parity", help="render the shared renderer-parity fixture")
    parity.add_argument("--renderers", default="python,hyperframes")
    parity.add_argument("--out", type=Path)
    sound = commands.add_parser("sound", help="synthesize a custom Sound Lab recipe")
    sound.add_argument("channel", type=Path)
    sound.add_argument("--recipe", required=True, type=Path)
    sound.add_argument("--library", default="audio/cast-v2.json")
    sound.add_argument("--variants", type=int)
    effect = commands.add_parser("effect", help="generate a custom Effect Lab SVG")
    effect.add_argument("channel", type=Path)
    effect.add_argument("--recipe", required=True, type=Path)
    effect.add_argument("--folder", default="vfx")
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

    if args.command == "align":
        from studio.alignment import apply, load as load_alignment
        from studio.core import load, write_json

        episode = load(args.episode, "episode")
        apply(episode, load_alignment(args.json))
        write_json(args.episode, episode)
        return {"episode": str(args.episode.resolve()), "lines": len(load_alignment(args.json).get("lines", []))}, 0
    if args.command == "safearea":
        from studio.safearea import build

        return build(args.platform, args.out), 0
    if args.command == "shot-template":
        from studio.core import write_json
        from studio.templates import build

        params = {}
        for item in args.set:
            if "=" not in item:
                raise ValueError(f"Use KEY=VALUE for --set: {item}")
            key, value = item.split("=", 1)
            params[key] = value
        data = build(args.template, params, args.channel.parent if args.channel else None)
        if args.out:
            write_json(args.out, data)
            return {"template": args.template, "out": str(args.out.resolve())}, 0
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    if args.command in {"presets", "templates"}:
        from studio.presets import available_styles
        from studio.templates import available as available_templates

        base = args.channel.parent if getattr(args, "channel", None) else None
        found = available_styles(base) if args.command == "presets" else available_templates(base)
        rows = [{"name": name, "path": str(path.resolve())} for name, path in sorted(found.items())]
        if args.json:
            return {"kind": args.command, "items": rows}, 0
        print(f"{args.command}: " + (", ".join(row["name"] for row in rows) or "none"))
        for row in rows:
            print(f"  {row['name']:24} {row['path']}")
        return 0
    if args.command == "motion":
        import inspect
        from studio import motion

        recipes = {
            "pop": motion.pop, "anticipate": motion.anticipate, "impact": motion.impact,
            "settle": motion.settle, "float": motion.float_loop, "breathe": motion.breathe,
            "enter": motion.enter, "exit": motion.exit,
        }
        if not args.recipe or args.list:
            print("motion recipes: " + ", ".join(sorted(recipes)))
            return 0
        if args.recipe not in recipes:
            raise ValueError(f"Unknown motion recipe: {args.recipe}. Available: {', '.join(sorted(recipes))}")
        function = recipes[args.recipe]
        available = set(inspect.signature(function).parameters)
        values = {"t0": args.t0, "duration": args.duration}
        if args.amount is not None:
            values["amount"] = args.amount
        kwargs = {key: value for key, value in values.items() if key in available}
        keys = function(**kwargs)
        return {"recipe": args.recipe, "keyframes": keys}, 0
    if args.command == "batch":
        from studio.batch import run

        report = run(args.season, only=args.only, status=args.status, renderer=args.renderer,
                     preview=args.preview, jobs=args.jobs, validate_only=args.validate_only,
                     dry_run=args.dry_run, out_root=args.out_root)
        return report, 0 if report.get("ok", True) else 1
    if args.command == "schema":
        from studio.core import write_json

        args.out.mkdir(parents=True, exist_ok=True)
        written = []
        for kind in ("episode", "channel", "audio_library", "library", "style_preset", "shot", "season"):
            path = args.out / f"{kind}.schema.json"
            write_json(path, {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"urn:viral-short-videos:{kind}",
                "$ref": f"../studio/schema.json#/$defs/{kind}",
            })
            written.append(str(path.resolve()))
        return {"schemas": written}, 0
    if args.command == "support":
        from studio.core import write_json
        from studio.support import markdown, matrix

        if args.markdown:
            text = markdown()
            if args.out:
                args.out.write_text(text, encoding="utf-8")
            else:
                print(text, end="")
            return {"out": str(args.out.resolve()) if args.out else None}, 0
        data = matrix()
        if args.out:
            write_json(args.out, data)
        print(json.dumps(data, indent=2))
        return data, 0
    if args.command == "parity":
        from studio.parity import run

        return run(tuple(item.strip() for item in args.renderers.split(",") if item.strip()), args.out), 0
    if args.command == "sound":
        from studio.soundlab import build

        return build(args.channel, args.recipe, library=args.library, variants=args.variants), 0
    if args.command == "effect":
        from studio.effectlab import build

        return build(args.channel, args.recipe, folder=args.folder), 0

    from studio.core import load, new_package, validate_channel, validate_episode, write_json

    if args.channel is None:
        from studio.project import resolve_channel

        args.channel = resolve_channel(Path(__file__).resolve().parent)
    channel = load(args.channel, "channel")
    validate_channel(channel, args.channel.parent)
    if args.command == "editor":
        from studio.editor import serve

        serve(args.episode, args.channel, args.port, not args.no_open)
        return 0
    if args.command == "resolve":
        from studio.presets import apply_style, resolved_config

        episode = load(args.episode, "episode")
        from studio.expand import expand as expand_defs

        episode = expand_defs(episode)
        episode = apply_style(episode, channel, args.channel.parent)
        from studio.markers import expand as expand_markers
        from studio.particles import expand as expand_particles
        from studio.trails import expand as expand_trails

        episode = expand_particles(expand_trails(expand_markers(episode, args.channel.parent)))
        data = resolved_config(episode, channel)
        if args.json:
            return data, 0
        rows = ["# Resolved episode", "", f"Channel: **{channel['name']}**", ""]
        for section in ("style", "render", "audio", "post", "captions"):
            value = data[section]
            rows.extend([f"## {section}", "", "```json",
                         json.dumps(value, indent=2, ensure_ascii=False), "```", ""])
        print("\n".join(rows).rstrip())
        return 0
    if args.command in {"brand", "channel-doc"}:
        from studio.publishing import channel_guide

        if args.command == "brand":
            from studio.design import make_brand

            with new_package(args.out) as out:
                make_brand(channel, args.channel.parent, out)
                write_json(out / "channel-publishing.json", {
                    key: channel[key] for key in ("name", "handle", "tagline", "description", "tags") if key in channel
                })
        guide = channel_guide(channel, args.channel.parent)
        (args.channel.parent / "channel.md").write_text(guide, encoding="utf-8")
        if args.command == "channel-doc":
            return {"channel": channel["name"],
                    "markdown": str((args.channel.parent / "channel.md").resolve())}, 0
        return {"brand": channel["name"], "package": str(args.out.resolve()),
                "markdown": str((args.channel.parent / "channel.md").resolve())}, 0

    from studio.audio_library import load_audio_library, validate_audio
    from studio.presets import apply_style

    episode = load(args.episode, "episode")
    from studio.expand import expand as expand_defs

    episode = expand_defs(episode)
    episode = apply_style(episode, channel, args.channel.parent)
    from studio.markers import expand as expand_markers
    from studio.particles import expand as expand_particles
    from studio.trails import expand as expand_trails

    episode = expand_markers(episode, args.channel.parent)
    episode = expand_trails(episode)
    episode = expand_particles(episode)
    validate_episode(episode, args.episode.parent, args.channel.parent, check_visual_assets=args.command != "audio")
    audio_library = load_audio_library(channel, args.channel.parent)
    validate_audio(episode, audio_library)
    if args.command == "still":
        from studio.scenes import load_library, validate_three
        from studio.still import contact_sheet, render_still
        from studio.visual import validate_visual
        from studio.workspace import default_output

        loaded = load_library(channel, args.channel.parent)
        for scene in episode["scenes"]:
            for shot in scene["shots"]:
                validate_three(shot, loaded)
        validate_visual(episode, loaded)
        shot_id = args.shot or episode["thumbnail"]["shot"]
        target = next((shot for scene in episode["scenes"] for shot in scene["shots"]
                       if shot["id"] == shot_id), None)
        if target is None:
            names = ", ".join(shot["id"] for scene in episode["scenes"] for shot in scene["shots"])
            raise ValueError(f"Unknown shot: {shot_id}. Available: {names}")
        needs_browser = "three" in target or any(layer["kind"] == "svg" for layer in target["layers"])
        renderer = args.renderer
        if renderer == "auto":
            renderer = "hyperframes" if needs_browser else "python"
        if renderer == "python" and needs_browser:
            raise ValueError("SVG and 3D stills need --renderer hyperframes or remotion")
        folder = default_output(args.episode, args.channel, "stills")
        times = [float(value) for value in args.times.split(",") if value.strip()] if args.times else []
        if times or args.sheet:
            count = max(2, args.sheet or len(times))
            if not times:
                duration = float(target["duration"])
                times = [round(duration * (index + 0.5) / count, 4) for index in range(count)]
            with TemporaryDirectory() as temp:
                paths, labels = [], []
                for index, moment in enumerate(times):
                    path = Path(temp) / f"still-{index}.png"
                    render_still(episode, channel, args.episode.parent, args.channel.parent, path,
                                 shot_id=shot_id, at=moment, scale=args.scale, renderer=renderer,
                                 burn=not args.no_captions, audio=not args.no_audio,
                                 library=loaded, audio_library=audio_library)
                    paths.append(path)
                    labels.append(f"{shot_id} · {moment:g}s")
                sheet = args.out or (folder / f"{shot_id}-sheet.png")
                contact_sheet(paths, sheet, labels=labels)
                return {"sheet": str(Path(sheet).resolve()), "shot": shot_id, "frames": len(times)}, 0
        stamp = f"{args.progress:g}" if args.progress is not None else f"{args.at:g}s"
        out = args.out or (folder / f"{shot_id}-{stamp}.png")
        report = render_still(episode, channel, args.episode.parent, args.channel.parent, out,
                              shot_id=shot_id, at=args.at, progress=args.progress, scale=args.scale,
                              renderer=renderer, burn=not args.no_captions, audio=not args.no_audio,
                              library=loaded, audio_library=audio_library)
        return report, 0
    if args.command in {"audio", "render"} and args.out is None:
        suffix = "audio" if args.command == "audio" else "v1"
        if args.command == "render" and (args.preview or args.full_size_preview):
            suffix = "preview"
        from studio.workspace import default_output

        args.out = default_output(args.episode, args.channel, suffix)
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

    options = {}
    if args.no_captions:
        options["captions"] = False
    if args.no_thumbnail:
        options["thumbnail"] = False
    if args.no_publishing:
        options["publishing"] = False
    if args.stems:
        options["stems"] = True
    if args.crf is not None:
        options["crf"] = args.crf
    if args.preset:
        options["preset"] = args.preset
    if args.audio_bitrate is not None:
        options["audio_bitrate"] = args.audio_bitrate
    if args.scale is not None:
        options["scale"] = args.scale
    report = render(episode, channel, args.episode.parent, args.channel.parent, args.out, args.preview,
                    not (args.no_burn or args.no_captions), backend=args.renderer, library=library,
                    audio_library=audio_library, options=options)
    return {**report, "package": str(args.out.resolve())}, 0


def main():
    try:
        result = execute(options())
    except ModuleNotFoundError as error:
        print(f"studio: {error}. Install requirements.txt in your Python environment.", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as error:
        print(f"studio: {error}", file=sys.stderr)
        return 1
    if isinstance(result, tuple):
        result, status = result
    else:
        status = result if isinstance(result, int) else 0
        result = None
    if result is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main())
