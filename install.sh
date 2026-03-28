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

log() { echo "[devtools] $1"; }

#--- Dev environment launcher ---
log "Deploying dev environment launcher..."
mkdir -p "${PREFIX}/opt/devtools"
cp "$COMPONENT_DIR/dtl.py" "${PREFIX}/opt/devtools/"
chmod +x "${PREFIX}/opt/devtools/dtl.py"

# Create symlink for easy CLI access
ln -sf /opt/devtools/dtl.py "${PREFIX}/usr/local/bin/dtl"

#--- Environment file for API keys ---
SECRETS_ENV="/media/secrets/devtools/env"
CONFIG_DIR="${PREFIX}/home/${SUDO_USER:-$USER}/.config/dtl"
CONFIG_ENV="${CONFIG_DIR}/env"

mkdir -p "$CONFIG_DIR"

if [ -f "$SECRETS_ENV" ]; then
    log "Linking env file from SECRETS partition..."
    ln -sf "$SECRETS_ENV" "$CONFIG_ENV"
elif [ ! -f "$CONFIG_ENV" ]; then
    log "Creating template env file on SECRETS partition..."
    mkdir -p "$(dirname "$SECRETS_ENV")"
    cat > "$SECRETS_ENV" << 'ENVEOF'
# Dev Tools API Keys — fill in your values
# This file lives on the SECRETS partition and persists across OS rebuilds
# Permissions should be 600 (owner read/write only)
ANTHROPIC_API_KEY=
GIT_AUTHOR_NAME=
GIT_AUTHOR_EMAIL=
# Optional service keys
DTL_BOT_TOKEN=
DTL_BOT_CHAT_ID=
ENVEOF
    chmod 600 "$SECRETS_ENV"
    ln -sf "$SECRETS_ENV" "$CONFIG_ENV"
    log "WARNING: Fill in your API keys at $SECRETS_ENV"
fi

# Fix ownership (install.sh runs as sudo)
if [ -n "${SUDO_USER:-}" ]; then
    chown -R "$SUDO_USER:$SUDO_USER" "$CONFIG_DIR"
fi

log "Dev tools component deployed"
