# Export/Import UX & Implementation Plan

## Overview

Export/import enables sharing complete ComfyUI environments as single `.tar.gz` files. This unlocks the network effect - users can distribute working setups with all dependencies.

**Core Value**: "I can share my entire working setup as a single file that others can import and run immediately"

## Key Design Principles

### 1. **Batch Planning Over Sequential Prompting**
   - Collect ALL user decisions upfront (nodes + models)
   - Show complete overview BEFORE any downloads
   - Execute downloads in batch after planning phase
   - Prevents "death by 1000 cuts" UX where users wait after each decision

### 2. **Criticality-Driven Model Acquisition**
   - Show model criticality in every prompt (required/flexible/optional)
   - Aggregate criticality across workflows using **most conservative** rule:
     * `optional + flexible → flexible`
     * `optional + required → required`
     * `flexible + required → required`
   - Offer criticality-based shortcuts:
     * Download ALL
     * Download REQUIRED only
     * Download REQUIRED + FLEXIBLE
     * Custom (decide per model)

### 3. **Context-Rich Decision Making**
   - Every model prompt shows:
     * Size and category
     * Effective criticality with explanation
     * Which workflows use it
     * Download source (if available)
   - Users make informed decisions with full context

### 4. **Comprehensive Final Validation**
   - After import completes, re-analyze all workflows
   - Show per-workflow status (ready vs issues)
   - Clear next steps based on actual state
   - Detailed breakdown of what was acquired

## What Gets Bundled

### Included (in .tar.gz)
- `manifest.json` - Basic export metadata
- `pyproject.toml` - All config, nodes, model references with hashes
- `uv.lock` - Python dependency lockfile
- `.python-version` - Python version used in creating .venv
- `workflows/` - All tracked workflow JSON files
- `dev_nodes/` - Full source code of development nodes (respecting `.gitignore`)

### Referenced (downloaded on import)
- **Registry nodes**: By ID + version (downloaded from cache/registry)
- **Git nodes**: By repo URL + commit hash (cloned fresh)
- **Models**: By hash + source URLs (downloaded or substituted)

### Never Included
- Model files (too large - use hash references instead)
- Registry/git node binaries (cached globally, re-downloaded on import)
- Virtual environment (`.venv/`) - recreated via `uv.lock`
- ComfyUI itself (cloned fresh during environment creation)

## Export Process

### Phase 1: Pre-Export Validation

**Goal**: Ensure environment is commit-ready before expensive operations.

```bash
$ comfydock export my-env
```

**Steps**:

1. **Check for uncommitted changes**
   - Git: Check `.cec/` for uncommitted files
   - Workflows: Check if any workflows modified/new/deleted in ComfyUI
   - **If changes detected**: Error with suggestion to commit first
   - **Rationale**: Export should capture a stable snapshot, not work-in-progress

2. **Analyze all workflows** (quick pass - no fixes)
   - Parse each workflow JSON
   - Extract node types + model references
   - Check against current pyproject.toml resolutions
   - Identify any unresolved issues (missing nodes, ambiguous models, etc.)

3. **Present validation summary**
   ```
   📋 Export Validation Summary:

   Workflows:
     ✓ workflow_1.json (3 nodes, 2 models - all resolved)
     ⚠ workflow_2.json (5 nodes, 4 models - 1 unresolved model)
     ✓ test_workflow.json (2 nodes, 1 model - all resolved)

   Issues Found:
     • workflow_2.json: Model "custom_lora.safetensors" is unresolved

   Options:
     [r] Resolve issues interactively
     [c] Cancel export
   ```

4. **Interactive resolution** (if issues found)
   - Use existing `InteractiveModelStrategy` and `InteractiveNodeStrategy`
   - Walk user through each unresolved issue
   - Allow marking as optional (skip download on import)
   - Save resolutions to pyproject.toml as we go
   - **After resolution complete**: Auto-commit with message "Pre-export resolution"

5. **Final validation checkpoint**
   - Re-analyze all workflows
   - Confirm no remaining issues
   - If still issues and user didn't mark as optional: abort export

### Phase 2: Model Hash Enrichment (Optional)

**Goal**: Calculate full hashes + lookup source URLs for models that need them.

**What we have now** (in model index):
- Short hash (blake3 sample - fast dedup)
- Blake3 full hash (if calculated before)
- SHA256 full hash (if calculated before)
- Source URLs (if model was downloaded via comfydock)

**What we need for export**:
- Blake3 full hash (for verification) - **optional but improves reproducibility**
- SHA256 full hash (for external searches) - **optional but improves reproducibility**
- At least one source URL (civitai/HF/custom)

**Process**:

1. **Collect all model hashes and check enrichment status**
   - Extract from `pyproject.toml` → `[tool.comfydock.workflows.*].models[].hash`
   - Get unique set of model hashes
   - Count how many need full hash calculation

