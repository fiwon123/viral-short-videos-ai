"""Episode state from evidence, the delivery gate, and the review pack.

    python -m studio.episode_state state  EPISODE [--channel C] [--write]
    python -m studio.episode_state deliver EPISODE [--channel C] [--video V]
    python -m studio.episode_state verify DELIVERY_MD
    python -m studio.episode_state review-pack EPISODE [--video V]

A status line written by hand can claim more than happened. ``state`` reads the
files instead and reports the furthest stage the evidence supports, in order:

    concept → planned → built → stills → previewed → reviewed → mastered → delivered → published

* planned     ``treatment.md`` exists and ``treatment-lint`` is not red
* built       ``video.py validate`` passes (schema, style lock, lint)
* stills      a review still exists under ``renders/<episode>-stills/``
* previewed   a preview render newer than ``episode.json`` with a film-qa report
* reviewed    a director's note under ``episodes/<episode>/review/*.md``
* mastered    a ``-vN`` render newer than ``episode.json`` whose film-qa is not red
* delivered   that master has a ``delivery.md`` whose facts verify
* published   ``episodes/<episode>/published.json`` (``make published``)

A render older than ``episode.json`` is stale and does not count. ``--write``
puts the computed stage on the ``Status:`` line of ``NOTES.md``.

``deliver`` is the gate: it reruns film-qa, treatment-lint and viral-check on
the newest master (or ``--video``), refuses a red film-qa or treatment verdict
(exit 2), and otherwise writes ``delivery.md`` beside the MP4. Its facts section
is written by the tool and sealed with a sha256, so ``verify`` can tell when it
was edited by hand or the MP4 changed afterwards. The maker adds notes (why each
amber item is acceptable) below the facts. Review files are listed, never read:
the reviewer's words are their own.

``review-pack`` gathers what cold reviewers need into ``review/pack-<render>/``,
one prompt per lens: the director (``prompt.md``: contact sheet, energy chart,
film-qa report, treatment, the treatment's key-still frames), sound
(``prompt-sound.md``: ``sound.png``, the mix's level with every cue and cut marked,
and ``sound-cues.json``) and continuity (``prompt-continuity.md``: ``cuts.png``, the
frames on both sides of every hard cut). Each lists the earlier review notes so a
round does not re-report what was fixed.

Adapted from lanshu-create-ai-presenter-video's evidence state machine, the
fingerprinted delivery notes of huashu-art-motion and cinetic's critic files (MIT).
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("concept", "planned", "built", "stills", "previewed", "reviewed", "mastered", "delivered", "published")
MASTER = re.compile(r"-v(\d+)$")
FACTS_START = "<!-- delivery facts: written by make deliver; do not edit -->"
FACTS_END = re.compile(r"<!-- delivery facts end sha256=([0-9a-f]{64}) -->")
PROMPT = """You are reviewing a vertical animated Short you did not make. Be specific and demanding.

Files (in this folder): {files}

1. Picture first: cover any text. For each row of sheet.png, one line: what happens.
   Any "nothing happens" is a P0.
2. Answer with frame times: Is something moving on frame one? Is the subject big enough to read at
   phone size when it changes? Is any stretch one framing with only text changing? Does the payoff get
   its own shot size or move? Does the end move? Is the cast one style with the set? Would this look
   the same on another channel?
3. Read report.json last. Name any film-qa note you disagree with, and why.
4. Give the three notes a demanding director would give, ranked P0/P1, each with the fix.

Earlier notes for this episode (read them first; do not re-report what was fixed): {earlier}

Write the result to {target}. The verdict is yours; do not soften it for the maker.
"""
SOUND_PROMPT = """You are the sound reviewer for a vertical animated Short you did not make. You cannot hear it, so
read it. Be specific and demanding.

Files (in this folder): {files}

sound.png is the soundtrack: the mix's level over time (dB), a tick and a name for every sound cue, a grey line
for every hard cut, and the picture's motion per second as pale bars behind. sound-cues.json lists every cue
(time, sound, shot) and, where film-qa measured it, its sync status and offset in ms.

