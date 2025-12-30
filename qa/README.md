# ComfyGit Agent-Based QA Testing

Automated QA testing using Claude agents to explore and find bugs in ComfyGit.

## Philosophy

Traditional tests are great for regression but don't find new bugs. Agent-based testing combines:
- **Structured scenarios** - Defined test flows with expected outcomes
- **Exploratory testing** - Agents find edge cases humans miss
- **Detailed reporting** - Every command and output documented

## Quick Start

### 1. Build the QA container

```bash
cd qa
docker build -t comfygit-qa .
```

### 2. Run a scenario (native mode, no API key needed)

```bash
# See what would run
docker run --rm comfygit-qa --dry-run scenarios/01_basic_workspace_setup.yaml

# Actually run (native mode)
docker run --rm -v $(pwd)/reports:/reports comfygit-qa --native scenarios/01_basic_workspace_setup.yaml
```

### 3. Run with Claude agent (requires API key)

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
│   └── run_scenario.py        # Orchestration script
├── reports/                   # Generated reports (gitignored)
└── README.md
```

## Writing Scenarios

Scenarios are YAML files that define:
- **Setup** - Environment preparation
- **Steps** - Sequential test actions
- **Explore** - Open-ended investigation
- **Cleanup** - Post-test reset

### Example Scenario

```yaml
name: My Test Scenario
description: What this tests
category: workflow

setup:
  - command: cg init --name test
    description: Initialize workspace

steps:
  - action: Create environment
    command: cg env create production
    expect: Environment created successfully
    on_failure: investigate

  - action: Explore edge cases
    explore: |
      Try some variations:
      1. What if the name has spaces?
      2. What if the directory already exists?

cleanup:
  - command: rm -rf /workspace/*
```

### Step Types

| Field | Description |
|-------|-------------|
| `command` | Shell command to execute |
| `expect` | What should happen (for documentation) |
| `on_failure` | `investigate`, `skip`, `abort`, or `document` |
| `timeout` | Seconds before timeout |
| `verify` | List of commands to run after step |
| `explore` | Free-form exploration (Claude chooses what to try) |

## Running Modes

### Native Mode (`--native`)
Runs steps directly without Claude. Good for:
- Testing scenario syntax
- Quick verification
- Environments without API access

### Dry Run (`--dry-run`)
Shows what would execute without running anything.

### Claude Agent Mode (default)
Full AI-powered testing:
- Follows scenario structure
- Makes judgment calls on "explore" steps
- Investigates failures
- Writes detailed reports

## Reports

Reports are Markdown files with:
- Summary of results
- Each step's command and output
- Bugs found (with reproduction steps)
- UX issues noted
- Recommended regression tests

Example report location: `reports/basic_workspace_setup_20241230_143022.md`

## Cost Considerations

Claude agent mode incurs API costs:
- Haiku: ~$0.25/M input, ~$1.25/M output
- Sonnet: ~$3/M input, ~$15/M output

Typical scenario: $0.50-2.00 depending on complexity.

Use `--native` mode for development/debugging to avoid costs.

## Phase 1 Limitations

This is the PoC phase. Current limitations:
- Single agent (no parallel execution)
- Manual triggering only
- Basic report format
- No automatic test generation

See `beads-pnm` for the full roadmap.

## Troubleshooting

### Container won't build
```bash
# Ensure Docker is running
docker info

# Check for build errors
docker build -t comfygit-qa . 2>&1 | tee build.log
```

### Claude CLI not found
```bash
# The container should have it, but verify:
docker run --rm comfygit-qa which claude
```

### Scenario fails to parse
```bash
# Validate YAML
python -c "import yaml; yaml.safe_load(open('scenarios/your_scenario.yaml'))"
```

### API key issues
```bash
# Verify key is set
echo $ANTHROPIC_API_KEY | head -c 10

# Test with native mode first
docker run --rm comfygit-qa --native scenarios/01_basic_workspace_setup.yaml
```