2. **Prompt for hash enrichment** (if models need it)
   ```
   📊 Hash Enrichment Check:

   5 models do not have full hash information calculated.

   Hash enrichment improves reproducibility and enables better
   model verification on import, but can take time for large models.

   Estimated time: ~3-5 minutes

   [Y] Calculate now  [s] Skip (models marked as local-only)

   Choice [Y]/s: _
   ```

3. **Calculate hashes with progress** (if user chooses yes)
   ```python
   models_to_enrich = [m for m in models if m.blake3_hash is None or m.sha256_hash is None]

   for idx, model in enumerate(models_to_enrich, 1):
       print(f"[{idx}/{len(models_to_enrich)}] {model.filename}...")
       full_hashes = repository.calculate_full_hashes(model.hash)
       repository.update_model_hashes(model.hash, full_hashes)
       print(f"  ✓ Complete")
   ```

4. **Check if source URLs exist**
   ```
   sources = repository.get_model_sources(model.hash)

   if not sources:
       # No source URLs - need user input
       print(f"\n📦 Model: {model.filename} ({model.relative_path})")
       print(f"   Size: {model.file_size / (1024**3):.2f} GB")
       print(f"   Hash (SHA256): {model.sha256_hash[:16]}...")
       print(f"\n   No download source found.")
       print(f"   [u] Enter URL")
       print(f"   [s] Skip (mark as 'unknown source')")

       choice = input("Choice [u]/s: ")

       if choice == 'u':
           url = input("Enter download URL: ")
           source_type = detect_url_type(url)  # civitai/huggingface/custom
           repository.add_source(model.hash, source_type, url)
       else:
           # Mark as unknown - won't auto-download on import
           repository.add_source(model.hash, "unknown", "")
   ```

5. **Update pyproject.toml with enriched model data**
   - For each model in `[tool.comfydock.models]`:
     ```toml
     [tool.comfydock.models."abc123..."]
     filename = "sd15.safetensors"
     size = 4265380512
     relative_path = "checkpoints/sd15.safetensors"
     category = "checkpoints"
     blake3_hash = "full_blake3_hash_here..."
     sha256_hash = "full_sha256_hash_here..."
     sources = ["https://civitai.com/api/download/models/123"]
     ```

### Phase 3: Bundle Creation

**Goal**: Package everything into distributable `.tar.gz`.

**Structure**:
```
my_env_export_2025-01-15.tar.gz
├── manifest.json           # export metadata
├── pyproject.toml          # Full environment config
├── uv.lock                 # Python lockfile
├── .python-version         # Python version file
├── workflows/              # All tracked workflows
│   ├── workflow_1.json
│   └── workflow_2.json
└── dev_nodes/              # Development node sources
    ├── my-custom-node/
    │   ├── __init__.py
    │   ├── nodes.py
    │   └── requirements.txt (filtered by .gitignore)
    └── experimental-node/
        └── ...
```

```toml
[tool.comfydock]
version = "2.0.0"
comfyui_version = "v0.2.2"
python_version = "3.11"
```

manifest.json:
```json
{
   "timestamp": "2025-01-15T10:30:00Z",
   "comfydock_version": "0.5.0",
   "environment_name": "my-env",
   "workflows": ["workflow_1.json", "workflow_2.json"],
   "python_version": "3.11",
   "comfyui_version": "v0.2.2",
   "platform": "linux",
   "total_models": 5,
   "total_nodes": 12
}
```

**Steps**:

1. **Create temp directory structure**
   ```python
   temp_dir = tempfile.mkdtemp()
   export_dir = temp_dir / "export"

   # Copy files
   shutil.copy(pyproject_path, export_dir / "pyproject.toml")
   shutil.copy(uv_lock_path, export_dir / "uv.lock")
   shutil.copytree(workflows_cec_path, export_dir / "workflows")
   ```

2. **Bundle development nodes**
   ```python
   dev_nodes = pyproject.nodes.get_by_source("development")

   for node_name, node_info in dev_nodes.items():
       src_path = custom_nodes_path / node_name
       dest_path = export_dir / "dev_nodes" / node_name

       # Filter using node's .gitignore (if exists) + hardcoded fallbacks
       copy_with_gitignore_filter(
           src_path, dest_path,
           fallback_patterns=['__pycache__', '*.pyc', '.git', 'node_modules', '.venv', '*.egg-info']
       )

       # Warn if dev node is large after filtering
       node_size = sum(f.stat().st_size for f in dest_path.rglob('*') if f.is_file())
       if node_size > 50 * 1024 * 1024:  # 50MB
           print(f"⚠ Development node '{node_name}' is {node_size / 1024**2:.1f} MB")
   ```

3. **Estimate and show bundle size**
   ```python
   # Calculate estimated size before creating tarball
   total_size = 0
   total_size += pyproject_path.stat().st_size
   total_size += uv_lock_path.stat().st_size
   total_size += sum(f.stat().st_size for f in workflows_cec_path.rglob('*') if f.is_file())
   if dev_nodes_dir.exists():
       total_size += sum(f.stat().st_size for f in dev_nodes_dir.rglob('*') if f.is_file())

   print(f"\n📦 Bundle size estimate: {total_size / 1024**2:.1f} MB")
   print(f"   Continue? [Y/n]: ", end="")
   if input().lower() == 'n':
       return
   ```

