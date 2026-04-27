<!--
  HANDOFF-BRIEF.md — session-to-session continuity artifact.

  The outgoing PM produces an instance of this at the end of each session.
  The incoming PM reads it FIRST, runs Verify Before Acting, then proceeds.

  Rules for writing one:
  - Lead with the lead. The TL;DR section is the only thing that's guaranteed
    to be read in full. Bury nothing important after it.
  - Pure markdown. No tool-specific (TodoWrite, memory/, mcp__*) references.
  - Absolute file paths only. Specific PIDs, log paths, commit SHAs.
  - Prefer cutting to padding. Anything derivable from `git log`, the current
    repo state, or CLAUDE.md does NOT belong here. Brief is a delta + snapshot.
  - "Awaiting User Decision" is a separate section by design — items there
    must NEVER appear in "Action Items", because the next PM will execute them.
  - Delete this comment block when producing an instance.
-->

# PM Handoff Brief — {YYYY-MM-DD HH:MM} {timezone}

## TL;DR

{1-3 lines. The single most important fact + the most urgent action (if any). If something failed overnight, lead with that. If everything is healthy and idle, say so.}

---

## Verify Before Acting

The brief goes stale fast. Run these and reconcile against the rest of the document. If anything contradicts, trust what you observe.

```bash
pgrep -af 'python3.*dtl.py workflow run' || echo "no workflow processes"
for p in ~/Projects/*/; do [ -d "$p/.git" ] || continue; n=$(basename "$p"); cd "$p"
  echo "=== $n ==="; git status --porcelain; echo "branch: $(git branch --show-current)"; git log --oneline -1
done
for r in Psaphon/loom Psaphon/devtools Psaphon/morning-brief; do
  echo "=== $r ==="; gh pr list -R "$r" --state open
done
ls -lah ~/.local/state/*.log 2>/dev/null
systemctl --user list-timers --no-pager | grep -E 'dtl|NEXT'
```

---

## Status

| Project | Branch | Tree | Open PRs | Next Unblocked Feature |
|---------|--------|------|----------|------------------------|
| loom | {develop} | {clean} | {none / #N} | {feature-name or "—"} |
| devtools | | | | |
| morning-brief | | | | |

---

## Background Processes

If none, say "None scheduled" and skip the table.

| PID | Command | Log path | Fires at | Notes |
|-----|---------|----------|----------|-------|
| {pid} | `dtl workflow run --projects ...` | `~/.local/state/...log` | {HH:MM} | {what it's doing} |

Watchdog: {`active` / `not installed`}. Next fire: {HH:MM, from `systemctl --user list-timers`}.

---

## Action Items

Ordered by priority. Each item must be executable without asking the user.

### Critical — {one-line title}
**What:** {description, 1-2 sentences}
**Why:** {impact}
**Do:** {concrete command or steps}

### High — {one-line title}
{...}

### Medium — {one-line title}
{...}

(If no action items, write "None — handoff is informational only.")

---

## Awaiting User Decision

Items the next PM must NOT execute. Each must give the user enough context to decide.

- {item with options A/B/C and tradeoffs} — {context}

(If none, write "None.")

---

## Notes

Surgical facts the next PM may not derive from the repo. Skip anything that's already in `CLAUDE.md` or a project's `CLAUDE.md`.

- **{project}**: {non-obvious fact, e.g., "src-layout; conftest.py has a sys.path shim — don't delete"}
- **Infra**: {e.g., "PEP 668 system Python — pip needs --break-system-packages"}

---

<!--
  Self-test before handing this off: can the incoming PM answer these from
  the brief alone, without re-asking the user?
    1. What's the single most important verify-first fact?
    2. Is anything running right now?
    3. Last merge, next unblocked feature, per project?
    4. Any user decision outstanding?
  If you can't answer all four from your own brief, fix it before posting.
-->
