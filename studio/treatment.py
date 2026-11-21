"""Treatment lint: check an episode's plan before any shot is built.

    python -m studio.treatment workspace/<slug>/episodes/<episode>/episode.json   (or the treatment.md)

A treatment (``episodes/<episode>/treatment.md``, template in docs/memory-templates.md)
holds the idea in one sentence, the route, the energy curve and the shot table.
Plans fail in recognisable ways long before a render shows it, so this reads the
plan and reports:

* missing       no shot table (high) or no energy table (medium); no idea sentence
* row           a shot with no concrete subject or no action, or a template placeholder
* time          rows that leave gaps, overlap, or do not add up to the runtime
* hook-title    the film opens on a text card instead of an action
* hook-long     the first shot holds over 3 s without a camera move
* words         more than six words of on-screen text in a shot
* text-led      text cards fill over 30 % of the runtime
* text-ending   the film ends on a text card
* same-framing  two shots in a row share size and a still camera: a cut nobody sees
* one-size      every shot is the same size (one framing reads as a slide)
* push-run      three push-ins in a row: go in, then come back out
* accents       more accent moves (crash zoom, whip, shake, slam) than the film can carry
* shot-length   a shot over 6 s (12 s is high); the continuous route allows long takes
* flat          the energy curve barely changes, or never reaches 7
* slow-open      the first stretch is under 5
* no-landing    the peak is the last stretch: no beat to land the payoff
* repeat        the opening or payoff device repeats one of the last three ledger episodes
* manifest      episode.json disagrees with the plan's runtime or shot count

Red (any high) exits 1. Method adapted from the shot-list lint of huashu-art-motion,
the rhythm sheet of huashu-motion and the spine and variety checks of cinetic (all MIT).
"""

import argparse
import json
import math
from pathlib import Path
import re

from .film_qa import meta_from_text, read_meta, verdict

SIZES = {
    "extreme-close": ("extreme-close", "extreme close", "ecu", "xcu", "macro", "detail"),
    "close": ("close", "close-up", "closeup", "cu", "mcu", "medium-close", "medium close"),
    "medium": ("medium", "mid", "ms", "mid-shot", "medium shot", "cowboy", "two-shot", "two shot"),
    "wide": ("wide", "ws", "ls", "long", "full", "full shot", "establishing"),
    "extreme-wide": ("extreme-wide", "extreme wide", "ews", "xws", "aerial"),
    "insert": ("insert", "prop", "cutaway"),
    "card": ("card", "title", "title card", "text", "text card", "end card"),
}
STILL_CAMERA = ("", "hold", "still", "locked", "static", "none", "-", "drift", "float", "breathe")
PUSHES = ("push", "push-in", "dolly-in", "dolly in", "zoom-in", "zoom in", "crash-zoom", "crash zoom", "punch-in")
ACCENTS = ("crash", "whip", "shake", "slam", "snap", "punch-in", "smash")
TEXT_SUBJECTS = ("title", "text", "card", "caption", "logo", "headline", "words")
PLACEHOLDER = re.compile(r"<[^>]*>")


def _note(kind, severity, note, fix, **extra):
    return {"kind": kind, "severity": severity, "note": note, "fix": fix, **extra}


def size_of(value):
    text = (value or "").strip().lower()
    for size, names in SIZES.items():
        if text in names:
            return size
    for size, names in SIZES.items():  # "close on the cup", "wide, low angle"
        if any(re.search(rf"\b{re.escape(name)}\b", text) for name in names if len(name) > 2):
            return size
    return text or None


def parse_time(value):
    numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", value or "")]
    return (numbers[0], numbers[1]) if len(numbers) >= 2 and numbers[1] > numbers[0] else None


def tables(text):
    """{section heading (lower case): [row dicts keyed by lower-case column]}."""
    found, heading, header = {}, None, None
    for line in text.splitlines():
        title = re.match(r"^##\s+(.+?)\s*$", line)
        if title:
            heading, header = title.group(1).strip().lower(), None
            continue
        if not line.strip().startswith("|") or heading is None:
            if line.strip():
                header = None  # prose ends a table; a later table in the section brings its own header
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
            continue
        if header is None:
            header = [re.sub(r"[^a-z0-9 ]", "", cell.lower()).strip() for cell in cells]
            continue
        found.setdefault(heading, []).append(dict(zip(header, cells + [""] * (len(header) - len(cells)))))
    return found