4. **Create .tar.gz**
   ```python
   output_path = workspace_path / f"{env_name}_export_{timestamp}.tar.gz"

   with tarfile.open(output_path, "w:gz") as tar:
       tar.add(export_dir, arcname=".")
   ```

5. **Cleanup and success**
   ```
   ✓ Export complete: my_env_export_2025-01-15.tar.gz (12.5 MB)

   Summary:
     • 3 workflows
     • 12 custom nodes (2 development, 10 registry/git)
     • 5 models (4 with download URLs, 1 unknown source)

   Share this file to distribute your complete environment!
   ```

---

## Import Process

### Phase 1: Validation & Extraction

**Goal**: Unpack and validate export bundle.

```bash
$ comfydock import my_env_export.tar.gz --name imported-env
```

**Steps**:

1. **Extract bundle to temp directory**
   ```python
   temp_dir = tempfile.mkdtemp()

   with tarfile.open(bundle_path, "r:gz") as tar:
       tar.extractall(temp_dir)
   ```

2. **Validate bundle structure**
   ```python
   required_files = ["pyproject.toml", "uv.lock", "workflows"]

   for file in required_files:
       if not (temp_dir / file).exists():
           raise ValueError(f"Invalid bundle: missing {file}")
   ```

3. **Parse pyproject.toml and show import summary**
   ```
   📦 Import Summary:

   Source: my-env (exported 2025-01-15 10:30 UTC)
   ComfyUI: v0.2.2
   Python: 3.11
   Exported by: comfydock v0.5.0

   Contents:
     • 3 workflows
     • 12 custom nodes (2 dev, 8 registry, 2 git)
     • 8 unique models (23.5 GB total)

   Target environment: imported-env
   ```

4. **Version compatibility check**
   ```python
   # Check if bundle was created with newer comfydock version
   current_version = get_current_comfydock_version()
   export_version = pyproject_data.get("export_comfydock_version")

   if export_version and is_newer_version(export_version, current_version):
       print(f"⚠ Bundle created with newer comfydock ({export_version} > {current_version})")
       print("  May have compatibility issues. Proceed with caution.")
   ```

5. **Confirm import**
   ```
   [Y] Continue  [c] Cancel
   Choice [Y]/c: _
   ```

### Phase 2: Environment Setup

**Goal**: Create new environment with base ComfyUI.

**Steps**:

1. **Check for name collision and create environment**
   ```python
   # Check if environment already exists
   target_name = args.name
   if workspace.environment_exists(target_name):
       # Auto-append suffix
       counter = 1
       while workspace.environment_exists(f"{target_name}-{counter}"):
           counter += 1
       target_name = f"{target_name}-{counter}"
       print(f"⚠ Environment '{args.name}' exists, using '{target_name}' instead")

   # Extract metadata from pyproject.toml
   pyproject_data = load_pyproject(temp_dir / "pyproject.toml")
   metadata = pyproject_data["tool"]["comfydock"]

   # Note: uv will handle Python version from .python-version file
   env = workspace.create_environment(
       name=target_name,
       python_version=metadata["python_version"],
       comfyui_version=metadata["comfyui_version"]
   )
   ```

2. **Copy bundle files to environment**
   ```python
   # Overwrite pyproject.toml and uv.lock with imported versions
   shutil.copy(temp_dir / "pyproject.toml", env.pyproject_path)
   shutil.copy(temp_dir / "uv.lock", env.cec_path / "uv.lock")

   # Copy workflows to .cec/workflows
   shutil.copytree(temp_dir / "workflows", env.workflows_cec_path, dirs_exist_ok=True)
   ```

3. **Install development nodes**
   ```python
   if (temp_dir / "dev_nodes").exists():
       for node_dir in (temp_dir / "dev_nodes").iterdir():
           target = env.custom_nodes_path / node_dir.name
           shutil.copytree(node_dir, target)
   ```

### Phase 3: Dependency Acquisition Planning

**Goal**: Collect user decisions for ALL nodes and models BEFORE downloading anything.

This phase uses a **two-stage approach**: Planning (collect decisions) → Execution (batch download).

#### Stage 3A: Node Acquisition Planning

**Why batch nodes?**: With 50+ nodes, sequential prompting is painful. Batch planning lets users make all decisions upfront.

1. **Parse and categorize nodes**
   ```python
   pyproject = PyprojectManager(env.pyproject_path)
   nodes = pyproject.nodes.get_existing()

   registry_nodes = [v for v in nodes.values() if v.source == "registry"]
   git_nodes = [v for v in nodes.values() if v.source == "git"]
   dev_nodes = [v for v in nodes.values() if v.source == "development"]

   # Dev nodes already bundled - no acquisition needed
   nodes_to_acquire = registry_nodes + git_nodes
   ```

