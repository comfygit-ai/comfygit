# Deferred Model Downloads - Implementation Plan

## Overview
Move model downloads from interactive resolution to batch execution at the end. This improves UX by collecting all download intents during user interaction, then downloading everything at once.

## Problem
Currently when user selects `[d]` download during `workflow resolve`, the model downloads immediately. This:
- Blocks user interaction during download
- Prevents batching multiple downloads
- Doesn't allow progress overview

## Solution
Store download "intent" in pyproject during interactive resolution, execute batch downloads at end.

## Architecture Principles

**Core Library Purity**: The `comfydock_core` library must remain decoupled from CLI rendering:
- ❌ NO `print()` or `input()` in core library code
- ✅ Use callbacks for all user-facing output (progress, status messages)
- ✅ CLI package (comfydock_cli) provides callback implementations

**Callback Architecture**: Two-level callback system for batch downloads:
1. **Batch coordination callbacks** - Start/complete notifications for the entire batch
2. **Per-file progress callbacks** - Real-time download progress for individual files

---

## Schema Changes

### ManifestWorkflowModel
Add fields to support download intents:

```python
@dataclass
class ManifestWorkflowModel:
    filename: str
    category: str
    criticality: str
    status: str  # "resolved" | "unresolved"
    nodes: list[WorkflowNodeWidgetRef]
    hash: str | None = None
    sources: list[str] = field(default_factory=list)  # NEW: [URL] for download intents
    relative_path: str | None = None  # NEW: target path for download
```

**Download Intent State**:
- `status = "unresolved"` (no hash yet)
- `sources = ["https://civitai.com/..."]`
- `relative_path = "checkpoints/sdxl/model.safetensors"` (user-confirmed path)
- `hash = None`

**Post-Download State**:
- `status = "resolved"`
- `hash = "abc123..."` (actual model hash)
- `sources` and `relative_path` remain for reference
- Model added to global table in pyproject.toml based on new model's index values

### ResolvedModel
Add field to track download target path:

*Note* we use the existing 'model_source' field to add the URL found in the pyproject.toml (or initially specified by the user during interactive resolution).

```python
@dataclass
class ResolvedModel:
    workflow: str
    reference: WorkflowNodeWidgetRef
    resolved_model: ModelWithLocation | None = None
    model_source: str | None = None
    is_optional: bool = False
    match_type: str | None = None  # Existing - will use "download_intent" value
    match_confidence: float = 1.0
    target_path: Path | None = None  # NEW: Where user intends to download model to
```

### ModelResolutionContext
Update to store full ManifestWorkflowModel objects instead of just hashes:

**Current**:
```python
@dataclass
class ModelResolutionContext:
    workflow_name: str
    previous_resolutions: dict[WorkflowNodeWidgetRef, str] = field(default_factory=dict)  # hash only
    # ... other fields
```

**New**:
```python
@dataclass
class ModelResolutionContext:
    workflow_name: str
    previous_resolutions: dict[WorkflowNodeWidgetRef, ManifestWorkflowModel] = field(default_factory=dict)  # Full model
    # ... other fields
```

**Rationale**: Storing the full `ManifestWorkflowModel` gives resolution strategies access to:
- `sources` list (to detect download intents)
- `status` (to distinguish resolved vs unresolved vs optional)
- `relative_path` (for download intents)
- Future extensibility without changing the interface

This avoids passing the entire `PyprojectManager` to the model resolver while still providing rich context.

### BatchDownloadCallbacks
New dataclass for callback-based batch download coordination (keeps core library pure):

```python
@dataclass
class BatchDownloadCallbacks:
    """Callbacks for batch download coordination in core library.

    All callbacks are optional - if None, core library performs operation silently.
    CLI package provides implementations that render to terminal.
    """

    # Called once at start with total number of files
    on_batch_start: Callable[[int], None] | None = None

    # Called before each file download (filename, current_index, total_count)
    on_file_start: Callable[[str, int, int], None] | None = None

    # Called during download for progress updates (bytes_downloaded, total_bytes)
    on_file_progress: Callable[[int, int | None], None] | None = None

    # Called after each file completes (filename, success, error_message)
    on_file_complete: Callable[[str, bool, str | None], None] | None = None

    # Called once at end (success_count, total_count)
    on_batch_complete: Callable[[int, int], None] | None = None
```