Answer with times:
1. The hook: does a sound start within the first 0.3 s, while something moves?
2. Lock: is every hit, click and pop on the frame its action starts or stops? Name each that is off and by how
   many frames (sound-cues.json status early/late; for unmatched ones, look at the stills near that time).
3. Cause: does every visible action a viewer expects to hear (a landing, a grab, a release, a door) have a sound,
   and does every sound have a visible cause? Does one kind of action sound the same each time?
4. Restraint: no two designed sounds within 3 frames of each other on a key beat; the payoff is the loudest
   moment, ideally after a short dip (a 0.3-0.8 s stop before it).
5. Music, if any: a join that jumps (film-qa music-join), an ending that is not the track's own, music
   fighting a voice line.
6. The end: the last sound has finished before the last frame; nothing is cut off.

Earlier notes for this episode (read them first; do not re-report what was fixed): {earlier}

Write the result to {target}: a table (priority, time, problem, fix), then two sentences on the soundtrack.
Every fix names the field and the amount: a cue's `at` / `at_word` (by N frames), `gain`, `sound` or
`variant`, the shot's `snap`, `music.fit` or `music.library_track`. P0: heard on a key beat, or a sound with no
picture; P1: noticed on a normal viewing with sound; P2: a refinement.
"""
CONTINUITY_PROMPT = """You are the continuity reviewer for a vertical animated Short you did not make. You look at
frames side by side and name every difference that should not be there. Be specific and demanding.

Files (in this folder): {files}

cuts.png holds every hard cut as a pair: the last frame before it on the left, the first frame after it on the
right, with the time. still-*.png are the treatment's key moments at full size. treatment.md is the plan.

For every pair and every still:
1. Contact: feet, bodies and props rest on the floor or on what holds them; nothing floats or sinks, before and
   after a camera change. The set moves with the cast when the camera moves.
2. Ownership: every limb, prop and accessory is attached to the character it belongs to; nothing appears next
   to a character it does not belong to.
3. Across the cut: the same cast in the same places, the same prop in the same hand, the same screen direction
   of looking and moving, the same scale for one character in every shot; what changes is what the story needs.
4. Layering: who is in front of whom; a carried prop in front of its carrier; no arm across a face.
5. Edges: no set edge or empty corner showing, no layer cut off by the frame by accident, no caption under the
   platform's buttons.
6. Style: one line weight and one rendering style across cast, props and set.

Earlier notes for this episode (read them first; do not re-report what was fixed): {earlier}

