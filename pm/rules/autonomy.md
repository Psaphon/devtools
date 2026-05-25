# Autonomous Operation & Watch Supervision

The PM runs the multi-project workflow with minimal input. The user supervises
asynchronously — often from an Apple Watch over SSH, reading short messages and
replying by voice-text or a button tap. Optimize for that: **decide and act on
your own where it's safe; ask only when a choice genuinely needs the human, and
make that choice a tap.**

## What the PM does WITHOUT asking (green-light)

These are pre-authorized. Just do them and report tersely.

- Run discovery (`/status`) and build the prioritized worklist.
- Create `feature/*`, `fix/*`, `chore/*`, `docs/*` branches off `develop`.
- Write/refine AI prompt files; run `dtl ai run` directly (PM is the developer).
- Review delegated AI output against the **real boundary** (clean venv, on-disk
  scaffold, actual CLI exit code) — never trust "tests passed" self-reports.
- Fix bugs/test/CI defects found in review; commit; `git push` feature branches.
- `gh pr create --base develop`; `gh pr merge --auto --squash`.
- Reconcile DEVPLAN statuses to reality (chore PR).
- Audit/fix CI required-checks; keep them complete (tests must gate, not just run).
- Remove re-downloadable build artifacts and `node_modules` (reversible).
- Update memory, this file, PROJECTS.md, and CLAUDE.md.
- Schedule overnight `dtl workflow run` on eligible repos (see decision below).

## What needs the human (confirm-first — make it a tap)

- Anything destructive/irreversible: deleting a whole project clone, force-push,
  history rewrite, deleting GitHub repos, dropping data.
- Releases to `main` (production gate) — the user decides when to cut a release.
- Branch-protection / governance changes (already reviewed once; re-confirm new ones).
- Enabling a real overnight render/timer that consumes the GPU or spends money
  (e.g. loom go-live with real media; raising the Claude API spend cap).
- Anything touching secrets or the SECRETS USB.
- `sudo` — never run it; hand the exact command to the user via `! <cmd>`.

When confirming, present **2–4 options, recommended first**, each answerable with
one tap. Keep the question to one screen.

## Discovery loop (start every session with this)

1. Read `/home/comp/Projects/.claude/PROJECTS.md` → the **active** project paths.
2. For each active project: branch/dirty state, open PRs, latest CI conclusion,
   and DEVPLAN `Not Started` features (with deps + `Requires:`).
   - The `/status` skill does this; prefer it over ad-hoc commands.
3. Produce one prioritized worklist: unblocked AI-ready features, failing CI,
   stale PRs, then a single recommended next action.
4. Only consider features whose deps are `Merged` and `Requires:` includes `ai`.
   Treat `[HUMAN]` acceptance criteria as non-blocking for the AI build (the code
   ships; the human criteria are tracked separately).

## Decision: run NOW vs SCHEDULE overnight

**Run now** (`dtl ai run`, PM reviews the same session) when:
- It unblocks other work, is a fix/hotfix, or is security/risk-sensitive.
- It's the first feature in a new area (establish patterns under supervision).
- The user is present and wants to see it land.

**Schedule overnight** (`dtl workflow run --schedule HH:MM`, unattended auto-merge) when:
- There's a queue of well-specified, independent, `Requires: ai`, low-risk
  Not-Started features on a repo whose **required CI checks include real tests**
  (verify: `gh api repos/{r}/branches/develop/protection/required_status_checks`).
- The user is away (async/watch supervision).
- Off-peak electricity + Pro-usage budget favor batching (target ~14%/day, ~02:00).

**Do not schedule** when: the repo's tests don't gate merges, the next features
are risky/cross-boundary, or they need heavy PM review. Those run now, supervised.

Cost frame: off-peak electricity, $5–10/week, use the weekly Pro allowance; prefer
one overnight batch over many daytime one-offs.

## Watch-supervision message style

- **Lead with the headline**, then ≤3 short lines. The first line must stand alone.
- End actionable turns with **the single next command** the user can fire
  (e.g. `go`, `status`, `schedule tonight`, `review`, `handoff`).
- Put detail in files (PR bodies, HANDOFF.md), not long chat blocks. No giant
  code dumps to a watch screen.
- Decisions → tappable options, recommended first.

## Simple commands the user can fire (and what the PM does)

| User says | PM does |
|---|---|
| `status` | Run discovery; reply with worklist + one recommended next action |
| `go` / `proceed` | Execute the top recommended action end-to-end, report result |
| `kickoff <project>` | Prep + run the next AI feature for that project |
| `schedule tonight` | Set up the overnight `dtl workflow run` (after pre-launch hygiene) |
| `weekly-review` | Run the weekly security/productivity review; reply with the digest |
| `handoff` | Write `/home/comp/Projects/.claude/HANDOFF.md` |

## Pre-launch hygiene before any `dtl workflow run` (non-negotiable)

1. No zombie workflow: `pgrep -af 'python3.*dtl.py workflow run'` → kill stale.
2. Target repos on `develop`, clean trees, synced with origin.
3. DEVPLAN statuses accurate (merged features show `Merged`).
4. Log path OUTSIDE any repo (default `~/.local/state/dtl/<proj>-workflow.log`).
5. Required CI checks include the test jobs (else auto-merge is blind).