**Example CLI Implementation** (in `comfydock_cli/utils/progress.py`):
```python
def create_batch_download_callbacks() -> BatchDownloadCallbacks:
    """Create CLI callbacks for batch downloads with terminal output."""
    return BatchDownloadCallbacks(
        on_batch_start=lambda count: print(f"\n⬇️  Downloading {count} model(s)..."),
        on_file_start=lambda name, idx, total: print(f"\n[{idx}/{total}] {name}"),
        on_file_progress=create_progress_callback(),  # Existing helper
        on_file_complete=lambda name, success, error:
            print("  ✓ Complete") if success else print(f"  ✗ Failed: {error}"),
        on_batch_complete=lambda success, total:
            print(f"\n✅ Downloaded {success}/{total} models")
    )
```

---

## Implementation Steps

### 1. Interactive Strategy (`interactive.py:713-796`)

**Current**: `_handle_download()` downloads immediately
**Change**: Return download intent

```python
def _handle_download(self, reference, context) -> ResolvedModel | None:
    # Get URL from user
    url = input("\nEnter download URL: ").strip()

    # Suggest and confirm path (existing logic)
    suggested_path = context.downloader.suggest_path(...)
    # ... path confirmation loop ...

    # NEW: Return intent instead of downloading
    return ResolvedModel(
        workflow=context.workflow_name,
        reference=reference,
        resolved_model=None,  # Not downloaded yet!
        model_source=url,
        is_optional=False,
        match_type="download_intent",  # NEW marker
        target_path=suggested_path # NEW field
    )
```

### 2. Progressive Write (`workflow_manager.py:108-166`)

**Current**: `_write_single_model_resolution()` expects resolved_model
**Change**: Handle download intent case

```python
def _write_single_model_resolution(self, workflow_name, resolved):
    model_ref = resolved.reference

    if resolved.match_type == "download_intent":
        # NEW: Download intent path
        manifest_model = ManifestWorkflowModel(
            filename=model_ref.widget_value,
            category=self._get_category_for_node_ref(model_ref),
            criticality=self._get_default_criticality(category),
            status="unresolved",  # No hash yet
            nodes=[model_ref],
            sources=[resolved.model_source],  # URL
            relative_path=resolved.target_path  # NEW field
        )
        self.pyproject.workflows.add_workflow_model(workflow_name, manifest_model)
        return

    # Existing logic for resolved models...
```

### 3. Resume Detection (`model_resolver.py:172-206`)

**Current**: `_try_context_resolution()` checks hash lookup from previous_resolutions dict
**Change**: Use full ManifestWorkflowModel to detect download intents

```python
def _try_context_resolution(self, context: ModelResolutionContext, widget_ref: WorkflowNodeWidgetRef) -> ResolvedModel | None:
    """Check if this ref was previously resolved using context lookup."""
    workflow_name = context.workflow_name

    # Check if ref exists in previous resolutions (now contains full ManifestWorkflowModel)
    manifest_model = context.previous_resolutions.get(widget_ref)

    if not manifest_model:
        return None

    # NEW: Check if download intent (has URL but no hash yet)
    if manifest_model.status == "unresolved" and manifest_model.sources:
        # Download intent found - don't re-prompt user
        return ResolvedModel(
            workflow=workflow_name,
            reference=widget_ref,
            match_type="download_intent",
            resolved_model=None,
            model_source=manifest_model.sources[0],  # URL from previous session
            target_path=Path(manifest_model.relative_path) if manifest_model.relative_path else None,
            is_optional=False,
            match_confidence=1.0,
        )

    # Handle optional unresolved models (marked with special status)
    if manifest_model.status == "unresolved" and not manifest_model.sources:
        return ResolvedModel(
            workflow=workflow_name,
            reference=widget_ref,
            match_type="workflow_context",
            resolved_model=None,
            is_optional=True,
            match_confidence=1.0,
        )

    # Handle resolved models - look up in repository by hash
    if manifest_model.hash:
        resolved_model = self.model_repository.get_model(manifest_model.hash)

        if not resolved_model:
            logger.warning(f"Model {manifest_model.hash} in previous resolutions but not found in repository")
            return None

        return ResolvedModel(
            workflow=workflow_name,
            reference=widget_ref,
            match_type="workflow_context",
            resolved_model=resolved_model,
            match_confidence=1.0,
        )

    return None
```

