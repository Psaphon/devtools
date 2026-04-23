# {PROJECT_NAME}

## What This Is

{1-3 sentences: what this project does, who it's for, why it exists.}

## Architecture

```
{ASCII diagram showing major components and data flow.
Keep it simple — if it doesn't fit in 15 lines, it's too detailed for here.}
```

## Tech Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Language | {e.g., Python 3.11+} | {reason} |
| {category} | {tool/lib} | {reason} |

## Project Structure

```
{project}/
├── src/ or {pkg_name}/
│   ├── {key directories and files}
├── tests/
├── docs/
│   └── DEVPLAN.md
└── {config files}
```

## Constraints

{Non-negotiable rules. Security, compatibility, dependencies, style.}

- {constraint}
- {constraint}

## Commit Conventions

- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`
- Gitflow branching: `main`, `develop`, `feature/*`, `release/*`, `hotfix/*`
- Feature branches merge to develop via PR

## Code Standards

- {linter}: `{lint command}` before every commit
- {formatter}: `{format command}`
- Tests: `{test command}` — all must pass before push

## Key Decisions

{Design choices already made. State them so the AI doesn't re-decide.}

- {decision}: {why}

## External Services

<!-- Optional. Use when this project depends on a service that runs outside the repo — Ollama, ComfyUI, Postgres, a Cloudflare Worker, etc. List what must be running, where it lives, and who manages its lifecycle. Skip if the project is self-contained. -->

| Service | Endpoint / How to reach | Managed by | Notes |
|---------|-------------------------|------------|-------|
| {e.g., ComfyUI} | {http://localhost:8188} | {external — user starts manually / systemd unit XYZ} | {version, GPU/CPU, VRAM budget} |

## Coordination

<!-- Optional. Use when this project shares resources (GPU, a scheduled window, a port) with another project, or hands off to/from another project. Skip for stand-alone projects. -->

- **{Shared resource, e.g., GPU 00:00-05:30}** — {who has it when, who stops what}
- **{Hand-off, e.g., produces artifact that another project consumes}** — {consumer, format, location}
- **Cross-project docs**: see `/home/comp/Projects/{other-project}/docs/COORDINATION.md` (if present)

## Audience and Tone

{Who will read the README and code? What should they take away?
This section is for portfolio/hiring context — skip for internal tools.}

- Target reader: {e.g., hiring manager for DevOps roles}
- README should emphasize: {e.g., security thinking, clean architecture}
- Pairs with: {other portfolio projects, if applicable}
