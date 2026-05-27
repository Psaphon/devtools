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
**Status:** Merged
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

---

## Feature: prompt-hygiene-pr-suffix

**Branch:** `feature/prompt-hygiene-pr-suffix`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Stop the AI from emitting `(#N)` PR-number suffixes in commit subjects. GitHub appends one automatically on squash-merge, so an AI-authored commit subject ending in `(#N)` produces a duplicate suffix on `develop` (`feat: foo (#4) (#4)`). Verified live in `loom@a5d3a32`.

The fix is a one-line addition to the AI prompt explaining that GitHub adds the PR-number suffix on squash, and the AI must not include one.

### Acceptance Criteria

- [ ] `_build_ai_prompt` (dtl.py:2990–3005) appends a sentence telling the AI not to include a `(#N)` PR-number suffix in commit subjects (GitHub adds it on squash-merge)
- [ ] Existing `_build_ai_prompt` tests in `tests/test_workflow.py:192–212` still pass
- [ ] One new test asserts the warning string is present in the returned prompt
- [ ] Lint clean (`ruff check . && ruff format --check .`)
- [ ] All tests pass

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Append the no-PR-suffix instruction to `_build_ai_prompt` (lines ~2998–3004) |
| `tests/test_workflow.py` | Modify | Add a test asserting `_build_ai_prompt` output contains the no-suffix warning |

### Key Decisions

- Warning lives in the prompt string, not as a post-commit rewrite step. Cheaper, no commit history mutation, and the AI learns the rule rather than having dtl silently fix it.
- The wording must explicitly say *why* (squash-merge appends it). The AI mimics what it sees in `git log`, where every prior commit ends in `(#N)`. Without the *why*, the rule looks arbitrary and risks being ignored when the AI is uncertain.

### Notes

Origin: loom night 3 (2026-04-24) feature/comfyui-client AI commit `29bfe0c` had subject `feat: async ComfyUI client — submit, poll, fetch outputs (#4)`. Squash-merged on 2026-04-26 as `a5d3a32 feat: async ComfyUI client ... (#4) (#4)`. The duplication is a feedback loop: each squash-merged commit reinforces the AI's belief that suffixes belong in subjects.

Cross-reference: AI prompt design feedback in PM memory has long emphasized "Do NOT push" and "include exact commit msg" — this adds "do NOT include `(#N)`" to that list.

---

## Feature: scheduled-run-freshness

**Branch:** `feature/scheduled-run-freshness`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Make `dtl workflow run --schedule HH:MM` execute against the current on-disk `dtl.py` at fire time, not the in-memory copy from process start. Today, a process launched at 15:00 with `--schedule 02:00` will run the 02:00 work using whatever `dtl.py` was on disk at 15:00 — even if dtl was updated overnight. This caused loom night 3 to fail PEP 668 even after devtools merged the fix at 01:02.

The fix uses **subprocess delegation**: when `--schedule` is set, the parent process sleeps until the target time, then spawns a fresh `subprocess.run([sys.executable, sys.argv[0], "workflow", "run", "--projects", ...])` *without* `--schedule`. The child reads disk-current `dtl.py` at exec time. Parent waits for child and exits with the child's return code.

### Acceptance Criteria

- [ ] When `--schedule HH:MM` is set, `cmd_workflow_run` (dtl.py:3707) sleeps until target, then `subprocess.run`s a fresh invocation of itself **without** `--schedule`, forwarding all other args (`--projects`, `--max-failures`, `--max-wall-clock`, `--max-ai-retries`, `--log` if present)
- [ ] Parent process exits with the child's returncode
- [ ] When `--schedule` is *not* set, behavior is unchanged (no subprocess; runs in-process as today)
- [ ] One new test in `tests/test_workflow.py` patches `subprocess.run` and asserts: (a) called with `[sys.executable, sys.argv[0], "workflow", "run", "--projects", ...]` (b) `--schedule` is NOT in the child argv (c) parent exits with the patched returncode
- [ ] Existing `cmd_workflow_run` tests still pass
- [ ] Lint clean
- [ ] All tests pass

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | After the `time.sleep(wait_secs)` in `cmd_workflow_run` (line ~3754), short-circuit into `subprocess.run` of self without `--schedule`; return the child's exit code |
| `tests/test_workflow.py` | Modify | New test class for `--schedule` subprocess delegation |

### Key Decisions

- **Subprocess over `os.execv`**: parent stays alive as a sentinel, can log "spawning child at HH:MM", and the child's exit code is observable to the parent. `execv` would replace the parent — simpler, but loses the spawn log line and conflates parent/child state.
- **Subprocess over `importlib.reload`**: dtl.py is single-file stdlib-only; reload semantics for `__main__` are awkward and reload-ed modules can keep references to old globals. A fresh subprocess is unambiguous.
- **No env-var hack** (e.g., `DTL_SKIP_SCHEDULE=1`): the child simply doesn't pass `--schedule`. Argparse already rejects unknown args; no magic.
- **Schedule semantics preserved**: parent still does the `time.sleep` — only the actual workflow execution moves to the child. Tomorrow's overnight run remains a single user-visible process tree (parent + one child).

### Notes

