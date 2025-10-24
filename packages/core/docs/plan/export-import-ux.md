# Export/Import UX & Implementation

## Overview

Export/import enables sharing complete ComfyUI environments as single `.tar.gz` files. This unlocks the network effect - users can distribute working setups with all dependencies.

**Core Value**: "I can share my entire working setup as a single file that others can import and run immediately"

## Design Principles

1. **Simple, Clear UX** - Three-choice model acquisition (all/required/skip), no complex per-item prompting
2. **Fail Fast on Critical Issues** - Block export on uncommitted changes or unresolved workflows
3. **Allow Partial Success** - Some models/nodes failing during import is OK, user can fix with existing tools
4. **Reuse Existing Tools** - `workflow resolve` handles complex model substitution and interactive fixes post-import
5. **pyproject.toml is the Manifest** - No separate manifest file, pyproject contains all metadata

---

## What Gets Bundled

### Included (in .tar.gz)
- `pyproject.toml` - All config, nodes, model references with hashes, and environment metadata
- `uv.lock` - Python dependency lockfile
- `.python-version` - Python version specification
- `workflows/` - All tracked workflow JSON files
- `dev_nodes/` - Full source code of development nodes (filtered by .gitignore)

### Referenced (downloaded on import)
- **Registry nodes**: By ID + version (downloaded from cache/registry)
- **Git nodes**: By repo URL + commit hash (cloned fresh)
- **Models**: By hash + source URLs (downloaded on import based on strategy)

### Never Included
- Model files (too large - use hash references + source URLs instead)
- Registry/git node binaries (cached globally, re-downloaded on import)
- Virtual environment (`.venv/`) - recreated via `uv.lock`
- ComfyUI itself (cloned fresh during environment creation)

---

## Export Process (Current Implementation)

### Phase 1: Pre-Export Validation

**Goal**: Ensure environment is export-ready before creating bundle.

```bash
$ comfydock export
# or
$ comfydock -e my-env export
```

**Validation Checks** (fail-fast, block export):

1. **Uncommitted workflow changes**
   - Check if workflows in ComfyUI differ from `.cec/workflows/`
   - **If detected**: Error and tell user to commit first
   ```
   ✗ Cannot export with uncommitted workflow changes

   📋 Uncommitted workflows:
     • workflow1.json
     • workflow2.json

   💡 Commit first:
      comfydock commit -m 'Pre-export checkpoint'
   ```

