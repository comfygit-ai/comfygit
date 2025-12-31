# ComfyGit Agent-Based QA Testing

Automated QA testing using Claude agents to explore and find bugs in ComfyGit.

## Philosophy

Traditional tests are great for regression but don't find new bugs. Agent-based testing combines:
- **Structured scenarios** - Defined test flows with expected outcomes
- **Exploratory testing** - Agents find edge cases humans miss
- **Detailed reporting** - Every command and output documented in JSON + markdown

## Quick Start

### 1. Build the QA container

```bash
cd qa
docker build -t comfygit-qa .
```

### 2. Validate scenarios (no API key needed)

```bash
docker run --rm comfygit-qa --validate scenarios/01_basic_workspace_setup.yaml
```

### 3. Run a scenario in native mode (no API key needed)

```bash
# See what would run
docker run --rm comfygit-qa --dry-run scenarios/01_basic_workspace_setup.yaml

# Actually run (native mode - executes commands directly)
docker run --rm -v $(pwd)/reports:/reports comfygit-qa --native scenarios/01_basic_workspace_setup.yaml
```

### 4. Run with Claude agent (requires API key)

```bash
docker run --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v $(pwd)/reports:/reports \
  comfygit-qa scenarios/01_basic_workspace_setup.yaml
```

## Directory Structure

```
qa/
├── Dockerfile                 # Container with ComfyGit + Claude CLI
├── agent_instructions/        # Instructions for Claude agents
│   ├── base_system.md         # Core agent behavior
│   └── scenario_runner.md     # How to execute scenarios
├── scenarios/                 # Test scenarios in YAML
│   ├── 01_basic_workspace_setup.yaml
│   └── 02_workflow_sync.yaml
├── scripts/
│   ├── run_scenario.py        # Orchestration script
│   └── schema.py              # Pydantic models for validation
├── reports/                   # Generated reports (gitignored)
└── README.md
```

## Writing Scenarios

Scenarios are YAML files with a validated schema. The schema enforces structure and catches errors early.

### Scenario Structure

```yaml
name: My Test Scenario        # Required
description: |                # Optional but recommended
  What this tests and why it matters.
category: workflow            # workspace|workflow|node|model|collaboration|export
priority: high                # critical|high|medium|low

requirements:                 # Optional - informational
  comfygit: ">=0.3.0"
  disk_space: "500MB"
  network: true

setup:                        # Commands to prepare environment
  - command: rm -rf /workspace/*
    description: Clean workspace
    ignore_errors: true

steps:                        # Required - main test steps
  - action: Create environment
    command: cg env create production
    expect: Environment created successfully
    on_failure: investigate   # investigate|skip|abort|document
    timeout: 300
    verify:
      - "ls -la /workspace/.comfygit/environments/"

  - action: Explore edge cases
    explore: |
      Try some variations:
      1. What if the name has spaces?
      2. What if the directory already exists?

cleanup:                      # Runs after steps complete
  - command: rm -rf /workspace/*
    ignore_errors: true

success_criteria: |           # Optional - defines what success looks like
  - All steps pass
  - No unexpected errors
```

### Step Types

| Field | Description |
|-------|-------------|
| `command` | Shell command to execute (mutually exclusive with `explore`) |
| `explore` | Free-form exploration prompt for Claude (mutually exclusive with `command`) |
| `expect` | What should happen (documentation/guidance) |
| `on_failure` | `investigate`, `skip`, `abort`, or `document` |
| `timeout` | Seconds before timeout (default: 60) |
| `verify` | List of commands to run after step |

### Validation

Scenarios are validated using Pydantic models. To validate before running:

```bash
docker run --rm comfygit-qa --validate scenarios/my_scenario.yaml
```

Validation checks:
- Required fields present (`name`, `steps`)
- Each step has either `command` or `explore` (not both, not neither)
- Valid enum values for `category`, `priority`, `on_failure`
- Proper types for all fields

## Running Modes

### Native Mode (`--native`)
Runs steps directly without Claude. Good for:
- Testing scenario syntax
- Quick verification
- Environments without API access

Outputs JSON + markdown reports.

### Dry Run (`--dry-run`)
Shows what would execute without running anything. No reports generated.

### Validate Only (`--validate`)
Validates scenario YAML against schema. No execution.

### Claude Agent Mode (default)
Full AI-powered testing:
- Follows scenario structure
- Makes judgment calls on "explore" steps
- Investigates failures intelligently
- Writes detailed reports

Options:
- `--model haiku|sonnet|opus` - Choose Claude model (default: sonnet)
- `--timeout N` - Timeout in minutes (default: 30)

## Reports

Reports are generated in two formats:

### JSON Report
Machine-readable format for aggregation and analysis:
```json
{
  "scenario_name": "Basic Workspace Setup",
  "overall_status": "pass",
  "steps_total": 10,
  "steps_passed": 9,
  "steps_failed": 1,
  "step_results": [...],
  "bugs": [...],
  "ux_issues": [...]
}
```

