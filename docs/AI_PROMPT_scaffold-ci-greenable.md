# AI Development Prompt — scaffold-ci-greenable

**Branch:** `feature/scaffold-ci-greenable`
**Base:** `develop`

Read `CLAUDE.md` for project context and `docs/DEVPLAN.md` for the full feature
block (`## Feature: scaffold-ci-greenable`) — it lists seven template defects and
the acceptance criteria you must satisfy. Do NOT push; the host workflow handles
push and PR.

## Why this matters

A freshly scaffolded repo must pass its own CI on the first push. Today it cannot.
Worse, defect 7 broke a live overnight run on 2026-09-01: atrade's AI added `respx`
to `[project.optional-dependencies] dev` — the correct place — the local preflight
installed `-e .[dev]` and went green, then CI installed its own hand-listed package
set, and the build died on `ModuleNotFoundError: respx`. The batch stalled all night.

The root cause is not a missing package. It is that **dependencies and CI steps are
each defined twice**, and the two copies are kept in sync by discipline.

## What to build

Everything lives in `dtl.py`'s inline templates (`_CI_YML_SCAFFOLD` and friends).

### 1. Dependency source of truth

The generated `lint-and-test` job must install from the project's own declaration:

- `pip install -e '.[dev]'` when the scaffold emits a `dev` extra
- `pip install -r requirements.txt` when the scaffold emits that instead
- never a hand-written list of test packages on the pip line
- **no `|| pip install ...` fallback** — a broken extra must fail loudly. The
  fallback form silently degrades to an incomplete environment and converts a
  clear dependency error into a confusing collection failure elsewhere.

Pin ruff (`ruff==<version>`) to match the fleet convention; an unpinned install
lets an upstream release turn CI red with no change on our side.

### 2. `scripts/ci.sh` — the parity entrypoint

Generate a `scripts/ci.sh` containing the lint/format/test sequence. Then:

- the generated `ci.yml` **calls** `bash scripts/ci.sh` instead of restating steps
- `_run_lint_and_tests` in `dtl.py` runs `scripts/ci.sh` when the project has one,
  and falls back to its current behaviour when it does not

This is the point of the feature: one script, two callers. CI and the local
preflight cannot disagree, because there is only one definition.

Keep it POSIX-ish bash, `set -euo pipefail`, and shellcheck-clean — the scaffold
ships a shellcheck job. Preserve the existing pytest exit-code-5 tolerance
(`no tests collected` on an empty scaffold) and nothing else.

### 3. Defects 1–6

Fix them as written in the DEVPLAN feature block. Do not re-derive them.

## Tests

The existing tests assert that jobs are *generated*, never that a scaffold *passes*.
That is how six defects shipped. Add, in `tests/`:

- a test that scaffolds a project, adds a test importing a package declared ONLY in
  the `dev` extra, and asserts the generated CI installs it — the exact atrade
  PR #7 failure, locked down
- a test asserting the generated `ci.yml` and `_run_lint_and_tests` invoke the SAME
  script, so parity is enforced by a test rather than by discipline
- a test that the generated `notify.py` is already `ruff format` clean
- the strongest one: scaffold a project, add one trivial importing test, and assert
  the generated CI logic actually goes green

## Rules

- Run `ruff check dtl.py`, `ruff format --check dtl.py`, and `pytest tests/ -v`
  before EVERY commit. All 306+ existing tests must still pass.
- Backward compatible: existing scaffolded repos must keep working. `scripts/ci.sh`
  is used **when present**, never assumed.
- Do NOT push.
- Do NOT modify files outside `dtl.py`, `tests/`, and `docs/DEVPLAN.md`.
- Do not touch `.github/workflows/` in THIS repo — you are changing what dtl
  *generates*, not how devtools itself builds.

## Commit message

```
feat(scaffold): make generated CI green from birth and CI/local parity structural

Scaffolded repos failed their own CI out of the box on seven template defects,
and the seventh stalled a live overnight batch: CI installed a hand-listed
package set while the project declared its test dependencies properly, so a
correctly-added dependency was invisible to CI (atrade PR #7, 2026-09-01).

Generated CI now installs from the project's own declaration, with no masking
fallback and a pinned ruff. The lint/format/test sequence moves into a generated
scripts/ci.sh that both ci.yml and _run_lint_and_tests invoke, so the two cannot
drift -- there is only one definition. Tests assert a scaffold actually goes
green, not merely that its jobs were emitted.
```
