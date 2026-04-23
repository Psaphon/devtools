<!--
  HANDOFF-BRIEF.md — session-to-session continuity artifact

  The outgoing PM produces an instance of this at the END of every session.
  The incoming PM (Claude, Codex, GPT-5, or any other agent) receives it as
  their starting state and uses it to resume work without user onboarding.

  Rules:
  - Pure markdown. No tool-specific (TodoWrite, memory/, mcp__*) references.
  - Absolute file paths only. Specific PIDs, log paths, commit SHAs.
  - The brief is a SNAPSHOT — it can go stale within hours. The incoming PM
    MUST verify key claims before acting (see "Verify before acting" below).
  - Delete this comment block when producing an instance.
-->

# PM Handoff Brief — {YYYY-MM-DD HH:MM} {timezone}

**Outgoing PM session id:** {optional — e.g., conversation hash or user label}
**Next scheduled event:** {e.g., `dtl workflow run` at 02:00 local on /home/comp/Projects/loom, or "none"}

---

## Read First (in this order)

1. `/home/comp/Projects/CLAUDE.md` — your role, workflow, rules.
2. `/home/comp/Projects/.claude/rules/gitflow.md` and `.claude/rules/security.md` — hard constraints.
3. `/home/comp/Projects/devtools/templates/PROJECTS-CONTEXT.md` — workstation specs, cross-project conventions.
4. This brief, from the top.

---

## Verify Before Acting

Any claim below with a timestamp is a snapshot. If more than a few hours have passed, verify before taking action. Minimum verification:

```bash
# What workflow processes are alive right now?
pgrep -af 'python3.*dtl.py workflow run'

# Per project: is the tree clean? any open PRs?
for p in ~/Projects/*/; do
  [ -d "$p/.git" ] || continue
  name=$(basename "$p")
  echo "=== $name ==="
  cd "$p" && git status --porcelain && git log --oneline -1
done
gh pr list --state open -R Psaphon/loom
gh pr list --state open -R Psaphon/devtools
gh pr list --state open -R Psaphon/morning-brief

# Any workflow logs grown recently?
ls -lah ~/.local/state/*.log 2>/dev/null
```

If any fact contradicts the brief, trust what you observe and flag the discrepancy to the user.

---

## Projects At A Glance

| Project | Current Branch | Tree | Open PRs | Active Workflow | Next Unblocked Feature |
|---------|----------------|------|----------|-----------------|------------------------|
| loom | {develop} | {clean/dirty} | {list #s or none} | {PID + schedule or none} | {feature-name or "none — DEVPLAN empty"} |
| devtools | | | | | |
| morning-brief | | | | | |
| {others} | | | | | |

---

## Background Processes

| PID | Command | Log path | Scheduled start | Notes |
|-----|---------|----------|-----------------|-------|
| {pid} | `dtl workflow run --projects ...` | `~/.local/state/...log` | {HH:MM or "running"} | {what it's doing} |

If there are zombie processes from previous days, **kill them before launching anything new** — they hold the git index and cause mysterious stash/checkout failures.

---

## Last Session Summary

**Session date:** {YYYY-MM-DD}
**Duration:** {rough estimate}

What happened (chronological, prose, keep under 300 words):

- {change 1}
- {change 2}

What merged (PRs):

- #{num} — {title} — {project}
- ...

What failed or got stuck:

- {item} — {why}

---

## Overnight Run Results (if applicable)

If a workflow was scheduled overnight, report its results here. If none was scheduled, delete this section.

**Started:** {HH:MM}
**Exited:** {HH:MM or still running}
**Features attempted:** {N}
**Features merged:** {N}

Per feature:
- `{feature-name}`: {merged #PR / failed at {stage} / in progress}

If anything failed, include the first 10 lines of the error from the log.

---

## Open Issues Requiring Action

Prioritize by severity. For each:

### {Critical | High | Medium | Low} — {one-line title}

**What:** {description}
**Why it matters:** {impact}
**Suggested action:** {concrete next step with command if applicable}
**Blocked on:** {user input / nothing — ready to execute}

---

## Items Awaiting User Input

Things the incoming PM should not resolve unilaterally:

- {item with enough context for user to decide}

---

## Parked / Low Priority

Mentioned here so the incoming PM doesn't re-file them:

- {item} — parked reason

---

## Immediate Next Steps For The Incoming PM

Ordered list of concrete actions. Aim for the PM to be productive within 5 minutes of reading this.

1. {Action}: `{command or file to read}`
2. {Action}: ...
3. {Action}: ...

---

## Project-Specific Notes Worth Remembering

Short, surgical facts the next PM may not derive from reading the repo:

- **{project}**: {fact, e.g., "src-layout; `tests/conftest.py` has a sys.path shim because dtl's install step was broken before PR #21"}
- ...

---

## Known Infrastructure Quirks

Ephemeral-workstation-specific or bootstrap-specific landmines:

- **PEP 668** on system Python: `pip install` needs `--break-system-packages` or a venv.
- **Ollama GPU tenancy**: stop before heavy VRAM tasks.
- **ComfyUI**: external service; loom assumes it's running but does not manage it.
- (add project-specific quirks as they emerge)

---

## Files Referenced In This Brief

So the incoming PM can pre-load context:

- `/home/comp/Projects/{project}/docs/DEVPLAN.md`
- `/home/comp/Projects/{project}/docs/FEATURE-REQUESTS.md`
- `/home/comp/Projects/devtools/dtl.py:{line-range}` — {what's there}
- {other paths}

---

## End of brief

If you (incoming PM) can answer these without re-asking the user, the brief did its job:

1. What's the single most important thing to verify first?
2. Is any workflow process running right now, and what is it doing?
3. What was the last merge, and what's the next unblocked feature?
4. Is there a user decision outstanding?

If you can't answer any of these from the brief, the outgoing PM failed — flag it and proceed with caution.
