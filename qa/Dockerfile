# QA Testing Container for Agent-Based Testing
# Extends base ComfyGit image with Claude CLI for AI-driven testing
#
# Runs as non-root 'qa' user for security (similar to ACFS 'ubuntu' user pattern)

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        nodejs \
        npm \
        bash \
        procps \
        sudo && \
    rm -rf /var/lib/apt/lists/*

# =============================================================================
# Create QA User (non-root, similar to ACFS ubuntu user pattern)
# =============================================================================
RUN useradd -m -s /bin/bash -u 1000 qa && \
    echo "qa ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/qa && \
    chmod 0440 /etc/sudoers.d/qa

# Install Claude CLI (as root, globally available)
RUN npm install -g @anthropic-ai/claude-code

# Create workspace directories with correct ownership
RUN mkdir -p /workspace /qa /reports && \
    chown -R qa:qa /workspace /reports

# Copy QA testing materials (paths relative to build context which is repo root)
COPY --chown=qa:qa qa/agent_instructions/ /qa/agent_instructions/
COPY --chown=qa:qa qa/scenarios/ /qa/scenarios/
COPY --chown=qa:qa qa/scripts/ /qa/scripts/

# Install Python dependencies for QA runner (system-wide)
RUN uv pip install --system pydantic pyyaml

# Install comfygit from PyPI (system-wide)
# For local development, mount the repo and run: uv pip install --system /comfygit/packages/core /comfygit/packages/cli
RUN uv pip install --system comfygit

# Verify installation
RUN cg --version

# =============================================================================
# User Environment Setup
# =============================================================================
ENV HOME=/home/qa
ENV USER=qa
ENV COMFYGIT_HOME=/workspace
ENV QA_SCENARIOS=/qa/scenarios
ENV QA_INSTRUCTIONS=/qa/agent_instructions
ENV QA_REPORTS=/reports

# Create user directories
RUN mkdir -p /home/qa/.claude /home/qa/.config && \
    chown -R qa:qa /home/qa

# Copy entrypoint script and make executable
COPY qa/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

# Switch to qa user
USER qa
WORKDIR /workspace

# Entrypoint handles auth setup, then runs command
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "/qa/scripts/run_scenario.py", "--help"]