Origin: loom night 3 (2026-04-24). Devtools workflow scheduled 01:00, loom workflow scheduled 02:00, both processes launched 15:32 the prior day. Devtools fix landed at 01:02; loom hit the same PEP 668 error at 02:03 because its in-memory `dtl.py` predated the fix. With this freshness fix, the devtools merge at 01:02 would automatically benefit the 02:00 loom child, eliminating the cross-project ordering hazard.

Diagnostic confirmation: `loom-workflow-night3.log` shows `02:00:00 [loom] Starting feature: comfyui-client` followed by `02:03:34 [loom] Lint/tests failed... error: externally-managed-environment` — same error already fixed in devtools/dtl.py on disk by 01:02.

---

## Feature: preflight-auto-merge-check

**Branch:** `feature/preflight-auto-merge-check`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Add a preflight check at the start of `dtl workflow run` that detects whether each target project's GitHub repo has `allow_auto_merge=true`. Behavior on a failed check depends on `--schedule`:

- **With `--schedule`:** refuse to start. Log a clear error naming the affected repo(s) and exit non-zero before sleeping. A scheduled run on a repo without auto-merge stalls the polling loop indefinitely overnight (no human awake to merge).
- **Without `--schedule`:** print a one-shot warning banner naming the repo(s) and continue. The existing manual-merge polling loop already handles human-merged PRs correctly — the user is interactive and merges via the GitHub app.

This closes the night-4 stall pattern on `Psaphon/loom`, where the scheduled 02:30 run sat 14h on PR #6 because `allow_auto_merge` cannot be enabled on private repos under a Free-plan account (the API silently no-ops the PATCH).

### Acceptance Criteria

- [ ] New helper `_preflight_auto_merge(project_dir: Path) -> Optional[bool]` calls `gh api repos/<owner>/<name> --jq .allow_auto_merge` and returns the boolean. Returns `None` (skip) if the remote is not a GitHub URL or `gh` is unavailable.
- [ ] Owner/name parsed from `git remote get-url origin`; reuse any existing dtl utility for this — do not duplicate parsing.
- [ ] At the top of `cmd_workflow_run` (dtl.py line ~3707, before the schedule sleep), iterate each `--projects` path; collect those where preflight returns `False`.
- [ ] If any returned `False` AND `--schedule` is set: log the offending repos, the recommended fixes ("upgrade to GitHub Pro for private repos, or run without --schedule"), and exit non-zero before any sleep.
- [ ] If any returned `False` AND `--schedule` is NOT set: log a clear one-shot WARNING banner naming the repos and noting "PRs require manual merge via GitHub app". Continue execution.
- [ ] Returned `None` (skipped repos) does not block — log a single info line.
- [ ] Two new tests in `tests/test_workflow.py`: (a) preflight + `--schedule` + a fixture with `allow_auto_merge=False` exits non-zero and `time.sleep` is never called; (b) preflight without `--schedule` + same fixture proceeds and the warning banner is in captured logs.
- [ ] Existing `cmd_workflow_run` and scheduled-run-freshness subprocess-delegation tests still pass.
- [ ] Lint clean (`ruff check . && ruff format --check .`).
- [ ] All tests pass.

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `_preflight_auto_merge` helper; call it at top of `cmd_workflow_run`; gate `--schedule` on result |
| `tests/test_workflow.py` | Modify | Two new tests covering `--schedule` rejection and warning-banner paths |

### Key Decisions