### Markdown Report
Human-readable format with full details:
```markdown
# QA Report: Basic Workspace Setup
Date: 2024-12-30 14:30:22
Agent: native
Duration: 45.3s

## Summary
Executed 10 steps: 9 passed, 1 failed.

## Scenario Execution
### Step 1: Initialize workspace
...

## Findings
### Bugs Found
...
```

Report locations:
- JSON: `reports/{scenario}_{timestamp}.json`
- Markdown: `reports/{scenario}_{timestamp}.md`
- Raw Claude output (agent mode): `reports/raw_{timestamp}.txt`

## Cost Considerations

Claude agent mode incurs API costs:
- Haiku: ~$0.25/M input, ~$1.25/M output (~$0.10-0.50 per scenario)
- Sonnet: ~$3/M input, ~$15/M output (~$0.50-2.00 per scenario)
- Opus: ~$15/M input, ~$75/M output (~$2-10 per scenario)

Use `--native` mode for development/debugging to avoid costs.
Use `--model haiku` for cost-sensitive runs.

## Development

### Building with local ComfyGit

```bash
# Build from parent directory
cd qa
docker build \
  --build-arg INSTALL_LOCAL=true \
  -t comfygit-qa:local \
  -f Dockerfile ..
```

### Running tests locally (without Docker)

```bash
cd qa/scripts
python run_scenario.py --native ../scenarios/01_basic_workspace_setup.yaml \
  --reports-dir ../reports \
  --instructions-dir ../agent_instructions
```

## Phase 2 Improvements

This is Phase 2 of the QA system. Key improvements over Phase 1:

1. **Schema Validation**: Pydantic models validate scenarios before execution
2. **Structured Reports**: JSON + markdown dual output for programmatic and human use
3. **Better Error Handling**: Graceful failures with structured error information
4. **Refined Instructions**: More specific guidance for agents with examples
5. **New Options**: `--validate`, `--model`, `--verbose` flags

## Troubleshooting

### Scenario validation fails
```bash
# Get detailed error messages
docker run --rm comfygit-qa --validate scenarios/my_scenario.yaml
```

### Container won't build
```bash
# Check for build errors
docker build -t comfygit-qa . 2>&1 | tee build.log
```

### Claude CLI not found
```bash
# Verify inside container
docker run --rm comfygit-qa which claude
```

### API key issues
```bash
# Verify key is set
echo $ANTHROPIC_API_KEY | head -c 10

# Test with native mode first
docker run --rm comfygit-qa --native scenarios/01_basic_workspace_setup.yaml
```

### Reports not appearing
```bash
# Ensure volume mount is correct
docker run --rm -v $(pwd)/reports:/reports comfygit-qa --native ...
ls -la reports/
```

## Phase 3: Multi-Agent Parallel Execution

Phase 3 adds infrastructure for running multiple QA agents in parallel.

### Architecture

```
qa-shared volume
├── uv_cache/              # Shared UV package cache (fast installs via hardlinks)
├── workspace-1/           # Agent 1's isolated workspace
├── workspace-2/           # Agent 2's isolated workspace
├── workspace-N/           # Agent N's isolated workspace
└── .installed-{N}         # Per-agent install markers
```

### Quick Start (Multi-Agent)

```bash
cd qa

# Create shared volume (once)
docker volume create qa-shared

# Start multiple agents
AGENT_ID=1 docker compose -p qa-1 up -d
AGENT_ID=2 docker compose -p qa-2 up -d
AGENT_ID=3 docker compose -p qa-3 up -d

# Run different scenarios on each
docker compose -p qa-1 exec qa python /qa/scripts/run_scenario.py /qa/scenarios/01_basic_workspace_setup.yaml
docker compose -p qa-2 exec qa python /qa/scripts/run_scenario.py /qa/scenarios/02_workflow_sync.yaml
docker compose -p qa-3 exec qa python /qa/scripts/run_scenario.py /qa/scenarios/03_model_resolution.yaml

# Cleanup
docker compose -p qa-1 down
docker compose -p qa-2 down
docker compose -p qa-3 down
```

### Benefits

- **Isolation**: Each agent has its own workspace directory
- **Fast installs**: Shared UV cache enables hardlinks (same filesystem)
- **Local code**: Entrypoint auto-installs from `/comfygit` mount
- **Traceability**: Git identity includes AGENT_ID

### Local ComfyGit Development

The entrypoint auto-installs from `/comfygit` mount if present. To reinstall after changes:

```bash
docker compose -p qa-1 exec qa /qa/install-local.sh
```

## Next Steps (Phase 4)

- Python orchestrator for parallel scenario execution
- Report aggregation across agents
- CI/CD integration for weekly runs