2. **Show node summary**
   ```
   📦 Custom Nodes Required:

   Registry nodes (8):
     • comfyui-manager (v1.2.3)
     • comfyui-impact-pack (v4.18)
     • ... (6 more)

   Git nodes (2):
     • https://github.com/user/custom-node (abc123)
     • https://github.com/org/experimental (def456)

   Development nodes (2):
     • my-custom-node (bundled)
     • experimental-node (bundled)

   Total to download: 10 nodes
   ```

3. **Prompt for node acquisition strategy**
   ```
   Choose node installation strategy:
     [a] Install all (recommended)
     [i] Choose interactively

   Choice [a]/i: _
   ```

4. **Collect acquisition plan** based on strategy
   ```python
   node_acquisition_plan = {}

   if strategy == 'install_all':
       # Batch install all nodes
       for node in nodes_to_acquire:
           node_acquisition_plan[node.name] = NodeAcquisitionDecision(
               node=node,
               action="install",
               source=node.download_url or node.repository
           )
   else:
       # Interactive - prompt per node
       for node in nodes_to_acquire:
           print(f"\nInstall '{node.name}'? [Y/n]: ", end="")
           choice = input().lower()
           if choice != 'n':
               node_acquisition_plan[node.name] = NodeAcquisitionDecision(
                   node=node, action="install",
                   source=node.download_url or node.repository
               )
           else:
               print("  ⚠ Workflows requiring this node may not function properly")
   ```

#### Stage 3B: Model Acquisition Planning

**Critical UX Improvement**: Show complete model overview with criticality BEFORE prompting.

1. **Aggregate model criticality across workflows**

   Since same model can appear in multiple workflows with different criticality, use **most conservative** rule:

   ```python
   def aggregate_model_criticality(workflows: dict) -> dict[str, tuple[ManifestWorkflowModel, str]]:
       """Aggregate models across workflows, picking most conservative criticality.

       Promotion rules:
       - optional + flexible → flexible
       - optional + required → required
       - flexible + required → required

       Returns:
           Dict[model_hash] -> (model_data, effective_criticality, workflows_using)
       """
       model_aggregates = {}

       for wf_name, wf_data in workflows.items():
           for model in wf_data.get('models', []):
               hash_key = model.hash

               if hash_key not in model_aggregates:
                   model_aggregates[hash_key] = {
                       'model': model,
                       'criticality': model.criticality,
                       'workflows': [wf_name]
                   }
               else:
                   # Promote criticality if needed
                   current = model_aggregates[hash_key]['criticality']
                   new_crit = promote_criticality(current, model.criticality)
                   model_aggregates[hash_key]['criticality'] = new_crit
                   model_aggregates[hash_key]['workflows'].append(wf_name)

       return model_aggregates

   def promote_criticality(current: str, new: str) -> str:
       """Pick most conservative criticality."""
       priority = {"optional": 0, "flexible": 1, "required": 2}
       return max(current, new, key=lambda c: priority.get(c, 0))
   ```

2. **Check local availability**
   ```python
   available_models = []
   missing_models = []

   for hash_key, agg in model_aggregates.items():
       existing = model_repository.get_model(hash_key)

       if existing:
           available_models.append((hash_key, agg, existing))
       else:
           missing_models.append((hash_key, agg))
   ```

3. **Show condensed model overview** (shows criticality summary upfront)
   ```
   📦 Model Acquisition Overview:

   8 unique models required (23.5 GB total):
     • Required: 3 models (6.8 GB)
     • Flexible: 3 models (12.5 GB)
     • Optional: 2 models (4.2 GB)

   Local availability:
     ✓ 2 models found locally (14.3 GB)
     ⬇ 6 models need acquisition (17.2 GB)

   [v] View detailed list

   Choose acquisition strategy:
     [a] Download ALL available (17.2 GB)
     [r] Download REQUIRED only (4.7 GB)
     [f] Download REQUIRED + FLEXIBLE (17.2 GB)
     [c] Custom (decide for each model)
     [q] Quit import

   Choice [a]/r/f/c/q: _
   ```

   **If user chooses `[v]`** - expand to show full list:
   ```
   Required (3 models, 6.8 GB):
     • sd15.safetensors - 4.2 GB - checkpoints
       Used by: workflow1.json, workflow2.json
     • controlnet_canny.safetensors - 2.1 GB - controlnet
       Used by: workflow1.json
     • vae.safetensors - 500 MB - vae
       Used by: workflow1.json, workflow2.json, workflow3.json

   Flexible (3 models, 12.5 GB):
     [... expanded list ...]

   Optional (2 models, 4.2 GB):
     [... expanded list ...]
   ```