**Key changes**:
- Use `context.previous_resolutions.get(widget_ref)` to get full `ManifestWorkflowModel`
- Check `manifest_model.sources` to detect download intents
- Extract `relative_path` from manifest model for target path
- No need to pass `PyprojectManager` - context provides all needed data

### 4. Batch Download Execution

**Location**: In `Environment.resolve_workflow()` after `fix_resolution()`

**Update Environment.resolve_workflow() signature**:
```python
def resolve_workflow(
    self,
    name: str,
    node_strategy: NodeResolutionStrategy | None = None,
    model_strategy: ModelResolutionStrategy | None = None,
    fix: bool = True,
    download_callbacks: BatchDownloadCallbacks | None = None  # NEW parameter
) -> ResolutionResult:
    """Resolve workflow dependencies - orchestrates analysis and resolution.

    Args:
        name: Workflow name to resolve
        node_strategy: Strategy for resolving missing nodes
        model_strategy: Strategy for resolving ambiguous/missing models
        fix: Attempt to fix unresolved issues with strategies
        download_callbacks: Optional callbacks for batch download progress (CLI provides)

    Returns:
        ResolutionResult with changes made
    """
    # ... existing resolution logic ...

    if result.has_issues and fix:
        result = self.workflow_manager.fix_resolution(
            result,
            node_strategy,
            model_strategy
        )

    # NEW: Execute pending downloads if any download intents exist
    if result.has_download_intents:  # Add this property to ResolutionResult
        download_results = self._execute_pending_downloads(result, download_callbacks)
        # Update result with download outcomes

    return result
```

**New Method** (in Environment class):
```python
def _execute_pending_downloads(
    self,
    result: ResolutionResult,
    callbacks: BatchDownloadCallbacks | None = None
) -> list[DownloadResult]:
    """Execute batch downloads for all download intents in result.

    IMPORTANT: This method is in the core library and must not use print().
    All user-facing output is delivered via callbacks.

    Args:
        result: Resolution result containing download intents
        callbacks: Optional callbacks for progress/status (provided by CLI)

    Returns:
        List of download results
    """
    from comfydock_core.services.model_downloader import DownloadRequest

    # Collect download intents
    intents = [r for r in result.models_resolved if r.match_type == "download_intent"]

    if not intents:
        return []

    # Notify batch start
    if callbacks and callbacks.on_batch_start:
        callbacks.on_batch_start(len(intents))

    results = []
    for idx, resolved in enumerate(intents, 1):
        filename = resolved.reference.widget_value

        # Notify file start
        if callbacks and callbacks.on_file_start:
            callbacks.on_file_start(filename, idx, len(intents))

        # Check if already downloaded (deduplication)
        existing = self.model_downloader.repository.find_by_source_url(resolved.model_source)
        if existing:
            # Reuse existing model - update pyproject with hash
            self.workflow_manager._update_model_hash(
                result.workflow_name,
                resolved.reference,
                existing.hash
            )
            # Notify success (reused existing)
            if callbacks and callbacks.on_file_complete:
                callbacks.on_file_complete(filename, True, None)
            results.append(DownloadResult(success=True, model=existing))
            continue

        # Download new model
        target_path = self.model_downloader.models_dir / resolved.target_path
        request = DownloadRequest(
            url=resolved.model_source,
            target_path=target_path,
            workflow_name=result.workflow_name
        )

        # Use per-file progress callback if provided
        progress_callback = callbacks.on_file_progress if callbacks else None
        download_result = self.model_downloader.download(request, progress_callback=progress_callback)

        if download_result.success:
            # Update pyproject with actual hash
            self.workflow_manager._update_model_hash(
                result.workflow_name,
                resolved.reference,
                download_result.model.hash
            )
            # Notify success
            if callbacks and callbacks.on_file_complete:
                callbacks.on_file_complete(filename, True, None)
        else:
            # Notify failure (model remains unresolved with source in pyproject)
            if callbacks and callbacks.on_file_complete:
                callbacks.on_file_complete(filename, False, download_result.error)

        results.append(download_result)

    # Notify batch complete
    if callbacks and callbacks.on_batch_complete:
        success_count = sum(1 for r in results if r.success)
        callbacks.on_batch_complete(success_count, len(results))

    return results
```

