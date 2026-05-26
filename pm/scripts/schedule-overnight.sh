#!/usr/bin/env bash
# schedule-overnight.sh — launch the overnight `dtl workflow run` as a
# systemd --user transient unit, with the PATH the workflow actually needs.
#
# Why this script exists:
#   On 2026-05-26 the overnight run failed at 02:07 with:
#       FileNotFoundError: [Errno 2] No such file or directory: 'ruff'
#   `ruff` lives in ~/.local/bin, which is added to interactive PATH via
#   ~/.profile. A systemd --user transient unit does NOT source the profile
#   and inherits only a minimal PATH (/usr/local/bin:/usr/bin:/bin). So `dtl
#   workflow finish` could find `dtl` itself but not `ruff` when it shelled
#   out to lint. The whole 9-feature queue aborted on the first finish step.
#
# Fix: bake PATH into the unit via --setenv. Also bind HOME, since some
# scripts may rely on it being set.
#
# Usage:
#   schedule-overnight.sh <HH:MM> <project1>[,project2,...] [extra dtl args...]
#
# Example:
#   schedule-overnight.sh 02:00 \
#     /home/comp/Projects/hub,/home/comp/Projects/devtools \
#     --max-failures 2
#
# The log defaults to ~/.local/state/dtl/overnight-workflow.log (outside any
# repo, per the pre-launch hygiene rule). Override with --log <path>.

set -euo pipefail

SCHEDULE="${1:-}"
PROJECTS="${2:-}"
shift 2 || true

if [[ -z "${SCHEDULE}" || -z "${PROJECTS}" ]]; then
    echo "Usage: $0 <HH:MM> <project1>[,project2,...] [extra dtl args...]" >&2
    exit 1
fi

LOG_DEFAULT="${HOME}/.local/state/dtl/overnight-workflow.log"
mkdir -p "$(dirname "${LOG_DEFAULT}")"

# If caller did not pass --log, append the default.
EXTRA_ARGS=("$@")
HAS_LOG=0
for a in "${EXTRA_ARGS[@]}"; do
    [[ "${a}" == "--log" ]] && HAS_LOG=1
done
if [[ ${HAS_LOG} -eq 0 ]]; then
    EXTRA_ARGS+=(--log "${LOG_DEFAULT}")
fi

# PATH must include ~/.local/bin (ruff, yamllint, etc.) AND the system dirs.
# Mirrors what an interactive shell would have, minus user-specific extras.
RUN_PATH="${HOME}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Zombie check — never launch over an existing workflow process.
if pgrep -af 'python3.*dtl.py workflow run' >/dev/null; then
    echo "ERROR: an existing dtl workflow run process is active." >&2
    echo "  Kill it first or wait for it to finish:" >&2
    echo "    pgrep -af 'python3.*dtl.py workflow run'" >&2
    exit 1
fi

UNIT="overnight-dev-run"
echo "INFO: Launching ${UNIT} — schedule=${SCHEDULE} projects=${PROJECTS}" >&2
echo "INFO: PATH for unit = ${RUN_PATH}" >&2
echo "INFO: Log file = ${LOG_DEFAULT}" >&2

# Drop any stale failed/loaded transient unit of the same name. systemd-run
# refuses to re-register a unit name that is still loaded, even if it exited.
# (Discovered 2026-05-26 when relaunching after a failed prior run blocked
# the new unit with "Unit ... was already loaded or has a fragment file".)
systemctl --user reset-failed "${UNIT}.service" 2>/dev/null || true

exec systemd-run --user \
    --unit="${UNIT}" \
    --description="overnight dev run (PATH-fixed launcher)" \
    --setenv="PATH=${RUN_PATH}" \
    --setenv="HOME=${HOME}" \
    /usr/local/bin/dtl workflow run \
        --projects "${PROJECTS}" \
        --schedule "${SCHEDULE}" \
        "${EXTRA_ARGS[@]}"
