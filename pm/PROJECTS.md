# Project Registry

Single source of truth for which projects are **active** (work happens here),
**parked**, **archived**, **dormant**, or **stub**. Discovery, status, cleanup,
and the weekly review all key off this file. Keep it current — when a project
changes state, edit the table here first.

Status meanings:
- **active** — under development; scan its DEVPLAN for work, include in reviews.
- **parked** — paused indefinitely; do NOT queue features, do NOT schedule runs.
- **dormant** — planned but not yet scaffolded for AI dev (no CI / under-scoped).
- **archived** — dead; superseded; kept only for reference (GitHub-archived).
- **stub** — a planning `CLAUDE.md` only; not a git repo; lives for future scoping.
- **at-risk** — has unbacked work (no git/remote); needs attention before anything else.

## Registry

| Project | Path | State | Repo (Psaphon/) | Vis | Role |
|---|---|---|---|---|---|
| hub | /home/comp/Projects/hub | active | hub | private | Headless Tailnet workstation; substrate for the others |
| devtools | /home/comp/Projects/devtools | active | devtools | public | `dtl` scaffolder + AI dev orchestrator |
| loom | /home/comp/Projects/loom | active | loom | public | Overnight music-video pipeline (ComfyUI+ffmpeg) |
| morning-brief | /home/comp/Projects/morning-brief | active | morning-brief | public | Automated news dashboard pipeline |
| Prompt-Fishing | /home/comp/Projects/Prompt-Fishing | parked | Prompt-Fishing | public | Parked indefinitely — do not queue features |
| ollama | /home/comp/Projects/ollama | dormant | ollama | public | Local LLM mgmt; planning-only, no CI, not AI-ready |
| usb-autoinstall-public | /home/comp/Projects/usb-autoinstall-public | archived | usb-autoinstall-public | public | GitHub-archived; superseded by hub |
| impact-etl | /home/comp/Projects/impact-etl | stub | — | — | Planning CLAUDE.md only; not scaffolded |
| log-sentinel | /home/comp/Projects/log-sentinel | stub | — | — | Planning CLAUDE.md only; not scaffolded |
| water-monitor-infra | /home/comp/Projects/water-monitor-infra | stub | Water-Monitor | public | Planning stub; remote exists, local is CLAUDE.md only |
| crystallize | /home/comp/Projects/crystallize | at-risk | — | — | Next.js app, **NO git/remote** — needs init + private remote + backup |

## Active project paths (machine-readable — keep in sync with the table)

```
/home/comp/Projects/hub
/home/comp/Projects/devtools
/home/comp/Projects/loom
/home/comp/Projects/morning-brief
```

## Notes

- **Scheduling eligibility** (GitHub Pro): every active repo can `gh pr merge --auto`
  on both public and private — visibility is not a scheduling constraint.
- **crystallize** is the one urgent anomaly: real work with no version control and an
  `.env.local` present. Resolve before treating it as a project (git init → `.gitignore`
  the env → private remote → push). Do NOT delete.
- **GitHub repos not cloned locally** (old portfolio / one-offs): a-frame-in-100-lines,
  api-routes-apollo-server-and-client-auth, create-react-app, dashboard, farcaster-analyzer,
  fastapi-temp, nextjs, security, web-radio. Not local clutter; ignore unless asked.