**Key principles**:
- ❌ NO `print()` statements in core library
- ✅ All output via optional callbacks
- ✅ Graceful degradation when callbacks are None (silent operation)
- ✅ CLI provides callback implementations that render to terminal

### 5. Context Building in WorkflowManager

**Location**: `WorkflowManager` needs to populate `ModelResolutionContext.previous_resolutions` with full `ManifestWorkflowModel` objects

**Current** (in `WorkflowManager._build_model_context()`):
```python
def _build_model_context(self, workflow_name: str) -> ModelResolutionContext:
    # Build lookup: widget_ref -> hash
    previous_resolutions = {}
    for manifest_model in self.pyproject.workflows.get_workflow_models(workflow_name):
        for ref in manifest_model.nodes:
            if manifest_model.hash:  # Only add if resolved
                previous_resolutions[ref] = manifest_model.hash  # Just hash
    # ...
```

**New**:
```python
def _build_model_context(self, workflow_name: str) -> ModelResolutionContext:
    """Build model resolution context with full manifest models."""
    # Build lookup: widget_ref -> ManifestWorkflowModel (full object)
    previous_resolutions = {}
    for manifest_model in self.pyproject.workflows.get_workflow_models(workflow_name):
        for ref in manifest_model.nodes:
            # Store full model object (not just hash)
            # This allows strategies to access sources, status, relative_path, etc.
            previous_resolutions[ref] = manifest_model

    return ModelResolutionContext(
        workflow_name=workflow_name,
        previous_resolutions=previous_resolutions,
        search_fn=self._create_search_function(),
        downloader=self.model_downloader,
        auto_select_ambiguous=True
    )
```

**Key change**: Store entire `ManifestWorkflowModel` instead of just the hash string. This enables download intent detection without passing `PyprojectManager` to the resolver.

### 6. CLI Integration

**Location**: CLI command handler (e.g., `comfydock_cli/commands/workflow.py` or similar)

```python
from comfydock_cli.utils.progress import create_batch_download_callbacks

def workflow_resolve(args):
    """CLI command to resolve workflow dependencies."""
    workspace = get_workspace_or_exit()
    env = workspace.get_environment(args.env_name)

    # Create interactive strategies
    node_strategy = InteractiveNodeStrategy()
    model_strategy = InteractiveModelStrategy()

    # Create download callbacks for terminal output
    download_callbacks = create_batch_download_callbacks()

    # Call core library with callbacks
    result = env.resolve_workflow(
        name=args.workflow_name,
        node_strategy=node_strategy,
        model_strategy=model_strategy,
        fix=True,
        download_callbacks=download_callbacks  # CLI provides rendering
    )

    # ... handle result ...
```

