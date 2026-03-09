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

log "Dev tools component deployed"
