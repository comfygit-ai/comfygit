# ComfyDock Documentation Status

## Quick Summary (as of 2025-11-10)

**Overall Progress: 90% Complete**

| Phase | Status | Progress |
|-------|--------|----------|
| **Phase 1: Getting Started** | ✅ Complete | 5/5 files (100%) |
| **Phase 2: User Guide** | ✅ Complete | 20/20 files (100%) |
| **Phase 3: CLI Reference** | ✅ Complete (Auto-generated) | 5/5 files (100%) |
| **Phase 4: Troubleshooting** | ⏳ Partial | 1/5 files (20%) |

**What's Complete:**
- ✅ Getting Started (5 files)
- ✅ User Guide: Workspaces (1 file, 249 lines)
- ✅ User Guide: Environments (3 files, 1,629 lines)
- ✅ User Guide: Custom Nodes (3 files, 1,558 lines)
- ✅ User Guide: Models (4 files, 2,669 lines)
- ✅ User Guide: Workflows (3 files, 1,733 lines)
- ✅ User Guide: Python Dependencies (2 files, 1,428 lines)
- ✅ User Guide: Collaboration (3 files, 2,188 lines)
- ✅ CLI Reference (5 files, auto-generated) **← NEW**

**What's Remaining:**
- ⏳ Troubleshooting (4 files) - ~2-3 hours

**Total Lines Written:** 11,454 lines in User Guide + auto-generated CLI reference

## Overview

This document tracks the status of the ComfyDock v1.0 documentation rewrite. The documentation has been reorganized to reflect the new UV-based architecture and follows an Anthropic-style tone similar to Claude Code docs.

## Completed (Phase 1) - UPDATED 2025-11-09

### Core Structure

- ✅ Moved legacy v0.x docs to `docs/legacy/`
- ✅ Created new directory structure for v1.0 docs
- ✅ Updated `mkdocs.yml` with new navigation
- ✅ Added Material for MkDocs theme with modern features
- ✅ Created custom CSS (`stylesheets/extra.css`)

### Getting Started Section (Complete & Verified)

- ✅ `index.md` - Main landing page with Anthropic-style overview
- ✅ `getting-started/installation.md` - Complete installation guide
- ✅ `getting-started/quickstart.md` - 5-minute quickstart tutorial (CORRECTED)
- ✅ `getting-started/concepts.md` - Deep dive into core concepts (UPDATED)
- ✅ `getting-started/migrating-from-v0.md` - Migration guide for v0.x users (UPDATED)

### User Guide Section (68% Complete - 9,266 lines)

**Completed Sections:**

