# Development Plan: Dev Tools Launcher (dtl)

**Status:** In Progress
**Created:** 2026-03-28
**Updated:** 2026-03-28

## Overview

dtl is a single-file Python scaffolder for containerized dev environments with AI provider support. This plan covers the features needed to support automated gitflow workflows, AI-driven development, and mobile planning.

## Constraints

- Single file (`dtl.py`), stdlib-only, no pip dependencies
- Must work offline (installed to USB-based workstation)
- All generated containers: `cap_drop: ALL`, `no-new-privileges`, no host port mappings
- Secrets via environment variables only, never on disk
- Backward-compatible with existing scaffolded projects

---

## Feature: workflow-command

**Branch:** `feature/workflow-command`
**Depends on:** none
**Status:** PR Open

### Goal

Add a `dtl workflow next` command that reads a DEVPLAN.md, finds the next unstarted feature, creates a feature branch off develop, and launches the AI with the feature spec as context.

### Acceptance Criteria

- [ ] `dtl workflow next --plan docs/DEVPLAN.md` parses the plan and identifies the next feature with status "Not Started"
- [ ] Creates `feature/{feature-name}` branch off current develop
- [ ] Passes the feature spec (goal, acceptance criteria, files, decisions, notes) as the AI prompt
- [ ] `dtl workflow list --plan docs/DEVPLAN.md` prints all features with their status
- [ ] Handles edge cases: no plan file, all features done, dirty working tree
- [ ] Updates the feature's status to "In Progress" in the plan file
- [ ] Tests cover parsing, branch creation, and status updates

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `workflow` subcommand group with `next` and `list` |
| `tests/test_workflow.py` | Create | Test plan parsing and branch logic |
| `templates/DEVPLAN.md` | Already exists | Reference template |

### Key Decisions

- Parse DEVPLAN.md with regex, not a markdown library (stdlib-only constraint)
- Feature blocks delimited by `## Feature:` headings
- Status field parsed from `**Status:**` line within each feature block
- Branch name derived from the feature heading: `## Feature: foo-bar` becomes `feature/foo-bar`

### Notes