4. **Collect model acquisition decisions** based on strategy

   **Strategy: Auto (`a`)**
   ```python
   for hash_key, agg in missing_models:
       if agg['model'].sources:
           acquisition_plan[hash_key] = ModelAcquisitionDecision(
               model=agg['model'],
               action="download",
               source_url=agg['model'].sources[0],
               target_path=models_dir / agg['model'].relative_path
           )
       else:
           # No source - must skip
           acquisition_plan[hash_key] = ModelAcquisitionDecision(
               model=agg['model'],
               action="skip"
           )
   ```

   **Strategy: Required Only (`r`)**
   ```python
   for hash_key, agg in missing_models:
       if agg['criticality'] == 'required' and agg['model'].sources:
           acquisition_plan[hash_key] = ModelAcquisitionDecision(
               model=agg['model'],
               action="download",
               source_url=agg['model'].sources[0],
               target_path=models_dir / agg['model'].relative_path
           )
       else:
           acquisition_plan[hash_key] = ModelAcquisitionDecision(
               model=agg['model'],
               action="skip"
           )
   ```

   **Strategy: Custom (`c`)** - prompt for each model with FULL context
   ```python
   for hash_key, agg in missing_models:
       model = agg['model']
       criticality = agg['criticality']
       workflows_using = agg['workflows']

       # Show criticality and usage
       print(f"\n📦 {model.filename} ({model.file_size / 1024**3:.1f} GB)")
       print(f"   Category: {model.category}")
       print(f"   Criticality: {criticality.upper()} - ", end="")

       if criticality == "required":
           print("workflow will not function without this")
       elif criticality == "flexible":
           print("can substitute with similar model")
       else:
           print("workflow works without this (optional feature)")

       print(f"   Used by: {', '.join(workflows_using)}")

       if model.sources:
           print(f"   Source: {model.sources[0]}")
       else:
           print(f"   Source: None (must provide or substitute)")

       # Prompt with context-aware options
       if model.sources:
           print("\n   [Y] Download  [s] Substitute  [x] Skip")
           choice = input("   Choice [Y]/s/x: ").lower()
       else:
           print("\n   [s] Substitute  [x] Skip  [u] Enter URL")
           choice = input("   Choice [s]/x/u: ").lower()

       # Process choice...
   ```

5. **Show acquisition plan summary**
   ```
   📋 Acquisition Plan Summary:

   Nodes:
     ⬇ Install: 10 nodes

   Models:
     ⬇ Download: 4 models (6.3 GB)
       • sd15.safetensors (4.2 GB)
       • controlnet_canny.safetensors (2.1 GB)
     ↔ Substitute: 1 model
       • style_lora.safetensors → local_style.safetensors
     ⊗ Skip: 1 model
       • experimental_lora.safetensors
     ✓ Found locally: 2 models (14.3 GB)

   Total download: ~6.3 GB
   Estimated time: 15-20 minutes

   [Y] Execute plan  [e] Edit plan  [c] Cancel
   Choice [Y]/e/c: _
   ```

### Phase 4: Batch Execution

**Goal**: Execute acquisition plan - install nodes and download models.

#### Stage 4A: Node Installation (Sequential)

Nodes must be installed sequentially as they may have dependency order requirements.

```python
print("\n📦 Installing custom nodes...\n")

installed_count = 0
failed_nodes = []

for node_name, decision in node_acquisition_plan.items():
    try:
        print(f"  • Installing {node_name}...", end=" ", flush=True)

        # Use existing add_node logic
        env.add_node(decision.source, no_test=True)

        print("✓")
        installed_count += 1

    except Exception as e:
        print(f"✗ ({e})")
        failed_nodes.append((node_name, str(e)))
        logger.error(f"Failed to install node '{node_name}': {e}", exc_info=True)

print(f"\n✅ Installed {installed_count}/{len(node_acquisition_plan)} nodes")

if failed_nodes:
    print(f"\n⚠️  {len(failed_nodes)} node(s) failed to install")
    print("   Failed nodes will be listed in final summary")
    print("   You can resolve issues after import with 'node add' or 'workflow resolve'")
```

#### Stage 4B: Model Acquisition (Batch with Progress)

Execute all model downloads in sequence with aggregate progress tracking.

**For downloads:**
```python
print("\n📥 Downloading models...\n")

download_tasks = [
    (hash_key, decision)
    for hash_key, decision in model_acquisition_plan.items()
    if decision.action == "download"
]

if download_tasks:
    total_size = sum(decision.model.file_size for _, decision in download_tasks)
    downloaded_size = 0

    results = []

    for idx, (hash_key, decision) in enumerate(download_tasks, 1):
        model = decision.model
        print(f"[{idx}/{len(download_tasks)}] {model.filename} ({model.file_size / 1024**3:.1f} GB)")

        # Download with progress callback
        result = downloader.download(
            request=DownloadRequest(
                url=decision.source_url,
                target_path=decision.target_path,
                workflow_name=None
            ),
            progress_callback=create_progress_callback()
        )

        if result.success:
            print("  ✓ Complete\n")
            downloaded_size += model.file_size
        else:
            print(f"  ✗ Failed: {result.error}\n")

        results.append((hash_key, result))

    # Check for failures
    failed_downloads = [(h, r) for h, r in results if not r.success]

    if failed_downloads:
        print(f"\n⚠️  {len(failed_downloads)} download(s) failed")

        # Offer retry
        print("\nOptions:")
        print("  [r] Retry failed downloads")
        print("  [s] Skip failed and continue")
        print("  [q] Quit import")
```

