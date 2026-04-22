# User's ~/Projects Stable — Context for Planning

This file summarizes the repos in User's `~/Projects` directory and the cross-cutting conventions they share. Use it when proposing stacks or features during planning sessions. Prefer existing patterns unless there's a clear reason to deviate.

**Last updated:** 2026-04-09

## Active Projects

| Project | Purpose | Stack |
|---------|---------|-------|
| **devtools** | CLI scaffolder and AI dev orchestrator (`dtl`) | Python 3.11, stdlib-only, single-file |
| **morning-brief** | Automated daily news dashboard pipeline | Python 3.11, async httpx, SQLite, Ollama (Qwen 2.5 7B), Jinja2, Rich, Click, Cloudflare Pages |
| **usb-autoinstall-public** | Ephemeral security workstation USB installer | Bash, shellcheck, Ubuntu 25.10 autoinstall, 4-partition USB |
| **ollama** | Local LLM management (separate from morning-brief) | Ollama runtime |
| **water-monitor-infra** | Water quality monitoring infrastructure | TBD |
| **log-sentinel** | Security log analysis | TBD |
| **impact-etl** | Data pipeline for impact metrics | TBD |

## Cross-Cutting Conventions

**Gitflow branching** — every project uses `main`, `develop`, `feature/*`, `fix/*`, `release/*`, `hotfix/*`. Feature branches merge to develop via PR. Never commit directly to main or develop. AI developers commit but do not push.

**Conventional commits** — `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.

**Security posture** — no secrets in code, all config via env vars, Docker containers run with `cap_drop: ALL` and `no-new-privileges`, SSH keys live on the SECRETS USB partition (persist across weekly workstation rebuilds).

**Ephemeral workstation** — User's development machine is reinstalled from USB roughly weekly. All persistent state must live in: (a) git repos on GitHub, (b) the SECRETS USB partition, (c) Docker named volumes for OAuth tokens. Nothing on `/home` is permanent.

**LLM strategy** — local-first. Use Ollama (Qwen 2.5 7B on RTX 2060) for bulk work. Use Claude API only for synthesis or high-reasoning tasks where quality matters more than cost. Budget: $5-10/week total.

**Remote access** — Tailscale mesh VPN. Phone access via Terminus SSH over Tailscale. the user manages projects from his phone via claude.ai and SSH terminal.

**Scheduling** — systemd user units (`.service` + `.timer`) for batch jobs. `dtl workflow run --schedule HH:MM` for overnight autonomous development, typically 02:00 for off-peak electricity.

**Hosting** — Cloudflare Pages for static sites, Cloudflare Workers for auth-gated APIs. Free tier is sufficient.

## Default Stack Choices

When the user says "PM decides" or hasn't expressed a preference, the PM will default to:

| Need | Default | Why |
|------|---------|-----|
| Language | Python 3.11+ | Most existing projects, the user is fluent |
| HTTP client | httpx (async) | Used in morning-brief, handles async well |
| Database | SQLite | Single-user, simple, no server to maintain |
| Templating | Jinja2 | Python standard, used in morning-brief |
| CLI framework | Click | Matches morning-brief; `argparse` if avoiding deps |
| Terminal UI | Rich | Used in morning-brief |
| Logging | Python `logging` module (never `print`) | Project standard |
| Paths | `pathlib.Path` (never string paths) | Project standard |
| Containers | Docker Compose, multi-stage, slim runtime | Established pattern |
| Shell scripts | Bash with `set -euo pipefail`, `shellcheck`-clean | Project standard |
| Linting (Python) | `ruff check . && ruff format --check .` | Project standard |
| Linting (Shell) | `shellcheck` | Project standard |

## Hardware

The workstation's hardware determines what is feasible locally (inference speed, VRAM budget, storage headroom) and what must be offloaded to cloud or deferred. Always read this section before proposing ML, media-processing, or compute-heavy features.

| Component | Spec | Notes |
|-----------|------|-------|
| GPU | {model, e.g., RTX 2060} | {e.g., CUDA 12.x, used for local inference} |
| VRAM | {GB} | {max model size at full precision; quantized budget} |
| RAM | {GB} | {available to host + containers} |
| CPU | {model / core count} | {relevant for CPU-only inference or build times} |
| Storage | {size, type} | {/ partition; ephemeral — rebuilds weekly} |
| Network | {e.g., Tailscale mesh, home gigabit} | {bandwidth for model pulls, API calls} |
| GPU tenants | {services sharing the GPU} | {e.g., Ollama, ComfyUI — VRAM contention} |
| Remote access | {e.g., Terminus SSH over Tailscale} | {how the user reaches the machine from phone} |

**Current workstation example** (update when hardware changes):

| Component | Spec | Notes |
|-----------|------|-------|
| GPU | NVIDIA RTX 2060 | CUDA 12.x; primary inference device |
| VRAM | 6 GB | Max ~7B param at Q4; 13B+ must be CPU-offloaded or cloud |
| RAM | 32 GB DDR4 | Comfortable for Docker Compose stacks + Ollama |
| CPU | {CPU model} | {fill in} |
| Storage | {size} SSD | Ephemeral `/home`; persistent state on SECRETS USB or Docker volumes |
| Network | Home gigabit + Tailscale mesh VPN | Low-latency to Cloudflare; Tailscale for phone/remote access |
| GPU tenants | Ollama (Qwen 2.5 7B default) | ComfyUI shares VRAM when running — don't run both at full load |
| Remote access | Terminus SSH over Tailscale | Primary mobile interface; user manages projects from iOS/Android |

## When to Deviate

Prefer existing patterns, but break the pattern when:

- The new project has fundamentally different constraints (e.g., embedded device → Rust over Python)
- An existing library is known to be painful for the specific use case (explain why)
- the user explicitly asks for a new stack (honor it, but note any maintenance cost on an ephemeral workstation)

When in doubt, ask the user. Capture the answer in the PROJECT-BRIEF's Stack Preferences section.
