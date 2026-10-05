# Ruleset templates

Import with **Settings → Rules → Rulesets → New ruleset → Import a ruleset** (one file at a time), or have the operator apply them by API. Every repo gets `protect-develop` and `protect-main`; public repos also get `public-codeql`. The templates name only generic job and branch names, so they're safe in this public repo.

**Prerequisite:** the repo's CI must end with the `ci-ok` aggregator job (`templates/ci/ci-ok-job.yml`). The rulesets require only that check.

## Why one `ci-ok` check instead of listing jobs

- **Names drift.** A required check must match a job name exactly. If you rename or split a job, the ruleset waits forever for a check that no longer exists.
- **New jobs get forgotten.** On 2026-10-05, devtools required `lint`, `test-unit` and `test-commands`, but its CI also runs `test-scaffold`, `test-ai-attach` and `test-templates`. Those three could fail and the PR still auto-merged. With `ci-ok`, a job only counts if it's in `needs`, and the one place to edit is the same file you're already changing.
- **Same template everywhere.** Every repo's checks differ (hub: shellcheck, ruff, yamllint, pytest, bats; loom: lint, test-unit), but every repo can require `ci-ok`.
- **`skipped` must fail.** A plain `contains(needs.*.result, 'failure')` check (atrade's version before this) passes when a job is skipped, so a mis-scoped `if:` could merge untested code. The template requires `success` from every job.

## What each rule does, and what was left out

| Rule | develop | main | Why |
|---|---|---|---|
| Restrict deletions | ✓ | ✓ | Shared branches can't vanish |
| Block force pushes | ✓ | ✓ | History can't be rewritten |
| Require a pull request, 0 approvals | ✓ | ✓ | No direct pushes, even by an admin token. **0 approvals** because a solo operator can't approve their own PR, and any approval requirement would block auto-merge entirely |
| Allowed merge methods | squash | merge, squash | develop gets one commit per feature; releases into main may use a merge commit |
| Require linear history | ✓ | — | Matches squash-only; main may carry release merge commits |
| Required status check `ci-ok`, strict, app = GitHub Actions (15368) | ✓ | ✓ | Pinned to Actions so no other token can post a fake green status. Strict means the PR must be up to date (see the caveat below) |
| Code scanning (CodeQL, high+ security alerts or errors) | public | public | Free on public repos only; private repos need a paid GitHub Code Security licence |

**Deliberately not used:**
- **Signed commits:** the AI sandbox commits unsigned, so every PR would break.
- **Code owner review and required reviewers:** solo operator, and required reviewers need teams.
- **Merge queue:** it would fix the strict-mode stall, but it isn't available for user-owned repos.
- **Deployments:** none to gate.
- **Secret-scanning merge gate:** paid on private repos. Public repos get push protection as a repo setting instead (Settings → Code security). gitleaks in CI covers private repos.

**Push rules** (restrict file paths, extensions or size, e.g. blocking `*.pem`, `.env` and files over 10 MB) are a separate ruleset type. They may not be offered on user-owned private repos. Try importing one before relying on it; gitleaks in CI is the guaranteed layer.

**Strict-mode caveat:** auto-merge never updates a branch that's behind. When two PRs are open, the second one sits "behind" until something runs `gh pr update-branch` (or a newer commit is pushed to it). The PM and dtl handle this. Turning strict off is the alternative, at the cost of merging untested combinations.

## Bypass

There are no bypass actors. On a user-owned repo, GitHub Actions can't be a bypass actor (the API rejects it). In an emergency, the operator temporarily sets the ruleset's enforcement to *Disabled*.

## Order for a new repo

1. Bootstrap push of `main` and `develop` (empty repo; `repo-bootstrap-push`).
2. Add CI with `ci-ok`, and let it run once.
3. Import `protect-develop` and `protect-main` (plus `public-codeql` and push protection for public repos).

Importing before step 1 would block the bootstrap push. Importing before step 2 would block every PR until `ci-ok` exists.