**For substitutions:**
```python
substitute_tasks = [
    (hash_key, decision)
    for hash_key, decision in model_acquisition_plan.items()
    if decision.action == "substitute"
]

if substitute_tasks:
    print(f"\n🔄 Applying {len(substitute_tasks)} model substitution(s)...")
    print("   Note: Substitutions are global and affect all workflows using this model\n")

    for hash_key, decision in substitute_tasks:
        original = decision.model
        substitute = decision.substitute

        # Update pyproject.toml workflows section (GLOBAL - affects all workflows)
        for wf_name in model_aggregates[hash_key]['workflows']:
            workflow_models = pyproject.workflows.get_workflow_models(wf_name)

            for wf_model in workflow_models:
                if wf_model.hash == hash_key:
                    # Update to point to substitute
                    wf_model.hash = substitute.hash
                    wf_model.filename = substitute.filename

            pyproject.workflows.set_workflow_models(wf_name, workflow_models)

        # Update global models table
        pyproject.models.add_model(ManifestModel.from_model_with_location(substitute))

        print(f"  ✓ {original.filename} → {substitute.filename}")

```

**For skipped models:**
```python
skipped_tasks = [
    (hash_key, decision)
    for hash_key, decision in model_acquisition_plan.items()
    if decision.action == "skip"
]

if skipped_tasks:
    print(f"\n⊗ Skipped {len(skipped_tasks)} model(s):")
    for hash_key, decision in skipped_tasks:
        model = decision.model
        criticality = model_aggregates[hash_key]['criticality']
        print(f"  • {model.filename} ({criticality})")
```

#### Stage 4C: Workflow Path Updates

Update workflow JSON files to reference acquired/substituted models.

```python
print("\n🔧 Updating workflow paths...")

for workflow_name in pyproject.workflows.get_all_with_resolutions().keys():
    workflow_path = env.workflows_cec_path / f"{workflow_name}.json"

    # Load workflow JSON
    workflow = WorkflowRepository.load(workflow_path)

    # Get workflow's models from pyproject
    workflow_models = pyproject.workflows.get_workflow_models(workflow_name)

    # Update each model reference
    for wf_model in workflow_models:
        if wf_model.status == "resolved" and wf_model.hash:
            # Get model from repository
            model = model_repository.get_model(wf_model.hash)

            if model:
                # Update all node references to this model
                for node_ref in wf_model.nodes:
                    if node_ref.node_id in workflow.nodes:
                        node = workflow.nodes[node_ref.node_id]

                        # Only update if it's a known ComfyUI loader node
                        if model_config.is_model_loader_node(node_ref.node_type):
                            # Strip base directory for ComfyUI loaders
                            display_path = strip_base_directory_for_node(
                                node_ref.node_type,
                                model.relative_path
                            )
                            node.widgets_values[node_ref.widget_index] = display_path

    # Save updated workflow
    WorkflowRepository.save(workflow, workflow_path)

print("  ✓ Updated workflow paths")
```

#### Stage 4D: Python Environment Sync

```python
print("\n📦 Syncing Python environment...")
env.uv_manager.sync_project(all_groups=True)
print("  ✓ Complete")
```

### Phase 5: Finalization & Validation

**Goal**: Finalize environment and validate completeness.

**Steps**:

1. **Copy workflows from .cec to ComfyUI**
   ```python
   print("\n📋 Finalizing workflows...")
   env.workflow_manager.restore_all_from_cec()
   print("  ✓ Workflows copied to ComfyUI")
   ```

2. **Create initial commit**
   ```python
   env.commit("Initial import from bundle")
   print("  ✓ Initial commit created")
   ```

3. **Validation check** (re-analyze to confirm status)
   ```python
   print("\n🔍 Validating import...")

   # Re-analyze workflows to check final status
   workflow_status = env.workflow_manager.get_workflow_status()

   total_workflows = len(workflow_status.analyzed_workflows)
   workflows_with_issues = workflow_status.workflows_with_issues

   print(f"  ✓ {total_workflows} workflow(s) imported")

   if workflow_status.is_commit_safe:
       print(f"  ✓ All dependencies satisfied")
   else:
       print(f"  ⚠ {len(workflows_with_issues)} workflow(s) have unresolved issues")
   ```

