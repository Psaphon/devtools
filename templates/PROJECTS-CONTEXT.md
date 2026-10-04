# The Operator's ~/Projects Stable: Context for Planning

What exists, how development actually runs, and the conventions every plan inherits. Read it before planning; prefer the existing patterns unless there's a clear reason to deviate.

**Last updated:** 2026-10-04

## Where development happens

Everything runs on **hub**: an always-on, headless Ubuntu Server 26.04 box on the Tailnet (LUKS + TPM auto-unlock, CIS-hardened, persistent). The old weekly-rebuilt USB workstation is retired.

- **PM:** a Project Manager Claude runs on hub in a durable `screen` session (`pm`). The operator reaches it from the phone over SSH (Shellfish) and supervises asynchronously, often from a watch.
- **AI developers:** each feature is built by `dtl ai run` (in-session, PM-reviewed) or by the nightly loop: `dtl-workflow@<project>.timer` at about 02:00 UTC builds the first `Status: Not Started` feature, opens a PR and auto-merges on green CI.
- **Planning handoff:** one `PLAN-<name>.md` file dropped at the top level of the Proton Drive folder `hub/pm-inbox`. Hub fetches it within 15 minutes and pings the phone, and the PM turns it into a DEVPLAN PR (features) or a scaffold-ready check (new project). See `PLANNING-GUIDE.md`.
- **Notifications:** ntfy on hub pushes to the phone (`hub-alert`): finished runs, failures, "PM needs you". No other alert channel works.

## Projects

| Project | State | Visibility | Purpose | Stack |
|---|---|---|---|---|
| **hub** | active | private | The always-on box itself: install, hardening, services, backups, the PM's tooling | Ubuntu 26.04, Ansible (konstruktoid.hardening), Bash + distro python3, systemd, Docker (rootless for the operator), Tailscale, ntfy, Glance/Beszel, Ollama |
| **devtools** | active | public | `dtl`: scaffolder and AI-dev orchestrator, plus these planning templates | Python 3.11, stdlib-only, single file |
| **loom** | active | public | Overnight music-video pipeline | Python 3.11, Click, httpx, librosa, ffmpeg, ComfyUI, systemd timer |
| **morning-brief** | active | public | Daily news dashboard; also writes the signals file atrade reads | Python 3.11, httpx, SQLite, Ollama, Jinja2, Click, Cloudflare Pages |
| **atrade** | active | private | Low-frequency autonomous **paper**-trading bot (live trading hard-guarded out) | Python |
| Prompt-Fishing, crystallize | parked | — | Don't propose features | — |
| ollama | dormant | public | Planning only, no CI | — |
| impact-etl, log-sentinel, water-monitor-infra | stub | — | Planning `CLAUDE.md` only; a plan may revive one as a new project | — |
| usb-autoinstall-public | archived | public | Superseded by hub | — |

If an idea overlaps an active repo, plan it as **features for that repo**. One repo per deployment surface: anything that configures hub belongs in hub.

## Hardware (hub)

| Component | Spec | Planning impact |
|---|---|---|
| GPU | NVIDIA RTX 2060, 6 GB VRAM | About 7–8B models at Q4 locally; bigger means CPU offload or the API |
| CPU | AMD Ryzen 5 3600XT, 6 cores / 12 threads | |
| RAM | 32 GB | Comfortable for compose stacks plus one model |
| Storage | 500 GB NVMe (system + `/data`), 2 TB HDD (backups) | Large media lives in `/data`; the HDD is backup-only |
| Local models (Ollama) | qwen2.5:7b, qwen2.5-coder:7b, qwen3:8b, phi4-mini | |
| Network | Home LAN + Tailscale; no inbound from the internet | |

**GPU and schedule tenants (UTC):** dtl nightly loop about 02:00 · borg backup 03:00 · off-site upload 04:00 · morning-brief 08:15 · atrade weekdays 10:30 · loom overnight when enabled. A new GPU job must name its window.

## Conventions every plan inherits

