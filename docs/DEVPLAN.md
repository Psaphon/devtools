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
**Status:** Merged
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
**Status:** Merged

### Goal

Individually containerize MCP servers with strict isolation: no network, read-only filesystem, memory/CPU caps. Based on Phase 3 of AI-SANDBOX-DESIGN.md (already implemented in usb-autoinstall, needs porting to dtl).

### Acceptance Criteria

- [x] `dtl ai add-mcp --server filesystem --project .` scaffolds an isolated MCP container
- [x] Generated container: `network_mode: none`, `read_only: true`, `cap_drop: ALL`, 512MB/1CPU
- [x] Communication via stdio pipe (docker exec), not TCP
- [x] 10 well-known MCP packages recognized (filesystem, github, memory, etc.)
- [x] Unknown package names pass through for custom servers
- [x] Claude Code settings.json wired to use containerized MCP servers
- [x] Tests cover container config generation and validation

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
**Status:** Merged

### Goal

Add VM-based isolation option for AI sandboxes using QEMU/KVM, providing hardware-level isolation beyond Docker containers. Based on AI-SANDBOX-DESIGN.md.

### Acceptance Criteria

- [x] `dtl new --ai claude --isolation vm` scaffolds QEMU/KVM-based AI sandbox
- [x] Generated files: cloud-init.yaml, vm-config.sh, Makefile (up/down/ssh/status/destroy)
- [x] VM boots with Docker pre-installed, SSH key-based auth
- [x] Network isolation: host-only TAP, allowlist for Ollama + Anthropic API only
- [x] `dtl ai start --project . --isolation vm` boots VM and connects
- [x] Resource limits configurable via env vars (AI_VM_CPUS, AI_VM_RAM, AI_VM_DISK)
- [x] Tests cover file generation and config validation

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

## Feature: fix-workflow-spin-loop

**Branch:** `feature/fix-workflow-spin-loop`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Fix the bug in `dtl workflow run` where a dirty working tree causes the outer `while True` loop to spin without sleep, generating multi-GB logs. Root cause: `any_work_done = True` is set before the dirty-tree check, so the outer loop never hits its `break`.

### Acceptance Criteria

- [ ] `any_work_done = True` is set **only** after all skip gates pass (dirty tree, branch-create failure, AI-run failure) — not before
- [ ] A floor `time.sleep(60)` is added at the bottom of the outer `while True` loop as belt-and-suspenders, regardless of work state
- [ ] New test in `tests/test_workflow.py` simulates a project with a dirty tree and asserts the loop exits after one pass (no spin) OR sleeps between iterations (rate-limited)
- [ ] Log output for a dirty-tree-only run contains at most one skip message per project per minute (not thousands)
- [ ] All existing tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Reorder `any_work_done` assignment and add floor sleep in `cmd_workflow_run` |
| `tests/test_workflow.py` | Modify | Add dirty-tree spin-loop regression test |

### Key Decisions

- Prefer fixing ordering (`any_work_done = True` only after all gates) AND adding floor sleep. Defense in depth; either alone is fragile.
- Floor sleep value: 60 seconds. Matches the existing PR-merge poll interval.

### Notes

Reference: FEATURE-REQUESTS.md item #9. Caused loom's 6-day silent stall (18GB log of `Working tree is dirty — skipping.`).

---

## Feature: workflow-log-defaults

**Branch:** `feature/workflow-log-defaults`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

`dtl workflow run` should write its own log to an XDG-compliant location by default, outside any project under `--projects`. Writing the log into a project is a footgun: the untracked log file makes the tree dirty and the loop skips the project forever.

### Acceptance Criteria

- [ ] `dtl workflow run` writes its log to `~/.local/state/dtl/<first-project-name>-workflow.log` by default (creates the directory if missing)
- [ ] `--log PATH` flag overrides the default
- [ ] If `--log PATH` resolves to a location inside any project in `--projects`, exit with a clear error: `refusing to write log inside a project directory; this would cause the dirty-tree skip loop`
- [ ] `dtl workflow run --help` documents the default and the footgun
- [ ] Test covers: default path creation, `--log` override, rejection of in-project log path
- [ ] Lint clean, tests pass

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `--log` arg, default computation, in-project rejection in `cmd_workflow_run` |
| `tests/test_workflow.py` | Modify | Test default, override, and rejection |

### Key Decisions

- XDG path: `$XDG_STATE_HOME` or `~/.local/state`, then `dtl/`, then `<project>-workflow.log`.
- In-project rejection uses `Path.resolve()` and `is_relative_to()` check against each project.

