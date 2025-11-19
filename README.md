# ComfyGit

[![Documentation](https://img.shields.io/badge/docs-comfyhub.org-blue)](https://docs.comfyhub.org/comfygit/)
[![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?logo=discord&logoColor=white)](https://discord.gg/2h5rSTeh6Y)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE.txt)

Git for your ComfyUI environments — version control, package management, and reproducible sharing.

## Highlights

- 🔄 **Isolated environments** — test new nodes without breaking production
- 📦 **Git-based versioning** — commit changes, rollback when things break
- 🚀 **One-command sharing** — export/import complete working environments
- 💾 **Smart model management** — content-addressable index, no duplicate storage
- 🔧 **Standard tooling** — built on UV and pyproject.toml, works with Python ecosystem
- 🖥️ **Cross-platform** — Windows, Linux, macOS

## Installation

```bash
# With UV (recommended)
uv tool install comfygit

# Or with pip
pip install comfygit
```

Need UV? See [UV installation](https://docs.astral.sh/uv/getting-started/installation/).

## Quick Start

```console
$ cg init
Initialized ComfyGit workspace at ~/comfygit

$ cg create my-project --use
Created environment 'my-project'
Active environment: my-project

$ cg node add comfyui-impact-pack
Resolving comfyui-impact-pack...
Installing ComfyUI-Impact-Pack from registry
 + comfyui-impact-pack@1.2.3

$ cg commit -m "Initial setup with Impact Pack"
[main a28f333] Initial setup with Impact Pack
 1 file changed, 15 insertions(+)

$ cg run
Starting ComfyUI at http://localhost:8188
```

See the [documentation](https://docs.comfyhub.org/comfygit/) for more examples including version control workflows, sharing environments, and team collaboration.

## Documentation

Full documentation at **[docs.comfyhub.org/comfygit](https://docs.comfyhub.org/comfygit)** including:

- [How It Works](https://docs.comfyhub.org/comfygit/concepts/) — architecture and design
- [Model Management](https://docs.comfyhub.org/comfygit/models/) — content-addressable indexing
- [Sharing Environments](https://docs.comfyhub.org/comfygit/sharing/) — export/import and git remotes

## Features

### Environments
```bash
cg create <name>              # Create new environment
cg list                       # List all environments
cg use <name>                 # Set active environment
cg status                     # Show environment state
cg run                        # Run ComfyUI
```

### Nodes
```bash
cg node add <id>              # Add from registry
cg node add <github-url>      # Add from GitHub
cg node remove <id>           # Remove node
cg node list                  # List installed nodes
```

### Version Control
```bash
cg commit -m "message"        # Save snapshot
cg log                        # View history
cg revert <commit>            # Undo a commit
cg checkout <commit>          # Explore old state
```

### Sharing
```bash
cg export <file.tar.gz>       # Export environment
cg import <file.tar.gz>       # Import environment
cg push / cg pull             # Sync with git remote
```

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

- [GitHub Issues](https://github.com/comfyhub-org/comfygit/issues) — bugs and features
- [GitHub Discussions](https://github.com/comfyhub-org/comfygit/discussions) — questions and ideas
- [Discord](https://discord.gg/2h5rSTeh6Y) — community chat

## License

ComfyGit is dual-licensed under [AGPL-3.0](LICENSE.txt) for open-source use and proprietary licenses for commercial use. See [licensing details](https://docs.comfyhub.org/comfygit/license/) for more information.
