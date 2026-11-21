## Testing Requirements

### General

- Tests are mandatory for new features and bug fixes
- Write tests before or alongside implementation
- Mock external services when possible — never call third-party production APIs in tests
- A *local* tool the project runs itself (ffmpeg, node, Chromium, eSpeak) is not a third-party API — tests may use it
- Aim for critical path coverage, not 100% line coverage

### Gates and baselines

A gate is only worth having if it can fail.

- **Do not fix pre-existing failures inside an unrelated PR.** If the suite (or
  `make check`) is already red when you start, your change is not the cause and
  the fix is not the change you set out to make. Say so, and either fix it
  forward on its own issue/branch or record it as a baseline below. Bundling an
  unrelated repair into your PR makes "is my change correct?" unanswerable from
  the diff.
- **Record a known-failing baseline.** When you inherit a red suite, write down
  which tests fail and why (a tracked issue, a TODO, the failing assertion) so
  the next person does not re-investigate the same failures. A baseline turns
  "the suite is red, I don't know why" into "these N are known-red".
- **A gate that cannot fail is worse than no gate.** A test target that collects
  zero tests, a CI job that always skips, or an assertion with no possible
  failure manufactures false confidence: it reads green and proves nothing. If a
  gate reports success without executing anything, treat it as **unverified**,
  not as passed — a skipped run is not a passed run.
- **A package with no tests is not a covered package.** A runner that prints
  `[no test files]` or `0 tests collected` for a package only compiled it. A
  green run that lists such packages is green for the packages that ran; say
  which ones did not.

### Proving a change

Learned the hard way across several projects built from this workflow; each
rule below is a defect that shipped at least once.

- **Reproduce the premise before implementing.** An issue's claim ("format X
  has a header", "tool Y supports platform Z") can be wrong. Check it first —
  a throwaway test or command — and say on the issue what you found.
- **Put the bug back.** A new regression test is only proven when it fails
  with the fix reverted and passes with it restored. A test written after the
  fix and never seen failing may be testing nothing.
- **Test through the path the user takes.** A test that calls a handler or
  widget method directly proves the handler, not the wiring: it passes when the
  click, route or flag that should reach it is broken. Drive the real entry
  point (the event, the HTTP route, the CLI through a pty).
- **A manifest test proves the data, not the picture.** A test that checks the
  expanded keys cannot see a frame the browser draws differently. Pair a
  renderer change with `make parity` and a still.
- **Prove build-time behaviour on the artifact.** A linker flag that names a
  missing symbol (`-X pkg.Var=…`), an embedded resource, a version stamp — a unit
  test cannot see any of them. Inspect the built binary (`go version -m`,
  `--version`, the archive listing).
- **A test's completion signal must be the last thing the work does.** Waiting
  on a flag the work clears *before* it finishes lets the test tear down under a
  goroutine that is still running, and the failure is reported against the next
  test.
- **A workflow edit is unverified until a run executes it.** A feature PR never
  parses a workflow that triggers only on release PRs or tags. Lint it
  (`actionlint`) and dispatch it (`workflow_dispatch`) before calling it done.
- **Say what you checked.** "The port answers" is not "the service can use this
  database"; "it builds" is not "it runs". State the exact command and what it
  showed, and name what you did not check.
- **Grep for the old wording after a fix.** A comment or doc describing the old
  behaviour outlives the code; no compiler or test reads prose.


### The studio's gates

Run from the repository root, on the host or in the sandbox (`make shell`):

| Command | What it proves |
|---|---|
| `make test` | The `unittest` suite in `tests/` (Python; the browser pose-parity tests run `node`). Every change. |
| `make treatment-lint EPISODE=...` | The episode's plan: hook, shot sizes, camera grammar, energy curve, variety against the ledger (red exits 1) |
| `make validate EPISODE=...` | The manifest against the schema, the style lock and the lint rules |
| `make check EPISODE=...` | Visual QA notes: captions, contrast, sound density, contacts |
| `make deliver EPISODE=...` | The delivery gate: film-qa, treatment and viral-check on the master; refuses red; writes sealed `delivery.md` (`VERIFY=` checks it) |
| `make narration-check EPISODE=...` | Each spoken line heard back (faster-whisper, optional) against the script: unheard, misread, number, repeat (red exits 1; `unchecked` without a recogniser) |
| `make film-qa VIDEO=...` | The render's pixels: energy per second, dead runs, frozen ending, blank frames, longest framing, sound effects against their picture events (red exits 1) |
| `make parity` | The renderers still agree on the shared fixture (non-zero past the threshold). Renderer changes. |
| `make doctor` | ffmpeg, the h264 encoder, the node renderers and Kokoro are usable |

A test that needs a tool the machine lacks is skipped (`node is not
installed`): a skipped test is not a passing one. Report the skip count, or run
the suite in the sandbox, where every tool is present.

Tests live in `tests/test_<area>.py`, as `unittest.TestCase` classes. Fixtures are
built in the test; nothing under `workspace/` or `reference-media/` (local, not
tracked) may be read by a test. The YouTube API is never called from a test.

## Visual checks

A manifest can validate, every test pass, and the video still be wrong: a
caption under the platform's buttons, a limb across a face, a black frame. Look
at the frames.

If your model cannot see images, delegate to the **`visual`** subagent: **the
main agent captures, the `visual` subagent looks, the main agent acts on the
findings.** Never report a visual conclusion the `visual` subagent has not
actually returned; if a review fails or is rate-limited, say the state is
unverified and retry in a smaller batch.

### Cadence: targeted while you work, full once at the end

| When | What |
|---|---|
| **While you work** | `make still SHOT=... PROGRESS=...` for the shots the change touches |
| **Before the PR** | A contact sheet (`make still SHEET=...`) or a `make preview`, once |

### Which artifact the change needs

| The change is… | Take |
|---|---|
| Layout, colour, captions, a pose | a still at the moment that matters |
| Motion, timing, easing, a camera move | `make still ONION=3`, `make motion-report`, or the preview MP4 frames |
| A whole episode | a contact sheet plus `make viral-check` and `make film-qa VIDEO=...` |

The Read tool renders PNG, JPEG and GIF, not MP4: pull frames out of a video
(`ffmpeg -ss <t> -i video.mp4 -frames:v 1 frame.png`) before review.

### Rules

- **Re-capture after fixing.** A fix is not verified until it has been looked at again.
- Report what you *see*. If you have not looked, say so.
- The tracked `examples/` previews are the showcase: regenerate them when a
  renderer change alters how they look.