- **Gitflow:** `main`, `develop`, `feature/*`, `fix/*`, `chore/*`, `docs/*`, `release/*`, `hotfix/*`. Features merge to `develop` by PR; the operator decides releases to `main`. AI developers commit but never push; the PM pushes.
- **Conventional commits:** `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.
- **CI is the merge gate:** ruff (pinned `0.16.4`, explicit `select`) and pytest (plus shellcheck/yamllint where relevant) on every PR, as **required** checks. A job that runs but isn't required gates nothing. CI installs dependencies from the project's own declaration (`pyproject.toml`), never a hand-written list.
- **Tests execute the real boundary.** Features in hub, morning-brief and loom merged green and broke in production because tests checked text instead of behaviour. Criteria must run the thing: CLI exit codes, real config parsing, scripts against stub binaries that record their arguments. Hardware or live-account checks become `[HUMAN]` criteria.
- **Repo defaults for new projects:** private, full nightly workflow, auto-merge, unless the plan says otherwise. GitHub Pro: auto-merge works on private and public alike, so visibility is a confidentiality choice only.
- **Secrets:** never in code or repos. They live on the SECRETS USB (mounted on hub at `/etc/hub/secrets`), as systemd credentials (`LoadCredential`), GitHub Actions secrets, or in Proton Pass. Everything else is config via env vars.
- **Network:** the Tailnet is the perimeter; no inbound from the internet. Every bind address is explicit (`127.0.0.1` or `tailscale0`), never `0.0.0.0`. Projects that bind, hold credentials, talk to another device or run unattended declare a `## Network Segmentation and Trust Boundaries` block in their `CLAUDE.md`.
- **Containers:** `cap_drop: ALL`, `no-new-privileges`, AppArmor profile. On hub, the operator's containers run under rootless Docker.
- **Scheduling:** systemd timers (user units for the operator's jobs; linger is on). Overnight AI development is the `dtl-workflow@` timer, not ad-hoc `--schedule` runs.
- **Security-sensitive features are supervised:** credentials, deletion, network or permission changes are built by the PM in session and reviewed against the real system, not left to the nightly loop. They're queued with a status the loop skips (`Ready (supervised)`).
- **No real names:** never the operator's real name in code, docs, commits or PRs. Use "the operator".
- **DEVPLAN vs FEATURE-REQUESTS:** `docs/DEVPLAN.md` is the committed work queue (one `## Feature:` per branch). `docs/FEATURE-REQUESTS.md` is the backlog of ideas, parked items and nice-to-haves. Entries graduate from the backlog into the DEVPLAN when they're specced.

## LLM and budget

- **Claude Pro is the developer:** the PM, `dtl ai run` and the nightly loop all use the Pro login. The weekly allowance resets Sunday 14:00 ET; aim for steady use of about 14% a day.
- **The Claude API is an app component**, not a backup developer: in-product features only, in a workspace capped at $40/month.
- **Local-first for bulk work:** Ollama on hub. Electricity is off-peak overnight; the total budget is $5–10/week.

## Hosting and backups

- **Static sites:** Cloudflare Pages; auth-gated APIs on Cloudflare Workers. The free tier is enough.
- **Backups:** hub's state (`/data` and the operator's home) gets a nightly borg backup to the HDD and a nightly encrypted copy to Proton Drive. A project that keeps irreplaceable state must put it under one of those paths, or say how else it's backed up.

## Default stack (when the plan says "PM decides")

| Need | Default |
|---|---|
| Language | Python 3.11+ |
| HTTP | httpx |
| Database | SQLite |
| CLI | Click (`argparse` when avoiding dependencies) |
| Templating / terminal UI | Jinja2 / Rich |
| Logging, paths | `logging` (never `print`), `pathlib.Path` |
| Shell | Bash, `set -euo pipefail`, shellcheck-clean |
| Containers | Docker Compose, multi-stage, slim runtime |
| Lint | `ruff check . && ruff format --check .` |

## When to deviate

When the constraints are fundamentally different (embedded device, browser-only app), when a default is known to be painful for the case, or when the operator asks. Say why in the plan's Key Decisions, and note the maintenance cost.