4. **Final summary**
   ```
   ✅ Import Complete!

   Environment: imported-env

   Workflows: 3 workflows imported
     ✓ workflow1.json (all dependencies satisfied)
     ✓ workflow2.json (all dependencies satisfied)
     ⚠ workflow3.json (1 optional model skipped)

   Custom Nodes: 10/12 installed
     • 2 development nodes (bundled)
     • 8 registry nodes (6 installed, 2 failed)
     • 2 git nodes (cloned)

     Failed nodes:
       ✗ comfyui-broken-node (failed to clone)
       ✗ experimental-node (dependency conflict)

   Models: 7/8 available
     ✓ 2 found locally (14.3 GB)
     ⬇ 4 downloaded (6.3 GB)
     ↔ 1 substituted
     ⊗ 1 skipped (optional)

   Status: Ready to use

   Next steps:
     1. Set as active: comfydock use imported-env
     2. Run ComfyUI: comfydock run

   Optional:
     • Resolve workflow3: comfydock workflow resolve "workflow3"
   ```

   **If issues remain:**
   ```
   ⚠️  Import Complete with Issues

   Environment: imported-env

   Workflows: 3 workflows imported
     ✓ workflow1.json
     ⚠ workflow2.json (1 required model missing)
     ⚠ workflow3.json (2 nodes unresolved)

   Issues found:
     • workflow2: 1 required model not downloaded
     • workflow3: 2 nodes could not be installed (see above)

   Fix issues after import:
     comfydock workflow resolve "workflow2"
     comfydock node add <node-id>  # For failed nodes

   Review logs for details:
     ~/.comfydock/logs/imported-env.log
   ```

---

## Implementation Plan

### Core Services Needed

1. **ExportService** (`packages/core/src/comfydock_core/services/export_service.py`)
   - `validate_for_export()` - Check for uncommitted changes + workflow issues
   - `enrich_model_metadata()` - Calculate full hashes + lookup sources
   - `create_bundle()` - Package into .tar.gz
   - Uses: `PyprojectManager`, `ModelRepository`, `WorkflowManager`, `GitManager`

2. **ImportService** (`packages/core/src/comfydock_core/services/import_service.py`)
   - `validate_bundle()` - Extract and validate structure
   - `install_nodes()` - Download registry/git nodes
   - `resolve_models()` - Download or prompt for models
   - `finalize_import()` - Copy workflows + commit
   - Uses: `WorkspaceFactory`, `ModelDownloader`, `NodeManager`, `WorkflowManager`

3. **ModelHasher** (extend existing `ModelRepository`)
   - `calculate_full_hashes(short_hash)` - Blocking SHA256 + Blake3 calculation
   - `update_model_hashes(short_hash, full_hashes)` - Persist to DB
   - Already exists partially - just need to expose as public API

### CLI Integration

**Global commands** (`packages/cli/comfydock_cli/global_commands.py`):

```python
def export_env(self, args):
    """Export environment to .tar.gz bundle."""
    env = self.workspace.get_environment(args.env_name)

    service = ExportService(env)
    bundle_path = service.export(
        output_path=args.output,
        interactive=not args.no_interactive
    )

    print(f"✓ Export complete: {bundle_path}")

def import_env(self, args):
    """Import environment from .tar.gz bundle."""
    service = ImportService(self.workspace)
    env = service.import_bundle(
        bundle_path=args.bundle,
        env_name=args.name,
        skip_models=args.skip_models,
        skip_nodes=args.skip_nodes
    )

    print(f"✓ Import complete: {env.name}")
```

### Data Structures & Protocols

**Import Strategy Protocol** (new):
```python
class ImportModelAcquisitionStrategy(Protocol):
    """Strategy for acquiring models during environment import.

    Different from ModelResolutionStrategy - that's for resolving
    ambiguous models in workflows. This is for import: we know the
    hash, we just need to decide download/substitute/skip.
    """

    def acquire_model(
        self,
        model: ManifestWorkflowModel,
        criticality: str,  # Aggregated criticality (most conservative)
        workflows_using: list[str],  # Which workflows use this
        context: ImportModelContext
    ) -> ModelAcquisitionDecision | None:
        """Decide how to acquire this model.

        Args:
            model: Model data from pyproject.toml
            criticality: Effective criticality (required/flexible/optional)
            workflows_using: List of workflow names using this model
            context: Import context with repository, downloader, etc.

        Returns:
            Decision (download/substitute/skip) or None to quit
        """
```

**Import Contexts**:
```python
@dataclass
class ImportModelContext:
    """Context for import model acquisition."""
    models_dir: Path
    model_repository: ModelRepository
    downloader: ModelDownloader

    # All models being imported (for overview)
    all_model_aggregates: dict[str, dict]  # hash -> {model, criticality, workflows}

    # Models already available locally
    existing_models: dict[str, ModelWithLocation]

@dataclass
class ImportNodeContext:
    """Context for import node acquisition."""
    env: Environment
    all_nodes: list[NodeInfo]  # All nodes to install
```

**Acquisition Decision Models**:
```python
@dataclass
class ModelAcquisitionDecision:
    """User's decision for how to acquire a model."""
    model: ManifestWorkflowModel
    action: str  # "download" | "substitute" | "skip" | "existing"

    # If download:
    source_url: str | None = None
    target_path: Path | None = None

    # If substitute:
    substitute: ModelWithLocation | None = None

@dataclass
class NodeAcquisitionDecision:
    """Decision for node installation."""
    node: NodeInfo
    action: str  # "install" | "skip" (nodes rarely skipped)
    source: str  # URL or registry ID
```

