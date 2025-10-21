# ComfyDock Monorepo - Codebase Map

ComfyDock is a Python monorepo using uv workspaces for unified environment management for ComfyUI. This map describes the root-level structure; see individual package maps for internal architecture.

## Root Configuration & Tooling

- **pyproject.toml** - Workspace root configuration defining workspace members (core, cli), shared dev dependencies, and tool configurations for ruff, pytest, and mypy
- **Makefile** - Development automation with targets for install, test, lint, format, Docker operations, and version management
- **CLAUDE.md** - Developer guidance including version management strategy, development commands, and project philosophy
- **uv.lock** - Locked dependency versions for workspace reproducibility
- **README.md** - High-level project overview and structure documentation

## Workspace Packages (`packages/`)

Coordinated Python packages built and tested together:

### Core Package (`packages/core/`)
ComfyDock Core library providing environment, node, model, and workflow management APIs. Designed as a reusable library without UI coupling. Depends on: aiohttp, requests, pyyaml, tomlkit, uv, blake3, psutil. See `packages/core/docs/codebase-map.md` for internal structure.

### CLI Package (`packages/cli/`)
Command-line interface for ComfyDock users. Provides `comfydock` and `cfd` entry points for interactive environment and node management. Depends on comfydock-core. See package directory for internal implementation details.

## Documentation (`docs/`)

- **comfydock-docs/** - User-facing documentation site built with MkDocs. Contains installation guides, usage documentation, troubleshooting, and best practices for end users.

## Development Environment (`dev/`)

- **docker-compose.yml** - Development environment orchestration for multi-container setup

## Key Files at Root

| File | Purpose |
|------|---------|
| `pyproject.toml` | Workspace configuration and shared tool settings |
| `Makefile` | Build and development automation |
| `CLAUDE.md` | Development instructions and guidelines |
| `uv.lock` | Dependency lock file for reproducibility |
| `README.md` | Project overview and structure |
| `LICENSE.txt` | Project license |

## Version Management

All packages must maintain the same major version. Use Makefile commands:
- `make show-versions` - Display all package versions
- `make check-versions` - Validate version compatibility
- `make bump-major VERSION=X` - Bump all packages together
- `make bump-package PACKAGE=name VERSION=X.Y.Z` - Update individual package

Current workspace version: 1.0.0 (all packages aligned to major version 1.x.x)

## Development Workflow

1. **Setup**: `make install` - Installs all packages in development mode
2. **Testing**: `make test` - Runs full test suite
3. **Linting**: `make lint` - Checks code quality
4. **Formatting**: `make format` - Auto-formats code
5. **Development**: `make dev` - Starts Docker-based dev environment

## Repository Structure Summary

```
comfydock/
├── packages/                      # Coordinated Python packages
│   ├── core/                      # Core library (reusable, no UI)
│   └── cli/                       # CLI interface
├── docs/
│   └── comfydock-docs/           # User documentation site
├── dev/
│   └── docker-compose.yml        # Dev environment setup
├── pyproject.toml                # Workspace root config
├── Makefile                      # Development automation
├── CLAUDE.md                     # Developer guidance
├── README.md                     # Project overview
└── uv.lock                       # Locked dependencies
```

## Key Entry Points

- **CLI**: Run `comfydock` or `cfd` command after installation
- **Core Library**: Import from `comfydock_core` for programmatic access
- **Development**: See CLAUDE.md for detailed instructions

## Architecture Notes

- **Workspace-based**: All packages share dependencies through uv workspaces
- **Library-first**: Core package is decoupled from presentation concerns
- **Version-locked**: Upper bounds in dependencies prevent major version conflicts
- **Single developer**: MVP-focused with simple, maintainable code philosophy
- **Pre-customer**: Backward compatibility avoided in favor of clean refactoring