**Callbacks implementation** (in `comfydock_cli/utils/progress.py`):
```python
from comfydock_core.models.workflow import BatchDownloadCallbacks

def create_batch_download_callbacks() -> BatchDownloadCallbacks:
    """Create callbacks for batch download progress rendering."""
    return BatchDownloadCallbacks(
        on_batch_start=lambda count: print(f"\n⬇️  Downloading {count} model(s)..."),
        on_file_start=lambda name, idx, total: print(f"\n[{idx}/{total}] {name}"),
        on_file_progress=create_progress_callback(),  # Existing per-file progress
        on_file_complete=lambda name, success, error:
            print("  ✓ Complete") if success else print(f"  ✗ Failed: {error}"),
        on_batch_complete=lambda success, total:
            print(f"\n✅ Downloaded {success}/{total} models")
    )
```

---

## Data Flow Example

### User Downloads Model

**Step 1**: Interactive prompt
```
⚠️  Model not found: mymodel.safetensors
[d] Download from URL

Enter URL: https://civitai.com/api/download/models/123
Model will be downloaded to: checkpoints/sdxl/mymodel.safetensors
[Y] Continue
```

**Step 2**: Progressive write to pyproject
```toml
[[tool.comfydock.workflows.default.models]]
filename = "mymodel.safetensors"
category = "checkpoints"
criticality = "flexible"
status = "unresolved"  # No hash yet
sources = ["https://civitai.com/api/download/models/123"]
relative_path = "checkpoints/sdxl/mymodel.safetensors"
nodes = [{node_id = "3", node_type = "CheckpointLoaderSimple", widget_idx = 0, widget_value = "mymodel.safetensors"}]
```

**Step 3**: User Ctrl+C (no download happened)

**Step 4**: User runs `workflow resolve` again
- `model_resolver._try_context_resolution()` finds entry with `sources` + `status=unresolved`
- Returns `ResolvedModel` with `match_type="download_intent"`
- Skips interactive prompt (already decided)
- Continues to next model

**Step 5**: At end of resolution
- Detects download intent in results
- Executes batch download
- Updates pyproject entry:
```toml
[[tool.comfydock.workflows.default.models]]
filename = "mymodel.safetensors"
status = "resolved"  # NOW has hash
hash = "abc123..."
sources = ["https://civitai.com/api/download/models/123"]
relative_path = "checkpoints/sdxl/mymodel.safetensors"
# ... rest unchanged
```
- Updates pyproject global models table with new model found in index.

---

## Migration Notes

**Existing downloads**: Already have `hash` + `status="resolved"`, no changes needed

**Backward compatibility**: Not needed (pre-customer MVP)

## Additional Schema Changes

### ResolutionResult
Add property to detect download intents:

```python
@dataclass
class ResolutionResult:
    workflow_name: str
    nodes_resolved: list[ResolvedNodePackage] = field(default_factory=list)
    nodes_unresolved: list[WorkflowNode] = field(default_factory=list)
    nodes_ambiguous: list[list[ResolvedNodePackage]] = field(default_factory=list)
    models_resolved: list[ResolvedModel] = field(default_factory=list)
    models_unresolved: list[WorkflowNodeWidgetRef] = field(default_factory=list)
    models_ambiguous: list[list[ResolvedModel]] = field(default_factory=list)

    @property
    def has_download_intents(self) -> bool:
        """Check if any models have download intents pending."""
        return any(m.match_type == "download_intent" for m in self.models_resolved)
```

---

## Implementation Order

For MVP, implement in this sequence:

1. **Schema updates** (data models first)
   - Add `relative_path` to `ManifestWorkflowModel`
   - Add `target_path` to `ResolvedModel`
   - Change `ModelResolutionContext.previous_resolutions` type
   - Add `BatchDownloadCallbacks` dataclass
   - Add `has_download_intents` property to `ResolutionResult`

2. **Context building** (WorkflowManager)
   - Update `_build_model_context()` to store full `ManifestWorkflowModel`

3. **Resume detection** (ModelResolver)
   - Update `_try_context_resolution()` to detect download intents

4. **Interactive strategy** (CLI)
   - Modify `_handle_download()` to return intent instead of downloading

5. **Progressive write** (WorkflowManager)
   - Update `_write_single_model_resolution()` to handle download intents

6. **Batch execution** (Environment)
   - Add `download_callbacks` parameter to `resolve_workflow()`
   - Implement `_execute_pending_downloads()` with callbacks
   - Add `_update_model_hash()` helper method

