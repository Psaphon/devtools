# AI Development Prompt — scaffold-shellcheck-parity

**Branch:** `feature/scaffold-shellcheck-parity`
**Base:** `develop`

Read `CLAUDE.md` for project context and `docs/DEVPLAN.md` (feature `scaffold-shellcheck-parity`) for full acceptance criteria. Do NOT push — the host workflow handles push and PR.

## What to build

`dtl.py` is a single, stdlib-only file whose scaffolding templates are inline. Make scaffolded repos lint shell identically in the AI loop and in CI:

1. **Emit `.shellcheckrc`** — when scaffolding a project, write a repo-root `.shellcheckrc` containing:
   ```
   external-sources=true
   source-path=SCRIPTDIR
   ```
   Find where `dtl.py` already writes other root config (e.g. `.gitignore`, pre-commit config) and add `.shellcheckrc` alongside, gated the same way.

2. **shellcheck in the container** — in the inline `claude-code` Dockerfile template that `dtl.py` emits, add `shellcheck` to the apt install layer so the containerized AI can run it before committing (the host has none). Add it to devtools' own `.ai/claude-code/Dockerfile` too, for consistency.

3. **Align CI** — ensure the generated CI lint workflow's shellcheck step relies on the `.shellcheckrc` (external-sources): a script that `source`s a sibling file via `# shellcheck source=` must pass.

4. **Test** — add/extend a test asserting scaffolded output contains `.shellcheckrc` with `external-sources=true`.

5. **Docs** — note the one-line retrofit for existing repos:
   `printf 'external-sources=true\nsource-path=SCRIPTDIR\n' > .shellcheckrc`

## Rules

- Respect the single-file, stdlib-only, backward-compatible constraints.
- Run `ruff check . && ruff format --check . && pytest` before EVERY commit.
- Commit message: `feat: scaffold .shellcheckrc and shellcheck-in-container for lint parity`
- Do NOT push. Do NOT modify files outside scope. Do NOT add a `(#N)` suffix to the commit subject.