- ✅ `user-guide/workspaces.md` - Complete workspace management guide (249 lines)
- ✅ `user-guide/workflows/workflow-model-importance.md` - Model importance documentation (283 lines)
- ✅ **Environments/** - All 3 files complete (1,629 lines):
  - `creating-environments.md` (409 lines)
  - `running-comfyui.md` (453 lines)
  - `version-control.md` (767 lines)
- ✅ **Custom Nodes/** - All 3 files complete (1,558 lines):
  - `adding-nodes.md` (486 lines)
  - `managing-nodes.md` (495 lines)
  - `node-conflicts.md` (577 lines)
- ✅ **Models/** - All 4 files complete (2,669 lines):
  - `model-index.md` (578 lines)
  - `downloading-models.md` (658 lines)
  - `managing-models.md` (781 lines)
  - `adding-sources.md` (652 lines)
- ✅ **Workflows/** - All 3 files complete (1,733 lines):
  - `workflow-tracking.md` (764 lines)
  - `workflow-resolution.md` (686 lines)
  - `workflow-model-importance.md` (283 lines)
- ✅ **Python Dependencies/** - All 2 files complete (1,428 lines) - **NEW 2025-11-09**:
  - `py-commands.md` (628 lines) - Complete coverage of py add/remove/list/uv
  - `constraints.md` (800 lines) - Complete coverage of constraint add/list/remove

### Key Features

**Documentation Style:**

- Anthropic Claude Code tone (friendly, practical, actionable)
- Progressive disclosure (beginner → advanced)
- Heavy use of code examples and command outputs
- Admonitions (tips, notes, warnings) for important context
- Tab-based code blocks for platform differences

**Navigation:**

- Sticky tabs for main sections
- Expandable sidebar navigation
- Search with smart highlighting
- Dark/light theme toggle
- Footer navigation

## In Progress / TODO

## Changes Made (2025-11-10)

### CLI Reference Section Complete ✅ (Auto-Generated)

**All 5 CLI reference files completed via automation:**

Created a custom documentation generator (`scripts/generate_cli_reference.py`) that automatically extracts command structure from the argparse parser and generates comprehensive markdown documentation:

1. **global-commands.md** - Auto-generated from argparse:
   - Workspace-level commands: init, list, import, export
   - Model management: model index (find/list/show/status/sync), model download, model add-source
   - System commands: registry (status/update), config, logs
   - Shell completion: completion (install/uninstall/status)
   - Complete usage syntax, arguments, options, defaults, and choices

2. **environment-commands.md** - Auto-generated from argparse:
   - Environment lifecycle: create, use, delete
   - Runtime: run, status, manifest, repair
   - Version control: commit, commit log, rollback
   - Collaboration: pull, push, remote (add/remove/list)
   - Python dependencies: py (add/remove/list/uv), constraint (add/list/remove)

3. **node-commands.md** - Auto-generated from argparse:
   - Node operations: add, remove, update, list, prune
   - Complete options documentation including --dev, --force, --no-test

4. **workflow-commands.md** - Auto-generated from argparse:
   - Workflow operations: list, resolve
   - Model importance management: workflow model importance

5. **shell-completion.md** - Manual content:
   - Shell completion installation and setup for bash/zsh/fish
   - Troubleshooting and manual configuration

**Automation Infrastructure:**

- **Generator script**: `scripts/generate_cli_reference.py`
  - Extracts from `comfydock_cli.cli.create_parser()`
  - Handles nested subcommands recursively
  - Formats arguments, options, defaults, choices
  - Categorizes commands into documentation sections

- **Build integration**: `Makefile`
  - `make generate-cli` - Generate CLI docs manually
  - `make build` - Build docs (auto-generates CLI reference)
  - `make serve` - Dev server (auto-generates CLI reference)
  - `make clean` - Remove build artifacts

- **Documentation**: `scripts/README.md`
  - Generator usage and customization guide
  - When to regenerate
  - Enhancement strategies

**Benefits:**

- ✅ Complete baseline coverage of all 40+ commands
- ✅ Always synchronized with CLI code (single source of truth)
- ✅ Low maintenance (regenerates on every build)
- ✅ Flexible for future enhancement (can be edited or replaced)
- ✅ Simple architecture (one Python script, no complex plugins)

**Phase 3 CLI Reference: 100% COMPLETE** 🎉

All CLI commands are now documented with auto-generated baseline coverage. Documentation can be enhanced manually over time as the API stabilizes.

## Changes Made (2025-01-09)

### Collaboration Section Complete ✅

**All 3 collaboration guides completed (2,188 lines):**

1. **export-import.md (572 lines)** - Complete guide for tarball-based environment sharing:
   - Overview of export/import vs git remotes
   - Export workflow with validation (model sources, uncommitted changes)
   - Import from tarball and git repositories
   - Model download strategies (all, required, skip)
   - Import analysis and preview
   - Development node handling
   - Troubleshooting (CivitAI auth, download failures, import errors)
   - Best practices for exporters and recipients

2. **git-remotes.md (768 lines)** - Complete guide for git-based collaboration:
   - Managing remotes (add, remove, list)
   - Push workflow and requirements
   - Pull workflow with full reconciliation
   - Model download strategies during pull
   - Merge conflict resolution
   - Automatic rollback on failure
   - Version history integration
   - Common workflows (setup, daily work, joining team)
   - Troubleshooting (push rejects, auth issues, detached HEAD)

3. **team-workflows.md (848 lines)** - Best practices and collaboration patterns:
   - Choosing collaboration methods (tarball vs git vs git import)
   - Pattern 1: Single maintainer distribution
   - Pattern 2: Active team development
   - Pattern 3: Template distribution
   - Pattern 4: Hybrid approaches
   - Model management strategies (centralized, individual, hybrid)
   - Communication and coordination practices
   - Team troubleshooting scenarios
   - Security considerations

**Phase 2 User Guide: 100% COMPLETE** 🎉

All 20 user guide files are now complete, totaling 11,454 lines of comprehensive documentation.

## Changes Made (2025-11-09)

### Python Dependencies Section Complete

1. **py-commands.md (628 lines)** - Comprehensive guide for Python package management:
   - All 4 py subcommands: `add`, `remove`, `list`, `uv`
   - Basic usage with real command outputs
   - Advanced features: `--upgrade`, `--group`, `--dev`, `--editable`, `--bounds`
   - Requirements.txt integration
   - 10 common patterns with real-world examples
   - 5 troubleshooting scenarios with solutions
   - Technical "How it works" section
   - Cross-references to related documentation

2. **constraints.md (800 lines)** - Complete guide for dependency constraints:
   - Understanding constraints as meta-dependencies
   - All 3 constraint commands: `add`, `list`, `remove`
   - 7 common constraint patterns (pin, range, CUDA, etc.)
   - 6 real-world use cases with examples
   - 8 advanced patterns (file-based, environment-specific, temporary)
   - 6 troubleshooting scenarios with detailed solutions
   - Technical deep-dive on UV resolution behavior
   - Best practices and integration with node management

## Previous Changes (2025-11-02)

### Accuracy Fixes

1. **Status output corrected** - Updated quickstart.md to match actual CLI output (simplified format)
2. **Commit log output corrected** - Updated to show actual compact format without table headers
3. **Node examples updated** - Replaced all `comfyui-manager` examples with `comfyui-depthflow-nodes` or `comfyui-akatz-nodes`
4. **Added ComfyUI-Manager warning** - Documented that ComfyDock replaces Manager functionality
5. **Constraint example updated** - Changed torch version to match code help text (2.4.1)

### New Documentation

1. **Workspaces guide completed** - Full documentation for workspace management including:
   - Initialization options
   - Configuration commands (config, registry, logs)
   - Registry management
   - Logging and debugging
   - Best practices

2. **Workflow model importance** - New comprehensive guide for model importance feature:
   - Interactive and non-interactive modes
   - Importance levels (required/flexible/optional)
   - Usage patterns and best practices
   - Integration with commit/import/repair

3. **Concepts updated** - Added model importance section to core concepts

### Phase 2: Core User Guide (100% Complete) ✅

**Status Summary:**
- ✅ 20 of 20 files complete
- ✅ 11,454 lines of documentation
- ✅ All sections complete!

**User Guide - Workspaces:**
- ✅ `user-guide/workspaces.md` - Workspace management, configuration (249 lines)

**User Guide - Environments:**
- ✅ `user-guide/environments/creating-environments.md` - Detailed environment creation (409 lines)
- ✅ `user-guide/environments/running-comfyui.md` - Running, stopping, managing (453 lines)
- ✅ `user-guide/environments/version-control.md` - Commit, rollback, commit log (767 lines)

**User Guide - Custom Nodes:**
- ✅ `user-guide/custom-nodes/adding-nodes.md` - Registry, GitHub, local dev (486 lines)
- ✅ `user-guide/custom-nodes/managing-nodes.md` - Update, remove, list (495 lines)
- ✅ `user-guide/custom-nodes/node-conflicts.md` - Resolving dependency conflicts (577 lines)

**User Guide - Models:**
- ✅ `user-guide/models/model-index.md` - How model indexing works (578 lines)
- ✅ `user-guide/models/downloading-models.md` - CivitAI, HuggingFace, direct URLs (658 lines)
- ✅ `user-guide/models/managing-models.md` - Index commands (list, find, show, sync) (781 lines)
- ✅ `user-guide/models/adding-sources.md` - Adding download URLs to models (652 lines)

**User Guide - Workflows:**
- ✅ `user-guide/workflows/workflow-model-importance.md` - Model importance (283 lines)
- ✅ `user-guide/workflows/workflow-resolution.md` - Resolving dependencies (686 lines)
- ✅ `user-guide/workflows/workflow-tracking.md` - How workflows are tracked (764 lines)

**User Guide - Python Dependencies:**
- ✅ `user-guide/python-dependencies/py-commands.md` - py add/remove/list/uv (628 lines)
- ✅ `user-guide/python-dependencies/constraints.md` - Managing constraints (800 lines)

**User Guide - Collaboration:**
- ✅ `user-guide/collaboration/export-import.md` - Tarball export/import (572 lines) **COMPLETED 2025-01-09**
- ✅ `user-guide/collaboration/git-remotes.md` - Remote add/remove/list, push, pull (768 lines) **COMPLETED 2025-01-09**
- ✅ `user-guide/collaboration/team-workflows.md` - Best practices for teams (848 lines) **COMPLETED 2025-01-09**

### Phase 3: CLI Reference (100% Complete - Auto-Generated) ✅

Complete command reference pages auto-generated from argparse parser:

- ✅ `cli-reference/global-commands.md` - init, list, import, export, model, registry, config, logs, completion (auto-generated)
- ✅ `cli-reference/environment-commands.md` - create, use, delete, run, status, repair, commit, rollback, pull, push, remote, py, constraint (auto-generated)
- ✅ `cli-reference/node-commands.md` - node add/remove/list/update/prune (auto-generated)
- ✅ `cli-reference/workflow-commands.md` - workflow list/resolve/model (auto-generated)
- ✅ `cli-reference/shell-completion.md` - completion install/uninstall/status (manual content)

**Note:** Model commands are included in global-commands.md as they are part of the global command structure.

**Auto-Generation System:**
- Generator script: `scripts/generate_cli_reference.py`
- Runs automatically on `make build` and `make serve`
- Extracts from argparse parser for guaranteed accuracy
- Can be enhanced manually or replaced with custom content as needed

### Phase 4: Troubleshooting (5% Complete)

- ⚠️ `troubleshooting/common-issues.md` - FAQ-style solutions (stub only, ~23 lines)
- [ ] `troubleshooting/dependency-conflicts.md` - Resolving node conflicts
- [ ] `troubleshooting/missing-models.md` - Model resolution issues
- [ ] `troubleshooting/uv-errors.md` - UV command failures
- [ ] `troubleshooting/environment-corruption.md` - Repair, cleanup

### Phase 5: Advanced Topics

Future sections (not in current nav):

- [ ] Advanced torch backend configuration
- [ ] Development node workflows
- [ ] Registry cache management
- [ ] CivitAI API configuration
- [ ] Workspace advanced configuration

## Content Guidelines

### Tone & Style (Anthropic-inspired)

**DO:**
- Use friendly, conversational tone
- Start with practical examples
- Include real command outputs
- Use "you" and "your" (not "the user")
- Show before/after states
- Provide "Next steps" at the end
- Use admonitions for tips and warnings

**DON'T:**
- Be overly formal or academic
- Include backwards compatibility notes
- Over-explain every detail
- Add unnecessary fallbacks
- Create complex abstractions

### Structure Pattern

Each guide page should follow:

1. **Title + tagline** - One-sentence description
2. **Prerequisites** (if any)
3. **Core content** - Step-by-step with examples
4. **Common variations** - "What if I want to..."
5. **Troubleshooting** - Quick fixes for common issues
6. **Next steps** - Links to related guides

### Code Example Pattern

```markdown
## Adding a custom node

Add a node from the ComfyUI registry:

\`\`\`bash
cfd node add comfyui-manager
\`\`\`

**Output:**

\`\`\`
🔍 Looking up node: comfyui-manager
✓ Found in registry: ltdrdata/ComfyUI-Manager
📦 Installing dependencies...
✓ Node installed: comfyui-manager
\`\`\`

!!! tip "Add from GitHub"
    \`\`\`bash
    cfd node add https://github.com/ltdrdata/ComfyUI-Manager
    \`\`\`
```

## Building the Docs

### Install dependencies

```bash
cd docs/comfydock-docs
uv sync
```

### Generate CLI reference

```bash
make generate-cli
```

This extracts command documentation from the argparse parser and generates markdown files in `docs/cli-reference/`.

### Local development

```bash
make serve
# Visit http://127.0.0.1:8000
# CLI reference is regenerated automatically
```

### Build static site

```bash
make build
# Output in site/
# CLI reference is regenerated automatically
```

### Clean build artifacts

```bash
make clean
# Removes site/ and generated CLI reference files
```

### Deploy to GitHub Pages

```bash
mkdocs gh-deploy
```

## Migration Notes

### From v0.x docs

The old Docker-based documentation has been moved to `docs/legacy/` and is still accessible via the "Legacy Docs (v0.x)" section in the nav. This allows v0.x users to reference old docs while transitioning.

**Key differences:**

| Aspect | v0.x Docs | v1.0 Docs |
|--------|-----------|-----------|
| Architecture | Docker + GUI | UV + CLI |
| Commands | `comfydock` | `cfd` |
| Focus | Environment cards, mount configs | Commands, git workflow |
| Examples | Screenshots, videos | Terminal commands, output |

## Assets & Media

### TODO: Add media

- [ ] Landing page demo GIF/asciinema
- [ ] Update logo/favicon for v1.0 branding
- [ ] Screenshots for key workflows (optional)

### Current assets

- Logo: `assets/comfy_env_manager-min.png` (reused from v0.x)
- CNAME: Points to custom domain (if configured)

## Review Checklist

Before marking Phase 1 complete:

- [x] All getting-started pages complete and proofread
- [x] mkdocs.yml navigation structure correct
- [x] Legacy docs moved and linked
- [x] Custom CSS working
- [x] Code examples tested and verified against actual CLI
- [x] Output examples match actual command output
- [x] All node examples use comfyui-depthflow-nodes or comfyui-akatz-nodes
- [x] No references to comfyui-manager in examples
- [x] Links between pages working
- [x] Missing commands documented (config, registry, logs, workflow model importance)
- [ ] Spell check all content
- [ ] Technical review by maintainer

## Contributing

When adding new documentation:

1. Follow the structure pattern above
2. Use Anthropic tone guidelines
3. Include practical examples
4. Test all command examples
5. Add to appropriate section in mkdocs.yml
6. Cross-link related pages

## Questions / Decisions Needed

1. **Video/GIFs**: Should we add terminal recordings (asciinema)? If yes, which sections?
2. **API Docs**: Should we auto-generate API docs for core library?
3. **Versioning**: Use mike for version-specific docs?
4. **Translations**: Plan for internationalization?
5. **Search**: Add algolia or stick with built-in?

## Timeline Estimate

- **Phase 1 (Complete)**: ~4 hours ✅
- **Phase 2 (Complete)**: ~14-16 hours ✅
  - ✅ All User Guide sections complete (20 files, 11,454 lines)
- **Phase 3 (Complete)**: ~2 hours (automation setup) ✅
  - ✅ CLI reference auto-generation (5 files, auto-generated)
  - ✅ Saves ~4-6 hours vs manual documentation
- **Phase 4 (Partial)**: ~2-3 hours remaining (troubleshooting)
- **Phase 5 (Optional)**: ~2-3 hours (advanced topics)

**Progress:**
- Completed: ~20-22 hours
- **Total remaining**: ~4-6 hours of writing

**Breakdown:**
- Troubleshooting (4 remaining files): ~2-3 hours
- Advanced Topics (optional): ~2-3 hours

**Time Saved:**
- CLI Reference automation saved ~4-6 hours of manual documentation
- Ongoing savings: CLI docs update automatically with code changes

## Contact

For questions about documentation:

- GitHub Issues: https://github.com/ComfyDock/comfydock/issues
- GitHub Discussions: https://github.com/ComfyDock/comfydock/discussions