- The AI prompt should include the full feature block plus the Constraints section from the top of the plan
- If the working tree is dirty, abort with a message (don't risk losing work)

---

## Feature: pr-notify

**Branch:** `feature/pr-notify`
**Depends on:** workflow-command
**Status:** Not Started

### Goal

After the AI finishes a feature and pushes a PR, send a notification (GitHub webhook or Telegram) so the user can review and merge from their phone.

### Acceptance Criteria

- [ ] `dtl workflow notify` sends a message with PR URL, title, and summary
- [ ] Supports Telegram bot as notification channel (configured in `.ai/config.json`)
- [ ] Falls back to printing the PR URL if no notification channel configured
- [ ] Notification includes: PR link, branch name, number of files changed, test results summary
- [ ] Tests cover message formatting and config loading

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `workflow notify` subcommand |
| `tests/test_notify.py` | Create | Test notification formatting |

### Key Decisions

- Telegram via raw HTTPS (urllib, not a library) to maintain stdlib-only
- Config lives in `.ai/config.json` under `notifications` key
- GitHub webhook is a future option, Telegram first (user already has bot configured)

### Notes

- Telegram bot API: `https://api.telegram.org/bot{token}/sendMessage`
- Message format: markdown with PR link, branch, file count
- This can be called automatically at the end of `dtl workflow next` after the AI pushes

---

## Feature: plan-from-phone

**Branch:** `feature/plan-from-phone`
**Depends on:** pr-notify
**Status:** Not Started

### Goal

Accept a DEVPLAN.md (or single feature spec) sent via Telegram bot, save it to the project, and optionally kick off `dtl workflow next` automatically.

### Acceptance Criteria

- [ ] `dtl workflow listen` starts a long-polling Telegram bot listener
- [ ] Accepts a markdown file or text message containing a feature spec
- [ ] Saves received plan to `docs/DEVPLAN.md` (or appends a feature block)
- [ ] Optional `--auto-start` flag triggers `dtl workflow next` after receiving a plan
- [ ] Validates that received content matches DEVPLAN.md structure before saving
- [ ] Tests cover message parsing and file writing

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `workflow listen` subcommand |
| `tests/test_listen.py` | Create | Test plan parsing from messages |

### Key Decisions

- Long-polling, not webhooks (no public endpoint needed, works behind NAT)
- Only processes messages from the configured chat_id (security)
- Validate structure: must have `## Feature:`, `### Goal`, `### Acceptance Criteria` at minimum

### Notes

- This is the "phone to computer" bridge — user writes a plan on their phone, sends it to the Telegram bot, the computer picks it up and starts working
- Consider a systemd service or tmux session for persistent listening
- The auto-start flow: phone sends plan -> bot saves -> dtl launches AI -> AI codes -> AI pushes PR -> notification sent back to phone

---

## Feature: ai-sandbox-vm

**Branch:** `feature/ai-sandbox-vm`
**Depends on:** none (parallel track)
**Status:** Not Started

### Goal

Add VM-based isolation option for AI sandboxes using QEMU/KVM, providing hardware-level isolation beyond Docker containers. Based on AI-SANDBOX-DESIGN.md.

### Acceptance Criteria

- [ ] `dtl new --ai claude --isolation vm` scaffolds QEMU/KVM-based AI sandbox
- [ ] Generated files: cloud-init.yaml, vm-config.sh, Makefile (up/down/ssh/status/destroy)
- [ ] VM boots with Docker pre-installed, SSH key-based auth
- [ ] Network isolation: host-only TAP, allowlist for Ollama + Anthropic API only
- [ ] `dtl ai start --project . --isolation vm` boots VM and connects
- [ ] Resource limits configurable via env vars (AI_VM_CPUS, AI_VM_RAM, AI_VM_DISK)
- [ ] Tests cover file generation and config validation

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `--isolation` flag, VM scaffolding templates |
| `tests/test_vm_scaffold.py` | Create | Test generated VM configs |

### Key Decisions

- Ollama stays on host (GPU constraint — see AI-SANDBOX-DESIGN.md)
- One VM per project (separate qcow2 images)
- Pre-downloaded Ubuntu cloud image on STORAGE partition
- SSH key from SECRETS partition (shared across VMs, acceptable for local-only)

### Notes

- Depends on QEMU/KVM being installed (`qemu-system-x86`, `libvirt-daemon-system`)
- Cloud image (~600MB) must be pre-downloaded to USB during `download-all-packages.sh`
- This is a larger feature — consider splitting VM scaffolding and VM runtime into separate branches if needed

---

## Feature: mcp-isolation

**Branch:** `feature/mcp-isolation`
**Depends on:** ai-sandbox-vm
**Status:** Not Started

### Goal

Individually containerize MCP servers with strict isolation: no network, read-only filesystem, memory/CPU caps. Based on Phase 3 of AI-SANDBOX-DESIGN.md (already implemented in usb-autoinstall, needs porting to dtl).

### Acceptance Criteria

- [ ] `dtl ai add-mcp --server filesystem --project .` scaffolds an isolated MCP container
- [ ] Generated container: `network_mode: none`, `read_only: true`, `cap_drop: ALL`, 512MB/1CPU
- [ ] Communication via stdio pipe (docker exec), not TCP
- [ ] 10 well-known MCP packages recognized (filesystem, github, memory, etc.)
- [ ] Unknown package names pass through for custom servers
- [ ] Claude Code settings.json wired to use containerized MCP servers
- [ ] Tests cover container config generation and validation

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `ai add-mcp` subcommand, MCP container templates |
| `tests/test_mcp.py` | Create | Test MCP container scaffolding |

### Key Decisions

- Each MCP server gets its own container (no sharing)
- Project files mounted read-only into MCP containers
- Trust levels (untrusted/reviewed/trusted) deferred to future feature

---

## Feature: gitflow-automation

**Branch:** `feature/gitflow-automation`
**Depends on:** workflow-command
**Status:** Not Started

### Goal

Automate the full gitflow cycle: after the AI finishes coding on a feature branch, automatically run tests, commit, push, create PR to develop, and notify the user.

### Acceptance Criteria

- [ ] `dtl workflow finish` runs lint + tests, commits, pushes, creates PR
- [ ] PR title and body derived from the feature spec in DEVPLAN.md
- [ ] Commit message follows conventional commits (`feat:` prefix, spec summary)
- [ ] If tests fail, stops and notifies user instead of pushing broken code
- [ ] Updates feature status to "PR Open" in DEVPLAN.md
- [ ] After user merges (detected via polling or webhook), updates status to "Merged"
- [ ] Tests cover the happy path and test-failure abort

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `workflow finish` subcommand |
| `tests/test_gitflow.py` | Create | Test PR creation and status updates |

### Key Decisions

- Use `gh` CLI for PR creation (already available on the workstation)
- Push and PR happen on the HOST, not inside the container — the AI only commits locally
- Container has no git credentials by design (security boundary)
- `dtl workflow finish` runs on the host: reads container's commits from workspace mount, pushes, creates PR
- Poll for merge status every 60s if `--wait` flag passed, otherwise just notify
- Never force-push or merge automatically — user always approves

### Notes

- The full automated flow becomes: `dtl workflow next` (branch + AI in container) -> AI commits locally -> `dtl workflow finish` (host pushes + PR + notify) -> user merges on phone -> `dtl workflow next` (picks up next feature)

---

## Feature: telegram-bot

**Branch:** `feature/telegram-bot`
**Depends on:** gitflow-automation, pr-notify
**Status:** Not Started

### Goal

A standalone systemd service (`dtl-bot.py`) that bridges Telegram to dtl. Receives development plans from the user's phone, saves them to the project, runs the full autonomous pipeline (branch → AI codes → test → PR → notify), and sends results back. This is the "launch autonomous dev from anywhere" capability.

### Acceptance Criteria

- [ ] `dtl-bot.py` runs as a long-polling Telegram bot (no public IP, no webhooks)
- [ ] Only responds to messages from the configured chat_id (security)
- [ ] Accepts a DEVPLAN.md file attachment or inline markdown feature spec
- [ ] Validates received content has required structure (`## Feature:`, `### Goal`, `### Acceptance Criteria`)
- [ ] Saves plan to the target project's `docs/DEVPLAN.md` (append or overwrite, user specifies)
- [ ] `/start {project-path}` command sets the active project directory
- [ ] `/next` command triggers `dtl workflow next` on the active project
- [ ] `/status` command returns: current branch, git status, last test result, open PRs
- [ ] Streams progress updates back to Telegram (started, tests running, PR created, etc.)
- [ ] Handles errors gracefully: sends failure message with log excerpt, does not crash
- [ ] Installs as a systemd user service (`systemctl --user enable dtl-bot`)
- [ ] Tests cover message parsing, plan validation, command routing

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl-bot.py` | Create | Telegram bot service (standalone, stdlib-only) |
| `dtl-bot.service` | Create | systemd unit file for user service |
| `install.sh` | Modify | Add optional bot service installation |
| `tests/test_bot.py` | Create | Test message parsing, plan validation, command routing |

### Key Decisions

- Separate file from dtl.py (it's a long-running service, not a CLI tool)
- stdlib-only: `urllib.request` for Telegram API, `json` for parsing, `subprocess` to call dtl
- Long-polling with 30s timeout (Telegram's recommended approach)
- One active project at a time (set via `/start`, stored in a state file)
- Bot token and chat_id from environment variables (`DTL_BOT_TOKEN`, `DTL_BOT_CHAT_ID`)
- Progress updates via Telegram message edits (edit the same message as stages complete)

### Notes

- **Env file strategy:** All secrets (`ANTHROPIC_API_KEY`, `DTL_BOT_TOKEN`, `DTL_BOT_CHAT_ID`, `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`) live in `/media/secrets/devtools/env` on the SECRETS partition. `install.sh` symlinks this to `~/.config/dtl/env`. The systemd unit loads via `EnvironmentFile=`. This persists across weekly OS rebuilds. If the SECRETS file doesn't exist, `install.sh` creates a template and warns.
- Telegram bot API long polling: `getUpdates?offset={last_id+1}&timeout=30`
- Message edits: `editMessageText` to update a single status message as the pipeline progresses
- The bot should survive dtl crashes — catch subprocess errors, report them, stay alive
- Consider a `/stop` command to cancel a running pipeline (sends SIGTERM to dtl subprocess)
- Future: `/queue` command to stack multiple features, process sequentially
- systemd unit should restart on failure: `Restart=on-failure`, `RestartSec=10`
- systemd unit uses `EnvironmentFile=/home/comp/.config/dtl/env` (symlinked to SECRETS partition)
- The full phone-to-PR flow: user sends plan on phone → bot saves + runs dtl → AI codes → tests → PR → bot sends PR link → user merges on GitHub mobile
