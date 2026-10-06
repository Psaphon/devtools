#!/usr/bin/env bash
# install.sh — Materialize the canonical PM config into the ~/Projects workspace.
#
# devtools/pm/ is the version-controlled source of truth for the project-manager
# coordination layer (CLAUDE.md + .claude/ rules, commands, registry, scripts,
# permission baseline). This installs it onto an ephemeral workstation so the PM
# survives the weekly rebuild. Run from hub first-boot or by hand after a rebuild.
#
# Preserves machine-local / volatile files that do NOT belong in git:
#   - <workspace>/.claude/settings.local.json   (machine-specific allow-list)
#   - <workspace>/.claude/HANDOFF.md            (regenerated each session)
#
# Usage: bash devtools/pm/install.sh [--dry-run]
# Env:   PM_WORKSPACE  target workspace dir (default: /home/comp/Projects)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PM_WORKSPACE="${PM_WORKSPACE:-/home/comp/Projects}"
DRY_RUN=false
for arg in "$@"; do
    case "${arg}" in
        --dry-run) DRY_RUN=true ;;
        *) printf 'ERROR: unknown argument: %s\n' "${arg}" >&2; exit 1 ;;
    esac
done

log()  { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
run()  { if [[ "${DRY_RUN}" == true ]]; then log "[dry-run] $*"; else "$@"; fi; }

CLAUDE_DIR="${PM_WORKSPACE}/.claude"
log "Installing PM config from ${SCRIPT_DIR} into ${PM_WORKSPACE}"

run mkdir -p "${CLAUDE_DIR}/rules" "${CLAUDE_DIR}/commands" "${CLAUDE_DIR}/scripts"

# Coordinator doc at the workspace root.
run cp "${SCRIPT_DIR}/CLAUDE.md" "${PM_WORKSPACE}/CLAUDE.md"

# Versioned .claude payload (settings.local.json + HANDOFF.md are NOT shipped).
run cp "${SCRIPT_DIR}/settings.json" "${CLAUDE_DIR}/settings.json"
run cp "${SCRIPT_DIR}/PROJECTS.md"   "${CLAUDE_DIR}/PROJECTS.md"
for d in rules commands scripts; do
    for f in "${SCRIPT_DIR}/${d}"/*; do
        [[ -e "${f}" ]] || continue
        run cp "${f}" "${CLAUDE_DIR}/${d}/$(basename "${f}")"
    done
done
for f in "${CLAUDE_DIR}/scripts/"*.sh; do
    [[ -e "${f}" ]] || continue
    run chmod +x "${f}"
done

log "Done. Preserved (if present): ${CLAUDE_DIR}/settings.local.json, ${CLAUDE_DIR}/HANDOFF.md"
