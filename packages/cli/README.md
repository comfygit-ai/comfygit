# ComfyGit CLI

Command-line interface for ComfyGit workspace and environment management.

## Overview

The CLI (`cfd` command) provides interactive, user-friendly access to ComfyGit's environment management system. It wraps the `comfygit-core` library with:

- **Smart tab completion** - Context-aware shell completion for bash/zsh
- **Interactive resolution** - User-guided dependency resolution for ambiguous cases
- **Environment logging** - Automatic logging of all operations per environment
- **Error formatting** - Translates exceptions into actionable CLI commands
- **Progress display** - Download progress, ETA, and statistics

## Installation

See the [root README](../../README.md#installation) for installation instructions.

TL;DR:
```bash
uv tool install comfydock-cli
# or
pip install comfydock-cli
```

## CLI-Specific Features

### Tab Completion

The CLI provides smart shell completion that understands your workspace context:

```bash
cfd use <TAB>           # Lists all environments
cfd -e prod node remove <TAB>  # Lists installed nodes in 'prod'
cfd workflow resolve <TAB>     # Prioritizes unresolved workflows
```

**Setup:**
```bash
cfd completion install    # One-time setup (bash/zsh)
cfd completion status     # Check installation
```

The installer:
1. Detects your shell (.bashrc or .zshrc)
2. Installs argcomplete if needed (via UV tool)
3. Adds completion lines to your shell config
4. Prompts you to reload shell

### Interactive Resolution

When workflows contain unknown nodes or missing models, the CLI enters interactive mode:

**Node Resolution:**
```
⚠️  Node not found in registry: MyCustomNode
🔍 Searching for: MyCustomNode

Found 3 potential matches:

  1. user/my-custom-node (installed)
     A custom node for doing XYZ...

  2. other-user/custom-node-pack
     Collection of utility nodes

  3. another/node-collection
     No description

  [1-5] - Select package to install
  [r]   - Refine search
  [m]   - Manually enter package ID
  [o]   - Mark as optional (workflow works without it)
  [s]   - Skip (leave unresolved)

Choice [1]/r/m/o/s:
```

**Model Resolution:**
```
⚠️  Model not found: checkpoints/sd_xl_base.safetensors
  in node #12 (CheckpointLoaderSimple)

🔍 Searching for: sd_xl_base.safetensors

Found 2 matches:

  1. checkpoints/sd_xl_base_1.0.safetensors (6.46 GB)
     High confidence match

  2. checkpoints/sd_xl_base_0.9.safetensors (6.17 GB)
     Medium confidence match

  [r] Refine search
  [d] Download from URL
  [o] Mark as optional
  [s] Skip

Choice [1]/r/d/o/s:
```

This only happens when the CLI can't automatically resolve dependencies. Most of the time, things "just work."

### Environment Logging

Every command is logged to environment-specific files:

```
~/comfydock/
└── logs/
    ├── production/
    │   ├── full.log        # All operations in 'production'
    │   └── full.log.1      # Rotated logs (10MB per file, 5 backups)
    └── workspace.log       # Workspace-level operations (init, import, etc)
```

View logs:
```bash
cfd logs                    # Last 200 lines of active env
cfd logs -n 500             # Last 500 lines
cfd logs --full             # All logs (no limit)
cfd logs --level ERROR      # Only errors
cfd logs --workspace        # Workspace logs instead of env
```

Logs include:
- Command invocations
- Node installations and removals
- Model downloads and resolutions
- Git operations
- UV/Python dependency changes
- Error stack traces

### Error Formatting

Core library errors are translated into actionable CLI commands:

**Example:**
```
✗ Node conflict: Directory 'ComfyUI-Manager' already exists
  Filesystem: https://github.com/ltdrdata/ComfyUI-Manager.git
  Registry:   https://github.com/ltdrdata/ComfyUI-Manager.git

Suggested actions:
  1. Track existing directory as development node
     → cfd node add ComfyUI-Manager --dev
  2. Remove and reinstall from registry
     → cfd node remove ComfyUI-Manager
     → cfd node add comfyui-manager
```

## Command Reference

### Global Options

```bash
cfd [options] <command> [args]

Options:
  -e, --env NAME    Target specific environment (uses active if not specified)
  -v, --verbose     Verbose output
  -h, --help        Show help
```

### Workspace Commands

Commands that operate at the workspace level (no environment needed):

```bash
# Initialize workspace (one-time setup)
cfd init [PATH]
  --models-dir PATH    Point to existing models directory
  --yes, -y            Use all defaults, no prompts

# List all environments
cfd list

# Import environment from tarball or git
cfd import [PATH|URL]
  --name NAME          Environment name (skips prompt)
  --branch, -b REF     Git branch/tag/commit
  --torch-backend BACKEND  PyTorch backend (auto/cpu/cu128/rocm6.3/xpu)
  --use                Set as active environment after import

# Export environment to tarball
cfd export [PATH]
  --allow-issues       Skip confirmation if models lack source URLs

# Configuration
cfd config
  --civitai-key KEY    Set CivitAI API key (empty string to clear)
  --show               Show current configuration

# Registry management
cfd registry status    # Show registry cache status
cfd registry update    # Update registry data from GitHub

# Model index (workspace-wide)
cfd model index find QUERY        # Find models by hash/filename
cfd model index list              # List all indexed models
cfd model index show IDENTIFIER   # Show detailed model info
cfd model index status            # Show index status
cfd model index sync              # Scan models directory
cfd model index dir PATH          # Set models directory

# Model download (to workspace models directory)
cfd model download URL
  --path PATH          Target path relative to models dir
  -c, --category TYPE  Model category for auto-path (checkpoints/loras/vae)
  -y, --yes            Skip path confirmation

# Model source management
cfd model add-source [MODEL] [URL]  # Interactive if args omitted

# Tab completion
cfd completion install     # Install completion for your shell
cfd completion uninstall   # Remove completion
cfd completion status      # Show installation status
```

### Environment Management

Commands that operate ON environments:

```bash
# Create new environment
cfd create NAME
  --template PATH      Template manifest
  --python VERSION     Python version (default: 3.11)
  --comfyui VERSION    ComfyUI version
  --torch-backend BACKEND  PyTorch backend (auto/cpu/cu128/rocm6.3/xpu)
  --use                Set as active environment

# Set active environment
cfd use NAME

# Delete environment
cfd delete NAME
  -y, --yes            Skip confirmation

# Show environment status
cfd status
  -v, --verbose        Show full details

# Repair environment to match pyproject.toml
cfd repair
  -y, --yes            Skip confirmation
  --models MODE        Model download strategy (all/required/skip)
```

### Environment Operations

Commands that operate IN environments (require `-e` or active environment):

```bash
# Run ComfyUI
cfd run [COMFYUI_ARGS...]
  --no-sync            Skip environment sync before running

# View logs
cfd logs
  -n, --lines N        Number of lines (default: 200)
  --level LEVEL        Filter by log level (DEBUG/INFO/WARNING/ERROR)
  --full               Show all logs (no line limit)
  --workspace          Show workspace logs instead of environment logs
```

### Version Control

Git-based versioning for environments:

```bash
# Commit current state
cfd commit
  -m, --message MSG    Commit message (auto-generated if not provided)
  --auto               Auto-resolve issues without interaction
  --allow-issues       Allow committing workflows with unresolved issues

# View commit history
cfd commit log
  -v, --verbose        Show full details

# Rollback to previous state
cfd rollback [VERSION]
  # No version: Discard uncommitted changes
  # With version (e.g., v1, v2): Restore that commit
  -y, --yes            Skip confirmation
  --force              Force rollback, discard uncommitted changes
```

### Git Integration

Sync environments via git remotes:

```bash
# Remote management
cfd remote add NAME URL      # Add git remote
cfd remote remove NAME       # Remove git remote
cfd remote list              # List all remotes

# Pull from remote
cfd pull
  -r, --remote NAME    Remote name (default: origin)
  --models MODE        Model download strategy (all/required/skip)
  --force              Discard uncommitted changes

# Push to remote
cfd push
  -r, --remote NAME    Remote name (default: origin)
  --force              Force push using --force-with-lease
```

### Custom Nodes

```bash
# Add custom node
cfd node add IDENTIFIER [IDENTIFIER...]
  # IDENTIFIER can be:
  #   - Registry ID: comfyui-manager
  #   - GitHub URL: https://github.com/user/repo
  #   - GitHub URL with ref: https://github.com/user/repo@v1.0
  #   - Directory name (with --dev): my-custom-node --dev

  --dev                Track existing directory as development node
  --no-test            Skip dependency resolution test
  --force              Force overwrite existing directory

# Remove custom node
cfd node remove IDENTIFIER [IDENTIFIER...]
  --dev                Remove development node specifically

# List installed nodes
cfd node list

# Update node
cfd node update IDENTIFIER
  -y, --yes            Auto-confirm updates
  --no-test            Skip dependency resolution test
```

### Workflows

```bash
# List workflows with status
cfd workflow list

# Resolve workflow dependencies
cfd workflow resolve NAME
  --auto               Auto-resolve without interaction
  --install            Auto-install missing nodes
  --no-install         Skip node installation prompt
```

### Python Dependencies

```bash
# Add Python package
cfd py add [PACKAGE...]
  -r, --requirements FILE  Add from requirements.txt
  --upgrade                Upgrade existing packages

# Remove Python package
cfd py remove PACKAGE [PACKAGE...]

# List dependencies
cfd py list
  --all                Show all including dependency groups

# Manage constraints (UV constraint dependencies)
cfd constraint add PACKAGE [PACKAGE...]    # e.g., torch==2.4.1
cfd constraint list
cfd constraint remove PACKAGE [PACKAGE...]
```

## Common Workflows

### Setting Up a New Project

```bash
# 1. Initialize workspace (one-time)
cfd init

# During init, you'll be prompted to set up models directory:
# - Point to existing ComfyUI models directory (recommended)
# - Or use the default empty directory

# 2. Create and activate environment
cfd create my-project --use

# 3. Add custom nodes
cfd node add comfyui-manager
cfd node add https://github.com/ltdrdata/ComfyUI-Impact-Pack

# 4. Run ComfyUI and build your workflow
cfd run

# 5. Commit your work
cfd commit -m "Initial setup with Impact Pack"

# 6. Export for sharing
cfd export my-project-v1.tar.gz
```

### Importing a Shared Project

```bash
# Import from tarball
cfd import workflow-pack.tar.gz --name imported-project --use

# Or import from git
cfd import https://github.com/user/comfyui-project.git --name team-project --use

# The import process will:
# 1. Download missing nodes
# 2. Resolve models from your index (or download if available)
# 3. Set up Python environment
# 4. Prepare ComfyUI for running

cfd run
```

### Team Collaboration via Git

```bash
# On machine 1: Set up and share
cfd create team-workflow --use
cfd node add comfyui-animatediff
# ... build workflow ...
cfd commit -m "Initial animation workflow"

# Add GitHub/GitLab remote
cfd remote add origin https://github.com/team/comfy-project.git
cfd push

# On machine 2: Clone and work
cfd import https://github.com/team/comfy-project.git --name team-workflow --use
# ... make changes ...
cfd commit -m "Added refiners"
cfd push

# Back on machine 1: Pull updates
cfd pull
cfd run
```

### Managing Models Across Environments

```bash
# Check what models you have
cfd model index status
# Output: 124 models indexed in /home/user/models

# Find specific model
cfd model index find "sd_xl"
# Shows matches with hash, size, file path

# Download new model
cfd model download https://civitai.com/models/133005

# Update index after manually adding models
cfd model index sync

# Models are automatically symlinked into environments
# No duplication, shared across all environments
```

### Resolving Workflow Dependencies

```bash
# Load a workflow with missing nodes/models
cfd workflow resolve my-animation

# The CLI will:
# 1. Analyze the workflow
# 2. Prompt for any unknown nodes (with search/suggestions)
# 3. Check models against your index
# 4. Offer to download missing models
# 5. Update environment to match

# For non-interactive use:
cfd workflow resolve my-animation --auto --install
```

### Experimenting Without Breaking Production

```bash
# Create experimental environment
cfd create experimental --use

# Install risky nodes
cfd node add some-experimental-node

# If things break:
cfd rollback  # Discard uncommitted changes

# Or commit and rollback later:
cfd commit -m "Testing experimental node"
# ... test ...
cfd rollback v1  # Go back to before the commit

# When ready to merge changes back to production:
cfd export experimental.tar.gz
cfd use production
# Manually review and selectively add nodes from experimental
```

## Debugging

### Using Logs

Logs are your friend when things go wrong:

```bash
# View recent logs
cfd logs

# View all logs
cfd logs --full

# Filter by error level
cfd logs --level ERROR

# View more lines
cfd logs -n 1000

# View workspace logs (for init, import, export issues)
cfd logs --workspace
```

**Log locations:**
```
~/comfydock/logs/
├── <env-name>/
│   ├── full.log        # Current log
│   ├── full.log.1      # First rotation
│   └── full.log.2      # Second rotation
└── workspace.log       # Workspace-level operations
```

Logs rotate automatically at 10MB with 5 backups kept.

### Common Issues

**"No workspace found"**
```bash
# Make sure you've initialized
cfd init

# Or set COMFYGIT_HOME to point to existing workspace
export COMFYGIT_HOME=/path/to/workspace
```

**"No active environment"**
```bash
# List environments
cfd list

# Set active environment
cfd use <name>

# Or use -e flag
cfd -e <name> status
```

**Node installation fails**
```bash
# Check the logs
cfd logs --level ERROR

# Try repairing the environment
cfd repair -y

# View Python dependency conflicts
cfd py list
```

**Tab completion not working**
```bash
# Check status
cfd completion status

# Reinstall if needed
cfd completion uninstall
cfd completion install

# Reload shell
source ~/.bashrc  # or ~/.zshrc
```

## Environment Variables

- `COMFYGIT_HOME` - Override default workspace location (`~/comfygit`)
- `COMFYGIT_DEV_COMPRESS_LOGS` - Enable compressed logging (dev feature: `true`/`1`/`yes`)
- `CIVITAI_API_KEY` - CivitAI API key (or use `cfd config --civitai-key`)

Example:
```bash
export COMFYGIT_HOME=/mnt/storage/comfygit
cfd init
```

## For Library Users

If you want programmatic access without the CLI, use `comfydock-core` directly:

```python
from comfydock_core.factories.workspace_factory import WorkspaceFactory

# Load workspace
workspace = WorkspaceFactory.find()

# Get environment
env = workspace.get_environment("my-project")

# Add node
env.add_node("comfyui-manager")

# Commit changes
env.commit("Added manager")
```

See [packages/core/README.md](../core/README.md) for core library documentation.

## Contributing

This is a MVP project run by a single developer. Contributions welcome!

**Note:** Contributors must sign our [Contributor License Agreement](../../CLA.md) to enable dual-licensing. See [CONTRIBUTING.md](../../CONTRIBUTING.md) for details.

**Adding a new command:**
1. Add command parser in `cli.py` (`_add_global_commands` or `_add_env_commands`)
2. Implement handler in `global_commands.py` or `env_commands.py`
3. Add completer in `completers.py` if needed
4. Update this README

**Project structure:**
- `cli.py` - Argument parser and command router
- `global_commands.py` - Workspace-level commands
- `env_commands.py` - Environment-level commands
- `completion_commands.py` - Tab completion management
- `strategies/` - Interactive resolution strategies
- `formatters/` - Error formatting for user-friendly output
- `logging/` - Environment-specific logging system
- `utils/` - Progress display, pagination, etc.
