---
description: Discovery — active projects' git/PR/CI state + pending features + one recommended next action
---

Run the discovery loop (see `.claude/rules/autonomy.md`). Scope to **active**
projects only — read their paths from the machine-readable block in
`/home/comp/Projects/.claude/PROJECTS.md` (do NOT sweep parked/archived/stub/dormant).

For each active project:
1. Branch + dirty count (`git -C <path> status --porcelain`, `branch --show-current`).
2. Open PRs (`gh pr list -R Psaphon/<name> --state open`).
3. Latest develop CI conclusion (`gh run list -R Psaphon/<name> --branch develop -L 1`).
4. Next `Not Started` feature in `docs/DEVPLAN.md` whose deps are `Merged` and
   `Requires:` includes `ai` (`[HUMAN]` criteria don't disqualify the AI build).

Reply watch-friendly:
- A compact table: `Project | Branch | Dirty | Open PR | CI | Next feature`.
- Then **one** line: the single recommended next action and the command to fire it
  (`go` to execute it, or `kickoff <project>`, or `schedule tonight`).

Flag anything off-pattern (dirty tree that isn't a known placeholder, red CI, a PR
aging > 2 days, an at-risk project from the registry) in one line at the top.
