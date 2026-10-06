# AI Development Prompt — ai-sandbox-git-identity

**Branch:** `fix/ai-sandbox-git-identity`
**Base:** `develop`

Read `CLAUDE.md` for project context. Do NOT push — the host workflow handles push and PR.

## Problem
Commits made inside the AI sandbox come out as `Developer <dev@localhost>`. The
compose template sets `GIT_AUTHOR_NAME=${GIT_AUTHOR_NAME:-Developer}` (and the
email/committer equivalents), and nothing on the host exports those variables.

## What to build (all in `dtl.py`)
1. Change `_compose_env()` to take the project directory: `_compose_env(project_dir: Path | None = None)`.
   When `project_dir` is given, for each of `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`,
   `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL` that is NOT already set in
   `os.environ`, read `git -C <project_dir> config user.name` / `user.email`
   (use `subprocess.run(..., capture_output=True, text=True, check=False)`),
   and set the author AND committer pair from it.
2. If the repo has no `user.name` or `user.email`, print ONE warning to stderr
   (`[dtl ai] warning: no git user.name/user.email in <dir>; sandbox commits will use the template default`)
   and leave the variables unset. Never invent an identity.
3. Pass the project dir at the two call sites that have one: the `dtl ai run`
   docker path (`_run_ai_with_limits(cmd, _compose_env(...), ...)`) and the
   interactive-session hint in `dtl ai start`. `_run_cmd` keeps calling
   `_compose_env()` with no project (unchanged behaviour).
4. Tests in `tests/test_ai_rootless.py` (same file, same style): create a real
   git repo in `tmp_path` with `git init` + `git config user.name/user.email`
   and assert: (a) the identity comes from the repo, (b) an exported
   `GIT_AUTHOR_NAME` wins, (c) a repo with no identity leaves the variables
   unset and warns. Keep `_docker_is_rootless` monkeypatched as the existing
   tests do.

## Rules
- Run `ruff check dtl.py tests/ && ruff format --check dtl.py tests/` and `python -m pytest -q tests/` before committing (create a venv outside /workspace if tools are missing).
- Do NOT modify files other than `dtl.py` and `tests/test_ai_rootless.py`.
- Do NOT push.
- Commit message (exactly):

      fix(ai): commit in the sandbox as the repo's git identity

      Sandbox commits came out as Developer <dev@localhost> because the
      compose template's defaults were never overridden. dtl now passes the
      project's git user.name/user.email as GIT_AUTHOR_*/GIT_COMMITTER_*,
      lets an exported value win, and warns instead of inventing one.