**Import Results**:
```python
@dataclass
class ImportResult:
    """Final import result with detailed breakdown."""
    success: bool
    environment: Environment | None

    # Nodes
    nodes_installed: int
    nodes_failed: list[tuple[str, str]]  # (node_name, error)

    # Models
    models_downloaded: int
    models_substituted: int
    models_skipped: int
    models_found_local: int
    models_failed: list[tuple[str, str]]  # (filename, error)

    # Validation
    workflows_complete: int  # All deps satisfied
    workflows_with_issues: int

    errors: list[str]

@dataclass
class ModelAggregate:
    """Aggregated model info across workflows."""
    model: ManifestWorkflowModel
    criticality: str  # Most conservative across all workflows
    workflows: list[str]  # Workflows using this model
    total_size: int
```

**Export Bundle** (simplified):
```python
@dataclass
class ExportBundle:
    """Bundle contents for export."""
    pyproject_path: Path
    uv_lock_path: Path
    python_version_path: Path
    workflows_dir: Path
    dev_nodes_dir: Path | None

    def to_tarball(self, output_path: Path) -> Path:
        """Create .tar.gz from bundle contents."""
        # Create manifest.json with basic export metadata
```

---

## Edge Cases & Error Handling

### Export Edge Cases

1. **Uncommitted changes**
   - Error: "Cannot export with uncommitted changes. Commit first."
   - Solution: `comfydock commit -m "Pre-export checkpoint"`

2. **Unresolved workflow issues**
   - Prompt: Interactive resolution using existing strategies
   - Allow: Marking models/nodes as optional
   - Block: Export if critical issues remain

3. **Model missing from disk** (hash in pyproject, file deleted)
   - Error: "Model {filename} referenced but not found in index"
   - Solution: Re-index or remove reference

4. **Development node with large files**
   - Use dev node's own `.gitignore` (if exists) plus fallback patterns
   - Fallback: `__pycache__`, `*.pyc`, `.git`, `node_modules`, `.venv`, `*.egg-info`
   - Warn if dev node > 50MB after filtering

### Import Edge Cases

1. **Version mismatch** (bundle created with newer comfydock)
   - Warn: "Bundle created with newer version - may have compatibility issues"
   - Continue: Best-effort import

2. **Model hash collision** (different file, same hash - unlikely)
   - Prompt: "Existing model with same hash found. Use existing or download?"

3. **Node installation fails**
   - Continue with other nodes
   - Report failed nodes in final summary
   - User can fix after import with `node add` or `workflow resolve`

4. **Network failure during download**
   - Allow: Resume or skip
   - Preserve: Partial progress (completed downloads stay)

---

## Open Questions / Future Enhancements

### MVP Scope (what we're NOT doing yet)

- **Automatic model source lookup**: CivitAI/HF API search by hash
  - For now: Manual URL entry
  - Future: `search_civitai_by_hash()`, `search_huggingface_by_hash()`

- **Parallel model downloads**: Sequential for simplicity
  - Future: Concurrent downloads with progress aggregation

- **Differential exports**: Always full bundle
  - Future: Export only changes since last export

- **Export profiles**: Single export format
  - Future: Minimal (no models), Full (include models), Workflow-only

- **Bundle signing/verification**: No cryptographic verification
  - Future: GPG signatures for bundle authenticity

- **Workflow subset exports**: Export specific workflows instead of all
  - For now: Create separate environments with desired workflows
  - Future: `comfydock export my-env --workflows workflow1.json,workflow2.json`

- **Per-workflow model substitution**: Substitute models for specific workflows only
  - For now: Substitution is global (affects all workflows using that model)
  - Future: Allow per-workflow substitution preferences

- **Incremental environment updates**: Update existing environment from new bundle
  - For now: Import always creates new environment
  - Future: Merge/update functionality

- **Python version mismatch handling**: Explicit version checking
  - For now: uv handles Python version via `.python-version` file automatically
  - Future: Pre-check and warn if version unavailable

### Implementation Priorities

**Phase 1 (MVP)**:
1. Export validation + resolution
2. Model hash enrichment (blocking)
3. Bundle creation (.tar.gz)
4. Import with node installation
5. Import with model download prompts

**Phase 2 (Post-MVP)**:
1. Automatic model source lookup
2. Parallel downloads
3. Progress bars for long operations
4. Better error recovery

---

## Success Criteria

**Export works when**:
- User can export environment with all workflows resolved
- Bundle is < 100MB (no model files)
- Bundle unpacks on different machine
- All metadata preserved (hashes, versions, sources)

**Import works when**:
- New user can import and run workflow immediately
- Models download automatically (if URLs present)
- User can substitute local models (if URLs missing, or criticality == 'flexible' or 'optional')
- Final environment matches original functionality

**UX wins**:
- Clear prompts at each step
- No silent failures (explicit confirmations)
- Resumable on network failures
- Informative error messages
