# Project Brief: {PROJECT_NAME}

**Created:** {DATE}

## Pitch

{One line, 15 words or less. What this is.}

## Problem / Motivation

{Why does this need to exist? What pain does it solve? 2-4 sentences.}

## Target User

{Who uses this? Just you? A persona? Hiring managers reviewing the portfolio?}

## Stack Preferences

{Rough preferences — language, local vs cloud, database, libraries you love/hate.
Use "PM decides" for anything you don't care about. Examples below.}

- Language: {e.g., Python 3.11+, or "PM decides"}
- HTTP: {e.g., httpx (async), or "PM decides"}
- Database: {e.g., SQLite, or "PM decides"}
- LLM: {e.g., Ollama if possible, Claude API for synthesis, or "none"}
- Hosting: {e.g., Cloudflare Pages, or "local only"}
- Other: {any strong preferences or anti-preferences}

## Must-Haves (v1)

{What makes this worth building. Each item maps to one or more DEVPLAN features.}

- {must-have}
- {must-have}

## Nice-to-Haves (later)

{Defer these to end of DEVPLAN or a future version.}

- {nice-to-have}
- {nice-to-have}

## Non-Goals

{What this is explicitly NOT. Prevents scope drift during autonomous development.}

- {non-goal}
- {non-goal}

## Risks & Unknowns

{Anything that might blow up: API costs, performance, unfamiliar tech, data access, legal.}

- {risk}: {mitigation or "TBD"}

## Repo Visibility

<!-- REQUIRED. The choice between public and private determines whether the PM uses `dtl workflow run --schedule` (overnight autonomous, public+auto-merge only) or `dtl ai run` with manual PR approval (private). See PLANNING-GUIDE.md "Repo Visibility & Scheduling Eligibility" for the full rationale. -->

- **Visibility:** {public | private}
- **Why:** {what makes this public-OK or private-only — credentials? hardware specifics? portfolio value?}
- **Development model:** {public → "overnight-scheduled, unattended"; private → "daytime, manual PR approval per feature"}
- **Future move:** {if private now, what would have to be true to move to public later? if public now, what would force a move to private?}

## Hardware Target

<!-- OPTIONAL. REQUIRED when the project provisions a machine (OS install, Pi setup, embedded device, router config). Skip for pure-software projects. -->

- **Form factor:** {desktop tower / SBC / cloud VM / laptop / phone}
- **Motherboard / SoC:** {e.g., MSI MAG B550 Tomahawk, Raspberry Pi 5, generic x86_64}
- **CPU:** {model + core count}
- **GPU:** {model + VRAM, or "none"}
- **RAM:** {GB}
- **Storage:** {drives, sizes, intended partitioning}
- **Networking:** {wired / wifi-only / cellular; required for which features?}
- **Firmware features to enable:** {Secure Boot, fTPM 2.0, IOMMU, etc. — list manual BIOS prereqs}
- **What's untouched:** {drives or interfaces this project does NOT manage, so the AI doesn't reformat them}

## Security & Trust Boundaries

<!-- REQUIRED if the project touches any of: a network interface beyond localhost, credentials of any kind, another device, unattended operation, or infrastructure deployed to metal. Skip for pure-software, single-user, localhost-only projects. -->

- **Inbound access:** {who can reach this and over what — Tailnet only / LAN only / public internet / specific tags}
- **Credentials held:** {what secrets live here, on which storage — SECRETS USB partition, Docker named volume, env var, file path}
- **Identity:** {what user / service account / OAuth client / Tailnet tag this system acts as}
- **Exposed services:** {service + bind interface — e.g., `ntfy on tailscale0:443`, `ollama on 127.0.0.1:11434`. Bind addresses must be explicit; do not leave for the AI developer to pick}
- **Trust boundary (1-2 lines):** {who trusts whom, in which direction — e.g., "watch trusts hub over Tailnet; hub trusts nothing on the LAN except break-glass sshd on :2022"}
- **Segmentation level:** {same-host containers / separate VLAN / separate hardware} — {why this level and not the next one up}

## Audience and Tone

- Target reader: {e.g., hiring manager for DevOps roles, or "internal only"}
- Tone: {e.g., technical and terse, friendly and approachable}
- Pairs with: {other ~/Projects repos this complements, if any}

## Notes

{Anything else the PM should know. Skip section if none.}