### Notes

Reference: FEATURE-REQUESTS.md item #11.

---

## Feature: workflow-stall-visibility

**Branch:** `feature/workflow-stall-visibility`
**Depends on:** fix-workflow-spin-loop
**Status:** Merged
**Requires:** ai

### Goal

When `dtl workflow run` skips a project (dirty tree, branch-create failure, or other non-fatal skip), the skip is currently invisible to anyone not tailing the log. Make it observable via a state file and a notification after N consecutive skips.

### Acceptance Criteria

- [ ] On every skip, `dtl` writes `~/.local/state/dtl/<project>-workflow-state.json` with `{last_check, last_skip_reason, consecutive_skips, next_retry}`
- [ ] After 3 consecutive skips of the same reason, invoke the project's `.ai/notify.py` (if present) with a `stalled` message
- [ ] State file is atomically written (temp + rename)
- [ ] `dtl workflow status --project <path>` prints the current state in a human-readable form
- [ ] Test: simulated dirty-tree skip x3 triggers one notify call
- [ ] Lint clean, tests pass

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Emit state file, call notify.py, add `workflow status` subcommand |
| `tests/test_workflow.py` | Modify | Test state file writes and notification trigger |

### Key Decisions

- State lives alongside logs in `~/.local/state/dtl/`, not in the project (avoids the dirty-tree footgun we're trying to fix).
- Notification uses the existing `.ai/notify.py` primitive — do not add a new notification mechanism.
- 3-skip threshold is a constant in `dtl.py`, not configurable in v1.

### Notes

Reference: FEATURE-REQUESTS.md item #10.

---

## Feature: require-ci-workflow

**Branch:** `feature/require-ci-workflow`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

`dtl ai attach` currently warns when `.github/workflows/ci.yml` is missing but proceeds. Without CI, `gh pr merge --auto --squash` has nothing to gate on, and the workflow loop stalls at "waiting for merge." Promote CI from advisory to required, with a scaffold option.

### Acceptance Criteria

- [ ] `dtl ai attach` fails hard if no `.github/workflows/*.yml` exists, unless `--no-ci` is passed
- [ ] `dtl ai attach --scaffold-ci` writes a standard `.github/workflows/ci.yml` (ruff check + ruff format check + pytest) if missing
- [ ] Scaffolded CI tolerates pre-pyproject state: conditional steps that skip ruff/pytest when no Python source exists yet
- [ ] Scaffolded CI runs on PR and push to `develop` and `main`
- [ ] Error message explains why CI is required (auto-merge gating) and how to bypass (`--no-ci`) or scaffold (`--scaffold-ci`)
- [ ] Test: attach on project without CI fails; with `--scaffold-ci` succeeds and writes file; with `--no-ci` succeeds without writing
- [ ] Lint clean, tests pass

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Promote CI check to required; add `--scaffold-ci` and `--no-ci` flags; inline the ci.yml template |
| `tests/test_ai_attach.py` | Modify or Create | Cover the three CI paths |

### Key Decisions

- CI template is inlined into `dtl.py` (stdlib-only constraint — no file reads from installed path).
- Default behavior is `fail` rather than `warn`: force the user to choose.

### Notes

Reference: FEATURE-REQUESTS.md item #12. The standard ci.yml pattern is already in use at `~/Projects/loom/.github/workflows/ci.yml` and morning-brief — use that as the reference.

---

## Feature: ai-dev-loop-break

**Branch:** `feature/ai-dev-loop-break`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

The AI developer inside `dtl ai run` can burn hours retrying a broken command or stuck test. Wrap AI invocations with retry caps and wall-clock timeouts, and emit a structured failure report on giving up.

### Acceptance Criteria

- [ ] `dtl ai run` accepts `--max-wall-clock SECONDS` (default 1800 = 30 min per feature) — hard kill on exceed
- [ ] `dtl ai run` accepts `--max-ai-retries N` (default 3) — counts failed "tests failed, retrying" loops inside one feature
- [ ] When either limit is hit: container is stopped, a `FAILURE-REPORT.md` is written to the project root with last 200 log lines + which limit was hit + feature name
- [ ] `FAILURE-REPORT.md` is gitignored by default (add to dtl's scaffolded `.gitignore` template if not already)
- [ ] `dtl workflow run` picks up the failure, marks feature status as `Failed`, and proceeds to next feature (reusing existing `consecutive_failures` logic)
- [ ] Test: simulated AI hang exits via wall-clock timer; simulated loop hits retry cap
- [ ] Lint clean, tests pass

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Wrap AI subprocess with timeout + retry counter; write FAILURE-REPORT.md on bail |
| `tests/test_ai_run.py` | Modify or Create | Cover timeout and retry-cap paths |

### Key Decisions

- Timeout wraps the subprocess, not the model call — we don't inspect AI output for "stuck" heuristics (unreliable).
- Failure report is `FAILURE-REPORT.md` in project root, gitignored — easily findable but doesn't pollute commits.
- Retry counting: parse AI stdout for `tests failed, retrying` or similar heuristic markers; if not detectable reliably, skip the retry cap and rely only on wall-clock.

### Notes

Reference: FEATURE-REQUESTS.md item #6. User pain point — "AI developer may get stuck retrying broken renders."

---

## Feature: workflow-watchdog

**Branch:** `feature/workflow-watchdog`
**Depends on:** workflow-stall-visibility
**Status:** Merged
**Requires:** both

### Goal

A locally-scheduled watchdog that periodically checks all `dtl`-managed projects for stalls, absent PR activity, and anomalous log growth, then notifies on anomaly. Free (systemd user timer), complements (not replaces) the in-loop stall visibility.

### Acceptance Criteria

- [x] `dtl watchdog install --projects PATH[,PATH…]` writes `~/.config/systemd/user/dtl-watchdog.{service,timer}` and prints activation commands
- [x] Default timer interval: 2 hours, overridable via `--interval MINUTES`
- [x] Service runs `dtl watchdog check --projects <paths>` which emits a pass/fail summary
- [x] Check detects: (a) `dtl workflow run` process absent when DEVPLAN has Not Started features; (b) dirty tree older than 24h; (c) no PR activity in 48h when Not Started features exist; (d) log growth > 100MB/day in `~/.local/state/dtl/`
- [x] On any anomaly, invokes every project's `.ai/notify.py` with a structured message
- [x] `dtl watchdog status` prints last run result and next scheduled run
- [ ] [HUMAN] Install the timer via `systemctl --user enable --now dtl-watchdog.timer`
- [x] Test: fixture projects exercising each anomaly type trigger exactly one notify call
- [x] Lint clean, tests pass

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `watchdog` subcommand group: `install`, `check`, `status` |
| `templates/dtl-watchdog.service.tmpl` | Create | Service unit template (inline in dtl.py if stdlib-only constraint forces it) |
| `templates/dtl-watchdog.timer.tmpl` | Create | Timer template (same note) |
| `tests/test_watchdog.py` | Create | Anomaly detection tests with fixture projects |

### Key Decisions

- Unit templates are inlined into `dtl.py` if the stdlib-only / single-file constraint demands it — check convention of existing templates.
- Anomaly thresholds (24h dirty, 48h PR silence, 100MB/day log) are constants for v1, not configurable.
- Notifications reuse each project's `.ai/notify.py` — do not add a new notification system.

### Notes

Complements the in-loop stall visibility (`workflow-stall-visibility`) — that one emits state; this one watches state and notifies humans. Both feed into the user's phone via `notify.py`.

---

## Feature: planning-templates-refresh

**Branch:** `feature/planning-templates-refresh`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Three small additions to dtl's planning templates that make non-code and asset-heavy projects (like loom) fit the PM flow without awkward workarounds.

### Acceptance Criteria

- [ ] `templates/PLANNING-GUIDE.md` gets a new section titled "Non-code features" explaining that acceptance criteria can be "produces expected artifact" rather than "tests pass"
- [ ] `templates/DEVPLAN.md` gets an optional `### Assets` section in the per-feature block, documented as "use when a feature produces non-code deliverables (workflow JSONs, prompts, reference images, etc.)"
- [ ] `templates/PROJECTS-CONTEXT.md` gets a standing `## Hardware` section with placeholders for GPU, VRAM, RAM, CPU, storage, network, GPU tenants, and a filled example for the current workstation (RTX 2060 6GB, 32GB RAM, Tailscale, Terminus SSH)
- [ ] All three templates remain internally consistent (no broken cross-links, no duplicate sections)
- [ ] No code changes to `dtl.py` — template-only feature
- [ ] Lint clean (no tests this feature; templates aren't lintable by ruff)

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `templates/PLANNING-GUIDE.md` | Modify | Add "Non-code features" section |
| `templates/DEVPLAN.md` | Modify | Add optional Assets section |
| `templates/PROJECTS-CONTEXT.md` | Modify or Create | Add Hardware section with example |

### Key Decisions

- Bundle three template changes into one feature — each is too small to be its own PR and they share the same reviewer attention.
- No `dtl.py` changes means no tests; the acceptance is "does a reader understand how to use the new sections."

### Notes

Reference: FEATURE-REQUESTS.md items #3, #4, #5. Origin: loom's media-pipeline / asset-JSON / hardware-aware planning.

---

## Feature: workflow-install-deps-before-test

**Branch:** `feature/workflow-install-deps-before-test`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Make `dtl workflow finish`'s local lint/test gate install the project's declared dependencies before running pytest, so src-layout Python projects with declared deps (numpy, httpx, etc.) pass the gate. Without this, the AI's commit is rejected even when CI would pass.

### Acceptance Criteria

- [ ] When `pyproject.toml` exists in the project, `_run_lint_and_tests` runs `pip install -e ".[dev]"` before pytest, falling back to `pip install -e .` if the `dev` extra is missing
- [ ] Install runs quietly (`--quiet`) so the output log isn't spammed on cache hits
- [ ] Install failures surface clearly: if `pip install` fails, lint/test gate returns failed with the pip output captured
- [ ] Existing projects without `pyproject.toml` (old stacks) are unaffected — no install attempt
- [ ] A new unit test covers: (a) pyproject detected → install invoked; (b) no pyproject → install skipped; (c) pip failure → gate reports failed
- [ ] Lint clean (`ruff check . && ruff format --check .`)
- [ ] All tests pass (`pytest tests/`)

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | `_run_lint_and_tests` around line 3394–3415: add editable install step when `pyproject.toml` is present |
| `tests/test_workflow.py` | Modify or Create | Unit test for the new install step |

### Key Decisions

- `pip install -e ".[dev]"` (not `pip install .`) — editable matches CI and keeps test-time src edits live.
- Use the same Python interpreter that runs pytest — don't introduce a venv; dtl runs on the host.
- `--quiet` output but capture stderr so failures are not silent.
- Fallback to `pip install -e .` preserves compatibility with projects that don't declare a `dev` extra.

### Notes

Reference: FEATURE-REQUESTS.md item #16. Origin: loom night 1 — both scaffold and song-analysis failed the gate with `ModuleNotFoundError` despite correct code; CI (which does editable-install) would have passed. Scaffold was rescued with a manual PR + a `tests/conftest.py` sys.path shim; this feature removes the need for that workaround.

---

## Feature: workflow-install-deps-pep668

**Branch:** `feature/workflow-install-deps-pep668`
**Depends on:** none
**Status:** In Progress
**Requires:** ai

### Goal

Make the editable-install step added in PR #21 tolerate PEP 668 "externally-managed" environments (Debian/Ubuntu system Python). Without this, every Python project on the ephemeral workstation fails the local gate on install — blocking every src-layout project from shipping, regardless of whether its code is correct.

### Acceptance Criteria

- [ ] `pip install -e ".[dev]"` in `_run_lint_and_tests` (dtl.py:3414–3428) passes `--break-system-packages` to bypass PEP 668 rejection
- [ ] Same flag applied to the `.` fallback install
- [ ] Existing behavior on non-PEP-668 hosts (e.g., CI runners, venvs) is unchanged — `--break-system-packages` is a no-op outside externally-managed environments
- [ ] Unit test: given a mock pip invocation, the command string includes `--break-system-packages`
- [ ] A short comment in code cites PEP 668 + ephemeral-workstation rationale so the flag isn't mistaken for a hack
- [ ] All tests pass (`pytest tests/`)
- [ ] Lint clean (`ruff check . && ruff format --check .`)

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `--break-system-packages` to both pip commands in `_run_lint_and_tests` (lines ~3415 and ~3420) |
| `tests/test_workflow.py` | Modify | Assert the pip command includes the flag |

### Key Decisions

- `--break-system-packages` chosen over per-project venv because the workstation is ephemeral (rebuilt weekly from USB); system Python is disposable. Venv would add first-run latency and cleanup surface without a durable benefit in this environment.
- Flag is applied unconditionally, not conditionally on detecting PEP 668. Unconditional is idempotent and simpler; pip ignores the flag on hosts that don't enforce PEP 668.

### Notes

Reference: FEATURE-REQUESTS.md item #17. Origin: loom night 2 — `workflow-install-deps-before-test` (PR #21) ran cleanly at the logic level but pip refused to install into system site-packages with `error: externally-managed-environment`. Clean exit, no spin-loop (#9 fix held), but zero features merged. This is the follow-up fix to unblock Python projects on this workstation.
