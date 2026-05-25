# Weekly Security & Productivity Review

A standing weekly check across **active** projects (see PROJECTS.md). Based on
DORA delivery metrics + layered application-security scanning (the conventional
"continuous automated scanning, weekly digest, deeper quarterly audit" model).

Run it with the `review` command → executes
`/home/comp/Projects/.claude/scripts/weekly-review.sh` and replies with the digest.
The script is read-only and degrades gracefully when a scanner isn't installed.

## Cadence

- **Weekly** (automated, ~Sunday before the Pro reset): run the script, skim the
  digest, file follow-ups as `fix/` or `chore/` work or DEVPLAN entries.
- **Quarterly** (deeper, manual): full gitleaks history scan across all branches,
  dependency CVE triage + bumps, branch-protection drift review, token/key rotation,
  SECRETS USB integrity check.

## Productivity (DORA-adapted, per active repo, last 7d)

| DORA metric | Proxy used here |
|---|---|
| Deployment frequency | PRs merged / week |
| Lead time for changes | age of oldest open PR (open→merge) |
| Change failure rate | red CI conclusion rate on develop |
| MTTR | time from red CI to next green (eyeball from `gh run list`) |

Watch for: PRs aging > a few days, repeated red CI (flaky or green-but-blind),
zero throughput on a repo that should be moving.

## Security (layered)

1. **Secrets** — tracked `.env`/`secrets/`/`*.pem`/`*.key`/`id_rsa` (templates
   excluded); `gitleaks` working-tree scan if installed.
2. **Dependencies (SCA)** — `pip-audit` for Python repos, `npm audit` for Node.
3. **SAST** — `ruff` already gates in CI; `bandit`/`semgrep` add depth if installed.
4. **Branch protection** — confirm required checks still include the test jobs
   (`gh api repos/{r}/branches/{br}/protection/required_status_checks`).

## Strengthen the review (install once; bake into hub setup)

The scanners are optional and the script notes when they're missing. To make the
review fully effective, install (no sudo needed for these):

```
pip install --user pip-audit bandit semgrep
# gitleaks: download the static binary from its GitHub releases to ~/.local/bin
```

On the ephemeral workstation these are lost on rebuild — the durable home for them
is hub's tooling install (`scripts/install-*` / a security-tools step), so add them
there rather than relying on the dev box.

## Output

Digest goes to stdout and `~/.local/state/pm/weekly-review-YYYY-MM-DD.md`. Keep the
chat reply to the headline + any ⚠️ lines; the file holds the full table.
