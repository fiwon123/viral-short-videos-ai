<!--
Keep the sections below — they are read at the moment a claim is written, which
is the only moment it can be checked. Delete this comment block before you open
the PR.
-->

Closes #<issue-number>

## What

<!-- What changed, in one or two sentences, and which files or packages carry it. -->

## Why

<!-- The problem this solves. Link the issue's reasoning rather than restating it. -->

## Verification

<!--
What actually ran, and what it proved. Be specific: a command and its exit
status is evidence; "tests pass" is a claim.

State the gate as it is, not more:

- `make test`, and for renderer work `make parity` and a still — list what ran.
- A test reported as skipped (`skipped=N`) was NOT exercised — say so.
- CI runs on `dev` → `main` PRs only. A feature PR may trigger no run at all,
  and a job gated out comes back `skipped`, not `passed`.
- Workflows are not covered by CI. A workflow change is unverified until a run
  executes the job that exercises it.
- A skipped job, a run that never happened, or an empty test target is
  **unverified**, not passed.
-->

- [ ] `make test` — tests run, skipped:
- [ ] `make parity` / `make still` (renderer, caption or motion changes) — result, frames inspected:
- [ ] `make dev-build` (Dockerfile, requirements or package-lock changes) — exit status:
- Areas touched that no test covers:
- Anything else that was run, and what it showed:

## Notes

<!--
- Follow-ups deliberately left out of scope, and the issue that tracks them.
- Known caveats a reviewer should not have to rediscover.
- Anything in the diff that looks wrong but is intentional, and why.
-->
