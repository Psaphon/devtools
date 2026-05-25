# pm/ — Project-Manager coordination layer

The version-controlled source of truth for the **PM** that coordinates AI
development across `~/Projects`. It is a component that runs *on top of* hub:
hub provisions the host and installs `dtl`; this layer makes the workspace a
self-managing, watch-supervisable PM.

Previously this config lived only as loose files in `~/Projects/` and
`~/Projects/.claude/` — unversioned, and lost on the weekly USB rebuild.
Canonizing it here gives it a durable, backed-up home.

## Contents

| Path | Role |
|---|---|
| `CLAUDE.md` | PM coordinator instructions (the `~/Projects/CLAUDE.md`) |
| `PROJECTS.md` | Project registry — active vs parked/archived/stub |
| `rules/autonomy.md` | Green-light actions, discovery loop, now-vs-scheduled, watch protocol |
| `rules/weekly-review.md` | Weekly security + productivity review spec |
| `rules/gitflow.md`, `rules/security.md` | Branching + security rules |
| `commands/` | Fire-able PM skills: `status`, `kickoff`, `handoff`, `weekly-review` |
| `scripts/weekly-review.sh` | The weekly-review digest generator |
| `settings.json` | Claude Code permission baseline (durable; survives rebuild) |
| `install.sh` | Materializes the above into a workspace |

## Install / restore

```bash
bash devtools/pm/install.sh                 # → /home/comp/Projects
PM_WORKSPACE=/path/to/ws bash devtools/pm/install.sh --dry-run
```

Machine-local / volatile files are NOT shipped and are preserved on install:
`~/Projects/.claude/settings.local.json` and `~/Projects/.claude/HANDOFF.md`.

## Workflow

Edit the canonical copy **here**, PR to `develop`, then re-run `install.sh` on the
workstation (a future `dtl pm install` / `dtl pm sync` will wrap this and run from
hub first-boot). Don't hand-edit the deployed `~/Projects/.claude` copies as the
source of truth — they're a deployment of this directory.
