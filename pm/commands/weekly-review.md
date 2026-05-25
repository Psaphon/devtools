---
description: Run the weekly security + productivity review and reply with the digest
---

Run the weekly review (see `.claude/rules/weekly-review.md`):

```
bash /home/comp/Projects/.claude/scripts/weekly-review.sh
```

The script is read-only, scopes to active projects (from PROJECTS.md), and saves
the full digest to `~/.local/state/pm/weekly-review-YYYY-MM-DD.md`.

Reply watch-friendly:
- Headline: any ⚠️ security findings first (tracked secrets, audit hits), else "clean".
- One line of productivity signal (merges/wk, any aging PRs or red CI).
- If a scanner was skipped (not installed), note it once and point to the install
  step in `rules/weekly-review.md`.
- Turn real findings into `fix/`/`chore/` work or DEVPLAN entries — don't just report.
