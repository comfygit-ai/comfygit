"""Startup script generator for RunPod deployments.

Generates bash scripts that set up ComfyGit environments on RunPod pods
using the cg CLI commands.
"""

import re
import secrets
from datetime import datetime


def generate_deployment_id(env_name: str) -> str:
    """Generate a unique deployment ID.

    Format: deploy-{sanitized_env_name}-{YYYYMMDD}-{HHMMSS}-{random}

    Args:
        env_name: Source environment name

    Returns:
        Unique deployment identifier
    """
    # Sanitize env name: replace special chars with dashes, collapse multiple dashes
    sanitized = re.sub(r"[^a-zA-Z0-9-]", "-", env_name)
    sanitized = re.sub(r"-+", "-", sanitized).strip("-").lower()
    if not sanitized:
        sanitized = "env"

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    random_suffix = secrets.token_hex(2)  # 4 hex chars

    return f"deploy-{sanitized}-{timestamp}-{random_suffix}"


def generate_startup_script(
    deployment_id: str,
    import_source: str,
    branch: str | None = None,
    comfyui_port: int = 8188,
) -> str:
    """Generate the pod startup script for ComfyGit environment setup.

    This script runs on the RunPod pod and:
    1. Sets up COMFYGIT_HOME environment variable
    2. Initializes workspace with cg init --yes
    3. Imports environment with cg import --yes --name {deployment_id}
    4. Starts ComfyUI with cg -e {deployment_id} run --listen 0.0.0.0

    Args:
        deployment_id: Unique identifier for this deployment
        import_source: Git URL or local path for cg import
        branch: Optional git branch/tag for import
        comfyui_port: Port for ComfyUI (default 8188)

    Returns:
        Bash script string
    """
    # Build branch flag if specified
    branch_flag = f" -b {branch}" if branch else ""

    return f'''#!/bin/bash
set -e

# =============================================================================
# ComfyGit Deployment Startup Script
# Deployment ID: {deployment_id}
# =============================================================================

# Status tracking
STATUS_FILE="/workspace/.comfygit_deploy_status.json"
START_TIME=$(date -Iseconds)

update_status() {{
    local phase="$1"
    local detail="$2"
    local progress="$3"
    cat > "$STATUS_FILE" << EOF
{{
    "deployment_id": "{deployment_id}",
    "phase": "$phase",
    "phase_detail": "$detail",
    "progress_percent": $progress,
    "started_at": "$START_TIME",
    "error": null
}}
EOF
}}

set_error() {{
    local message="$1"
    cat > "$STATUS_FILE" << EOF
{{
    "deployment_id": "{deployment_id}",
    "phase": "ERROR",
    "phase_detail": "$message",
    "progress_percent": 0,
    "started_at": "$START_TIME",
    "error": "$message"
}}
EOF
    echo "ERROR: $message" >&2
    exit 1
}}

# Ensure workspace directory exists
mkdir -p /workspace

# =============================================================================
# Phase: INITIALIZING
# =============================================================================
update_status "INITIALIZING" "Setting up environment..." 5

# Set ComfyGit home directory
export COMFYGIT_HOME=/workspace/comfygit
export PATH="$HOME/.local/bin:$PATH"

update_status "INITIALIZING" "Installing uv package manager..." 10

# Install uv if not present (default RunPod template doesn't include it)
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh || set_error "Failed to install uv"
fi

# Source uv's env file to ensure PATH is configured correctly
source "$HOME/.local/bin/env" 2>/dev/null || true
export PATH="$HOME/.local/bin:$PATH"

update_status "INITIALIZING" "Installing ComfyGit CLI..." 12

# Install comfygit CLI via uv
if ! command -v cg &> /dev/null; then
    uv tool install comfygit || set_error "Failed to install comfygit CLI"
fi

# Verify cg is available after installation (catch PATH issues early)
command -v cg &> /dev/null || set_error "cg command not found after installation - check PATH"

# =============================================================================
# Phase: WORKSPACE_INIT
# =============================================================================
update_status "WORKSPACE_INIT" "Initializing ComfyGit workspace..." 15

# Initialize workspace (idempotent - fails gracefully if exists)
mkdir -p "$COMFYGIT_HOME"
cd "$COMFYGIT_HOME"
cg init --yes "$COMFYGIT_HOME" 2>/dev/null || true

# =============================================================================
# Phase: ENVIRONMENT_CHECK (handles restart vs fresh deploy)
# =============================================================================
ENV_PATH="$COMFYGIT_HOME/environments/{deployment_id}"

if [ -d "$ENV_PATH" ] && [ -d "$ENV_PATH/ComfyUI" ]; then
    # Restart case: environment already exists from previous run
    update_status "RESTARTING" "Environment exists, skipping import..." 60
    echo "Detected existing environment: {deployment_id}"
    echo "   Skipping import, proceeding to start ComfyUI..."
    cg use {deployment_id} 2>/dev/null || true
else
    # Fresh deploy: import the environment
    update_status "IMPORTING" "Preparing import source..." 25

    IMPORT_SOURCE="{import_source}"

    update_status "IMPORTING" "Importing environment {deployment_id}..." 30

    # Import the environment (--models all downloads all models with sources)
    cd "$COMFYGIT_HOME"
    cg import "$IMPORT_SOURCE"{branch_flag} --name {deployment_id} --yes --use --models all || set_error "Failed to import environment"

    update_status "IMPORTING" "Environment imported successfully" 60
fi

# =============================================================================
# Phase: STARTING_COMFYUI
# =============================================================================
update_status "STARTING_COMFYUI" "Starting ComfyUI server..." 80

# Start ComfyUI with the imported environment
cd "$COMFYGIT_HOME"
nohup cg -e {deployment_id} run --listen 0.0.0.0 --port {comfyui_port} > /workspace/comfyui.log 2>&1 &
COMFYUI_PID=$!

# Wait for ComfyUI to start (check port)
update_status "STARTING_COMFYUI" "Waiting for ComfyUI to become ready..." 90

for i in {{1..120}}; do
    if curl -s http://localhost:{comfyui_port} > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

if ! curl -s http://localhost:{comfyui_port} > /dev/null 2>&1; then
    set_error "ComfyUI failed to start within 4 minutes. Check /workspace/comfyui.log"
fi

# =============================================================================
# Phase: READY
# =============================================================================
update_status "READY" "ComfyUI is running" 100

echo "=== Deployment Complete ==="
echo "Deployment ID: {deployment_id}"
echo "ComfyUI is running at http://localhost:{comfyui_port}"

# Keep the script running (RunPod terminates if script exits)
tail -f /workspace/comfyui.log
'''
