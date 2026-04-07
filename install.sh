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

#--- Link SSH keys from SECRETS partition ---
SECRETS_SSH="/media/secrets/ssh"
USER_SSH="${PREFIX}/home/${SUDO_USER:-$USER}/.ssh"

if [ -d "$SECRETS_SSH" ]; then
    mkdir -p "$USER_SSH"
    chmod 700 "$USER_SSH"
    for key in "$SECRETS_SSH"/id_*; do
        [ -f "$key" ] || continue
        cp "$key" "$USER_SSH/"
        chmod 600 "$USER_SSH/$(basename "$key")"
    done
    # Make public keys readable
    for pub in "$USER_SSH"/*.pub; do
        [ -f "$pub" ] && chmod 644 "$pub"
    done
    # Pre-trust GitHub so SSH never prompts
    if ! grep -q "github.com" "$USER_SSH/known_hosts" 2>/dev/null; then
        ssh-keyscan -t ed25519 github.com >> "$USER_SSH/known_hosts" 2>/dev/null
    fi
fi

# Fix ownership (install.sh runs as sudo)
if [ -n "${SUDO_USER:-}" ]; then
    chown -R "$SUDO_USER:$SUDO_USER" "$CONFIG_DIR"
    [ -d "$USER_SSH" ] && chown -R "$SUDO_USER:$SUDO_USER" "$USER_SSH"
fi

echo "[devtools] installed"
