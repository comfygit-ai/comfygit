# Features

ComfyGit provides comprehensive environment and package management for ComfyUI. This page gives an overview of all available features.

## Environments

Create and manage isolated ComfyUI installations.

| Command | Description |
|---------|-------------|
| `cg init` | Initialize a workspace |
| `cg create <name>` | Create new environment |
| `cg list` | List all environments |
| `cg use <name>` | Set active environment |
| `cg status` | Show environment state |
| `cg delete <name>` | Delete environment |
| `cg run` | Start ComfyUI |

**Environment options:**

```bash
# Specify PyTorch backend
cg create my-env --torch-backend cu128   # NVIDIA CUDA 12.8
cg create my-env --torch-backend rocm6.3 # AMD ROCm 6.3
cg create my-env --torch-backend cpu     # CPU only

# Set as active immediately
cg create my-env --use
```

## Custom Nodes

Install custom nodes from the registry, GitHub, or local directories.

| Command | Description |
|---------|-------------|
| `cg node add <id>` | Add from registry |
| `cg node add <url>` | Add from GitHub |
| `cg node add <dir> --dev` | Add local development node |
| `cg node remove <id>` | Remove node |
| `cg node update <id>` | Update to latest |
| `cg node list` | List installed nodes |

**Node sources:**

```bash
# From ComfyUI registry
cg node add comfyui-impact-pack

# From GitHub URL
cg node add https://github.com/ltdrdata/ComfyUI-Impact-Pack

# Specific version or branch
cg node add comfyui-impact-pack@v1.0.0
cg node add comfyui-impact-pack@main

# Local development
cg node add ~/my-nodes/custom-node --dev
```

## Version Control

Track changes, branch, and rollback when things break.

| Command | Description |
|---------|-------------|
| `cg commit -m "msg"` | Save current state |
| `cg log` | View commit history |
| `cg revert <commit>` | Undo a specific commit |
| `cg checkout <commit>` | Explore old state (detached) |
| `cg reset --hard` | Discard uncommitted changes |
| `cg diff` | Show uncommitted changes |
| `cg branch <name>` | Create new branch |
| `cg switch <branch>` | Switch to branch |

**Version control workflow:**

```bash
# Save state after changes
cg commit -m "Added IPAdapter nodes"

# View history
cg log
cg log --verbose  # With timestamps and full hashes

# Undo last commit (creates new revert commit)
cg revert HEAD

# Explore old state
cg checkout a28f333  # Detached HEAD
cg checkout main     # Return to latest

# Discard all uncommitted changes
cg reset --hard

# Branching
cg branch experimental
cg switch experimental
```

## Sharing & Collaboration

Export environments for sharing or sync with Git remotes.

| Command | Description |
|---------|-------------|
| `cg export <file>` | Export to tarball |
| `cg import <file>` | Import from tarball |
| `cg import <url>` | Import from Git URL |
| `cg remote add <name> <url>` | Add Git remote |
| `cg remote list` | List configured remotes |
| `cg push` | Push to remote |
| `cg pull` | Pull from remote |

**Export/import:**

```bash
# Export complete environment
cg export my-workflow.tar.gz

# Import on another machine
cg import my-workflow.tar.gz --name imported-env
```

**Git remotes:**

```bash
# Add remote and push
cg remote add origin https://github.com/you/my-env.git
cg push

# Import from Git URL
cg import https://github.com/team/shared-env.git --name team-env

# Pull updates
cg pull
```

## Model Management

Index, download, and manage models with content-addressable storage.

| Command | Description |
|---------|-------------|
| `cg model index sync` | Scan and index models |
| `cg model index dir <path>` | Add directory to index |
| `cg model index find <query>` | Search indexed models |
| `cg model download <url>` | Download from CivitAI/HuggingFace |

**Model workflow:**

```bash
# Index existing models
cg model index dir ~/my-models
cg model index sync

# Download from CivitAI
cg model download https://civitai.com/models/133005

# Find indexed models
cg model index find "juggernaut"
```

Models are symlinked into environments from the global index, preventing duplicates.

## Workflows

Track workflows and resolve their dependencies.

| Command | Description |
|---------|-------------|
| `cg workflow list` | List all workflows with sync status |
| `cg workflow resolve <name>` | Resolve missing nodes and models |
| `cg workflow model importance <name>` | Set model importance (required/flexible/optional) |

**Workflow resolution:**

```bash
# Analyze workflow and install missing nodes/models
cg workflow resolve my-workflow.json

# Auto-install without prompts
cg workflow resolve my-workflow.json --install

# Set model importance for sharing
cg workflow model importance my-workflow.json
```

## Python Dependencies

Manage additional Python packages beyond what nodes require.

| Command | Description |
|---------|-------------|
| `cg py add <package>` | Add Python package |
| `cg py remove <package>` | Remove package |
| `cg py remove-group <group>` | Remove entire dependency group |
| `cg py list` | List dependencies |
| `cg py uv <args>` | Direct UV passthrough (advanced) |

**Python packages:**

```bash
# Add packages
cg py add requests
cg py add numpy==1.24.0

# From requirements file
cg py add -r requirements.txt

# Remove
cg py remove requests

# Advanced: direct UV commands
cg py uv pip list
```

## Shell Completion

Tab completion for commands, environments, and nodes.

```bash
# Install completion for your shell
cg completion install

# Supports bash, zsh, fish
```

## Debugging

View logs and debug issues.

| Command | Description |
|---------|-------------|
| `cg debug` | Show recent logs (default 200 lines) |
| `cg debug -n <lines>` | Show specific number of lines |
| `cg debug --level <level>` | Filter by log level (DEBUG/INFO/WARNING/ERROR) |
| `cg debug --full` | Show all logs (no limit) |
| `cg debug --workspace` | Show workspace logs instead of environment |

```bash
# Show recent logs
cg debug
cg debug -n 100  # Last 100 lines

# Filter by level
cg debug --level ERROR

# Verbose output for any command
cg --verbose node add comfyui-impact-pack
```

## Configuration

Manage workspace and API settings.

| Command | Description |
|---------|-------------|
| `cg config --show` | Show current configuration |
| `cg config --civitai-key <key>` | Set CivitAI API key |

```bash
# View configuration
cg config --show

# Set CivitAI API key for model downloads
cg config --civitai-key your-api-key

# Clear API key
cg config --civitai-key ""
```

## Directory Structure

ComfyGit stores configuration in the workspace:

```
~/comfygit/
├── .metadata/
│   └── workspace.toml    # Workspace settings
├── environments/         # Your environments
├── models/              # Shared models
└── comfygit_cache/      # Registry and node cache
```

Each environment has its own configuration:

```
environments/my-project/
├── ComfyUI/             # ComfyUI installation
│   ├── custom_nodes/    # Installed nodes
│   ├── models/          # Symlinks to workspace models
│   └── .venv/           # Python environment
└── .cec/                # Version control
    ├── pyproject.toml   # Dependencies
    ├── uv.lock          # Lockfile
    └── workflows/       # Tracked workflows
```

## Next Steps

- **[Core Concepts](concepts.md)** — Understand how ComfyGit works
- **[CLI Reference](../cli-reference/environment-commands.md)** — Complete command documentation
- **[Troubleshooting](../troubleshooting/common-issues.md)** — Common issues and solutions
