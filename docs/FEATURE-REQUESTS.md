# Devtools Feature Requests

Cross-cutting dtl improvements surfaced during other projects' planning. Each entry notes origin and date.

Items here are **backlog** — ideas, open problems, or explicitly parked work. When an item is concrete enough to spec (branch name, acceptance criteria, files), it gets **promoted** to `DEVPLAN.md` and built by `dtl workflow run`. Promoted items keep a stub here for traceability.

---

## Captured 2026-04-12 — from loom planning

### 1. `dtl schedule` — GPU-tenant handoff primitive

**Problem.** Multiple projects want the GPU. Currently coordinated ad-hoc (loom's systemd unit stops Ollama). Needs a general primitive.

**Proposal.** `dtl schedule` defines named time-boxed GPU tenant windows. Projects register against tenants. dtl handles service stop/start at window boundaries.

Example: `dtl schedule add --tenant loom --window 00:00-05:30 --requires gpu --conflicts-with ollama`

### 2. `dtl service` — managed external services

**Problem.** ComfyUI (and future services) need install, start, stop, health-check, version-pin. Currently manual.

**Proposal.** `dtl service install comfyui` / `dtl service start comfyui`, integrated with `dtl schedule` for VRAM-awareness. Service definitions could live in usb-autoinstall so they persist across weekly rebuilds.

### 3. Hardware section in PROJECTS-CONTEXT.md

**Status: Promoted to DEVPLAN 2026-04-21** (bundled into `planning-templates-refresh`).

**Problem.** Planning sessions don't know workstation specs. Burns time asking.

**Proposal.** Add a standing Hardware section to PROJECTS-CONTEXT.md template:

- GPU model + VRAM
- System RAM
- CPU
- Storage type + free space
- Network: ISP bandwidth, Tailscale mesh, remote access (Terminus SSH from phone)
- GPU tenants + current schedule

Brainstormer reads this before making stack suggestions. The user's current config: RTX 2060 6GB VRAM, 32GB RAM, Tailscale, Terminus SSH from iPhone.

### 4. Planning guide addendum — non-code projects

**Status: Promoted to DEVPLAN 2026-04-21** (bundled into `planning-templates-refresh`).

**Problem.** PLANNING-GUIDE.md assumes every feature produces testable code. Media pipelines, asset-curation work, config-heavy projects don't fit.

**Proposal.** Add section: "Non-code features are legitimate. Acceptance criteria can be 'produces expected artifact' rather than 'tests pass.' Features that curate assets (workflow JSONs, prompts, sample inputs) should be explicitly called out."

### 5. Optional Assets table in DEVPLAN template

**Status: Promoted to DEVPLAN 2026-04-21** (bundled into `planning-templates-refresh`).

**Problem.** Features that produce non-code artifacts (ComfyUI workflow JSONs, prompt templates, reference images) don't fit the "Files to Create or Modify" code-centric table cleanly.

**Proposal.** Add an optional `### Assets` section alongside `### Files to Create or Modify` for features with non-code deliverables.

### 6. Better loop-break semantics for AI developer

**Status: Promoted to DEVPLAN 2026-04-21** as `ai-dev-loop-break`.

**Problem.** AI developer can loop for hours retrying a broken command. The user called this out as a major pain point.

**Proposal.** dtl wraps AI-dev invocations with:
- Max retries per acceptance criterion
- Max wall-clock time per feature
- Clear "stuck, exiting" state that saves progress and doesn't resume automatically
- Structured failure report the user can triage

### 7. Revisit planning artifact pattern (parked)

See separate meta parking-lot note. Current DEVPLAN-as-monolith may not be the optimal primitive. Feature-requests-as-first-class-objects, per-project backlogs, or roadmap-plus-tickets splits worth researching. Don't solve now; revisit after 2–3 more projects ship.

### 8. Brainstormer ↔ PM ↔ AI-dev communication (parked)

See separate meta parking-lot note. One-way forward handoff breaks when plans hit reality. Don't solve now.

---

## Captured 2026-04-21 — from loom post-mortem (6-day silent stall)

### 9. `workflow run` spin-loops when every project has dirty tree (BUG)

**Status: Promoted to DEVPLAN 2026-04-21** as `fix-workflow-spin-loop`.

**Problem.** In `dtl.py` around line 3129, `any_work_done = True` is set **before** the dirty-tree check at 3137. If the only project in the run has a dirty tree, the inner `for` loop skips (with `continue`), but `any_work_done` was already flipped to True. The outer `while True` (line 3376) therefore never hits its `break`, and re-enters immediately with no sleep. Over 6 days this generated an 18GB log of `[loom] Working tree is dirty — skipping.`

**Fix options.**
- Set `any_work_done = True` **only** after passing all skip gates (dirty tree, branch create, etc.)
- Or: add a floor sleep (e.g. `time.sleep(60)`) at the bottom of the outer `while True` loop regardless of work state
- Or: count dirty-tree skips into `consecutive_failures` so the project drops out after N iterations

**Severity.** High. Turns a setup mistake (in-repo log file) into disk pressure and process death, with no progress for days.

### 10. Dirty-tree skip is invisible (UX bug)

**Status: Promoted to DEVPLAN 2026-04-21** as `workflow-stall-visibility`.

**Problem.** When the loop skips a project for a dirty tree, the only signal is one log line. The feature stays `Not Started`, no PR is opened, no CI runs — everything looks normal from the outside. The user has no way to know work isn't happening without tailing the log.

**Fix.** On dirty-tree skip:
- Emit a structured "stalled" state somewhere visible (e.g. `.workflow-state.json` in the project root, or stderr write)
- Optionally: after N consecutive dirty-tree skips, send a push notification (reuse `.ai/notify.py`)
- Consider: run `git stash -u` automatically on dirty tree, run the feature, restore after — risky but makes the loop more resilient

### 11. `dtl workflow run` should document log placement

**Status: Promoted to DEVPLAN 2026-04-21** as `workflow-log-defaults`.

**Problem.** The command has no `--log` flag and no documented default. Users (and PMs!) default to writing a log inside the project directory with `nohup … > .workflow-run.log`, which **creates the exact dirty-tree condition that stalls the loop**. A self-hosting footgun.

**Fix.**
- Default log to `~/.local/state/dtl/<project>-workflow.log` (XDG-compliant)
- Or: add `--log PATH` flag
- Or at minimum: document in `--help` that logs must not be written into any project under `--projects`

### 12. `dtl ai attach` validator should require CI workflow, not just warn

**Status: Promoted to DEVPLAN 2026-04-21** as `require-ci-workflow`.

**Problem.** Validator reports `[!!] CI workflow exists` but proceeds. Without CI, `gh pr merge --auto --squash` has nothing to gate on; the loop stalls at "waiting for merge." Load-bearing, not cosmetic.

**Fix.** Either: (a) scaffold a standard ruff+pytest `ci.yml` when missing, or (b) fail `ai attach` hard if CI is missing and `--no-ci` wasn't passed.

---

## Captured 2026-04-21 — from PM/watchdog discussion

### 13. Cross-project workflow watchdog

**Status: Promoted to DEVPLAN 2026-04-21** as `workflow-watchdog`.

**Problem.** The PM cannot autonomously check on overnight workflow runs between sessions. Silent stalls (like loom's 6-day one) go undetected for days unless the user tails logs manually.

**Proposal.** `dtl watchdog install` scaffolds a user systemd timer that runs `dtl watchdog check` every N hours, detects anomalies (dead process, dirty tree, PR silence, log growth), and notifies via each project's `.ai/notify.py`. Free, runs locally, complements the in-loop stall-visibility feature.

---

## Captured 2026-04-21 — from morning-brief AI session debugging

### 14. `dtl ai run` Docker mode uses `--print` flag, preventing tool use (BUG)

**Severity: Critical.** Blocks all Docker-mode autonomous AI development.

**Problem.** In `dtl.py` line ~1882, the Docker-mode `ai_run()` passes `"--print"` to the Claude Code container. `claude --print -p` is "print mode" — it returns a single text response without tool use (no file editing, no bash commands, no commits). This makes autonomous coding impossible. The AI receives the prompt, responds conversationally, and exits without doing any work.

**Root cause.** Line 1874-1886 in `dtl.py`:
```python
cmd = [
    "docker", "compose", "-f", str(compose_file),
    "run", "--rm", "claude-code",
    "--print",  # <-- THIS IS THE BUG
]
cmd.extend(["-p", prompt])
```

**Fix.** Remove `"--print"` from the command list. The correct invocation is `claude -p "prompt"` (not `claude --print -p "prompt"`). The `--print` flag was likely confused with `-p` (which enables prompt/headless mode with full tool use).

**Impact.** Every `dtl ai run` call in Docker mode across all projects has been silently failing — the AI "runs" but produces zero code changes. This was the root cause of morning-brief's `balanced-summarization` being marked Failed with no commits.

### 15. `dtl ai run` Docker mode mangles long/multiline prompts (BUG)

**Severity: High.** Causes silent prompt truncation.

**Problem.** In `dtl.py` line ~1886, the prompt is passed as a CLI argument: `cmd.extend(["-p", prompt])`. When the prompt is a full AI_PROMPT markdown file (4KB+), it gets truncated or mangled passing through `subprocess.run()` → Docker CLI → container. The output shows only the first ~5 lines of the prompt with no Claude Code execution.

**Root cause.** Shell argument length limits and special character expansion across the subprocess → Docker → container boundary. Markdown prompts contain `#`, `*`, backticks, newlines, and code fences that interact badly with shell parsing.

**Fix options.**
1. **File mount (recommended):** Write the prompt to a temp file, mount it into the container with `-v`, and read it inside: `claude -p "$(cat /tmp/prompt.md)"`. Requires overriding the entrypoint to `sh -c` since the default entrypoint is `claude`.
2. **Stdin pipe:** Pipe the prompt via stdin instead of CLI args. Requires removing `stdin=subprocess.DEVNULL` (line 1891).
3. **Both fixes applied in `run.sh`:** The VM-mode `run.sh` template should also be updated.

**Workaround tested.** Modified `morning-brief/.ai/run.sh` with temp file + entrypoint override approach — prompt arrived intact (4196 bytes verified inside container). But this doesn't help because Docker-mode `dtl ai run` bypasses `run.sh` entirely (it calls `docker compose run` directly).

**Note.** The `run.sh` template generated by `dtl ai attach` also has the `--print` bug (line ~1403 in `dtl.py`). Both the inline Docker path and the template need fixing.

---

## Captured 2026-04-22 — from loom night 1 post-mortem

### 16. `dtl workflow finish` does not install project deps before pytest (BUG)

**Status: Promoted to DEVPLAN 2026-04-22** as `workflow-install-deps-before-test`.

**Severity: High.** Blocks any Python project with a src-layout `pyproject.toml` (i.e. any modern Python project) from passing the local test gate.

**Problem.** In `dtl.py:3394-3401` (`_run_lint_and_tests`), the Python branch is:

```python
if (project_dir / "pyproject.toml").exists():
    lint_cmd = ["ruff", "check", "."]
    test_cmd = ["pytest", "--tb=short"]
```

No `pip install -e ".[dev]"` step. Two failure modes for a src-layout project:
1. `ModuleNotFoundError` — tests import the package, but `src/<pkg>/` is not on sys.path and no editable install was performed.
2. `ModuleNotFoundError` for declared deps (numpy, httpx, librosa, etc.) — listed in `pyproject.toml` but never installed.

**Observed impact (loom night 1).** scaffold feature failed with `ModuleNotFoundError: No module named 'loom'` despite a correct `src/loom/` layout. song-analysis WIP failed with `ModuleNotFoundError: No module named 'numpy'`. Both were caught by the test gate and never committed. Combined with the pre-fix spin-loop bug, loom produced 0 merged features on night 1.

**Fix.** Before invoking pytest when `pyproject.toml` exists, run `pip install -e ".[dev]"` (fall back to `pip install -e .` if the `dev` extra is missing). Should be quiet on cache-hit second runs — pip is idempotent. Consider keeping a `--no-install` escape hatch for CI or sandboxed runs.

**CI is unaffected.** The scaffolded `.github/workflows/ci.yml` already does `pip install -e ".[dev]"` before pytest, so the PR CI passes. The local dtl gate is the only place this bites.

---

## Captured 2026-04-23 — from loom night 2 post-mortem

### 17. `pip install -e` in `_run_lint_and_tests` hits PEP 668 on system Python (BUG)

**Severity: High.** The fix from #16 (PR #21) unblocks one failure mode but introduces another on Debian/Ubuntu system Python (PEP 668 "externally-managed environment"). Loom night 2: 0/9 features merged, same gate failure on the *install* step instead of the *test* step.

**Problem.** PR #21 added `pip install -e ".[dev]" --quiet` at `dtl.py:3415`. On Ubuntu 25.10 (the workstation's stock image), `/usr/bin/pip` is marked externally-managed per PEP 668 and refuses installs into system site-packages without a flag. pip exits non-zero, `_run_lint_and_tests` returns failed, the gate rejects the AI's (correct) commit.

**Observed.** Loom song-analysis AI committed `40b9237` locally — code is fine. Then the gate hit:

```
error: externally-managed-environment
× This environment is externally managed
hint: See PEP 668 for the detailed specification.
```

No push, no PR, status ended at "Done" locally but never became "Merged". (Clean exit — the spin-loop fix from #9 did its job and the workflow did not loop.)

**Fix options.**
1. **`--break-system-packages`** — add the flag to both `pip install -e ".[dev]"` and the `.` fallback. Safe on this ephemeral weekly-rebuild workstation; system Python is disposable. Smallest diff.
2. **Per-project venv** — create `.dtl-venv/` at project root on first run, use its `python -m pip install` and `python -m pytest`. More correct, but heavier — also slower on first run and needs cleanup hooks.
3. **Detect and combine** — try the plain command first; if it fails with "externally-managed-environment" in stderr, retry with `--break-system-packages`. Gives compatibility across hosts.

Recommend option 1 given the ephemeral-workstation constraint. Revisit if dtl ever ships to a long-lived host.

**Bootstrap note.** This is the second iteration of a self-hosting fix. Each time we add capability to the gate, we discover an environment assumption baked into the tool. Keep a short list of "environment assumptions the gate makes" near this code so future fixes don't regress.