Write the result to {target}: a table (priority, time, where in the frame, problem, fix). Every fix names the
layer and the field (`x` / `y` / `z` keys, `parallax`, `scale`, a pose, the layer order) or the generator line.
P0: seen at full speed on a key beat; P1: seen on a normal viewing; P2: seen only on pause.
"""
LENSES = ("director", "sound", "continuity")


def _sha(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def paths(episode, channel=None):
    episode = Path(episode).resolve()
    folder = episode.parent
    from .workspace import episode_root
    root = episode_root(episode)
    if channel is None and root is not None and (root / "channel" / "channel.json").is_file():
        channel = root / "channel" / "channel.json"
    renders = (root / "renders") if root is not None else ROOT / "output" / folder.name
    return {"episode": episode, "folder": folder, "slug": folder.name, "renders": renders,
            "channel": Path(channel).resolve() if channel else None}


def renders(where):
    """Fresh and stale render folders of this episode, newest first."""
    found = []
    base, slug = where["renders"], where["slug"]
    if not base.is_dir():
        return found
    edited = where["episode"].stat().st_mtime if where["episode"].is_file() else 0
    for folder in base.glob(f"{slug}-*"):
        video = folder / "video.mp4"
        if not video.is_file():
            continue
        suffix = folder.name[len(slug) + 1:]
        kind = "hook" if suffix.startswith("hook") else "preview" if "preview" in suffix else \
            "master" if MASTER.search(folder.name) else "other"
        found.append({"folder": folder, "video": video, "kind": kind, "mtime": video.stat().st_mtime,
                      "fresh": video.stat().st_mtime >= edited})
    return sorted(found, key=lambda item: -item["mtime"])


def film_report(render):
    report = render["folder"] / "film-qa" / "report.json"
    if report.is_file():
        return json.loads(report.read_text(encoding="utf-8"))
    return None


def treatment_verdict(where):
    from .treatment import run
    return run(where["folder"] / "treatment.md")


def validates(where):
    if not where["episode"].is_file():
        return False, "no episode.json"
    command = [sys.executable, str(ROOT / "video.py"), "validate", str(where["episode"])]
    if where["channel"]:
        command += ["--channel", str(where["channel"])]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode == 0:
        return True, "video.py validate passed"
    return False, (result.stderr or result.stdout).strip().splitlines()[-1][:300] if (result.stderr or result.stdout) \
        else "video.py validate failed"


def reviews(where):
    folder = where["folder"] / "review"
    return sorted(path for path in folder.glob("*.md") if path.stat().st_size > 0) if folder.is_dir() else []


def state(episode, channel=None, *, validator=None):
    where = paths(episode, channel)
    rel = lambda path: str(Path(path).resolve().relative_to(ROOT)) if Path(path).resolve().is_relative_to(ROOT) \
        else str(path)
    target = rel(where["episode"])
    channel_arg = f" CHANNEL={rel(where['channel'])}" if where["channel"] else ""
    evidence, reached, missing, command = {"concept": "episode folder exists"}, "concept", [], None
    all_renders = renders(where)
    master = next((item for item in all_renders if item["kind"] == "master" and item["fresh"]), None)

    def stage(name, ok, detail, need, run):
        nonlocal reached, missing, command
        if missing:
            return
        if ok:
            evidence[name] = detail
            reached = name
        else:
            missing, command = need, run

    lint = treatment_verdict(where)
    root = where["renders"].parent
    create = f"make channel-memory SLUG={root.name} EPISODE={where['slug']}"
    stage("planned", lint["verdict"] != "red", f"treatment.md lints {lint['verdict']}",
          [note["note"] for note in lint["notes"] if note["severity"] == "high"] or ["treatment.md is red"],
          f"make treatment-lint EPISODE={target}" if (where["folder"] / "treatment.md").is_file() else
          f"{create}  # then fill treatment.md and run make treatment-lint")
    ok, detail = (validator or validates)(where)
    stage("built", ok, detail, [detail], f"python3 video.py validate {target}"
          + (f" --channel {rel(where['channel'])}" if where["channel"] else ""))
    stills = sorted((where["renders"] / f"{where['slug']}-stills").glob("*.png")) \
        if (where["renders"] / f"{where['slug']}-stills").is_dir() else []
    stage("stills", bool(stills), f"{len(stills)} review still(s)",
          ["no review stills: look at the hook and the payoff before a full render"],
          f"make still EPISODE={target} SHOT=<hook shot> PROGRESS=0.1{channel_arg}")
    preview = next((item for item in all_renders if item["kind"] == "preview" and item["fresh"]
                    and film_report(item)), None)
    stale = [item["folder"].name for item in all_renders if item["kind"] == "preview" and not item["fresh"]]
    stage("previewed", preview is not None, preview and f"{preview['folder'].name}: film-qa "
          f"{film_report(preview)['verdict']}",
          ["no preview newer than episode.json with a film-qa report"] + ([f"stale: {', '.join(stale)}"] if stale else []),
          f"make preview EPISODE={target}{channel_arg}")
    notes = reviews(where)
    stage("reviewed", bool(notes), f"review notes: {', '.join(path.name for path in notes)}",
          ["no director's notes in review/: run the director pass on the preview"],
          f"make review-pack EPISODE={target}")
    verdict = film_report(master)["verdict"] if master and film_report(master) else None
    stage("mastered", master is not None and verdict not in (None, "red"),
          master and f"{master['folder'].name}: film-qa {verdict}",
          ["no -vN render newer than episode.json"] if master is None else
          [f"{master['folder'].name} has no film-qa report"] if verdict is None else
          [f"{master['folder'].name}: film-qa is red; fix it and render a new -vN"],
          f"make render EPISODE={target}{channel_arg}" if master is None or verdict == "red" else
          f"make film-qa VIDEO={rel(master['video'])} EPISODE={target}")
    delivered = master and (master["folder"] / "delivery.md").is_file() and \
        verify(master["folder"] / "delivery.md")["ok"]
    stage("delivered", bool(delivered), master and f"{master['folder'].name}/delivery.md verifies",
          ["no verified delivery.md beside the master"], f"make deliver EPISODE={target}{channel_arg}")
    stage("published", (where["folder"] / "published.json").is_file(), "published.json",
          ["not marked published"], f"make published EPISODE={target}")
    following = STAGES[STAGES.index(reached) + 1] if reached != STAGES[-1] else None
    return {"episode": target, "state": reached, "next_state": following, "missing": missing,
            "next": command, "evidence": evidence,
            "renders": [{"folder": item["folder"].name, "kind": item["kind"], "fresh": item["fresh"]}
                        for item in all_renders]}


def write_status(episode, report, today=None):
    notes = Path(episode).resolve().parent / "NOTES.md"
    line = f"Status: {report['state']} (from evidence: make state, {(today or datetime.now()).date().isoformat()})"
    if not notes.is_file():
        notes.write_text(f"# {Path(episode).resolve().parent.name}: notes\n\n{line}\n", encoding="utf-8")
        return notes
    text = notes.read_text(encoding="utf-8")
    if re.search(r"^Status:.*$", text, re.M):
        text = re.sub(r"^Status:.*$", line, text, count=1, flags=re.M)
    else:
        head, _, rest = text.partition("\n")
        text = f"{head}\n\n{line}\n{rest}"
    notes.write_text(text, encoding="utf-8")
    return notes


def _probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    picture = next((item for item in data["streams"] if item.get("codec_type") == "video"), {})
    num, _, den = (picture.get("r_frame_rate") or "0/1").partition("/")
    return {"duration": round(float(data["format"]["duration"]), 2), "width": picture.get("width"),
            "height": picture.get("height"), "fps": round(float(num) / float(den or 1), 3),
            "audio": any(item.get("codec_type") == "audio" for item in data["streams"])}


def _viral(where, video):
    command = [sys.executable, "-m", "studio.viral_check", str(where["episode"]), "--video", str(video)]
    if where["channel"]:
        command += ["--channel", str(where["channel"])]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": (result.stderr or "no output").strip().splitlines()[-1][:200]}


def _narration(where, folder):
    """The narration check for a render, reusing its narration.json when it is newer than the video."""
    from .narration import check
    saved, video = folder / "narration.json", folder / "video.mp4"
    if saved.is_file() and video.is_file() and saved.stat().st_mtime >= video.stat().st_mtime:
        return json.loads(saved.read_text(encoding="utf-8"))
    if not (folder / "timeline.json").is_file():
        return {"verdict": "no-speech", "notes": []}
    report = check(folder / "timeline.json", where["folder"])
    if report["verdict"] not in ("unchecked", "no-speech"):
        saved.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def deliver(episode, channel=None, video=None, *, viral=None, narration=None):
    """Gate and write delivery.md; returns (report, exit code)."""
    from .film_qa import run as film_qa
    where = paths(episode, channel)
    if video:
        video = Path(video).resolve()
    else:
        master = next((item for item in renders(where) if item["kind"] == "master" and item["fresh"]), None)
        if master is None:
            return {"delivered": False, "reasons": ["no -vN render newer than episode.json"]}, 2
        video = master["video"]
    folder = video.parent
    film = film_qa(video, treatment=where["folder"] / "treatment.md")
    lint = treatment_verdict(where)
    reasons = [f"film-qa: {note['note']}" for note in film["notes"] if note["severity"] == "high"]
    reasons += [f"treatment: {note['note']}" for note in lint["notes"] if note["severity"] == "high"]
    if reasons:
        return {"delivered": False, "video": str(video), "film_qa": film["verdict"], "treatment": lint["verdict"],
                "reasons": reasons}, 2
    score = (viral or _viral)(where, video)
    speech = (narration or _narration)(where, folder)
    info = _probe(video)
    qa = json.loads((folder / "qa.json").read_text(encoding="utf-8")) if (folder / "qa.json").is_file() else {}
    loudness = ((qa.get("audio") or {}).get("loudness") or {})
    metrics = film["metrics"]
    notes = reviews(where)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    facts = [
        f"- File: `{video.name}` · sha256 `{_sha(video)}`",
        f"- Picture: {info['width']}×{info['height']} at {info['fps']:g} fps, {info['duration']} s; audio: "
        f"{'yes' if info['audio'] else 'none'}; loudness {loudness.get('integrated_lufs', 'not measured')} LUFS, "
        f"true peak {loudness.get('true_peak_db', 'not measured')} dB",
        f"- Film QA: **{film['verdict']}** · mean energy {metrics['mean_energy']} · low-energy share "
        f"{metrics['low_share']} · cuts {len(metrics['cuts'])} · longest framing {metrics['longest_framing']} s · "
        f"pops {len(metrics.get('pops', []))}",
    ]
    facts += [f"  - {note['severity']} `{note['kind']}`: {note['note']}" for note in film["notes"]]
    facts.append(f"- Treatment: **{lint['verdict']}**")
    facts += [f"  - {note['severity']} `{note['kind']}`: {note['note']}" for note in lint["notes"]]
    if "error" in score:
        facts.append(f"- Viral check: not run ({score['error']})")
    else:
        facts.append(f"- Viral check: **{score['score']}**/100")
        facts += [f"  - {note['severity']} `{note['kind']}`: {note['note']}" for note in score["notes"]]
    if speech["verdict"] == "unchecked":
        facts.append(f"- Narration: **not checked** ({speech.get('reason', 'no recogniser')})")
    elif speech["verdict"] != "no-speech":
        facts.append(f"- Narration: **{speech['verdict']}** ({len(speech.get('lines', []))} line(s) heard back with "
                     f"faster-whisper {speech.get('model', '')})".replace(" )", ")"))
        facts += [f"  - {note['severity']} `{note['kind']}`: {note['note']}" for note in speech["notes"]]
    facts.append(f"- Director's notes: {', '.join(f'`review/{path.name}`' for path in notes)} (listed, not read)"
                 if notes else "- Director's notes: **none** (no review/*.md; the director pass did not happen)")
    facts.append(f"- Publishing copy: {'`publishing.md`' if (folder / 'publishing.md').is_file() else 'missing'}")
    facts.append(f"- Written {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by make deliver"
                 + (f" at studio commit `{commit}`" if commit else ""))
    body = "\n".join(facts) + "\n"
    seal = hashlib.sha256(body.encode()).hexdigest()
    ambers = [f"film-qa `{note['kind']}`" for note in film["notes"] if note["severity"] == "medium"] + \
        [f"treatment `{note['kind']}`" for note in lint["notes"] if note["severity"] == "medium"] + \
        [f"narration `{note['kind']}`" for note in speech["notes"] if note["severity"] in ("medium", "high")]
    maker = ["## Maker's notes", "",
             "Write below this line. Say why each amber item is acceptable, what the director's notes changed, and "
             "what to paste where (see `publishing.md`)."]
    if ambers:
        maker += ["", "Amber items to answer: " + ", ".join(ambers) + "."]
    if not notes:
        maker += ["", "No director's notes exist: say why the director pass was skipped."]
    document = f"# Delivery: {where['slug']}\n\n{FACTS_START}\n{body}<!-- delivery facts end sha256={seal} -->\n\n" + \
        "\n".join(maker) + "\n"
    target = folder / "delivery.md"
    if target.is_file():  # keep the maker's notes from an earlier delivery of this render
        earlier = target.read_text(encoding="utf-8").split("## Maker's notes", 1)
        if len(earlier) == 2 and earlier[1].strip():
            document = document.split("## Maker's notes", 1)[0] + "## Maker's notes" + earlier[1]
    target.write_text(document, encoding="utf-8")
    return {"delivered": True, "delivery": str(target), "video": str(video), "film_qa": film["verdict"],
            "treatment": lint["verdict"], "viral_check": score.get("score"), "narration": speech["verdict"],
            "director_notes": len(notes),
            "amber": ambers}, 0


def verify(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if FACTS_START not in text:
        return {"ok": False, "reason": "no facts section written by make deliver"}
    body = text.split(FACTS_START, 1)[1].lstrip("\n")
    match = FACTS_END.search(body)
    if not match:
        return {"ok": False, "reason": "the facts seal is missing"}
    facts = body[:match.start()]
    if hashlib.sha256(facts.encode()).hexdigest() != match.group(1):
        return {"ok": False, "reason": "the facts were edited after make deliver wrote them"}
    named = re.search(r"File: `([^`]+)` · sha256 `([0-9a-f]{64})`", facts)
    if named:
        video = path.parent / named.group(1)
        if not video.is_file():
            return {"ok": False, "reason": f"{named.group(1)} is missing"}
        if _sha(video) != named.group(2):
            return {"ok": False, "reason": f"{named.group(1)} changed after delivery"}
    return {"ok": True}


def key_stills(treatment):
    """(label, seconds) from a treatment's Key stills list ("- Hook: 0.6 s (A)")."""
    if not Path(treatment).is_file():
        return []
    text = Path(treatment).read_text(encoding="utf-8")
    section = re.search(r"^##\s+Key stills\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    found = []
    for label, seconds in re.findall(r"^\s*[-*]\s*([A-Za-z ]+?)\s*:\s*[^\d\n]*?(\d+(?:\.\d+)?)\s*s\b",
                                     section.group(1) if section else "", re.M):
        found.append((label.strip().lower().replace(" ", "-"), float(seconds)))
    return found


def earlier_notes(where):
    """The episode's review notes so far, as paths a reviewer can open."""
    folder = where["folder"] / "review"
    names = sorted(path.name for path in folder.glob("*.md")) if folder.is_dir() else []
    return ", ".join(f"review/{name}" for name in names) or "none"


def cue_table(timeline, report):
    """Every sfx cue in the render's timeline, with film-qa's sync row when it measured one."""
    if not timeline.is_file():
        return []
    data = json.loads(timeline.read_text(encoding="utf-8"))
    fps = float(data.get("fps", 24))
    rows = (report.get("metrics") or {}).get("sync") or []
    cues = []
    for scene in data.get("scenes", []):
        for shot in scene.get("shots", []):
            for cue in shot.get("sfx", []):
                at = round(cue["start"] / fps, 3)
                entry = {"at": at, "sound": cue.get("sound") or cue.get("cue") or Path(str(cue.get("source", ""))).stem,
                         "shot": shot["id"], "gain": cue.get("gain")}
                match = next((row for row in rows if abs(row.get("cue", -1) - at) < 0.002), None)
                if match:
                    entry.update({key: match[key] for key in ("status", "offset_ms", "picture") if key in match})
                cues.append(entry)
    return cues


def sound_chart(video, cues, report, target, width=1080, height=360):
    """The mix's level over time with cues, cuts and the picture's energy: sound for a reader who cannot hear."""
    from PIL import Image, ImageDraw
    from .music import RATE, decode
    try:
        samples = decode(video)
    except subprocess.CalledProcessError:
        return None
    if not len(samples):
        return None
    hop = RATE // 50
    blocks = len(samples) // hop
    level = 20 * np.log10(np.sqrt(np.mean(samples[:blocks * hop].reshape(blocks, hop) ** 2, axis=1)) + 1e-6)
    duration = len(samples) / RATE
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    left, top, bottom = 40, 46, height - 24
    span = width - left - 10

    def x(seconds):
        return left + span * seconds / max(duration, 1e-6)

    def y(db):
        return bottom - (bottom - top) * (max(-60.0, min(0.0, db)) + 60) / 60

    energy = (report.get("metrics") or {}).get("energy") or []
    peak = max(energy) if energy else 1.0
    for second, value in enumerate(energy):
        draw.rectangle((x(second), bottom - (bottom - top) * value / max(peak, 1e-6) * 0.9, x(second + 1) - 1, bottom),
                       fill="#EEF2F6")
    for db in (-12, -24, -36, -48):
        draw.line((left, y(db), width - 10, y(db)), fill="#DEE2E6")
        draw.text((4, y(db) - 6), str(db), fill="#868E96")
    for cut in (report.get("metrics") or {}).get("cuts") or []:
        draw.line((x(cut), top, x(cut), bottom), fill="#ADB5BD", width=1)
    points = [(x(index * hop / RATE), y(value)) for index, value in enumerate(level)]
    draw.line(points, fill="#1C7ED6", width=1)
    colours = {"early": "#E03131", "late": "#E03131", "synced": "#2F9E44", "on-cut": "#2F9E44"}
    for index, cue in enumerate(cues):
        colour = colours.get(cue.get("status"), "#495057")
        draw.line((x(cue["at"]), top - 4, x(cue["at"]), bottom), fill=colour, width=1)
        draw.text((x(cue["at"]) + 2, 4 + 14 * (index % 3)), str(cue["sound"])[:12], fill=colour)
    for second in range(0, int(duration) + 1, max(1, int(duration) // 14 or 1)):
        draw.text((x(second) - 3, bottom + 6), str(second), fill="#495057")
    image.save(target)
    return target


def cut_pairs(video, report, target, tile=270, limit=12):
    """The last frame before and the first frame after every hard cut, side by side, one row per cut."""
    from PIL import Image, ImageDraw
    from .film_qa import probe
    cuts = ((report.get("metrics") or {}).get("cuts") or [])[:limit]
    if not cuts:
        return None
    fps = probe(video)["fps"]
    rows = []
    with tempfile.TemporaryDirectory() as temp:
        for index, cut in enumerate(cuts):
            frame = int(round(cut * fps))
            pair = []
            for side, number in (("before", frame - 1), ("after", frame)):
                path = Path(temp) / f"{index}-{side}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                                f"select=eq(n\\,{max(0, number)}),scale={tile}:-2", "-frames:v", "1", str(path)],
                               capture_output=True, check=False)
                if not path.is_file():
                    break
                pair.append(Image.open(path).convert("RGB"))
            if len(pair) == 2:
                rows.append((cut, pair))
    if not rows:
        return None
    high = rows[0][1][0].height
    sheet = Image.new("RGB", (tile * 2 + 12, (high + 22) * len(rows)), "#FFFFFF")
    draw = ImageDraw.Draw(sheet)
    for row, (cut, (before, after)) in enumerate(rows):
        top = row * (high + 22)
        draw.text((4, top + 4), f"cut at {cut:.2f} s: before | after", fill="#212529")
        sheet.paste(before, (0, top + 20))
        sheet.paste(after, (tile + 12, top + 20))
    sheet.save(target)
    return target


def review_pack(episode, video=None, lenses=LENSES):
    from .film_qa import run as film_qa
    where = paths(episode)
    if video:
        video = Path(video).resolve()
    else:
        fresh = [item for item in renders(where) if item["fresh"] and item["kind"] in ("preview", "master")]
        if not fresh:
            raise ValueError("No preview or master newer than episode.json; render one first (make preview).")
        video = fresh[0]["video"]
    report = (video.parent / "film-qa" / "report.json")
    if not report.is_file():
        film_qa(video, treatment=where["folder"] / "treatment.md")
    pack = where["folder"] / "review" / f"pack-{video.parent.name}"
    pack.mkdir(parents=True, exist_ok=True)
    files = []
    for name in ("sheet.png", "energy.png", "report.json"):
        source = video.parent / "film-qa" / name
        if source.is_file():
            shutil.copyfile(source, pack / name)
            files.append(name)
    treatment = where["folder"] / "treatment.md"
    if treatment.is_file():
        shutil.copyfile(treatment, pack / "treatment.md")
        files.append("treatment.md")
    for label, seconds in key_stills(treatment):
        name = f"still-{label}-{seconds:g}s.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(seconds), "-i", str(video), "-frames:v", "1",
                        str(pack / name)], capture_output=True, check=False)
        if (pack / name).is_file():
            files.append(name)
    unknown = [lens for lens in lenses if lens not in LENSES]
    if unknown:
        raise ValueError(f"Unknown lens {', '.join(unknown)}; choose from {', '.join(LENSES)}.")
    report_data = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}
    earlier = earlier_notes(where)
    stills = [name for name in files if name.startswith("still-")]
    prompts, targets = [], {}
    for lens in lenses:
        lens_files = list(files)
        if lens == "director":
            template, prompt_name = PROMPT, "prompt.md"
        elif lens == "sound":
            template, prompt_name = SOUND_PROMPT, "prompt-sound.md"
            cues = cue_table(video.parent / "timeline.json", report_data)
            (pack / "sound-cues.json").write_text(json.dumps(cues, indent=2) + "\n", encoding="utf-8")
            lens_files = ["sound-cues.json", "report.json"] + stills
            if sound_chart(video, cues, report_data, pack / "sound.png"):
                lens_files.insert(0, "sound.png")
        else:
            template, prompt_name = CONTINUITY_PROMPT, "prompt-continuity.md"
            lens_files = stills + (["treatment.md"] if "treatment.md" in files else [])
            if cut_pairs(video, report_data, pack / "cuts.png"):
                lens_files.insert(0, "cuts.png")
        target = f"episodes/{where['slug']}/review/{lens}-{video.parent.name}.md"
        (pack / prompt_name).write_text(template.format(files=", ".join(lens_files), target=target, earlier=earlier),
                                        encoding="utf-8")
        prompts.append(prompt_name)
        targets[lens] = target
    extra = [name for name in ("sound.png", "sound-cues.json", "cuts.png") if (pack / name).is_file()]
    return {"pack": str(pack), "files": files + extra + prompts, "video": str(video),
            "write_notes_to": targets.get("director") or next(iter(targets.values())), "lenses": targets}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("state", "deliver", "review-pack"):
        command = commands.add_parser(name)
        command.add_argument("episode", type=Path)
        command.add_argument("--channel", type=Path)
        if name == "state":
            command.add_argument("--write", action="store_true", help="put the stage on NOTES.md's Status line")
        else:
            command.add_argument("--video", type=Path)
        if name == "review-pack":
            command.add_argument("--lens", default=",".join(LENSES),
                                 help=f"comma-separated reviewers to prepare (default: {','.join(LENSES)})")
    check = commands.add_parser("verify")
    check.add_argument("delivery", type=Path)
    args = parser.parse_args()
    if args.command == "state":
        report = state(args.episode, args.channel)
        if args.write:
            report["notes"] = str(write_status(args.episode, report))
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "deliver":
        report, code = deliver(args.episode, args.channel, args.video)
        print(json.dumps(report, indent=2))
        return code
    if args.command == "verify":
        report = verify(args.delivery)
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    try:
        lenses = tuple(lens.strip() for lens in args.lens.split(",") if lens.strip())
        print(json.dumps(review_pack(args.episode, args.video, lenses), indent=2))
    except ValueError as error:
        print(f"studio: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