def column(row, *names):
    for name in names:
        for key, value in row.items():
            if key == name or key.startswith(name):
                return value
    return ""


def meta_lines(text):
    meta = {}
    for line in text.split("\n## ")[0].splitlines():
        match = re.match(r"\s*[-*]?\s*\**([A-Za-z ]+?)\**\s*:\**\s*(.*)$", line)
        if match:
            meta[match.group(1).strip().lower()] = match.group(2).strip()
    return meta


def parse(text):
    sections = tables(text)
    shots_key = next((key for key in sections if key.startswith("shot")), None)
    energy_key = next((key for key in sections if key.startswith("energy") or key.startswith("rhythm")), None)
    shots = []
    for index, row in enumerate(sections.get(shots_key, [])):
        shots.append({"id": column(row, "", "shot", "id") or str(index + 1), "time": parse_time(column(row, "time")),
                      "subject": column(row, "subject", "object", "what"), "action": column(row, "action", "verb"),
                      "size": size_of(column(row, "size", "framing")), "camera": column(row, "camera", "move").lower(),
                      "words": column(row, "on screen", "onscreen", "text", "words"),
                      "raw": " | ".join(row.values())})
    energy = []
    for row in sections.get(energy_key, []):
        if PLACEHOLDER.search(" ".join(row.values())):
            continue  # an unfilled template row rates nothing
        levels = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", column(row, "energy"))]
        energy.append({"stretch": column(row, "stretch", "section", "part"), "time": parse_time(column(row, "time")),
                       "levels": [level for level in levels if 0 <= level <= 10]})
    meta = meta_lines(text)
    return {"meta": meta, "shots": shots, "energy": energy, "has_energy": energy_key is not None}


def _text_card(shot):
    subject = shot["subject"].lower()
    return shot["size"] == "card" or any(re.search(rf"\b{word}\b", subject) for word in TEXT_SUBJECTS) \
        and not shot["action"].strip()


def _filled(value):
    return bool(value and value.strip() and not PLACEHOLDER.fullmatch(value.strip()) and value.strip() != "-")


def ledger_grammar(path, exclude=None, last=3):
    """[(episode, {opening, payoff, camera})] for the last ledger rows that record a grammar."""
    if not path or not Path(path).is_file():
        return []
    rows = []
    for rows_in_section in tables("## ledger\n" + Path(path).read_text(encoding="utf-8")).values():
        rows += rows_in_section
    found = []
    for row in rows:
        cell = column(row, "grammar")
        episode = column(row, "episode")
        if not cell or (exclude and exclude.lower() in episode.lower()):
            continue
        parts = {}
        for part in re.split(r"[·;]", cell):
            if ":" in part:
                key, value = part.split(":", 1)
                parts[key.strip().lower()] = value.strip().lower()
        if parts:
            found.append((episode, parts))
    return found[-last:]


def _same(a, b):
    words = lambda text: set(re.findall(r"[a-z]{3,}", text.lower())) - {"the", "and", "with", "into", "from"}
    left, right = words(a), words(b)
    return bool(left and right) and len(left & right) / min(len(left), len(right)) >= 0.6


