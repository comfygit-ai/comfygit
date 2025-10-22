## Project Overview

ComfyDock is a monorepo workspace using uv for Python package management. It provides unified environment management for ComfyUI through multiple coordinated packages.

### Codebase Maps
- @docs/codebase-map.md
- @packages/core/docs/codebase-map.md
- @packages/cli/docs/codebase-map.md

## Version Management Strategy

### Example Current Version Status
- **Workspace Root**: 0.5.0
- **comfydock-core**: 0.2.2
- **comfydock-server**: 0.3.2  
- **comfydock-cli**: 0.3.3
- **comfydock-cec**: 0.1.0

### Version Policy
- **Major version (X.0.0)**: All packages move together for breaking changes
- **Minor version (0.X.0)**: Independent feature additions per package  
- **Patch version (0.0.X)**: Independent bug fixes per package

### Version Management Commands
Available via Makefile:

```bash
# Show all package versions
make show-versions

# Check version compatibility across packages
make check-versions

# Bump major version for all packages (use when making breaking changes)
make bump-major VERSION=1

# Bump individual package version
make bump-package PACKAGE=core VERSION=0.2.3
```

### Dependency Upper Bounds
Packages use upper bounds to prevent major version incompatibilities:
- `packages/server/pyproject.toml`: `comfydock-core>=0.2.2,<1.0.0`
- `packages/cli/pyproject.toml`: `comfydock-server>=0.3.2,<1.0.0`

### Version Compatibility Check
The `scripts/check-versions.py` script validates that all packages share the same major version. Run via `make check-versions` before releases.

## Development Commands

### Environment Setup
```bash
# Install all packages in development mode
make install

# Start development environment
make dev
```

### Testing and Quality
```bash
# Run all tests
make test

# Run linting
make lint

# Format code
make format
```

### Version Management Workflow
1. Use `make check-versions` before any releases
2. For breaking changes: `make bump-major VERSION=1` 
3. For individual updates: `make bump-package PACKAGE=name VERSION=x.y.z`
4. Always run tests after version changes
5. Update dependency constraints when bumping major versions

## Important Notes
- All packages must maintain the same major version for compatibility
- Upper bounds prevent accidental major version conflicts
- Use the provided scripts rather than manual version editing
- Version compatibility is automatically validated by the check script

## General
Don't make any implementation overly complex. This is a one-person dev MVP project.
We are still pre-customer - any unnecessary fallbacks, unnecessary versioning, testing overkill should be avoided.
2-3 tests per file with only the main happy path tested is fine.
Simple, elegant, maintainable code is the goal.
We DONT want any legacy or backwards compatible code. If you make changes that will break older code that's good, make the new changes and then fix the older code to use the new code.
IF I see ANY backwards compatibility or legacy support code added I'm canceling my Claude subscription.
