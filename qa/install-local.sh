#!/bin/bash
# =============================================================================
# Reinstall local comfygit from /comfygit mount
# Run this after making changes to comfygit source code
# =============================================================================

set -e

COMFYGIT_MOUNT="/comfygit"
AGENT_ID="${AGENT_ID:-dev}"
INSTALL_MARKER="/shared/.installed-$AGENT_ID"

if [ ! -d "$COMFYGIT_MOUNT/packages/core" ] || [ ! -d "$COMFYGIT_MOUNT/packages/cli" ]; then
    echo "Error: ComfyGit not mounted at $COMFYGIT_MOUNT"
    echo "Ensure COMFYGIT_PATH is set in docker-compose or .env"
    exit 1
fi

echo "Reinstalling local comfygit..."
sudo uv pip install --system -e "$COMFYGIT_MOUNT/packages/core"
sudo uv pip install --system -e "$COMFYGIT_MOUNT/packages/cli"

# Update marker
sudo touch "$INSTALL_MARKER"
sudo chown qa:qa "$INSTALL_MARKER"

echo "Done. Version: $(cg --version)"
