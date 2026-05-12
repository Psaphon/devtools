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

## Network Segmentation and Trust Boundaries

<!-- REQUIRED for projects that bind to a network interface beyond localhost, hold credentials, accept input from another device, run unattended, or deploy to metal.
SKIP for pure-software, single-user, localhost-only projects (e.g., a CLI scaffolder, a build tool).
This section is load-bearing: the AI developer reads it before writing code that opens a socket, binds a port, or reads a credential. -->

### Inbound

- **{Interface, e.g., `tailscale0`}** — {who/what may reach this host on this interface; e.g., "members of the Tailnet, restricted by ACL to `tag:operator` and `tag:watch`"}
- **{Interface, e.g., `lo`}** — {what's bound here; e.g., "Ollama on 127.0.0.1:11434, never to be exposed beyond loopback"}
- **{Interface, e.g., `eth0` LAN}** — {what's reachable here; e.g., "break-glass sshd on :2022, keys-only, AllowUsers operator"}
- **Public internet** — {explicitly state "no inbound" or list the exceptions}

### Outbound

- {What this host initiates connections to, and why — e.g., "GitHub HTTPS for `git fetch`; Tailscale coordination server; Anthropic API during `dtl` runs; upstream ntfy.sh for iOS push forwarding"}

### Credentials

| Secret | Lives at | Read by | Lifetime |
|---|---|---|---|
| {e.g., Tailscale pre-auth key} | {SECRETS USB partition `/secrets/ts-authkey`} | {firstboot-tailscale.service} | {24h, single-use} |
| {e.g., GitHub SSH key} | {SECRETS USB → `~/.ssh/id_ed25519`} | {git} | {rebuild lifetime} |
| {e.g., Claude OAuth token} | {Docker named volume `claude-data`} | {Claude Code CLI} | {until revoked} |

### Identity

- **This host acts as:** {e.g., operator@hub on Tailnet tag:hub, GitHub identity Psaphon, Anthropic workspace member XYZ}
- **Devices that act as the operator:** {e.g., user's laptop, user's phone, user's watch — each tagged in Tailscale ACL}

### Service bind addresses

| Service | Bind | Why this bind, not 0.0.0.0 |
|---|---|---|
| {service} | {interface:port} | {reason} |

### Trust boundary statement

{1-2 lines: who trusts whom, in which direction.}

Example: *"This host trusts (a) Tailnet members matching `tag:operator`, (b) the local console during break-glass recovery. It trusts nothing on the LAN unless `eth0` sshd is explicitly used for fallback. It is itself trusted as `tag:hub` by Tailnet members for inbound SSH and Tailscale Serve endpoints."*

### Segmentation level chosen

- **Level:** {same-host containers / separate VLAN / separate hardware / air-gapped}
- **Why not the next level up:** {cost/benefit reasoning — e.g., "Separate hardware was rejected for v1 because the Tailnet edge already provides the trust boundary; revisit if a future feature adds public-internet exposure"}

## Audience and Tone

{Who will read the README and code? What should they take away?
This section is for portfolio/hiring context — skip for internal tools.}

- Target reader: {e.g., hiring manager for DevOps roles}
- README should emphasize: {e.g., security thinking, clean architecture}
- Pairs with: {other portfolio projects, if applicable}
