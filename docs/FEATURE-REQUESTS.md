# Devtools Feature Requests

Cross-cutting dtl improvements surfaced during other projects' planning. Each entry notes origin and date.

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

**Problem.** PLANNING-GUIDE.md assumes every feature produces testable code. Media pipelines, asset-curation work, config-heavy projects don't fit.

**Proposal.** Add section: "Non-code features are legitimate. Acceptance criteria can be 'produces expected artifact' rather than 'tests pass.' Features that curate assets (workflow JSONs, prompts, sample inputs) should be explicitly called out."

### 5. Optional Assets table in DEVPLAN template

**Problem.** Features that produce non-code artifacts (ComfyUI workflow JSONs, prompt templates, reference images) don't fit the "Files to Create or Modify" code-centric table cleanly.

**Proposal.** Add an optional `### Assets` section alongside `### Files to Create or Modify` for features with non-code deliverables.

### 6. Better loop-break semantics for AI developer

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

**Problem.** In `dtl.py` around line 3129, `any_work_done = True` is set **before** the dirty-tree check at 3137. If the only project in the run has a dirty tree, the inner `for` loop skips (with `continue`), but `any_work_done` was already flipped to True. The outer `while True` (line 3376) therefore never hits its `break`, and re-enters immediately with no sleep. Over 6 days this generated an 18GB log of `[loom] Working tree is dirty — skipping.`

**Fix options.**
- Set `any_work_done = True` **only** after passing all skip gates (dirty tree, branch create, etc.)
- Or: add a floor sleep (e.g. `time.sleep(60)`) at the bottom of the outer `while True` loop regardless of work state
- Or: count dirty-tree skips into `consecutive_failures` so the project drops out after N iterations

**Severity.** High. Turns a setup mistake (in-repo log file) into disk pressure and process death, with no progress for days.

### 10. Dirty-tree skip is invisible (UX bug)

**Problem.** When the loop skips a project for a dirty tree, the only signal is one log line. The feature stays `Not Started`, no PR is opened, no CI runs — everything looks normal from the outside. The user has no way to know work isn't happening without tailing the log.

**Fix.** On dirty-tree skip:
- Emit a structured "stalled" state somewhere visible (e.g. `.workflow-state.json` in the project root, or stderr write)
- Optionally: after N consecutive dirty-tree skips, send a push notification (reuse `.ai/notify.py`)
- Consider: run `git stash -u` automatically on dirty tree, run the feature, restore after — risky but makes the loop more resilient

### 11. `dtl workflow run` should document log placement

**Problem.** The command has no `--log` flag and no documented default. Users (and PMs!) default to writing a log inside the project directory with `nohup … > .workflow-run.log`, which **creates the exact dirty-tree condition that stalls the loop**. A self-hosting footgun.

**Fix.**
- Default log to `~/.local/state/dtl/<project>-workflow.log` (XDG-compliant)
- Or: add `--log PATH` flag
- Or at minimum: document in `--help` that logs must not be written into any project under `--projects`

### 12. `dtl ai attach` validator should require CI workflow, not just warn

**Problem.** Validator reports `[!!] CI workflow exists` but proceeds. Without CI, `gh pr merge --auto --squash` has nothing to gate on; the loop stalls at "waiting for merge." Load-bearing, not cosmetic.

**Fix.** Either: (a) scaffold a standard ruff+pytest `ci.yml` when missing, or (b) fail `ai attach` hard if CI is missing and `--no-ci` wasn't passed.
