# Dev Tools Launcher (dtl)

## What This Is

Single-file Python scaffolder for containerized dev environments with AI provider support. Installed to `/opt/devtools/` via `install.sh`. The main file is `dtl.py` (~2600 lines, stdlib-only).

## Architecture

```
dtl.py (single file, stdlib-only Python)
├── CLI: dtl new / dtl ai start / dtl ai run / dtl workflow next
├── Templates: Dockerfile, docker-compose, CLAUDE.md, CI, pre-commit (all inline)
├── Stacks: python, node, go, rust
├── Services: postgres, redis
├── AI providers: claude (containerized Claude Code)
└── Security: cap_drop ALL, no-new-privileges, gitleaks, semgrep
```

## Constraints

- **Single file** — `dtl.py` is the entire tool. No splitting into modules.
- **Stdlib-only** — no pip dependencies. urllib for HTTP, re for parsing, etc.
- **Works offline** — installed to ephemeral USB workstation, no network assumed.
- **Backward-compatible** — new features must not break existing scaffolded projects.

## Commit Conventions

- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`
- Gitflow branching: `main`, `develop`, `feature/*`, `release/*`, `hotfix/*`
- Feature branches merge to develop via PR
- Releases merge develop to main via release branch

## Code Standards

- Python 3.11+
- `ruff check . && ruff format .` before commit
- Tests in `tests/` directory, run with `pytest`
- No type: ignore without explanation

## Key Files

| File | Purpose |
|------|---------|
| `dtl.py` | The tool (all code lives here) |
| `install.sh` | Copies dtl.py to /opt/devtools/, creates symlink |
| `templates/DEVPLAN.md` | Reusable development plan template |
| `docs/DEVPLAN.md` | This project's own development plan |

## Development Plans (DEVPLAN.md)

A Development Plan is a planning document structured so each section maps directly to a git feature branch. It replaces traditional roadmaps for AI-assisted development.

### Structure

```
# Development Plan: {Project}
## Overview (what and why)
## Constraints (rules for ALL features)
## Feature: {name} (one per feature branch)
   - Branch name, dependencies, status
   - Goal, acceptance criteria, files, decisions, notes
```

### How to Create a Plan from Your Phone

1. Open any text editor or notes app
2. Copy this minimal template for each feature you want:

```
## Feature: {short-hyphenated-name}

**Branch:** `feature/{short-hyphenated-name}`
**Depends on:** {previous feature or "none"}
**Status:** Not Started

### Goal

{What this feature delivers in 1-2 sentences.}

### Acceptance Criteria

- [ ] {Thing that must be true when done}
- [ ] {Another thing}
- [ ] All tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/file.py` | Create | {what} |

### Notes

{Gotchas, links, edge cases. Skip if none.}
```

3. Save as `DEVPLAN.md` in the project's `docs/` directory
4. (Future) Send via Telegram to `dtl workflow listen` for automatic pickup

### Rules for Good Feature Specs

- **Each feature is independently mergeable** — the project works after every merge
- **Order by dependency** — later features build on earlier ones
- **Include file paths** — the AI needs to know where to write code
- **State decisions, don't leave them open** — "Use SQLite" not "Choose a database"
- **Acceptance criteria are tests** — if you can't test it, rewrite it

### Using a Plan with dtl

```bash
# See what's next
dtl workflow list --plan docs/DEVPLAN.md

# Start the next feature (creates branch, launches AI)
dtl workflow next --plan docs/DEVPLAN.md

# After AI finishes (future)
dtl workflow finish
```

## After Editing dtl.py

Always reinstall after changes:

```bash
sudo /home/comp/Projects/devtools/install.sh
```