7. **CLI integration**
   - Create `create_batch_download_callbacks()` in CLI utils
   - Wire up callbacks in CLI command handler

---

## Deferred for Later

### SHA-256 Hash Calculation
Computing additional sha256 hashes during download (for CivitAI/HF matching) can be added later:
- Not critical for MVP functionality
- Current blake3 hashing is sufficient for deduplication
- Can be added incrementally without breaking changes

**Future enhancement** (model_downloader.py):
```python
# Add sha256 alongside blake3
hasher_sha256 = hashlib.sha256()
# ... update in loop ...
# ... store in repository ...
```

---

## Testing

### Unit Tests
1. **Schema serialization** - ManifestWorkflowModel with sources/relative_path to/from TOML
2. **Context resolution** - Detect download intents vs resolved vs optional models
3. **Callback invocation** - Verify all callbacks called with correct parameters
4. **Deduplication** - Same URL downloads once, reuses existing model

### Integration Tests
1. **Download intent storage** - User selects [d], verify pyproject written correctly
2. **Resume after Ctrl+C** - Interrupt resolution, restart, verify intent detected
3. **Batch download flow** - Multiple intents execute in sequence
4. **Callback rendering** - Verify CLI output matches expected format
5. **Mixed resolution** - Some models resolved, some download intents, all handled correctly

### Manual Testing
1. **User workflow**:
   - Run `workflow resolve` on workflow with missing model
   - Select `[d]` download, enter URL, confirm path
   - Press Ctrl+C during resolution
   - Run `workflow resolve` again - should detect intent and not re-prompt
   - Complete resolution - should batch download at end
2. **Multiple downloads** - Workflow with 3+ missing models, verify batch execution
3. **Failed downloads** - Invalid URL, verify error handling and pyproject state

---

## Summary

### Key Architectural Decisions

1. **Callback-based rendering**: Core library uses callbacks for all user-facing output, maintaining separation between business logic and presentation layer

2. **Rich context objects**: `ModelResolutionContext` stores full `ManifestWorkflowModel` objects instead of just hashes, providing strategies with complete information without tight coupling to `PyprojectManager`

3. **Progressive persistence**: Download intents written immediately to `pyproject.toml` with `status="unresolved"` + `sources` list, enabling crash recovery and resume detection

4. **Batch execution in core**: Downloads execute in `Environment.resolve_workflow()` after fix_resolution(), keeping all resolution orchestration in one place

5. **Deduplication at core level**: Check for existing models by source URL before downloading, reuse across workflows

### Benefits

✅ **Non-blocking UX**: User completes all interactive decisions before any downloads start
✅ **Crash-safe**: Download intents persisted immediately, resume without re-prompting
✅ **Batch overview**: See all pending downloads, progress across multiple files
✅ **Core library purity**: No CLI coupling in `comfydock_core`, callbacks enable any frontend (CLI, GUI, API)
✅ **Simple MVP**: Minimal changes to existing code, clear separation of concerns
✅ **Extensible**: Callback architecture supports future features (parallel downloads, retry logic, etc.)

### Files Modified

**Core library** (`comfydock_core`):
- `models/workflow.py` - Add `target_path` to `ResolvedModel`, update `ModelResolutionContext`, add `BatchDownloadCallbacks`, add `has_download_intents` property
- `models/manifest.py` - Add `relative_path` to `ManifestWorkflowModel`
- `resolvers/model_resolver.py` - Update `_try_context_resolution()` to detect download intents
- `managers/workflow_manager.py` - Update context building and handle download intents in progressive write
- `core/environment.py` - Add `download_callbacks` parameter, implement `_execute_pending_downloads()`

**CLI package** (`comfydock_cli`):
- `strategies/interactive.py` - Modify `_handle_download()` to return intent
- `utils/progress.py` - Add `create_batch_download_callbacks()`
- CLI command handler - Wire up callbacks when calling `env.resolve_workflow()`
