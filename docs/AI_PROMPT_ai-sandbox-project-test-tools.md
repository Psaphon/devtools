# AI Development Prompt — ai-sandbox-project-test-tools

**Branch:** `fix/ai-sandbox-test-tools`
**Base:** `develop`

Read `CLAUDE.md` and the `ai-sandbox-project-test-tools` feature in `docs/DEVPLAN.md`.
Do NOT push — the host workflow handles push and PR.

## Problem (found on hub, 2026-09-29)
1. **Host side.** `_run_lint_and_tests()` (used by `dtl workflow` before every push)
   installs the project into the SYSTEM Python with `--break-system-packages` /
   `PIP_BREAK_SYSTEM_PACKAGES=1`, justified by "the ephemeral USB workstation is
   rebuilt weekly". hub is permanent, and its system Python has **no pip and no
   pytest**, so every lint/test step fails there and the overnight loop can never push.
2. **Sandbox side.** The AI had no ruff/pytest in the container and improvised a
   throwaway venv.

## What to build (in `dtl.py`)
1. `_project_venv(project_dir: Path) -> Path`: a per-project venv at
   `$XDG_CACHE_HOME/dtl/venvs/<project-name>-<first 8 hex of sha256(abs path)>`
   (fall back to `~/.cache` when `XDG_CACHE_HOME` is unset). Create it with
   `python3 -m venv` if missing. Never inside the project directory.
2. `_venv_env(venv: Path) -> dict[str, str]`: a copy of `os.environ` with
   `VIRTUAL_ENV` set, `<venv>/bin` first on `PATH`, and `PIP_BREAK_SYSTEM_PACKAGES`
   removed.
3. Rework `_run_lint_and_tests()` for Python projects (`pyproject.toml`, `setup.py`
   or `requirements.txt` present):
   - When `scripts/ci.sh` exists, run it with `_venv_env(_project_venv(...))`
     (it installs from the project's own declaration itself).
   - Otherwise, install with the venv's python: `-e '.[dev]'` when a `dev`
     extra exists, else `-r requirements.txt`, else `-e .`, PLUS the fleet-pinned
     `ruff=={RUFF_VERSION}` (the existing constant; every repo's CI installs it
     the same way), then run `ruff` and `pytest` from the venv. If `pytest` is
     still not installed after that, fail with a clear message naming the
     missing declaration; do not hand-install it.
   - Remove every `--break-system-packages` / `PIP_BREAK_SYSTEM_PACKAGES` use and
     the "ephemeral USB workstation" comments. Non-Python stacks are unchanged.
4. `_sandbox_tooling_note(project_dir: Path) -> str`: a short paragraph that
   `dtl ai run` (docker mode, claude provider) prepends to the prompt. It tells
   the AI to create a venv at `/home/claude/.venvs/<project-name>` (outside
   `/workspace`, so `git status` stays clean), install the project from its own
   declaration plus `ruff=={RUFF_VERSION}` (same rule as step 3), and run `scripts/ci.sh` with that venv
   active before committing when the file exists. For non-Python projects it
   returns "".
5. Update `tests/conftest.py`'s autouse `_isolated_xdg` fixture to also set
   `XDG_CACHE_HOME`, so tests never create venvs in the real cache.
6. Tests (new file `tests/test_project_venv.py`):
   - venv path is under `XDG_CACHE_HOME`, outside the project, stable for the
     same path and different for different paths;
   - a REAL venv for a tiny local project with no dependencies: `_run_lint_and_tests`
     style install works offline and `python` resolves inside the venv
     (use a project whose `scripts/ci.sh` prints `command -v python` and assert
     the output is under the venv);
   - no `break-system-packages` string remains in `dtl.py`;
   - the tooling note mentions `/home/claude/.venvs/` and `scripts/ci.sh` for a
     python project with ci.sh, and is empty for a non-python project.

## Rules
- Run `ruff check dtl.py && ruff format --check dtl.py tests/conftest.py tests/test_project_venv.py` and `python -m pytest -q tests/` before committing (create a venv outside /workspace if tools are missing).
- Do NOT reformat unrelated files. Do NOT push.
- Commit message (exactly):

      fix(ai): run project lint and tests in a per-project venv

      dtl installed projects into the system Python with
      --break-system-packages, justified by a weekly-rebuilt workstation.
      hub is permanent and its Python has no pip, so every workflow
      lint/test step failed there. Host checks now run in a per-project
      venv under XDG_CACHE_HOME, and the sandbox is told to do the same
      outside /workspace.
