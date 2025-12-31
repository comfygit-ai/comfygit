# ComfyGit QA Testing System

Agent-based QA testing using Claude to explore and find bugs in ComfyGit.

## Quick Start

```bash
cd qa

# Build the container (first time only)
docker compose build

# Start the container
docker compose up -d

# Connect interactively
docker compose exec qa bash

# Or run Claude directly
docker compose exec qa claude
```

**Note**: The container runs as the `qa` user (non-root) for security.

## Setup Modes

### Direct Host (Default)

If running Docker directly on your machine (not Docker-in-Docker):

```bash
cd qa
docker compose up -d
```

Default configuration:
- Claude auth: `~/.claude/.credentials.json` mounted (credentials only)
- ComfyGit repo: parent directory (`..`)
- Reports: `./reports`

### Docker-in-Docker (ACFS)

If running from inside another container (like ACFS):

```bash
cd qa
cp .env.example .env
# Edit .env with HOST paths (not container paths)
docker compose up -d
```

**Key insight**: In DinD, volume paths must be from the HOST's perspective, not the container's. Find your host dev path:

```bash
docker inspect acfs-dev | grep '"Source".*dev"'
```

Example `.env` for ACFS:
```bash
CLAUDE_CREDS_PATH=/var/lib/docker/volumes/acfs-setup_claude-auth/_data/.credentials.json
COMFYGIT_PATH=/home/youruser/dev/projects/comfygit-ai/comfygit
```

## Using Local ComfyGit Code

The container installs comfygit from PyPI by default. To test local changes:

```bash
docker compose exec qa bash
sudo uv pip install --system /comfygit/packages/core /comfygit/packages/cli
cg --version  # Verify local version
```

## Running Scenarios

### Native Mode (No Claude API)

Runs commands directly without Claude - good for testing scenario syntax:

```bash
docker compose exec qa python /qa/scripts/run_scenario.py --native /qa/scenarios/01_basic_workspace_setup.yaml
```

### Claude Agent Mode

Full AI-powered testing:

```bash
docker compose exec qa python /qa/scripts/run_scenario.py /qa/scenarios/01_basic_workspace_setup.yaml
```

Options:
- `--model haiku|sonnet|opus` - Choose model (default: sonnet)
- `--timeout N` - Timeout in minutes (default: 30)
- `--dry-run` - Show what would execute
- `--validate` - Validate scenario YAML only

## Writing Scenarios

Scenarios are YAML files in `scenarios/`. Structure:

```yaml
name: My Test Scenario
description: What this tests
category: workspace|workflow|node|model|collaboration|export
priority: critical|high|medium|low

setup:
  - command: rm -rf /workspace/*
    description: Clean workspace
    ignore_errors: true

steps:
  - action: Create environment
    command: cg env create production
    expect: Environment created successfully
    on_failure: investigate|skip|abort|document
    timeout: 300
    verify:
      - "ls -la /workspace/.comfygit/environments/"

  - action: Explore edge cases
    explore: |
      Try variations: spaces in names, existing directories, etc.

cleanup:
  - command: rm -rf /workspace/*
    ignore_errors: true
```

## Key Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Container configuration |
| `.env` | Local path overrides (gitignored) |
| `.env.example` | Template for .env |
| `Dockerfile` | Container image definition |
| `scenarios/*.yaml` | Test scenarios |
| `agent_instructions/` | Claude agent prompts |
| `scripts/run_scenario.py` | Scenario orchestrator |
| `scripts/schema.py` | Pydantic models for validation |
| `reports/` | Generated test reports |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_CREDS_PATH` | `~/.claude/.credentials.json` | Path to credentials file |
| `COMFYGIT_PATH` | `..` | Path to comfygit repo |
| `QA_REPORTS_PATH` | `./reports` | Report output directory |
| `QA_SCENARIOS_PATH` | `./scenarios` | Scenarios directory |
| `ANTHROPIC_API_KEY` | - | Alternative to OAuth auth |

## Troubleshooting

### "No Claude auth configured"

Either:
1. Set `CLAUDE_CREDS_PATH` to path of `.credentials.json` file
2. Set `ANTHROPIC_API_KEY` environment variable
3. For ACFS: Ensure `claude-auth` volume exists and is seeded

### Mounts show wrong/empty content (DinD)

Paths in `.env` must be HOST paths, not container paths. Use:
```bash
docker inspect acfs-dev | grep '"Source"'
```

### Container can't write reports

Ensure `QA_REPORTS_PATH` points to a writable directory on the host.

## Claude Auth Sharing (ACFS)

The ACFS setup includes a shared `claude-auth` volume:

1. ACFS container symlinks `~/.claude/.credentials.json` to the volume
2. QA container mounts the volume and copies credentials on startup
3. OAuth tokens refresh in ACFS, QA inherits automatically

To manually seed the volume:
```bash
docker run --rm \
  -v acfs-setup_acfs-home:/source:ro \
  -v acfs-setup_claude-auth:/dest \
  alpine cp /source/.claude/.credentials.json /dest/
```
