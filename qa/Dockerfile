# QA Testing Container for Agent-Based Testing
# Extends base ComfyGit image with Claude CLI for AI-driven testing

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install system dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        nodejs \
        npm && \
    rm -rf /var/lib/apt/lists/*

# Install Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# Create workspace directories
RUN mkdir -p /workspace /qa /reports

# Set up working directory
WORKDIR /workspace

# Copy QA testing materials
COPY agent_instructions/ /qa/agent_instructions/
COPY scenarios/ /qa/scenarios/
COPY scripts/ /qa/scripts/

# Install comfygit from PyPI (or local for dev)
ARG COMFYGIT_VERSION=latest
ARG INSTALL_LOCAL=false

# Copy local packages if building with local install
COPY --chown=root:root packages/ /tmp/packages/

RUN if [ "$INSTALL_LOCAL" = "true" ]; then \
        uv pip install --system /tmp/packages/core /tmp/packages/cli && \
        rm -rf /tmp/packages; \
    else \
        uv pip install --system comfygit; \
    fi

# Verify installation
RUN cg --version

# Environment setup
ENV COMFYGIT_HOME=/workspace
ENV QA_SCENARIOS=/qa/scenarios
ENV QA_INSTRUCTIONS=/qa/agent_instructions
ENV QA_REPORTS=/reports

# Default command: run the QA orchestrator
ENTRYPOINT ["python", "/qa/scripts/run_scenario.py"]
CMD ["--help"]
