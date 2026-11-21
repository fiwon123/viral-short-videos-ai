"""Treatment lint: the plan is checked before shots are built."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]

GOOD = """# Heavy lifting: treatment

Idea: The duck lifts a barbell that is secretly the octopus, and the rat sees it first.
Look: flat cel, warm sodium light
Route: hybrid
Runtime: 13
Opening: insert on the bar bending mid-lift
Payoff: crash zoom on the rat's face as the bar waves back

## Energy

| Stretch | Time | Energy | What carries it |
| --- | --- | --- | --- |
| hook | 0-2 | 7 | bar bends, creak on frame one |
| build | 2-7 | 5→7 | three lifts, each higher |
| stop | 7-7.5 | 1 | freeze at the top |
| payoff | 7.5-11 | 9 | the bar waves |
| exit | 11-13 | 4 | rat backs away |

## Shots

| # | Time | Subject | Action | Size | Camera | On screen | Sound |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | 0-2 | the barbell | bends under the duck's grip | insert | push-in | HEAVY DAY | creak |
| B | 2-5 | the duck | heaves the bar overhead twice | wide | hold | - | grunts |
| C | 5-7.5 | the rat | squints at the bar's end | close | drift | - | squeak |
| D | 7.5-9 | the bar | waves a tentacle at the rat | close | crash-zoom | - | slap |
| E | 9-13 | the rat | backs out of frame as the duck flexes | medium | pull-out | - | whoosh |
"""

HEADER = "| # | Time | Subject | Action | Size | Camera | On screen | Sound |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n"


def with_shots(rows, energy=None, extra=""):
    """GOOD with its shot table (and optionally its energy rows) replaced."""
    text = GOOD.split("## Shots")[0] + "## Shots\n\n" + HEADER + "\n".join(rows) + "\n"
    if energy is not None:
        head, tail = text.split("## Energy")
        rest = tail.split("## Shots")[1]
        text = head + "## Energy\n\n| Stretch | Time | Energy |\n| --- | --- | --- |\n" + "\n".join(energy) + \
            "\n\n## Shots" + rest
    return text.replace("Runtime: 13", "Runtime: 13" + extra)


def found(text, **kwargs):
    from studio.treatment import lint
    return {(note["kind"], note["severity"]) for note in lint(text, **kwargs)[0]}


def kinds(text, **kwargs):
    return {kind for kind, _ in found(text, **kwargs)}


class TreatmentLintTests(unittest.TestCase):
    def test_a_varied_plan_is_clean(self):
        from studio.treatment import lint
        notes, plan = lint(GOOD)
        self.assertEqual(notes, [])
        self.assertEqual([shot["size"] for shot in plan["shots"]], ["insert", "wide", "close", "close", "medium"])
        self.assertEqual(plan["energy"][1]["levels"], [5.0, 7.0])

    def test_the_memory_template_is_red_until_filled(self):
        from studio.memory import templates
        from studio.treatment import lint
        from studio.film_qa import verdict
        notes = lint(templates()["episodes/<episode>/treatment.md"])[0]
        self.assertEqual(verdict(notes), "red")
        self.assertIn(("row", "high"), {(note["kind"], note["severity"]) for note in notes})
        self.assertNotIn("slow-open", {note["kind"] for note in notes})  # placeholders rate nothing

    def test_text_cards_at_either_end(self):
        opening = with_shots(["| A | 0-2 | title card | | card | hold | HEAVY DAY | sting |",
                              "| B | 2-13 | the duck | lifts and drops the bar | wide | push-in | - | thud |"])
        self.assertIn(("hook-title", "high"), found(opening))
        ending = with_shots(["| A | 0-6 | the duck | lifts the bar | close | push-in | - | creak |",
                             "| B | 6-11 | the bar | waves back | wide | whip | - | slap |",
                             "| C | 11-13 | end card | | card | hold | FOLLOW FOR MORE | sting |"])
        self.assertIn(("text-ending", "high"), found(ending))

    def test_framing_rules(self):
        single = with_shots(["| A | 0-13 | the gym | the friends lift together | wide | push-in | - | music |"])
        self.assertIn(("one-size", "high"), found(single))
        self.assertNotIn("shot-length", kinds(single))
        self.assertNotIn("one-size", kinds(single.replace("Route: hybrid", "Route: continuous")))
        same = with_shots(["| A | 0-4 | the duck | lifts | wide | hold | - | a |",
                           "| B | 4-8 | the rat | watches | wide | drift | - | b |",
                           "| C | 8-13 | the bar | waves | wide | hold | - | c |"])
        self.assertIn(("one-size", "high"), found(same))
        self.assertIn(("same-framing", "medium"), found(same))
        pushes = with_shots(["| A | 0-3 | the duck | lifts | wide | push-in | - | a |",
                             "| B | 3-6 | the rat | watches | close | dolly-in | - | b |",
                             "| C | 6-9 | the bar | bends | insert | push-in | - | c |",
                             "| D | 9-13 | the bar | waves | medium | pull-out | - | d |"])
        self.assertIn(("push-run", "medium"), found(pushes))
        shaky = with_shots([f"| {name} | {i * 13 / 4:g}-{(i + 1) * 13 / 4:g} | thing {name} | moves | "
                            f"{size} | {camera} | - | x |" for i, (name, size, camera) in enumerate(
                                [("A", "wide", "whip"), ("B", "close", "shake"), ("C", "insert", "crash-zoom"),
                                 ("D", "medium", "whip")])])
        self.assertIn(("accents", "medium"), found(shaky))
        long = with_shots(["| A | 0-7.5 | the duck | lifts slowly | wide | hold | - | a |",
                           "| B | 7.5-13 | the rat | runs | close | whip | - | b |"])
        self.assertIn(("shot-length", "medium"), found(long))
        self.assertIn(("hook-long", "medium"), found(long))

    def test_rows_words_and_time(self):
        vague = with_shots(["| A | 0-6 | the duck | | close | push-in | ONE TWO THREE FOUR FIVE SIX SEVEN | a |",
                            "| B | 7-13 | | waves | wide | whip | - | b |"])
        result = found(vague)
        self.assertIn(("row", "high"), result)
        self.assertIn(("words", "medium"), result)
        self.assertIn(("time", "medium"), result)  # 6 -> 7 gap
        short = GOOD.replace("Runtime: 13", "Runtime: 20")
        self.assertIn(("time", "medium"), found(short))

    def test_energy_shapes(self):
        flat = with_shots(GOOD.split("| --- | --- | --- | --- | --- | --- | --- | --- |\n")[1].strip().splitlines(),
                          energy=["| hook | 0-6 | 4 |", "| rest | 6-13 | 5 |"])
        self.assertIn(("flat", "high"), found(flat))
        self.assertIn(("slow-open", "medium"), found(flat))
        low_peak = flat.replace("| rest | 6-13 | 5 |", "| rest | 6-13 | 6→2 |")
        self.assertIn(("flat", "medium"), found(low_peak))
        ends_high = flat.replace("| hook | 0-6 | 4 |\n| rest | 6-13 | 5 |",
                                 "| hook | 0-3 | 6 |\n| build | 3-9 | 7 |\n| peak | 9-13 | 9 |")
        self.assertIn(("no-landing", "low"), found(ends_high))

    def test_ledger_variety(self):
        from studio.treatment import ledger_grammar
        with TemporaryDirectory() as temp:
            ledger = Path(temp) / "episode-ledger.md"
            ledger.write_text(
                "# Ledger\n\n| # | Episode | Status | Grammar | Lessons |\n| --- | --- | --- | --- | --- |\n"
                "| 1 | old-one | delivered | opening: wide establishing lineup · payoff: fall over | |\n"
                "| 2 | mid-one | delivered | opening: insert on the bar bending mid-lift · payoff: chase | |\n"
                "| 3 | heavy-lifting | planned | opening: insert on the bar bending mid-lift | |\n",
                encoding="utf-8")
            grammar = ledger_grammar(ledger, exclude="heavy-lifting")
            self.assertEqual([episode for episode, _ in grammar], ["old-one", "mid-one"])
            self.assertIn(("repeat", "medium"), found(GOOD, ledger=grammar))
            self.assertNotIn("repeat", kinds(GOOD, ledger=grammar[:1]))

    def test_manifest_agreement(self):
        manifest = {"scenes": [{"shots": [{"id": "A", "duration": 4}, {"id": "B", "duration": 12}]}]}
        result = found(GOOD, manifest=manifest)
        self.assertIn(("manifest", "medium"), result)
        self.assertIn(("manifest", "low"), result)

    def test_treatment_lines_are_shared_with_film_qa(self):
        from studio.film_qa import meta_from_text
        self.assertEqual(meta_from_text(GOOD + "\nStop: 7-7.5\n"), {"route": "hybrid", "stops": [(7.0, 7.5)]})


class TreatmentCliTests(unittest.TestCase):
    def cli(self, target):
        return subprocess.run([sys.executable, "-m", "studio.treatment", str(target)], cwd=ROOT,
                              capture_output=True, text=True)

    def test_episode_path_finds_the_treatment_and_gates(self):
        with TemporaryDirectory() as temp:
            episode = Path(temp) / "episodes" / "heavy-lifting"
            episode.mkdir(parents=True)
            (episode / "episode.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            missing = self.cli(episode / "episode.json")
            self.assertEqual(missing.returncode, 1)
            self.assertEqual(json.loads(missing.stdout)["notes"][0]["kind"], "missing")
            (episode / "treatment.md").write_text(GOOD, encoding="utf-8")
            good = self.cli(episode / "episode.json")
            self.assertEqual(good.returncode, 0, good.stdout)
            self.assertEqual(json.loads(good.stdout)["verdict"], "green")
            (episode / "treatment.md").write_text(GOOD.replace("| bends under the duck's grip |", "| |"),
                                                  encoding="utf-8")
            self.assertEqual(self.cli(episode / "treatment.md").returncode, 1)


if __name__ == "__main__":
    unittest.main()
