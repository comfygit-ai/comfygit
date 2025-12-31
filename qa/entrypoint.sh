#!/bin/bash
# =============================================================================
# QA Container Entrypoint
# Runs as qa user, uses sudo for privileged operations
# =============================================================================

set -e

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
    # Update existing file to ensure onboarding is marked complete
    python3 -c "
import json
with open('$CLAUDE_JSON', 'r') as f:
    data = json.load(f)
if not data.get('hasCompletedOnboarding'):
    data['hasCompletedOnboarding'] = True
    with open('$CLAUDE_JSON', 'w') as f:
        json.dump(data, f, indent=2)
    print('Claude: marked onboarding complete in existing .claude.json')
else:
    print('Claude: onboarding already marked complete')
"
else
    # Create minimal .claude.json to skip onboarding
    echo '{"hasCompletedOnboarding": true}' > "$CLAUDE_JSON"
    echo "Claude: created .claude.json with onboarding complete"
fi

# Ensure workspace is owned by qa user
sudo chown -R qa:qa /workspace /reports 2>/dev/null || true

# Execute the command (or default to keeping container alive)
exec "$@"
