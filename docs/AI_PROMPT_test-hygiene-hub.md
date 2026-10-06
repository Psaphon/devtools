# AI Development Prompt — test-hygiene-hub

**Branch:** `fix/test-hygiene-hub`
**Base:** `develop`

Read `CLAUDE.md` and the `test-hygiene-hub` feature in `docs/DEVPLAN.md`.
Do NOT push — the host workflow handles push and PR.

## Problem (found on hub, 2026-09-29)
1. The test suite writes into the REAL `~/.local/state/dtl` (`workflow.log`,
   `proj-workflow-state.json`, `test_*-workflow-state.json`). dtl resolves its
   state dir from `XDG_STATE_HOME` (see `_dtl_state_dir()` and the other
   `XDG_STATE_HOME` reads in `dtl.py`), and no test sets it.
2. `tests/test_ai_run.py` and `tests/test_scaffold_ci_greenable.py` fake CLIs
   (`docker`, `git`, `claude`, ...) by writing scripts under `tmp_path`. On a
   host whose `/tmp` is mounted `noexec`, bash skips the non-executable fake
   and runs the REAL binary instead.

## What to build
1. Create `tests/conftest.py` with an **autouse** fixture that sets
   `XDG_STATE_HOME` (and `XDG_CONFIG_HOME`, since dtl reads
   `~/.config/dtl/notify.toml`) to directories under `tmp_path` via
   `monkeypatch.setenv`. Add a session-level guard: record the mtime/contents
   listing of the real `~/.local/state/dtl` (if it exists) at session start and
   fail the session at the end if anything was added or changed there.
2. Make fakes fail closed. In both test files, wherever a fake CLI is put on
   PATH, ALSO verify the fake actually ran. Each fake writes a marker line
   (e.g. to a `calls` file), and the test asserts the marker exists. If the
   real binary ran instead, the test fails rather than passing on the real
   tool's output. Put the fakes' directory under a location that is executable
   even when `/tmp` is noexec: prefer `pytest`'s `tmp_path_factory` base only
   if executable, otherwise fall back to a directory under the repo's `.pytest-fakes/`
   (add it to `.gitignore`). Add a helper in `conftest.py` for this so both
   files share it.
3. Keep every existing test's intent unchanged.

## Rules
- Run `ruff check dtl.py tests/ && ruff format --check dtl.py tests/conftest.py` and `python -m pytest -q tests/` before committing (create a venv outside /workspace if tools are missing).
- Do NOT reformat test files you did not otherwise change.
- Do NOT modify `dtl.py`.
- Do NOT push.
- Commit message (exactly):

      fix(tests): keep the suite off the real machine

      Tests wrote workflow state into the real ~/.local/state/dtl, and fake
      CLIs in tmp_path fell through to the real binaries on a noexec /tmp
      (hub). An autouse fixture now isolates XDG_STATE_HOME/XDG_CONFIG_HOME,
      a session guard fails if the real state dir changes, and fakes must
      prove they ran.