- **GitHub API is the source of truth.** `allow_auto_merge` is a server-side property — only `gh api` can read it accurately. Do not infer from local config or cache the value.
- **`--schedule` is the line.** Without `--schedule`, the user is interactive and can merge from the GitHub mobile app. The polling loop already handles human-merged PRs (verified live on loom PR #6, which was human-merged after a 14h wait and the workflow correctly resumed). With `--schedule`, the user is asleep and a stall is silent — refuse the run.
- **Do NOT auto-enable `allow_auto_merge`.** On Free-plan + private repos, GitHub silently no-ops `PATCH allow_auto_merge=true` — the PATCH returns 200, the field stays `false`. Pretending we fixed it is worse than refusing to start. Surface the constraint, don't paper over it.
- **Skip cleanly when `gh` or remote is unsuitable.** Local-only repos and non-GitHub remotes should not be blocked by the preflight — return `None` and proceed.

### Notes

Origin: loom night 4 (2026-04-27). Scheduled 02:30 run on `Psaphon/loom` produced PR #6, which `gh pr merge --auto --squash` could not queue ("Auto-merge not available — manual merge required"). The polling loop sat 14h until human merge at 17:32 EDT.

Why GitHub blocks the setting: `allow_auto_merge` requires GitHub Pro on private repos. Free-plan accounts can enable it freely on public repos. The `Psaphon` account holds three public repos with `allow_auto_merge=true` (devtools, morning-brief, Prompt-Fishing) and one private repo where the setting cannot be enabled (loom). Branch protection has the same gate — it returns 403 with the upgrade message.

Until Psaphon upgrades to GitHub Pro (~$4/mo), private-repo development uses interactive `dtl workflow run` (no `--schedule`). The user merges PRs from the GitHub mobile app as they appear.

Cross-reference: night-4 brief misdiagnosed this as "auto-merge wasn't enabled on loom" — implying a setting flip would fix it. The actual constraint is plan + visibility, not setting state. This feature makes that distinction explicit at runtime.

---

## Feature: ai-failure-snapshot

**Branch:** `feature/ai-failure-snapshot`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

When the AI subprocess in `dtl workflow run` exits non-zero, capture a triage bundle to `~/.local/state/dtl/` so the next PM session can diagnose without spelunking through a half-implemented branch. Today, on AI exit-code-1 the workflow marks the feature failed and moves on (or refuses on dirty tree); the dirty paths and the AI's last-N stderr lines are scattered across the project and the workflow log.

A triage bundle gives the next PM one place to look.

### Acceptance Criteria

- [ ] On AI subprocess non-zero exit in `cmd_workflow_run`, write `~/.local/state/dtl/<project>-<feature>-failure-<UTC-iso>.md` containing:
  - Project path, feature name, branch name, AI exit code, wall-clock duration
  - Last 200 lines of AI stdout/stderr (combined, in order, prefixed with stream name)
  - `git status --porcelain` snapshot at the moment of failure
  - `git diff --stat develop..HEAD` and the full `git diff develop..HEAD` (capped at 5000 lines, with a "truncated" marker if exceeded)
  - List of untracked files (relative paths only — no contents)
- [ ] Snapshot is written *before* any cleanup or branch-state change, so the captured `git status` matches the AI's view at exit
- [ ] If the snapshot directory does not exist, create it (mode 0700)
- [ ] If snapshot write fails (disk full, permissions), log the failure but do not propagate — the workflow's existing failure handling continues uninterrupted
- [ ] Snapshot path is logged as a single `INFO` line to the workflow log: `failure snapshot written: <path>`
- [ ] `dtl workflow status --project <path>` (existing subcommand from `workflow-stall-visibility`) prints the most recent failure snapshot path for the project, if any
- [ ] Two new tests in `tests/test_workflow.py`: (a) simulated AI exit-1 produces a snapshot file with all required sections; (b) snapshot write failure does not raise out of `cmd_workflow_run`
- [ ] Existing AI-failure / dirty-tree / consecutive-failure tests still pass
- [ ] Lint clean (`ruff check . && ruff format --check .`)
- [ ] All tests pass

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `_write_failure_snapshot(project, feature, ai_log_lines)` helper; call it from the AI-exit-non-zero branch in `cmd_workflow_run`; extend `cmd_workflow_status` to surface latest snapshot path |
| `tests/test_workflow.py` | Modify | Two new tests: snapshot content + snapshot-write-failure tolerance |

### Key Decisions

- **Snapshot lives in `~/.local/state/dtl/`, not the project directory.** Same rationale as `workflow-log-defaults` and `workflow-stall-visibility` — never write into a project root, the dirty-tree skip loop is a footgun.
- **Markdown over JSON.** A PM (human or LLM) reads this on incident; a markdown report is grep-able, copy-paste-friendly, and renders on phone. JSON adds parsing burden without a consumer.
- **Capture stdout/stderr combined and ordered, not separately.** The diagnostic value is the *sequence* — what the AI said before it died. Splitting streams reverses that.
- **Cap the diff at 5000 lines, mark when truncated.** Pathological cases (vendored deps, large generated files) shouldn't blow up the snapshot. 5000 lines covers >99% of feature-sized diffs and keeps the file <1MB.
- **Untracked file *list*, not contents.** Untracked files might include large binaries, secrets-shaped fixtures, or personal scratch. Filenames let the PM read what they want; embedding contents inflates the snapshot and risks leaking sensitive material.
- **Snapshot-write failure is non-fatal.** The original failure (AI exit-1) is what matters; a snapshot failure on top would mask it.

### Notes

Origin: loom night 4 (2026-04-27). The `diffusion-stylize` AI returned exit code 1 mid-feature; the workflow's retry refused on a dirty tree and exited. Triage the next morning required reading `git status`, opening four dirty files, running the test suite manually, and inferring from the lint output that the AI was 95% done but tripped on `ruff check`. With this snapshot, that morning would have been one file read instead of seven.

Open question (resolve in implementation): how to capture AI stdout/stderr. The current `dtl ai run` subprocess wiring may already tee to the workflow log; if so, extracting last-200 from that log is cheaper than re-buffering. If stdout/stderr are not currently captured, this feature requires adding a ring buffer in the subprocess wrapper. Worth a quick read of the existing `_run_ai` (or equivalent) before settling the approach.

Cross-reference: this complements `workflow-stall-visibility` (state file on every skip) and `ai-dev-loop-break` (FAILURE-REPORT.md on retry-cap or wall-clock kill). Those cover *successful refusal* and *self-detected stuck-loop*. This covers the *AI exited but produced uncommitted work* case — which is what actually happened on loom night 4.

---

## Feature: planning-templates-v2

**Branch:** `feature/planning-templates-v2`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Refine the planning-Claude templates (PROJECT-BRIEF.md, DEVPLAN.md, CLAUDE.md, PLANNING-GUIDE.md, PROJECTS-CONTEXT.md) so that planning sessions held on a phone produce briefs the PM can act on without back-and-forth: explicit repo-visibility decision, optional Hardware Target section, mandatory Security & Trust Boundaries section, and a duplicate-detection step before proposing a brief.

Origin: 2026-05-12 reconcile. The hub/hdlss-ws/watch-ops trio surfaced four gaps in the templates — duplicate planning of the same machine, missing public/private repo declaration, missing hardware section, no security-boundaries discipline.

### Acceptance Criteria

- [x] `templates/PLANNING-GUIDE.md` adds a "Before You Plan: Check What Already Exists" step (scan `~/Projects/NEW-PROJECTS/` for in-flight plans)
- [x] `templates/PLANNING-GUIDE.md` adds Q11 (public/private repo), Q12 (hardware provisioning), Q13 (security/trust boundaries)
- [x] `templates/PLANNING-GUIDE.md` adds a "Repo Visibility & Scheduling Eligibility" section explaining the GH Free auto-merge constraint
- [x] `templates/PLANNING-GUIDE.md` adds a "Security & Trust Boundaries — How to Plan" section
- [x] `templates/PROJECT-BRIEF.md` adds a Repo Visibility section (required)
- [x] `templates/PROJECT-BRIEF.md` adds an optional Hardware Target section (required when project provisions a machine)
- [x] `templates/PROJECT-BRIEF.md` adds an optional Security & Trust Boundaries section (required when project touches networking, credentials, devices, or deploys to metal)
- [x] `templates/CLAUDE.md` adds a Network Segmentation and Trust Boundaries section after Coordination
- [x] `templates/PROJECTS-CONTEXT.md` adds a Network Segmentation convention, a Repo Visibility & Scheduling Eligibility convention, and an "In-Flight Plans" pointer to `~/Projects/NEW-PROJECTS/`
- [x] All tests pass (no code changed — templates only)
- [x] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `templates/PLANNING-GUIDE.md` | Modify | Pre-plan scan, 3 new interview questions, 2 new sections |
| `templates/PROJECT-BRIEF.md` | Modify | 3 new sections (Repo Visibility required, Hardware/Security optional-but-conditional) |
| `templates/CLAUDE.md` | Modify | Network Segmentation and Trust Boundaries section |
| `templates/PROJECTS-CONTEXT.md` | Modify | Two new conventions + in-flight-plans pointer |

### Key Decisions

- **Templates carry the discipline, not the planner's improvisation.** Every gap surfaced by hub/hdlss-ws/watch-ops becomes an explicit section so the next planning round doesn't rely on the planning Claude remembering to ask.
- **Repo visibility is a hard fork in the development model** — public means overnight-scheduled, private means manual day-only. The template surfaces this so it's decided up front.
- **Security & Trust Boundaries is conditional-mandatory.** Pure-software localhost-only projects skip it; anything touching networking, credentials, or hardware requires it.
- **Bind addresses are never defaults.** The CLAUDE.md template's Network Segmentation block forces `127.0.0.1` / `tailscale0` / `0.0.0.0` to be a stated decision per service.
- **In-flight plans live in `~/Projects/NEW-PROJECTS/`** and the planner is now instructed to scan them. Structural fix for the hub/hdlss-ws duplicate.

### Notes

Second round of planning-template refinement after PRs #19 and #25. Templates now carry the lessons from the first 4 production planning sessions, including the two failures (duplicate plan, missing segmentation thinking).

Companion change made the same day: `~/Projects/NEW-PROJECTS/hub/PROJECT-BRIEF.md` and `DEVPLAN.md` rewritten against these refined templates; old `hub/Project-Brief.md`, `hub/Devplan.md`, `hdlss-ws/`, and `watch-ops/` moved to `~/Projects/NEW-PROJECTS/ARCHIVE/`.

---

## Feature: dtl-notify-hook

**Branch:** `feature/dtl-notify-hook`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Add a notification hook to `dtl workflow run` that emits structured events (`needs-attention`, `feature-merged`, `test-failure`, `idle`, `ai-failure`) to a configurable HTTP endpoint. The endpoint is typically ntfy on the user's hub, which forwards to iOS via APNs and to a watch action-button surface. This decouples `dtl` from any specific notification backend.

Origin: 2026-05-12, carved out of `watch-ops` planning. ntfy lives on hub (separate repo); the hook lives here because `dtl` is the event source.

### Acceptance Criteria

- [ ] `dtl workflow run` reads notification config from `~/.config/dtl/notify.toml` (gitignored, optional — absent = no notifications, log-only)
- [ ] Config schema:
  ```toml
  url = "https://ntfy.<tailnet>.ts.net/dtl"
  events = ["ai-failure", "feature-merged", "needs-attention", "idle"]
  auth_header_file = "/etc/dtl/ntfy-auth"  # optional; contents become Authorization: header
  retry_seconds = [1, 5, 30]                # backoff for delivery failures; then give up
  ```
- [ ] Events emitted (JSON POST body):
  - `ai-failure` — AI subprocess exited non-zero (project, feature, exit_code, failure_snapshot_path from ai-failure-snapshot)
  - `feature-merged` — workflow detected PR merged (project, feature, pr_number)
  - `needs-attention` — workflow paused for [HUMAN] criterion (project, feature, criterion)
  - `idle` — workflow has no Not-Started features left across all projects (timestamp)
- [ ] Each POST includes a stable `event_id` for deduplication
- [ ] Each POST includes optional `actions` array with `{label, url}` for ntfy action buttons (e.g., `approve PR 9` → POST to hub's action-handler endpoint)
- [ ] Delivery failures retried per `retry_seconds`; total delivery time bounded; failed deliveries logged but never block the workflow
- [ ] Notification config loaded once per workflow run, not per event
- [ ] `dtl notify test` subcommand sends a synthetic event for testing
- [ ] New tests in `tests/test_workflow.py`: (a) emits ai-failure event with correct shape on AI exit-1; (b) emits feature-merged on PR merge detection; (c) delivery failure is non-fatal
- [ ] `docs/notify.md` documents config + event shapes + ntfy action-handler integration
- [ ] All existing tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `_load_notify_config`, `_emit_notify_event`, integrate at the 4 event sites in `cmd_workflow_run`; add `dtl notify test` subcommand |
| `tests/test_workflow.py` | Modify | Three new tests covering event emission and delivery failure tolerance |
| `docs/notify.md` | Create | Config + event shapes + ntfy action-handler integration |

### Key Decisions

- **stdlib HTTP** (`urllib.request`) — preserves the dtl stdlib-only constraint
- **TOML config**, gitignored, optional — no surprise notifications, opt-in per machine
- **Stable `event_id`** — lets ntfy / action-handlers deduplicate, supports retries
- **Action buttons in the event payload** — the hook generates action URLs (e.g., `POST /api/approve/<project>/<pr>`); the hub-side action-handler endpoint dispatches them. Keeps verb vocabulary in one place (hub's dispatcher) but URL generation close to the event
- **Delivery failures are silent (logged, not raised)** — workflow must never fail because a notification failed

### Notes

- **Companion features in `hub`:** `ntfy-stack`, `action-handlers`. The hub side cannot do anything without this feature shipping first as the event source
- Authentication via `auth_header_file` is generic — works for Bearer, Basic, or none

## Feature: interruption-taxonomy

**Branch:** `feature/interruption-taxonomy`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Replace the substring-on-stdout auth-failure detection with a structured outcome signal. `_detect_auth_failure` (dtl.py:3666) does a full-text scan of AI output for strings like `"authentication failed"` — and on 2026-05-14 02:20 EDT it false-positive'd on the AI's own narration of writing a Cloudflare Worker error message, abandoning a fully-completed `research-worker` feature mid-run. This feature introduces a `RunOutcome` enum, a sentinel marker the AI prints as its final line, and tail-only fallback detection. No more stranded work because of substring collisions.

### Acceptance Criteria

- [ ] New `class RunOutcome` (string constants) defined in `dtl.py`: `COMPLETED`, `COMPLETED_TESTS_FAILED`, `COMPLETED_NOTHING_TO_PUSH`, `INTERRUPTED_QUOTA`, `INTERRUPTED_AUTH`, `INTERRUPTED_WALL_CLOCK`, `INTERRUPTED_NETWORK`, `FAILED_AI`, `FAILED_INFRA`
- [ ] New `_classify_run(exit_code, output_lines)` returns a `RunOutcome`. Looks for `<<<DTL:OUTCOME=NAME>>>` sentinel first, then falls back to tail-only scan (last 50 lines) with disjoint pattern sets per outcome
- [ ] `_build_ai_prompt` (dtl.py:3118) appends: *"After committing, print exactly this line as your final output: `<<<DTL:OUTCOME=COMPLETED>>>`. If you cannot complete, print `<<<DTL:OUTCOME=FAILED_AI>>>` followed by a one-line reason."*
- [ ] `_detect_auth_failure` is deleted; all callers route through `_classify_run`
- [ ] `cmd_workflow_run` (dtl.py:4322) replaces the `if _detect_auth_failure(ai_output): sys.exit(2)` block with a switch on `_classify_run(...)`. Each outcome has explicit handling (no silent `sys.exit`)
- [ ] `INTERRUPTED_AUTH` writes a snapshot, emits a notify event, and pauses cleanly
- [ ] `INTERRUPTED_QUOTA` and `INTERRUPTED_NETWORK` do NOT count toward the feature's failure budget (environmental)
- [ ] On any interruption, working tree is left clean (DEVPLAN status reverted, branch returned to develop) — no more dirty-tree skip loops on the next run
- [ ] Tests in `tests/test_workflow.py`: `TestRunClassification` covers one test per outcome plus a regression test for last night's bug (output containing `"authentication failed"` PLUS `<<<DTL:OUTCOME=COMPLETED>>>` must classify as `COMPLETED`)
- [ ] All existing tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `RunOutcome`, `_classify_run`; delete `_detect_auth_failure`; update `_build_ai_prompt` and `cmd_workflow_run` |
| `tests/test_workflow.py` | Modify | Add `TestRunClassification` |

### Notes

- **Single-file constraint:** `RunOutcome` is a class of string constants in `dtl.py`, not a separate module
- **Sentinel format:** `<<<DTL:OUTCOME=NAME>>>` chosen for low collision risk — triple-bracket sentinels are unusual in code, AI narration, or test output
- **Tail-only fallback:** scan `output_lines[-50:]` not full output. Last night's bug class is impossible if the AI never narrates auth errors in its closing 50 lines
- **Backward compat:** when the sentinel is absent (AI ignored the instruction), classification falls back to tail scan — never to full-text scan
- **Bootstrapping caveat:** this feature changes the very detection that would otherwise strand it. Build via direct edit, not via `dtl workflow run` (which would false-positive on its own test patterns)

## Feature: per-feature-state

**Branch:** `feature/per-feature-state`
**Depends on:** interruption-taxonomy
**Status:** Merged
**Requires:** ai

### Goal

Move the workflow's per-feature retry budget out of an in-memory dict (`consecutive_failures` in `cmd_workflow_run`) and into a persistent per-feature state file. Adds a clean separation: DEVPLAN status is the *lifecycle* (humans plan from it); per-feature state is the *cause* (workflow recovers from it). Makes interruption-recovery decisions possible across workflow restarts.

### Acceptance Criteria

- [ ] New `_feature_state_path(project_dir, feature_name)` returns `~/.local/state/dtl/<project>/<feature>.json`
- [ ] New `_read_feature_state` and `_write_feature_state` (atomic write via tempfile + rename, mode 0o600)
- [ ] State schema: `{"last_outcome": str, "last_run_iso": str, "attempts_completed": int, "attempts_interrupted": int, "partial_work_branch": str|null}`
- [ ] `cmd_workflow_run` removes `consecutive_failures: dict[str, int]` and reads/writes per-feature state instead
- [ ] `INTERRUPTED_*` outcomes increment `attempts_interrupted`, NOT `attempts_completed` (so quota interruptions don't burn the retry budget)
- [ ] `FAILED_*` outcomes increment `attempts_completed`; after `max_failures`, feature is marked `Failed` in DEVPLAN
- [ ] `_write_failure_snapshot` is the single snapshot writer. `_write_failure_report` is deleted (it dirtied the project root with `FAILURE-REPORT.md`)
- [ ] `_watchdog_check_*` reads `<project>/<feature>.json` as primary signal where applicable; falls back to git/gh
- [ ] New `dtl workflow status --plan <plan>` subcommand shows per-feature state alongside DEVPLAN status (lifecycle vs cause)
- [ ] Tests verify: state survives a simulated process restart; `INTERRUPTED_QUOTA` does not increment `attempts_completed`; existing workflow paths work unchanged
- [ ] All existing tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add state helpers, refactor `cmd_workflow_run`, delete `_write_failure_report`, update watchdog |
| `tests/test_workflow.py` | Modify | Add `TestFeatureState` |
| `tests/test_watchdog.py` | Modify | Verify watchdog reads state file |

### Notes

- **State directory:** uses existing `_dtl_state_dir()` (dtl.py:3251). New per-feature subdirectory: `~/.local/state/dtl/<project>/`
- **Migration:** none — first read of an absent file returns the empty default
- **`partial_work_branch`:** populated on `INTERRUPTED_WALL_CLOCK` so a future feature can teach the AI to resume on its existing branch
- **Lifecycle/cause split:** DEVPLAN status remains the planning-side source of truth; per-feature state is the workflow-side source of truth. Workflow trusts DEVPLAN for lifecycle, trusts state file for cause

## Feature: provider-chain

**Branch:** `feature/provider-chain`
**Depends on:** per-feature-state
**Status:** Merged
**Requires:** ai

### Goal

Make `dtl ai run` and `dtl workflow run` aware of an ordered list of AI providers, and rotate to the next provider on `INTERRUPTED_QUOTA`. Replaces the current single-provider-per-project model. Also refreshes the stale model IDs in `AI_PROVIDERS_CONFIG` (dtl.py:239) to current versions.

### Acceptance Criteria

- [ ] `<project>/.ai/config.json` accepts a new optional `provider_chain` field: ordered list of provider names. Falls back to single `provider` if absent (backward compat)
- [ ] `cmd_workflow_run` consults `provider_chain` on `INTERRUPTED_QUOTA`: writes `last_outcome=INTERRUPTED_QUOTA`, retries the same feature with the next provider in the chain. After exhausting the chain, sleeps until quota window resets (configurable, default 3600s)
- [ ] `AI_PROVIDERS_CONFIG` model IDs updated: opus → `claude-opus-4-7`, sonnet → `claude-sonnet-4-6`, haiku → `claude-haiku-4-5-20251001`
- [ ] `ollama` gains an autonomous adapter (`supports_autonomous: True`), serving as a no-quota fallback. Uses `ollama run` in print mode against the host daemon
- [ ] `dtl ai list-providers` output shows a quota-source annotation (e.g. `[anthropic-shared]` for claude/openclaw, `[local]` for ollama)
- [ ] `dtl ai run` accepts `--provider-chain claude,ollama` to override per-call (optional)
- [ ] Tests cover: chain rotation on simulated `INTERRUPTED_QUOTA`; chain exhaustion sleep; backward compat with single-provider config
- [ ] All existing tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add ollama autonomous adapter, refactor dispatcher, refresh model IDs |
| `tests/test_workflow.py` | Modify | Add `TestProviderChain` |
| `tests/test_ai_run.py` | Modify | Verify chain rotation |

### Notes

- **`openclaw` and `claude` share the Anthropic quota** when both use `ANTHROPIC_API_KEY` from the same account. Document this in `dtl ai list-providers` so users don't pick a useless chain
- **Local Ollama is the only true no-quota fallback** today, but its `supports_autonomous` is False — this PR adds the autonomous adapter
- **Model ID drift:** the current IDs (`claude-opus-4-20250514`) are pre-4.7. Update at merge time and document the bump convention

---

## Feature: install-staleness-guard

**Branch:** `feature/install-staleness-guard`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Refuse to start (or warn loudly) when `dtl workflow *` is invoked against an installed `dtl.py` that differs from the source-of-truth repo `dtl.py`. Closes the gap that produced 2026-05-17's overnight: PR #38 (`per-feature-state`) merged at 17:18 EDT, the overnight was scheduled at 19:42 against a stale `/opt/devtools/dtl.py`, and ran code that pre-dated `_write_feature_state`. The existing `scheduled-run-freshness` ensures the child re-reads `/opt` at fire time but cannot detect that `/opt` itself is stale relative to the repo.

### Acceptance Criteria

- [ ] New helper `_check_install_freshness(schedule_mode: bool) -> None` in `dtl.py`:
  - Resolves the running script: `Path(sys.argv[0]).resolve()`
  - Resolves the source-of-truth: `Path.home() / "Projects" / "devtools" / "dtl.py"` (also `.resolve()`)
  - Returns immediately if both paths resolve to the same file (running directly from repo)
  - Returns immediately if the source-of-truth path does not exist (no repo to compare against)
  - Compares file contents by sha256 hash
  - On match: returns
  - On mismatch: if `schedule_mode=True`, prints clear error to stderr (showing both paths + the exact `sudo install.sh` command) and `sys.exit(1)`; otherwise prints a warning to stderr and returns
- [ ] Called at the top of `cmd_workflow_run` (with `schedule_mode=bool(args.schedule)`), `cmd_workflow_next`, `cmd_workflow_finish`, `cmd_workflow_list`, and `cmd_workflow_status` — always with `schedule_mode=False` except in `cmd_workflow_run`
- [ ] Called BEFORE `_preflight_auto_merge` in `cmd_workflow_run` so staleness is reported before any GitHub API call
- [ ] When `--schedule` is set and the guard passes at parent-launch time, the spawned child also runs the guard (automatic because the child re-enters `cmd_workflow_run`)
- [ ] Tests in `tests/test_workflow.py`:
  - Same content → no exception, no exit
  - Different content + `schedule_mode=False` → returns, stderr contains "stale"
  - Different content + `schedule_mode=True` → `SystemExit(1)`
  - Source-of-truth missing → returns silently
  - `sys.argv[0]` resolves to the source-of-truth path → returns silently (running from repo)
- [ ] All existing tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `_check_install_freshness`; call from all five `cmd_workflow_*` entry points |
| `tests/test_workflow.py` | Modify | New `TestInstallFreshnessGuard` class covering the five scenarios above |

### Key Decisions

- **Hash comparison, not mtime or git rev**: hashes are unambiguous and survive `cp -p`. mtimes drift; git revs assume the running script comes from a clone (not always true on the ephemeral install).
- **Hardcoded repo path** (`~/Projects/devtools/dtl.py`): matches the PM's filesystem convention documented in CLAUDE.md. A `--dev-repo` override is YAGNI for a single-user single-machine tool.
- **Asymmetric failure mode**: `--schedule` hard-bails because an autonomous overnight against stale code wastes hours; interactive runs only warn because the human is at the keyboard and can decide. Mirrors the existing `preflight_auto_merge` asymmetry.
- **Guard runs in every `workflow` subcommand**, not just `run`: `next` and `finish` also drive automation behavior that depends on current code.

### Notes

Origin: 2026-05-17 overnight reconciliation. Stale `/opt/devtools/dtl.py` (pre-PR #38) ran the workflow, producing 4 clean merges but skipping all `_write_feature_state` calls because that function did not yet exist in the installed copy. Per-feature state directory `~/.local/state/dtl/<project>/<feature>.json` was therefore never created. Complement to (not replacement for) `scheduled-run-freshness`.

---

## Feature: scaffold-shellcheck-parity

**Branch:** `feature/scaffold-shellcheck-parity`
**Depends on:** none
**Status:** Merged

### Goal

Make shellcheck behave identically in the AI dev loop and in CI for every scaffolded repo, so source-following lint failures (SC1091) can never slip through to CI and stall auto-merge. Ship a repo-root `.shellcheckrc` with `external-sources=true`, install `shellcheck` in the scaffolded `claude-code` container so the AI can lint shell locally before committing, and ensure the generated CI shellcheck step is consistent with local.

### Acceptance Criteria

- [ ] `dtl` scaffolding writes a repo-root `.shellcheckrc` containing `external-sources=true` and `source-path=SCRIPTDIR` for newly scaffolded projects
- [ ] The scaffolded inline `claude-code` Dockerfile template installs `shellcheck` (apt) so the containerized AI can run it pre-commit, matching CI
- [ ] The generated CI lint workflow's shellcheck step succeeds on a script that `source`s a sibling file via a `# shellcheck source=` directive (regression for the hub PR #8 failure)
- [ ] Backward-compatible: existing scaffolded projects are unaffected; `docs/` documents the one-line retrofit for repos already created
- [ ] A test asserts the scaffolder emits `.shellcheckrc` with `external-sources=true`
- [ ] All tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Emit `.shellcheckrc` in project scaffolding; add `shellcheck` to the inline `claude-code` Dockerfile template; align the generated CI shellcheck step |
| `tests/test_*.py` | Modify | Assert scaffolded output includes `.shellcheckrc` (external-sources=true) |

### Key Decisions

- **`.shellcheckrc` with `external-sources=true` over per-line `disable=SC1091`**: fixes the root cause repo-wide and *honors* the `# shellcheck source=` hints the AI already writes, rather than suppressing them. A lint gate only *prevents* (vs merely *catches*) when local and CI run the same tool, flags, and config.
- **Install shellcheck in the AI container**, not just CI: the host has no shellcheck, so "run lint before every commit" silently skips shell unless the container provides it.
- **Additive only** (new file + one Dockerfile line): preserves the backward-compatibility constraint; existing repos keep working and opt in by re-scaffolding or the documented one-liner.

### Notes

Origin: hub PR #8 (2026-05-20) stalled on SC1091 — CI ran `shellcheck` without `-x` while `scripts/install-*.sh` carried `# shellcheck source=bootstrap/versions.env` hints (only honored with `-x`), and shellcheck was not in the dev loop to catch it locally. This feature is the scaffolder-level prevention; retrofitting existing repos (hub, loom, morning-brief) with `.shellcheckrc` is separate per-repo cleanup.


---

## Feature: dtl-pm-install

**Branch:** `feature/dtl-pm-install`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Add a `dtl pm install` subcommand that materializes the canonical PM coordination config (`pm/`) into a workspace — wrapping the logic already in `pm/install.sh` — so a rebuilt workstation (or hub first-boot) restores the PM layer with one command.

### Acceptance Criteria

- [ ] `dtl pm install [--dry-run] [--workspace DIR]` copies `pm/` (CLAUDE.md + the `.claude` payload: PROJECTS.md, rules/, commands/, scripts/, settings.json) into the target workspace (default `~/Projects`)
- [ ] PRESERVES `.claude/settings.local.json` and `.claude/HANDOFF.md` if they already exist (never overwrite machine-local / volatile files)
- [ ] Resolves the `pm/` source whether dtl runs from `/opt/devtools` or a dev clone
- [ ] `dtl pm --help` documents the command
- [ ] Unit test installs into a tmp workspace and asserts the files land AND a pre-existing settings.local.json is preserved (real boundary, not a string check)
- [ ] All tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `pm` subcommand + `cmd_pm_install` (stdlib-only) |
| `tests/test_pm_install.py` | Create | Install-to-tmp test + preservation assertion |

### Notes

`pm/install.sh` already implements the copy/preserve logic — reimplement in stdlib Python or shell out to it. Match existing dtl subcommand patterns.

---

## Feature: ci-aggregation-gate

**Branch:** `feature/ci-aggregation-gate`
**Depends on:** none
**Status:** Merged
**Requires:** ai

### Goal

Make scaffolded CI gate merges reliably even with matrix jobs. Add a single `ci-ok` aggregation job (`needs:` all other jobs) to the generated CI workflow so branch protection can require just `ci-ok` instead of brittle per-matrix-cell contexts (the exact gap that let untested code merge on hub/devtools).

### Acceptance Criteria

- [ ] The scaffolded CI workflow template in `dtl.py` includes a final `ci-ok` job that `needs` every other job, runs with `if: always()`, and FAILS if any needed job's result is not `success`
- [ ] Scaffolded README/docs instruct requiring only `ci-ok` in branch protection
- [ ] test-templates / test-scaffold assert the generated workflow contains `ci-ok` wired to the other jobs
- [ ] Backward compatible — existing scaffolded repos unaffected
- [ ] All tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `ci-ok` gate job to the CI workflow template |
| `tests/` | Modify | Assert the gate job is generated and wired |

### Notes

Standard solution to "matrix jobs can't be required status checks." The result-check step should inspect `needs.*.result`.

---

## Feature: scaffold-security-scan

**Branch:** `feature/scaffold-security-scan`
**Depends on:** ci-aggregation-gate
**Status:** In Progress
**Requires:** ai

### Goal

Make security scanning a scaffolding default so every new repo gets baseline AppSec without manual setup — the "right checks installed at scaffold time" principle extended to security.

### Acceptance Criteria

- [ ] Scaffolded CI includes a `security-scan` job: gitleaks (secrets) + `pip-audit` (python stack) / `npm audit` (node stack)
- [ ] The `security-scan` job is wired into the `ci-ok` gate (or documented as required)
- [ ] test-templates / test-scaffold assert the security-scan job is generated for the python and node stacks
- [ ] Scaffolded docs note how to read findings and triage
- [ ] All tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `dtl.py` | Modify | Add `security-scan` job to the CI workflow template |
| `tests/` | Modify | Assert generation per stack |

### Notes

Complements `pm/weekly-review.sh` (scans existing repos); this bakes scanning into new repos from day one. devtools' own security model already references gitleaks/semgrep.