2. **Uncommitted git changes in .cec/**
   - Check if `.cec/` has uncommitted changes (pyproject.toml, uv.lock, etc.)
   - **If detected**: Error and tell user to commit first
   ```
   ✗ Cannot export with uncommitted git changes

   💡 Commit git changes first:
      comfydock commit -m 'Pre-export checkpoint'
   ```

3. **Unresolved workflow issues**
   - Check if any workflows have unresolved nodes or models
   - **If detected**: Error and tell user to resolve first
   ```
   ✗ Cannot export - workflows have unresolved issues

   💡 Resolve workflow issues first:
      comfydock workflow resolve <workflow_name>
   ```

4. **Models without source URLs** (warning, allows proceeding)
   - Check if models lack download source URLs
   - Show first 3 models, allow expanding to see all
   - User can proceed or cancel
   ```
   📦 Exporting environment: my-env

   ⚠️  Export validation:

   3 model(s) have no source URLs.

     • sd15_model.safetensors
       Used by: workflow1.json, workflow2.json
     • custom_lora.safetensors
       Used by: workflow3.json
     • vae_model.safetensors
       Used by: workflow1.json

     ... and 2 more

   ⚠️  Recipients won't be able to download these models automatically.
      Add sources: comfydock model add-source

   Continue export? (y/N) or (s)how all models: _
   ```

   - `y` - Proceed with export
   - `N` or `<enter>` - Cancel export, delete tarball
   - `s` - Show all models without sources, then re-prompt

   **Note**: `--allow-issues` flag bypasses this confirmation

### Phase 2: Bundle Creation

**Goal**: Package environment into distributable `.tar.gz`.

**Bundle Structure**:
```
my_env_export_20250123.tar.gz
├── pyproject.toml          # Full environment config + metadata
├── uv.lock                 # Locked Python dependencies
├── .python-version         # Python version file
├── workflows/              # All tracked workflows
│   ├── workflow1.json
│   └── workflow2.json
└── dev_nodes/              # Development node source code
    └── my-custom-node/
        ├── __init__.py
        ├── nodes.py
        └── requirements.txt
```

**Metadata in pyproject.toml**:
```toml
[tool.comfydock]
version = "2.0.0"
comfyui_version = "v0.2.2"
python_version = "3.11"

[tool.comfydock.nodes]
# All custom nodes with source info

[tool.comfydock.workflows]
# All workflow metadata and resolutions

[tool.comfydock.models]
# Global model table with hashes and sources
```

**Success Output**:
```
✅ Export complete: my_env_export_20250123.tar.gz (12.3 MB)

Share this file to distribute your complete environment!
```

---

## Import Process (Current Implementation)

### Phase 1: Extraction & Validation

```bash
$ comfydock import my_env_export.tar.gz --name imported-env
```

**Steps**:

1. **Extract and validate bundle structure**
   ```python
   # Validate required files exist
   required_files = ["pyproject.toml", "uv.lock", "workflows"]

   # Validate content integrity
   pyproject = toml.loads((temp_dir / "pyproject.toml").read_text())
   metadata = pyproject["tool"]["comfydock"]
   ```

2. **Show import summary**
   ```
   📦 Import Summary:

   Source: my-env (exported 2025-01-23 10:30 UTC)
   ComfyUI: v0.2.2
   Python: 3.11

   Contents:
     • 3 workflows
     • 12 custom nodes (2 dev, 8 registry, 2 git)
     • 8 unique models (23.5 GB total)

   Target environment: imported-env

   [Y] Continue  [c] Cancel
   ```

3. **Version/platform compatibility warnings** (non-blocking)
   ```
   ⚠️  Bundle created with newer comfydock (0.6.0 > 0.5.0)
      May have compatibility issues

   ⚠️  Bundle created on linux, importing to darwin
      May have path/symlink compatibility issues
   ```

### Phase 2: Environment Setup

**Goal**: Create new environment with base ComfyUI.

**Steps**:

1. **Handle name collision**
   ```python
   target_name = args.name
   if workspace.environment_exists(target_name):
       counter = 1
       while workspace.environment_exists(f"{target_name}-{counter}"):
           counter += 1
       target_name = f"{target_name}-{counter}"
       print(f"⚠️  Environment '{args.name}' exists, using '{target_name}'")
   ```

2. **Create environment** (with cleanup on catastrophic failure)
   ```python
   print(f"\n📦 Creating environment '{target_name}'...")
   env = workspace.create_environment(
       name=target_name,
       python_version=metadata["python_version"],
       comfyui_version=metadata["comfyui_version"]
   )
   print("  ✓ Environment created")
   ```

3. **Copy bundle files to environment**
   ```python
   # Overwrite pyproject.toml and uv.lock with imported versions
   shutil.copy(temp_dir / "pyproject.toml", env.pyproject_path)
   shutil.copy(temp_dir / "uv.lock", env.cec_path / "uv.lock")

   # Copy workflows to .cec/workflows
   shutil.copytree(temp_dir / "workflows", env.workflows_cec_path)

   # Copy development nodes to custom_nodes/
   if (temp_dir / "dev_nodes").exists():
       for node_dir in (temp_dir / "dev_nodes").iterdir():
           shutil.copytree(node_dir, env.custom_nodes_path / node_dir.name)
   ```

### Phase 3: Dependency Acquisition

**Goal**: Install nodes and download models with simple UX.

#### Stage 3A: Node Installation

**Summary Display**:
```
📦 Custom Nodes Required:

Registry nodes (8): comfyui-manager, comfyui-impact-pack, ...
Git nodes (2): https://github.com/user/custom-node, ...
Development nodes (2): my-custom-node (bundled), ...

Installing 10 nodes...
```

**Sequential Installation** (partial failure allowed):
```
📦 Installing nodes...

  • comfyui-manager... ✓
  • comfyui-impact-pack... ✓
  • custom-node... ✗ (failed to clone)
  • rgthree-comfy... ✓
  ...

✅ Installed 9/10 nodes
⚠️  1 node(s) failed (can fix later with 'node add')
```

**Design**: Continue on node failures, report in final summary

#### Stage 3B: Model Acquisition (Simplified)

**Aggregate models across workflows**:
```python
# Promote criticality (optional < flexible < required)
for workflow in workflows:
    for model in workflow.models:
        if model.hash in aggregates:
            aggregates[model.hash].criticality = max(
                aggregates[model.hash].criticality,
                model.criticality
            )
```

**Check local availability**:
```python
for hash_key, agg in aggregates.items():
    if model_repository.get_model(hash_key):
        available_models.append(agg)
    else:
        missing_models.append(agg)
```

**Simple acquisition prompt**:
```
📦 Model Acquisition:

8 unique models required (23.5 GB total):
  • Required: 3 models (6.8 GB)
  • Flexible: 3 models (12.5 GB)
  • Optional: 2 models (4.2 GB)

Local availability:
  ✓ 2 models found locally (14.3 GB)
  ⬇ 6 models need download (17.2 GB)

Choose acquisition strategy:
  [a] Download ALL available (17.2 GB)
  [r] Download REQUIRED only (6.8 GB) - recommended
  [s] Skip downloads (I'll handle models manually)

Choice [r]/a/s: _
```

**Execute downloads** (sequential with progress):
```
📥 Downloading 3 model(s)...

[1/3] sd15.safetensors (4.2 GB)
████████████████████████████████ 100% (4.2 GB / 4.2 GB)
  ✓ Complete

[2/3] controlnet_canny.safetensors (2.1 GB)
████████████████████████████████ 100% (2.1 GB / 2.1 GB)
  ✓ Complete

[3/3] vae.safetensors (500 MB)
████████████████████████████████ 100% (500 MB / 500 MB)
  ✓ Complete

✅ Downloaded 3/3 models
```

**Handle download failures** (partial success allowed):
```
[2/3] controlnet_canny.safetensors (2.1 GB)
  ✗ Failed: 401 Unauthorized

✅ Downloaded 2/3 models
⚠️  1 model(s) failed (can fix later with 'workflow resolve')
```

### Phase 4: Finalization

**Goal**: Sync Python environment and finalize.

**Steps**:

1. **Sync Python environment**
   ```
   📦 Syncing Python environment...
     ✓ Complete
   ```

2. **Copy workflows from .cec to ComfyUI**
   ```
   📋 Finalizing workflows...
     ✓ Workflows copied to ComfyUI
   ```

3. **Create initial commit**
   ```
     ✓ Initial commit created
   ```

4. **Final summary**
   ```
   ✅ Import Complete!

   Environment: imported-env

   Workflows: 3 workflows imported

   Custom Nodes: 10/12 installed
     ✓ 2 development nodes (bundled)
     ✓ 8 registry/git nodes installed
     ✗ 2 nodes failed to install

   Models: 6/8 available
     ✓ 2 found locally (14.3 GB)
     ⬇ 4 downloaded (6.3 GB)
     ⊗ 2 skipped

   Next steps:
     1. Set as active: comfydock use imported-env
     2. Run ComfyUI: comfydock run

   Optional - fix remaining issues:
     • Resolve workflows: comfydock workflow resolve <workflow>
     • Add failed nodes: comfydock node add <node-url>
   ```

---

## Implementation Details

### Core Services

**ExportImportManager** (`packages/core/src/comfydock_core/managers/export_import_manager.py`)
- `create_export()` - Create tarball with pyproject, uv.lock, workflows, dev_nodes
- `extract_import()` - Extract tarball to target .cec directory
- `_add_filtered_directory()` - Bundle dev nodes with .gitignore filtering

**Environment** (`packages/core/src/comfydock_core/core/environment.py`)
- `export_environment()` - Validation + bundle creation with callbacks
- `finalize_import()` - Complete import setup after .cec extraction
- `prepare_import_with_model_strategy()` - Convert missing models to download intents

**Workspace** (`packages/core/src/comfydock_core/core/workspace.py`)
- `import_environment()` - Import from tarball
- `import_from_git()` - Import from git repository

**CLI Commands** (`packages/cli/comfydock_cli/global_commands.py`)
- `export_env()` - Export command with UI prompts
- `import_env()` - Import command with UI prompts

### Data Structures

**Export Callbacks**:
```python
class ExportCallbacks(Protocol):
    def on_models_without_sources(self, models: list[ModelWithoutSourceInfo]) -> None:
        """Called when models are missing source URLs."""
```

**Import Callbacks**:
```python
class ImportCallbacks(Protocol):
    def on_phase(self, phase: str, description: str) -> None:
        """Called at start of each import phase."""

    def on_workflow_copied(self, workflow_name: str) -> None:
        """Called when a workflow is copied."""

    def on_node_installed(self, node_name: str) -> None:
        """Called when a node is installed."""

    def on_workflow_resolved(self, workflow_name: str, downloads: int) -> None:
        """Called when a workflow is resolved."""

    def on_error(self, error: str) -> None:
        """Called on non-fatal errors."""

    def on_download_failures(self, failures: list[tuple[str, str]]) -> None:
        """Called when model downloads fail."""
```

**Error Context**:
```python
@dataclass
class ExportErrorContext:
    uncommitted_workflows: list[str] | None = None
    uncommitted_git_changes: bool = False
    has_unresolved_issues: bool = False
```

**Model Info**:
```python
@dataclass
class ModelWithoutSourceInfo:
    """Information about a model missing source URLs during export."""
    filename: str
    hash: str
    workflows: list[str]
```

**Model Aggregation**:
```python
def promote_criticality(current: str, new: str) -> str:
    """Pick most conservative criticality."""
    priority = {"optional": 0, "flexible": 1, "required": 2}
    return max(current, new, key=lambda c: priority[c])
```

---

## Edge Cases & Error Handling

### Export Edge Cases

1. **Uncommitted changes** (blocking)
   - Error with specific fix command
   - No automatic commit

2. **Unresolved workflow issues** (blocking)
   - Error and tell user to run `workflow resolve`
   - No interactive resolution during export

3. **Models without sources** (warning, allows proceeding)
   - Show first 3, allow expanding to see all
   - User confirms or cancels
   - Tarball deleted on cancel

4. **Tarball creation failure**
   - Generic error with exception message

### Import Edge Cases

1. **Environment creation fails** (catastrophic)
   - Cleanup: Remove partially created environment
   - Error out completely

2. **Some nodes fail to install** (partial success)
   - Continue with import
   - Report in final summary
   - User can fix with `node add` or `workflow resolve`

3. **Some models fail to download** (partial success)
   - Continue with import
   - Report in final summary
   - User can fix with `workflow resolve`

4. **Bundle corrupted**
   - Validate structure and content early
   - Error: "Bundle appears corrupted"

5. **Environment name collision**
   - Auto-append suffix: `imported-env-1`, `imported-env-2`, etc.
   - No user prompt

6. **Version mismatch**
   - Warn but allow import (best-effort)

7. **Platform mismatch** (linux→windows)
   - Warn but allow import (may have path issues)

---

## Post-MVP Enhancements

The following features are **not currently implemented** but documented here for future consideration:

### Export Enhancements

1. **Development node size limits**
   - Warn at 50MB
   - Block at 200MB (override with `--allow-large-dev-nodes`)
   - Helps prevent accidentally bundling huge dev nodes

2. **Bundle size estimate before creation**
   - Show estimated size and prompt for confirmation
   - Calculate from pyproject, uv.lock, workflows, dev_nodes sizes
   ```
   📦 Bundle size estimate: 15.3 MB
      Continue? [Y/n]: _
   ```

3. **Hash enrichment during export**
   - Calculate full Blake3 + SHA256 for all models
   - Improves reproducibility and verification
   - Adds 3-5 minutes for large model sets
   ```
   📊 Hash Enrichment:

   5 models do not have full hash information.
   Calculate now? [Y]/s: _
   ```

4. **Interactive resolution during export**
   - Prompt to resolve unresolved issues inline
   - Use existing `InteractiveModelStrategy` and `InteractiveNodeStrategy`
   - Auto-commit after resolution
   - Currently: user must run `workflow resolve` separately

5. **Workflow subset exports**
   - Export specific workflows instead of all
   ```bash
   $ comfydock export --workflows workflow1.json,workflow2.json
   ```

6. **Differential exports**
   - Export only changes since last export
   - Smaller bundles for incremental updates

7. **Export profiles**
   - Minimal (no models), Full (include models), Workflow-only
   ```bash
   $ comfydock export --profile minimal
   ```

### Import Enhancements

1. **Per-model custom prompting**
   - Ask for decision on each model individually
   - Show full context (criticality, workflows, size)
   ```
   📦 sd15.safetensors (4.2 GB)
      Category: checkpoints
      Criticality: REQUIRED - workflow will not function without this
      Used by: workflow1.json, workflow2.json
      Source: https://civitai.com/...

      [Y] Download  [s] Substitute  [x] Skip
      Choice [Y]/s/x: _
   ```

2. **Model substitution during import**
   - Interactive prompting for model substitution
   - Search local models by filename/hash
   - Update workflow references globally
   - Currently: use `workflow resolve` after import

3. **Parallel model downloads**
   - Download multiple models concurrently
   - Aggregate progress bars
   - Faster for large model sets

4. **Automatic model source lookup**
   - Search CivitAI/HuggingFace by hash for missing sources
   - `search_civitai_by_hash()`, `search_huggingface_by_hash()`
   - Reduce manual URL entry

5. **Python version validation**
   - Pre-check if required Python version available
   - Warn if version unavailable before environment creation
   - Currently: uv handles via `.python-version` file

6. **Incremental environment updates**
   - Update existing environment from new bundle
   - Merge/update functionality instead of always creating new
   ```bash
   $ comfydock import bundle.tar.gz --update existing-env
   ```

7. **Download resume on network failure**
   - Resume partial downloads
   - Preserve completed downloads across retries
   - Currently: failed downloads require complete retry

8. **Per-workflow model substitution**
   - Allow per-workflow substitution preferences
   - Currently: substitution is global (affects all workflows using that model)

### General Enhancements

1. **Bundle signing/verification**
   - GPG signatures for bundle authenticity
   - Verify bundle integrity before import

2. **Dry-run mode for export**
   - Show what would be bundled without creating tarball
   ```bash
   $ comfydock export --dry-run
   ```

3. **Better progress tracking**
   - Phase-level progress bars
   - Time estimates for long operations
   - Currently: per-file progress only

4. **Sophisticated cancellation**
   - Ctrl+C cleanup for partial state
   - Currently: Ctrl+C leaves partial state

5. **Export/import logs**
   - Detailed operation logs
   - Useful for debugging failed imports

---

## Success Criteria

**Export works when**:
- User can export environment with all workflows resolved
- Bundle is < 100MB (no model files)
- Export takes < 30 seconds (no hash calculation)
- Clear error messages for blocking issues

**Import works when**:
- New user can import bundle and get minimally viable environment
- Models download automatically for simple cases (all/required strategies)
- User can skip models and fix later with existing tools
- Partial failures don't block import completion
- Final summary clearly shows what succeeded and what needs fixing

**UX wins**:
- Simple three-choice model acquisition (all/required/skip)
- Clear error messages that point to fix commands
- Reuses existing `workflow resolve` for complex cases
- Fast exports (no blocking operations)
- No "death by 1000 prompts" - decisions collected upfront
