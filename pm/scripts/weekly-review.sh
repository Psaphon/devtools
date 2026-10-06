#!/usr/bin/env bash
# weekly-review.sh — Weekly security + productivity review across active projects.
#
# Produces a terse, watch-readable digest. Degrades gracefully: uses a security
# tool if it's installed, notes it as skipped if not. Read-only — never changes
# repos. Active projects are read from PROJECTS.md (single source of truth).
#
# Usage: bash ~/Projects/.claude/scripts/weekly-review.sh [--days N]
# Output: stdout + ~/.local/state/pm/weekly-review-YYYY-MM-DD.md
#
# Cadence (see rules/weekly-review.md): run weekly. The deeper items (full
# gitleaks history scan, dependency CVE triage) are quarterly — flagged below.

set -uo pipefail

DAYS=7
[[ "${1:-}" == "--days" && -n "${2:-}" ]] && DAYS="$2"

PROJECTS_MD="/home/comp/Projects/.claude/PROJECTS.md"
OWNER="Psaphon"
SINCE=$(date -u -d "-${DAYS} days" +%Y-%m-%d)
OUT_DIR="${HOME}/.local/state/pm"
OUT_FILE="${OUT_DIR}/weekly-review-$(date +%Y-%m-%d).md"
mkdir -p "${OUT_DIR}"

# Active project paths come from the fenced block in PROJECTS.md.
mapfile -t ACTIVE < <(grep -E '^/home/comp/Projects/[a-zA-Z0-9_-]+$' "${PROJECTS_MD}" 2>/dev/null)

have() { command -v "$1" >/dev/null 2>&1; }

{
  echo "# Weekly Review — $(date +%Y-%m-%d) (last ${DAYS}d)"
  echo

  echo "## Productivity (DORA-adapted)"
  echo "| Project | Merged | Open PRs (oldest) | Last CI |"
  echo "|---|---|---|---|"
  for p in "${ACTIVE[@]}"; do
    name=$(basename "$p"); repo="${OWNER}/${name}"
    merged=$(gh pr list -R "$repo" --state merged --search "merged:>=${SINCE}" --json number -q 'length' 2>/dev/null || echo "?")
    openct=$(gh pr list -R "$repo" --state open --json number -q 'length' 2>/dev/null || echo "?")
    oldest=$(gh pr list -R "$repo" --state open --json createdAt -q 'min_by(.createdAt)?.createdAt // "-"' 2>/dev/null | cut -dT -f1)
    ci=$(gh run list -R "$repo" --branch develop -L 1 --json conclusion -q '.[0].conclusion // "none"' 2>/dev/null)
    printf '| %s | %s | %s (%s) | %s |\n' "$name" "$merged" "${openct:-?}" "${oldest:--}" "$ci"
  done
  echo
  echo "_Deployment frequency ≈ merges/wk; lead time ≈ open-PR age; change-fail ≈ red CI._"
  echo

  echo "## Security"
  echo "Tooling present: gitleaks=$(have gitleaks && echo y || echo n)" \
       "pip-audit=$(have pip-audit && echo y || echo n)" \
       "npm=$(have npm && echo y || echo n)" \
       "bandit=$(have bandit && echo y || echo n)" \
       "semgrep=$(have semgrep && echo y || echo n)"
  echo
  for p in "${ACTIVE[@]}"; do
    [[ -d "$p/.git" ]] || continue
    name=$(basename "$p")
    echo "### ${name}"
    # 1. Secrets accidentally tracked (always cheap, always run)
    tracked=$(git -C "$p" ls-files 2>/dev/null | grep -EI '(^|/)\.env($|\.)|(^|/)secrets/|\.pem$|\.key$|id_rsa' | grep -vEi '\.(example|sample|template|dist)$' || true)
    if [[ -n "$tracked" ]]; then
      echo "- ⚠️ tracked secret-like files:"
      while IFS= read -r _l; do echo "    ${_l}"; done <<< "$tracked"
    else echo "- secrets: none tracked ✓"; fi
    # 2. Secret scan (gitleaks if present)
    if have gitleaks; then
      if gitleaks detect --source "$p" --no-banner -r /tmp/gl-"$name".json >/dev/null 2>&1; then echo "- gitleaks: clean ✓"; else echo "- ⚠️ gitleaks: findings (see /tmp/gl-${name}.json)"; fi
    fi
    # 3. Dependency audit (best-effort)
    if [[ -f "$p/pyproject.toml" || -f "$p/requirements.txt" ]] && have pip-audit; then
      pa=$(cd "$p" && pip-audit -q 2>/dev/null | tail -1 || echo "pip-audit error"); echo "- pip-audit: ${pa:-no issues}"
    fi
    if [[ -f "$p/package.json" ]] && have npm; then
      vuln=$(cd "$p" && npm audit --omit=dev 2>/dev/null | grep -E 'vulnerabilit' | head -1 || echo "n/a"); echo "- npm audit: ${vuln}"
    fi
  done
  echo
  echo "## Required follow-ups (quarterly, deeper)"
  echo "- Full gitleaks history scan across all branches (not just working tree)."
  echo "- Dependency CVE triage + bump; review GitHub branch-protection drift."
  echo "- Rotate any long-lived tokens/keys; confirm SECRETS USB integrity."
} | tee "${OUT_FILE}"

echo
echo "Saved: ${OUT_FILE}"
