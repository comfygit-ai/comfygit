## Project Overview

ComfyGit is a monorepo workspace using uv for Python package management. It provides unified environment management for ComfyUI through multiple coordinated packages.

### Codebase Maps
- @docs/codebase-map.md
- @packages/core/docs/codebase-map.md
- @packages/cli/docs/codebase-map.md

## Version Management Strategy

### Lockstep Versioning
Both packages (comfygit-core and comfygit) **always share the same version number**. This is enforced because:
- CLI is tightly coupled to core's types, models, and protocols
- Simplifies user mental model ("I'm on version 0.3.2")
- Eliminates version mismatch issues
- CLI depends on exact core version: `comfygit-core==X.Y.Z`

### Current Version
Both packages should always be at the same version. Check with:
```bash
make show-versions
```

### Version Management Commands
```bash
# Show all package versions
make show-versions

# Bump ALL packages to new version (the standard way to release)
make bump-version VERSION=0.4.0

# Check versions match (used by CI)
make check-versions
```

### Publishing (Automated)
Publishing is handled by `.github/workflows/publish.yml`:
1. **Triggers**: Push to main with pyproject.toml changes, or manual dispatch
2. **Validates**: Ensures core and CLI versions match (fails fast if not)
3. **Skips**: If version already exists on PyPI
4. **Publishes**: Core first → waits for PyPI availability → CLI
5. **Releases**: Creates GitHub release with AI-generated changelog

To release a new version:
```bash
make bump-version VERSION=0.4.0
git add -A && git commit -m "Bump version to 0.4.0"
git push origin main
# Workflow handles the rest automatically
```

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
```

### Cross-Platform Testing
Run tests across Linux, Windows, and macOS using `dev/scripts/cross-platform-test.py`.

```bash
# Run on all enabled platforms
python dev/scripts/cross-platform-test.py

# Run on specific platforms
python dev/scripts/cross-platform-test.py --platforms linux,windows

# Run specific test directory
python dev/scripts/cross-platform-test.py --test-path packages/core/tests/unit

# Pass pytest arguments after -- (full pytest control)
python dev/scripts/cross-platform-test.py -- -k "test_workspace" -x
python dev/scripts/cross-platform-test.py -- -k "test_git" --tb=short
python dev/scripts/cross-platform-test.py --test-path packages/core/tests -- -k "test_env" -x

# Common pytest flags:
#   -k "pattern"  - Run tests matching pattern
#   -x            - Stop on first failure
#   --lf          - Run last failed tests
#   -m "marker"   - Run tests with marker
#   --tb=short    - Shorter traceback format

# Other options
python dev/scripts/cross-platform-test.py --list        # List available platforms
python dev/scripts/cross-platform-test.py --no-sync     # Skip git sync on remote
python dev/scripts/cross-platform-test.py --sequential  # Run sequentially (not parallel)
python dev/scripts/cross-platform-test.py --verbose     # Full output for failures
```

Configuration: `dev/cross-platform-test.toml` (defaults) and `dev/cross-platform-test.local.toml` (your overrides, gitignored).

### Version Management Workflow
1. Make your changes across core and/or CLI
2. Run tests: `make test`
3. Bump version: `make bump-version VERSION=X.Y.Z`
4. Commit and push to main
5. GitHub Actions handles publishing and release creation

## Important Notes
- Both packages must always have the same version (lockstep)
- Never manually edit version numbers - use `make bump-version`
- The publish workflow validates version match and skips if already published
- GitHub releases include AI-generated summaries (requires ANTHROPIC_API_KEY secret)
- Code should be written assuming it should work across Linux, Windows, and Mac!

## General
Don't make any implementation overly complex. This is a one-person dev MVP project.
We are still pre-customer - any unnecessary fallbacks, unnecessary versioning, testing overkill should be avoided.
2-3 tests per file with only the main happy path tested is fine.
Simple, elegant, maintainable code is the goal.
We DONT want any legacy or backwards compatible code. If you make changes that will break older code that's good, make the new changes and then fix the older code to use the new code.