def lint(text, ledger=None, episode=None, manifest=None):
    plan = parse(text)
    meta, shots, energy = plan["meta"], plan["shots"], plan["energy"]
    notes = []
    route = meta_from_text(text)["route"]
    if not shots:
        return [_note("missing", "high", "No shot table.", "Add a ## Shots table: # | Time | Subject | Action | "
                      "Size | Camera | On screen | Sound (template in docs/memory-templates.md).")], plan
    if not plan["has_energy"] or not energy:
        notes.append(_note("missing", "medium", "No energy table.",
                           "Rate each stretch 0-10 (hook, build, stop, payoff, exit) before building."))
    if not _filled(meta.get("idea", "")):
        notes.append(_note("missing", "medium", "No idea sentence.",
                           "Write one sentence: the visible change the viewer waits for, and why it lands."))

    for shot in shots:
        if PLACEHOLDER.search(shot["raw"]) or not _filled(shot["subject"]) or not _filled(shot["action"]):
            notes.append(_note("row", "high", f"Shot {shot['id']} has no concrete subject and action.",
                               "Name the thing on screen (a noun) and what it does (a verb). A row you cannot "
                               "fill is a shot you cannot animate yet.", shot=shot["id"]))
        words = len(re.findall(r"[\w'’]+", PLACEHOLDER.sub("", shot["words"]))) if _filled(shot["words"]) else 0
        if words > 6:
            notes.append(_note("words", "medium", f"Shot {shot['id']} puts {words} words on screen.",
                               "Two to six words a line; let the picture say the rest.", shot=shot["id"]))

    timed = [shot for shot in shots if shot["time"]]
    runtime = None
    try:
        runtime = float(re.findall(r"\d+(?:\.\d+)?", meta.get("runtime", ""))[0])
    except IndexError:
        pass
    if len(timed) < len(shots):
        notes.append(_note("time", "medium", f"{len(shots) - len(timed)} shot(s) have no time range.",
                           "Give every shot a start-end in seconds, e.g. 2.0-3.5."))
    for before, after in zip(timed, timed[1:]):
        if abs(after["time"][0] - before["time"][1]) > 0.1:
            notes.append(_note("time", "medium", f"Shots {before['id']} and {after['id']} leave a gap or overlap "
                               f"({before['time'][1]:g} → {after['time'][0]:g}).", "Make the ranges continuous."))
    end = timed[-1]["time"][1] if timed else None
    runtime = runtime or end
    if runtime and end and abs(end - runtime) > 0.5:
        notes.append(_note("time", "medium", f"The shots end at {end:g} s but the runtime says {runtime:g} s.",
                           "Make the table and the Runtime line agree."))

    first, last = shots[0], shots[-1]
    if _text_card(first):
        notes.append(_note("hook-title", "high", "The film opens on a text card.",
                           "Open on a concrete action already in motion (a hand, a prop, a fall); put the "
                           "words over it.", shot=first["id"]))
    if first["time"] and first["time"][1] - first["time"][0] > 3.0 and first["camera"] in STILL_CAMERA:
        notes.append(_note("hook-long", "medium", f"The first shot holds {first['time'][1] - first['time'][0]:g} s "
                           "on a still camera.", "Cut or move by 3 s.", shot=first["id"]))
    if len(shots) > 1 and _text_card(last):
        notes.append(_note("text-ending", "high", "The film ends on a text card.",
                           "End on an action: the subject does one last thing (a settle, a reaction, a move "
                           "back to the opening frame for a loop).", shot=last["id"]))
    if runtime and timed:
        texty = sum(shot["time"][1] - shot["time"][0] for shot in timed if _text_card(shot))
        if texty / runtime > 0.3:
            notes.append(_note("text-led", "medium", f"Text cards fill {texty / runtime:.0%} of the runtime.",
                               "Keep text-led shots under 30 %; show the thing instead."))

    sizes = [shot["size"] for shot in shots if shot["size"]]
    if len(shots) == 1 and runtime and runtime > 6 and route != "continuous":
        notes.append(_note("one-size", "high", f"One shot carries all {runtime:g} s.",
                           "Give the turn and the payoff their own shot size: wide to set up, close on the "
                           "reaction, an insert on the prop."))
    elif len(sizes) >= 2 and len(set(sizes)) == 1:
        notes.append(_note("one-size", "high" if len(sizes) >= 3 else "medium",
                           f"Every shot is {sizes[0]}.", "Change shot size at every section: wide, close, insert."))
    for before, after in zip(shots, shots[1:]):
        if before["size"] and before["size"] == after["size"] and before["camera"] in STILL_CAMERA \
                and after["camera"] in STILL_CAMERA:
            notes.append(_note("same-framing", "medium", f"Shots {before['id']} and {after['id']} are both "
                               f"{after['size']} on a still camera.", "Change size or move the camera so the cut "
                               "reads.", shot=after["id"]))
    run = 0
    for shot in shots:
        run = run + 1 if any(word in shot["camera"] for word in PUSHES) else 0
        if run == 3:
            notes.append(_note("push-run", "medium", f"Three push-ins in a row, ending at shot {shot['id']}.",
                               "After a push in, pull out, pan across or cut to a new size.", shot=shot["id"]))
    accents = sum(any(word in shot["camera"] for word in ACCENTS) for shot in shots)
    budget = max(2, math.ceil((runtime or 0) / 6))
    if accents > budget:
        notes.append(_note("accents", "medium", f"{accents} accent moves for a {runtime or 0:g} s film.",
                           f"Keep crash zooms, whips and shakes for the reveal and the payoff (about {budget})."))
    for shot in timed if len(shots) > 1 else []:  # a single shot is already one-size
        length = shot["time"][1] - shot["time"][0]
        if route == "continuous":
            continue
        if length > 12:
            notes.append(_note("shot-length", "high", f"Shot {shot['id']} runs {length:g} s.",
                               "Split it at the turn.", shot=shot["id"]))
        elif length > 6:
            notes.append(_note("shot-length", "medium", f"Shot {shot['id']} runs {length:g} s.",
                               "Short-form changes the picture every 2-4 s; split it or move the camera with a "
                               "purpose.", shot=shot["id"]))

    levels = [level for stretch in energy for level in stretch["levels"]]
    if levels:
        if max(levels) - min(levels) < 3:
            notes.append(_note("flat", "high", f"The energy stays between {min(levels):g} and {max(levels):g}.",
                               "Design contrast: a hook, a build in steps, a stop or a dip, a peak, a landing."))
        elif max(levels) < 7:
            notes.append(_note("flat", "medium", f"The energy never passes {max(levels):g}.",
                               "Give the payoff a peak of 7 or more: a hard landing, a burst of quick beats."))
        opening = energy[0]["levels"]
        if opening and opening[0] < 5:
            notes.append(_note("slow-open", "medium", f"The opening stretch is rated {opening[0]:g}.",
                               "Hook at 5 or more: open mid-action."))
        peaks = [index for index, stretch in enumerate(energy) if stretch["levels"] and max(stretch["levels"]) ==
                 max(levels)]
        if peaks and peaks[0] == len(energy) - 1 and len(energy) > 2:
            notes.append(_note("no-landing", "low", "The peak is the last stretch.",
                               "Leave a beat after the payoff: a reaction, a settle, a tag or a loop back."))

    if ledger:
        for key in ("opening", "payoff"):
            mine = meta.get(key, "")
            if not _filled(mine):
                continue
            for other, grammar in ledger:
                if _same(mine, grammar.get(key, "")):
                    notes.append(_note("repeat", "medium", f"The {key} device repeats {other}: {grammar[key]}.",
                                       f"Change the {key}: another shot size, prop, reveal or camera grammar."))
                    break
    if manifest:
        shots_in = [shot for scene in manifest.get("scenes", []) for shot in scene.get("shots", [])]
        length = sum(float(shot.get("duration", 0)) for shot in shots_in)
        if runtime and shots_in and abs(length - runtime) > 1.0:
            notes.append(_note("manifest", "medium", f"episode.json runs {length:g} s; the treatment says "
                               f"{runtime:g} s.", "Update whichever changed; the treatment is the plan of record."))
        if shots_in and len(shots_in) != len(shots):
            notes.append(_note("manifest", "low", f"episode.json has {len(shots_in)} shots; the treatment has "
                               f"{len(shots)}.", "Keep the shot table in step with the manifest."))
    return notes, plan


def run(target):
    target = Path(target)
    path = target if target.suffix == ".md" else target.parent / "treatment.md"
    if not path.is_file():
        return {"treatment": str(path), "verdict": "red", "notes": [_note(
            "missing", "high", "No treatment.md.", "Create it with make channel-memory SLUG=<slug> EPISODE=<episode> "
            "and fill it before building shots.")]}
    episode_dir = path.parent
    manifest_path = episode_dir / "episode.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else None
    ledger = ledger_grammar(episode_dir.parent.parent / "channel" / "episode-ledger.md", exclude=episode_dir.name)
    notes, plan = lint(path.read_text(encoding="utf-8"), ledger, episode_dir.name, manifest)
    meta = read_meta(path)
    return {"treatment": str(path), "verdict": verdict(notes), "notes": notes,
            "summary": {"shots": len(plan["shots"]), "route": meta["route"], "stops": meta["stops"],
                        "sizes": [shot["size"] for shot in plan["shots"]],
                        "energy": [stretch["levels"] for stretch in plan["energy"]]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", type=Path, help="episode.json or treatment.md")
    args = parser.parse_args()
    report = run(args.target)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["verdict"] == "red" else 0


if __name__ == "__main__":
    raise SystemExit(main())
