# QA Testing Container for Agent-Based Testing
# Extends base ComfyGit image with Claude CLI for AI-driven testing

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
        procps && \
    rm -rf /var/lib/apt/lists/*

# Install Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# Create workspace directories
RUN mkdir -p /workspace /qa /reports

# Set up working directory
WORKDIR /workspace

# Copy QA testing materials (paths relative to build context which is repo root)
COPY qa/agent_instructions/ /qa/agent_instructions/
COPY qa/scenarios/ /qa/scenarios/
COPY qa/scripts/ /qa/scripts/

# Install Python dependencies for QA runner
RUN uv pip install --system pydantic pyyaml

# Install comfygit from PyPI (base image)
# For local development, mount the repo and run: uv pip install --system /comfygit/packages/core /comfygit/packages/cli
RUN uv pip install --system comfygit

# Verify installation
RUN cg --version

# Environment setup
ENV COMFYGIT_HOME=/workspace
ENV QA_SCENARIOS=/qa/scenarios
ENV QA_INSTRUCTIONS=/qa/agent_instructions
ENV QA_REPORTS=/reports
ENV HOME=/root

# Create claude config directory (will be overridden by mount if provided)
RUN mkdir -p /root/.claude

# Default command: run the QA orchestrator
ENTRYPOINT ["python", "/qa/scripts/run_scenario.py"]
CMD ["--help"]
