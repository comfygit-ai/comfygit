#!/bin/bash
# =============================================================================
# QA Container Entrypoint
# Runs as qa user, uses sudo for privileged operations
#
# Setup order:
# 1. Create workspace directory on shared volume
# 2. Configure UV cache on shared volume
# 3. Install local comfygit if mounted
# 4. Setup Claude auth
# =============================================================================

set -e

AGENT_ID="${AGENT_ID:-dev}"
echo "=== QA Agent $AGENT_ID starting ==="

# =============================================================================
# Shared Volume Setup
# Creates per-agent workspace and shared UV cache directories
# =============================================================================
WORKSPACE_DIR="/shared/workspace-$AGENT_ID"
UV_CACHE="/shared/uv_cache"

echo "Setting up shared volume directories..."
sudo mkdir -p "$WORKSPACE_DIR" "$UV_CACHE"
sudo chown -R qa:qa "$WORKSPACE_DIR" "$UV_CACHE"
echo "  Workspace: $WORKSPACE_DIR"
echo "  UV cache: $UV_CACHE"

# =============================================================================
# Local ComfyGit Installation
# Auto-install from /comfygit mount if present (editable mode)
# Uses shared UV cache for fast dependency resolution across agents
# =============================================================================
COMFYGIT_MOUNT="/comfygit"
INSTALL_MARKER="/shared/.installed-$AGENT_ID"

if [ -d "$COMFYGIT_MOUNT/packages/core" ] && [ -d "$COMFYGIT_MOUNT/packages/cli" ]; then
    # Check if we need to reinstall (marker missing or source changed)
    CORE_PYPROJECT="$COMFYGIT_MOUNT/packages/core/pyproject.toml"
    if [ ! -f "$INSTALL_MARKER" ] || [ "$CORE_PYPROJECT" -nt "$INSTALL_MARKER" ]; then
        echo "Installing local comfygit (editable mode)..."
        # Install core first, then CLI (CLI depends on core)
        sudo uv pip install --system -e "$COMFYGIT_MOUNT/packages/core" 2>&1 | tail -3
        sudo uv pip install --system -e "$COMFYGIT_MOUNT/packages/cli" 2>&1 | tail -3
        sudo touch "$INSTALL_MARKER"
        sudo chown qa:qa "$INSTALL_MARKER"
        echo "Local comfygit installed: $(cg --version 2>/dev/null || echo 'version check failed')"
    else
        echo "Local comfygit already installed (use /qa/install-local.sh to reinstall)"
    fi
else
    echo "Using PyPI comfygit (no local mount at $COMFYGIT_MOUNT)"
fi

# =============================================================================
# Claude Auth Setup
# Credentials mounted at /mnt/claude-credentials.json (read-only)
# Copy to ~/.claude/.credentials.json for Claude CLI to use
# =============================================================================
CLAUDE_DIR="/home/qa/.claude"
CREDS_MOUNT="/mnt/claude-credentials.json"
CREDS_TARGET="$CLAUDE_DIR/.credentials.json"

mkdir -p "$CLAUDE_DIR"

if [ -f "$CREDS_MOUNT" ]; then
    cp "$CREDS_MOUNT" "$CREDS_TARGET"
    chmod 600 "$CREDS_TARGET"
    echo "Claude auth: credentials copied from mount"
elif [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "Claude auth: using API key"
else
    echo "Warning: No Claude auth configured"
fi

# =============================================================================
# Skip Claude onboarding (GH issue #4714 workaround)
# Claude requires ~/.claude.json with hasCompletedOnboarding=true to skip
# the interactive onboarding flow, separate from ~/.claude/.credentials.json
# =============================================================================
CLAUDE_JSON="/home/qa/.claude.json"
if [ -f "$CLAUDE_JSON" ]; then
    python3 -c "
import json
with open('$CLAUDE_JSON', 'r') as f:
    data = json.load(f)
if not data.get('hasCompletedOnboarding'):
    data['hasCompletedOnboarding'] = True
    with open('$CLAUDE_JSON', 'w') as f:
        json.dump(data, f, indent=2)
    print('Claude: marked onboarding complete')
"
else
    echo '{"hasCompletedOnboarding": true}' > "$CLAUDE_JSON"
    echo "Claude: created .claude.json with onboarding complete"
fi

# Ensure reports directory is writable
sudo chown -R qa:qa /reports 2>/dev/null || true

echo "=== QA Agent $AGENT_ID ready ==="

# Execute the command (or default to keeping container alive)
exec "$@"
