# Development Plan: Dev Tools Launcher (dtl)

**Status:** In Progress
**Created:** 2026-03-28
**Updated:** 2026-03-28

## Overview

dtl is a single-file Python scaffolder for containerized dev environments with AI provider support. This plan covers the features needed to support fully autonomous gitflow workflows — from startup trigger through coding, testing, PR creation, merge detection, and auto-continuation to the next feature.

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
**Status:** Merged

### Goal

Add a `dtl workflow next` command that reads a DEVPLAN.md, finds the next unstarted feature, creates a feature branch off develop, and launches the AI with the feature spec as context.

### Acceptance Criteria

- [x] `dtl workflow next --plan docs/DEVPLAN.md` parses the plan and identifies the next feature with status "Not Started"
- [x] Creates `feature/{feature-name}` branch off current develop
- [x] Passes the feature spec (goal, acceptance criteria, files, decisions, notes) as the AI prompt
- [x] `dtl workflow list --plan docs/DEVPLAN.md` prints all features with their status
- [x] Handles edge cases: no plan file, all features done, dirty working tree
- [x] Updates the feature's status to "In Progress" in the plan file
- [x] Tests cover parsing, branch creation, and status updates

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

## Feature: gitflow-automation

**Branch:** `feature/gitflow-automation`
**Depends on:** workflow-command
**Status:** Merged

### Goal

Automate the full gitflow cycle into a continuous loop: AI codes a feature → lint + test → commit → push → create PR → poll for merge → auto-start next feature. The loop runs unattended until all DEVPLAN features are complete or a failure occurs. Can be triggered on system startup for scheduled autonomous development.

### Acceptance Criteria

- [x] `dtl workflow finish` runs lint + tests, commits, pushes, creates PR to develop
- [x] PR title and body derived from the feature spec in DEVPLAN.md
- [x] Commit message follows conventional commits (`feat:` prefix, spec summary)
- [x] If tests fail, stops and notifies user instead of pushing broken code
- [x] Updates feature status to "PR Open" in DEVPLAN.md
- [x] `dtl workflow finish --watch` polls `gh pr view --json state` every 60s for merge
- [x] When merge detected, updates status to "Merged" and auto-runs `dtl workflow next`
- [x] `dtl workflow run --projects dir1,dir2,...` runs the full loop: next → AI → finish → watch → repeat
- [x] Loop exits cleanly when: all features done, a feature fails tests, or PR is closed (not merged)
- [x] `dtl workflow run` can target multiple projects via `--projects dir1,dir2,...`
- [x] Logs all activity to `~/.local/share/dtl/workflow.log`
- [x] `dtl workflow run --schedule HH:MM` defers start until the specified time (for off-peak API usage)
- [x] Startup integration: `dtl-autodev.service` systemd user unit runs `dtl workflow run` on boot
- [x] Service loads secrets from `EnvironmentFile=~/.config/dtl/env` (symlinked to SECRETS partition)
- [x] Tests cover the happy path, test-failure abort, merge detection, and multi-project queueing

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `workflow finish`, `workflow run` subcommands |
| `dtl-autodev.service` | Create | systemd user unit for boot-triggered autonomous dev |
| `install.sh` | Modify | Add optional autodev service installation |
| `tests/test_gitflow.py` | Create | Test PR creation, merge polling, loop logic |

### Key Decisions

- Use `gh` CLI for PR creation and merge status polling (already available on the workstation)
- Push and PR happen on the HOST, not inside the container — the AI only commits locally
- Container has no git credentials by design (security boundary)
- `dtl workflow finish` runs on the host: reads container's commits from workspace mount, pushes, creates PR
- Poll for merge status every 60s (GitHub API rate limit: 5000/hr authenticated, this uses ~60/hr)
- Never force-push or merge automatically — user always approves merges
- `--schedule` uses `time.sleep()` until target time, not cron (keeps it self-contained)
- Multi-project: processes projects sequentially, one feature per project per round, then loops
- Claude Pro OAuth login persists in `claude-data` volume — no API key needed for development AI

### Notes

- The full automated flow: boot → `dtl workflow run` → picks first project with unfinished features → `workflow next` (branch + AI in container) → AI codes and commits locally → `workflow finish` (host pushes + PR) → polls for merge → user merges on phone → loop picks next feature → repeat
- User's daily workflow: morning — review and merge PRs on phone. Evening — write new DEVPLANs. Computer runs development autonomously in between.
- `--schedule` enables off-peak usage: `dtl workflow run --schedule 02:00` starts at 2 AM when API traffic is low
- systemd unit: `Restart=on-failure`, `RestartSec=60`, `EnvironmentFile=%h/.config/dtl/env`
- If a feature fails 3 times consecutively, skip it and move to the next (mark as "Failed" in DEVPLAN)

---

## Feature: smart-validation

**Branch:** `feature/smart-validation`
**Depends on:** none
**Status:** In Progress
**Requires:** ai

### Goal

Make the `validate_project` checks smarter so they don't produce false positives. Currently the port mapping check flags any `ports:` in the project's docker-compose.yml, but service containers (e.g. Ollama, Postgres) legitimately need host ports.

### Acceptance Criteria

- [ ] Port mapping check only flags the AI container (`claude-code`, `openclaw-gateway`), not service containers
- [ ] Check parses docker-compose.yml per-service instead of searching the whole file for `ports:`
- [ ] No false positives on projects with Ollama, Postgres, or Redis services
- [ ] Tests cover: AI container with ports (fail), service container with ports (pass), no ports (pass)
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Smarter port check in `validate_project` |
| `tests/test_validation.py` | Create | Test validation logic |

### Key Decisions

- Parse YAML with regex (stdlib-only constraint, no `pyyaml`)
- Only AI containers are expected to have no ports — service containers are fine

---

## Feature: mcp-isolation

**Branch:** `feature/mcp-isolation`
**Depends on:** none
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
