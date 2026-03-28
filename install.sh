#!/bin/bash
#===============================================================================
# Dev Tools Component Installer
#===============================================================================
# Deploys dev environment launcher.
# Called by post-install.sh during autoinstall or standalone for updates.
#
# Usage:
#   sudo ./install.sh              # deploy to running system
#   sudo ./install.sh /target      # deploy to chroot (during autoinstall)
#===============================================================================

set -euo pipefail

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"
PREFIX="${TARGET}"

#--- Deploy dtl ---
mkdir -p "${PREFIX}/opt/devtools"
cp "$COMPONENT_DIR/dtl.py" "${PREFIX}/opt/devtools/"
chmod +x "${PREFIX}/opt/devtools/dtl.py"
ln -sf /opt/devtools/dtl.py "${PREFIX}/usr/local/bin/dtl"

#--- Link env from SECRETS partition (autoinstall only) ---
SECRETS_ENV="/media/secrets/devtools/env"
CONFIG_DIR="${PREFIX}/home/${SUDO_USER:-$USER}/.config/dtl"
CONFIG_ENV="${CONFIG_DIR}/env"

mkdir -p "$CONFIG_DIR"

if [ -f "$SECRETS_ENV" ]; then
    ln -sf "$SECRETS_ENV" "$CONFIG_ENV"
elif [ -n "$TARGET" ]; then
    # Only create template during autoinstall (chroot target provided)
    mkdir -p "$(dirname "$SECRETS_ENV")"
    cat > "$SECRETS_ENV" << 'ENVEOF'
# Dev Tools Environment — persists across OS rebuilds
# Claude Code uses OAuth (claude login), no API key needed.
GIT_AUTHOR_NAME=
GIT_AUTHOR_EMAIL=
ENVEOF
    chmod 600 "$SECRETS_ENV"
    ln -sf "$SECRETS_ENV" "$CONFIG_ENV"
fi

# Fix ownership (install.sh runs as sudo)
if [ -n "${SUDO_USER:-}" ]; then
    chown -R "$SUDO_USER:$SUDO_USER" "$CONFIG_DIR"
fi

echo "[devtools] installed"
