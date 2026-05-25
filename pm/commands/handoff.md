---
description: Write the session handoff brief to ~/Projects/.claude/HANDOFF.md
---

Update `/home/comp/Projects/.claude/HANDOFF.md` with a fresh PM handoff brief.

This replaces the manual copy-paste handoff workflow. The next PM session in `~/Projects` will auto-load this file via the `SessionStart` hook in `~/Projects/.claude/settings.json`.

## Steps

1. Run snapshot commands (in parallel via separate Bash tool calls) and capture output:
   - `pgrep -af 'python3.*dtl.py workflow run'` — running workflow processes
   - For each `~/Projects/*/` git repo: `git status --porcelain`, `git branch --show-current`, `git log --oneline -1`
   - `gh pr list -R <repo> --state open` for `Psaphon/loom`, `Psaphon/devtools`, `Psaphon/morning-brief`, `Psaphon/Prompt-Fishing`
   - `ls -lah ~/.local/state/*.log 2>/dev/null`
   - `systemctl --user list-timers --no-pager | grep -E 'dtl|NEXT'`

2. Draft the brief following the shape in `/home/comp/Projects/devtools/templates/HANDOFF-BRIEF.md`. Required sections in order: TL;DR, Verify Before Acting, Status (table), Background Processes, Action Items, Awaiting User Decision, Notes.

3. Use the `Write` tool to overwrite `/home/comp/Projects/.claude/HANDOFF.md` with the new brief. Do NOT print the brief to chat — the file is the deliverable.

4. After write, confirm with a one-line message: `Handoff written: /home/comp/Projects/.claude/HANDOFF.md (<byte count>)`.

## Rules

- **Absolute paths only** — never `~`. The next PM may run from any cwd.
- **Include PIDs and log paths** for any background process left running.
- **"Awaiting User Decision" items must NEVER appear in "Action Items"** — the next PM will execute Action Items unattended.
- **Brief is delta + snapshot.** Anything derivable from `git log`, current repo state, or any `CLAUDE.md` does NOT belong here.
- **Convert relative dates to absolute** — "tonight" → `2026-04-27 02:00 EDT`. The brief outlives short-term context.
- **Lead with the lead.** TL;DR is the only section guaranteed to be read in full. Bury nothing important after it.
- **Lead with the single next command** the user can fire from a watch (e.g. `status`, `go`). State it explicitly in the TL;DR.
- **Scope to active projects** from `.claude/PROJECTS.md` — don't sweep parked/archived/stub dirs.
- **Any background process you leave running gets its own section** with the systemd unit / PID, log path, when it fires, and what to review when it finishes.
- **No tool-specific references** — no TodoWrite, MCP, memory/, slash command names. The next PM may be a different agent.

## Self-test before writing

Can the incoming PM answer these from the brief alone, without re-asking the user?
1. What's the single most important verify-first fact?
2. Is anything running right now?
3. Last merge, next unblocked feature, per project?
4. Any user decision outstanding?

If you can't answer all four from the brief you're about to write, fix it before calling Write.
