"""Build a copy-ready publishing guide for a rendered episode package."""

import re
from pathlib import Path

# Limits per destination. Keep platform rules here so a new destination is one entry.
LIMITS = {
    "youtube": {"title": 100, "description": 5000, "tags": 500, "tag": 100},
    "tiktok": {"caption": 2200},
}

FILE_NOTES = {
    "publishing.md": "This guide.",
    "publishing.json": "The title, description, and tags as machine-readable JSON.",
    "timed-script.md": "Per-shot staging, speech, and sound record.",
    "timeline.json": "Resolved frame timeline for re-editing.",
    "qa.json": "Verified runtime, resolution, codecs, and caption count.",
    "visual-qa.json": "Layer, contact, and continuity checks.",
    "captions.srt": "Subtitles for upload or review.",
    "thumbnail.png": "Cover image.",
    "mix.wav": "Mixed soundtrack before encoding.",
}

PACKAGE_ORDER = ("thumbnail.png", "captions.srt", "publishing.md", "publishing.json",
                 "timed-script.md", "timeline.json", "qa.json", "visual-qa.json")


def duration(seconds):
    minutes, seconds = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:d}:{seconds:02d}"


def fence(text):
    ticks = "`" * max(3, max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    return f"{ticks}text\n{text}\n{ticks}"


def limit_line(name, label, value, maximum, warnings):
    count = len(value)
    if count > maximum:
        warnings.append(f"{name} {label.lower()} is {count} characters; the limit is {maximum:,}")
        return (f"**{label}** — {count:,} / {maximum:,} characters · "
                "**over the limit, trim before publishing**")
    return f"**{label}** — {count:,} / {maximum:,} characters"


def hashtag_line(values):
    tags = []
    for value in values:
        words = re.findall(r"[^\W_]+", str(value).lstrip("#"))
        if not words:
            continue
        tag = words[0] if len(words) == 1 else "".join(word[:1].upper() + word[1:] for word in words)
        if tag.lower() not in (existing.lower() for existing in tags):
            tags.append(tag)
    return " ".join(f"#{tag}" for tag in tags)


def tiktok_body(episode):
    body = episode["description"].strip()
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    while lines and lines[-1].startswith("#") and all(word.startswith("#") for word in lines[-1].split()):
        lines.pop()
    body = "\n".join(lines).strip() or episode["title"]
    return re.sub(r"(\s+#[^\W_]+)+\s*$", "", body).strip()


def tiktok_caption(episode, channel):
    settings = episode.get("tiktok") or {}
    tags = list(settings.get("hashtags") or [])
    if not tags:
        tags = list(episode.get("tags") or [])
        if name := channel.get("name"):
            tags.append(name)
    suffix = hashtag_line(tags)
    body = (settings.get("caption") or tiktok_body(episode)).strip()
    present = {tag.lower() for tag in re.findall(r"#[^\W_]+", body)}
    missing = [tag for tag in suffix.split() if tag.lower() not in present]
    if missing:
        body = f"{body.rstrip()} {' '.join(missing)}".strip()
    return body


def youtube_section(episode, warnings):
    limit = LIMITS["youtube"]
    description = episode["description"].strip()
    tags = ", ".join(episode["tags"])
    rows = ["## YouTube", "",
            limit_line("YouTube", "Title", episode["title"], limit["title"], warnings), "",
            fence(episode["title"]), "",
            limit_line("YouTube", "Description", description, limit["description"], warnings), "",
            fence(description), "",
            limit_line("YouTube", "Tags", tags, limit["tags"], warnings), ""]
    if any(len(tag) > limit["tag"] for tag in episode["tags"]):
        warnings.append(f"YouTube has a tag longer than {limit['tag']} characters")
        rows.extend([f"One tag is longer than {limit['tag']} characters; YouTube keeps the first "
                     f"{limit['tag']}.", ""])
    rows.extend([fence(tags), "",
                 "Paste the title, description, and tags into YouTube Studio → Details. "
                 "Tags go under **Show more → Tags**.", ""])
    if episode["height"] > episode["width"]:
        rows.extend(["Keep `#Shorts` in the title or description so YouTube treats a vertical upload as a Short.", ""])
    return rows


def tiktok_section(episode, channel, warnings):
    caption = tiktok_caption(episode, channel)
    return ["## TikTok", "",
            "TikTok has no separate tags field, so the hashtags below belong to the caption, "
            "which is the description shown under the video. Only the first two lines show before "
            "\"See more\", and links are not clickable, so keep any link in your bio.", "",
            limit_line("TikTok", "Caption", caption, LIMITS["tiktok"]["caption"], warnings), "",
            fence(caption), "",
            "Paste it into the caption box before posting, with the hook on the first line.", ""]


def package_section(package, destination, video, episode, runtime):
    present = {entry.name for entry in package.iterdir() if entry.is_file()}
    present.update(("publishing.md", "qa.json"))
    names = [name for name in dict.fromkeys((video, *PACKAGE_ORDER)) if name in present]
    names += sorted(present - set(names))
    notes = dict(FILE_NOTES)
    notes[video] = f"Final {episode['width']} × {episode['height']} render at {runtime}. Upload this file."
    rows = ["## Package", "", f"Folder: `{destination.absolute()}`", ""]
    rows.extend(f"- `{name}` — {notes.get(name, 'Rendered file.')}" for name in names)
    return [*rows, ""]


def channel_guide(channel, base):
    """Human-readable channel identity with copy-ready platform blocks."""
    base = Path(base)
    name = channel["name"]
    handle = channel.get("handle", "")
    rows = [f"# 🎬 {name}", ""]
    if handle:
        rows.extend([f"`{handle}`", ""])
    rows.extend([f"> {channel['tagline']}", "",
                 "This page is generated from `channel.json`. Edit the JSON, then run "
                 "`python video.py channel-doc <channel.json>` to refresh it.", "",
                 "## Identity", "",
                 "| Field | Value |",
                 "| --- | --- |",
                 f"| Name | **{name}** |",
                 f"| Handle | `{handle or '—'}` |",
                 f"| Mark | `{channel.get('mark', '')}` |",
                 f"| Font | `{channel.get('font', 'default sans serif')}` |",
                 f"| Tags | {', '.join(channel.get('tags', []))} |", ""])
    palette = channel["palette"]
    rows.extend(["## 🎨 Palette", "",
                 "| Role | Hex | Swatch |",
                 "| --- | --- | --- |"])
    for role, value in palette.items():
        hexed = value.lstrip("#")
        rows.append(f"| {role} | `{value}` | "
                    f"![{role}](https://img.shields.io/badge/-%23{hexed}?style=flat-square&color={hexed}) |")
    rows.append("")
    if (base / "brand" / "logo.png").is_file():
        rows.extend(["## 🖼️ Brand kit", "",
                     "| Asset | File |",
                     "| --- | --- |",
                     "| Logo | [brand/logo.png](brand/logo.png) |",
                     "| Banner | [brand/banner.png](brand/banner.png) |",
                     "| Safe-area preview | [brand/banner-safe-preview.png](brand/banner-safe-preview.png) |", ""])
    rows.extend(["## 📺 YouTube channel description", "",
                 fence(channel["description"].strip()), "",
                 "## 🏷️ YouTube channel tags", "",
                 fence(", ".join(channel.get("tags", []))), "",
                 "## 🎵 TikTok bio", "",
                 fence((channel.get("tagline", "") + " " + hashtag_line(channel.get("tags", []))).strip()), "",
                 "## 📋 Where to paste", "",
                 "| Platform | Field | Source |",
                 "| --- | --- | --- |",
                 "| YouTube | Channel description | the block above |",
                 "| YouTube | Channel tags | the block above |",
                 "| TikTok | Bio | the block above |",
                 "| YouTube / TikTok | Episode title, description, tags and caption | each render's `publishing.md` |", ""])
    return "\n".join(rows).rstrip() + "\n"


def publishing_guide(episode, channel, timeline, package, destination=None):
    runtime = duration(timeline["duration_frames"] / timeline["fps"])
    video = next((entry.name for entry in sorted(package.glob("*.mp4"))), "video.mp4")
    warnings = []
    identity = channel["name"]
    if handle := channel.get("handle"):
        identity = f"{identity} ({handle})"
    rows = [f"# Publishing — {episode['title']}", "",
            f"{identity} · `{video}` · {episode['width']} × {episode['height']} · {runtime} · "
            f"{timeline['fps']} fps", "",
            "Every block below is copy-ready. Counts are characters including spaces.", ""]
    rows.extend(youtube_section(episode, warnings))
    rows.extend(tiktok_section(episode, channel, warnings))
    rows.extend(package_section(package, destination or package, video, episode, runtime))
    if warnings:
        rows[6:6] = ["> **Trim before publishing:** " + "; ".join(warnings) + ".", ""]
    return "\n".join(rows).rstrip() + "\n", warnings
