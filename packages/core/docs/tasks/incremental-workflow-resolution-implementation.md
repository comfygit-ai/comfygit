# Incremental Workflow Resolution Implementation Plan

**Date:** 2025-10-08
**Status:** Planning
**Priority:** High
**Affects:** Workflow resolution, commit flow, error handling, user experience

## Executive Summary

This document outlines **simple, focused improvements** to the workflow resolution system. The current architecture is already good - it supports resumability through git checkpoints and cached resolutions. We just need to add optional dependency support, fix error messages, and add dry-run mode.

**Key Goals:**
1. **Optional Dependencies**: Support marking nodes/models as "optional" for custom node-managed resources (Type 1 & Type 2)
2. **Better Error Messages**: Fix truncated UV errors and silent conflict failures
3. **Dry-Run Preview**: Add --dry-run mode to show all issues without persisting

**What We're NOT Doing:**
- ❌ New Environment API methods (current separation is clean)
- ❌ Incremental persistence phase (already works via commit --allow-issues)
- ❌ Non-interactive commit changes (already works correctly)
- ❌ New result objects (over-engineered for MVP)

## Table of Contents

1. [Current Architecture Analysis](#current-architecture-analysis)
2. [Proposed Architecture](#proposed-architecture)
3. [Implementation Phases](#implementation-phases)
4. [Detailed Changes by Component](#detailed-changes-by-component)
5. [Data Model Changes](#data-model-changes)
6. [User Experience Flows](#user-experience-flows)
7. [Testing Strategy](#testing-strategy)
8. [Migration & Rollout](#migration--rollout)
9. [Open Questions](#open-questions)

---

## Current Architecture Analysis

### Current Resolution Flow (IT ALREADY WORKS!)

```
User: comfydock workflow resolve "my_workflow"
  ↓
1. CLI creates strategies (InteractiveNodeStrategy, InteractiveModelStrategy)
2. CLI calls env.resolve_workflow(name, node_strategy, model_strategy)
3. Environment.resolve_workflow():
   - analyze_workflow() - Parse JSON, extract dependencies
   - resolve_workflow() - Auto-resolve with cache from pyproject.toml
   - fix_resolution(strategies) - Interactive prompts for remaining issues
   - apply_resolution() - Write ALL resolutions to pyproject.toml
  ↓
Result: All decisions saved to pyproject.toml
```

**Resumability (ALREADY WORKS!):**
```
User presses Ctrl+C during fix_resolution()
  ↓
Partial work in memory is lost (this is OK!)
  ↓
User runs: comfydock commit -m "WIP" --allow-issues
  ↓
Saves current pyproject.toml state (with partial resolutions)
  ↓
User runs: comfydock workflow resolve "my_workflow" again
  ↓
Auto-resolve phase uses cached resolutions from pyproject.toml
  ↓
Only unresolved items prompt user (resume complete!)
```

**Commit Flow (ALSO ALREADY WORKS!):**
```
User: comfydock commit -m "message"
  ↓
1. get_workflow_status() - Analyze all workflows
2. Check is_commit_safe (any unresolved issues?)
3. If unresolved AND NOT --allow-issues: Block commit
4. execute_commit():
   - apply_all_resolution() - Apply cached resolutions from pyproject.toml
   - copy_all_workflows() - Copy to .cec
   - git commit
  ↓
Result: No re-prompting! Uses cached resolutions.
```

### Real Problems to Fix

| Problem | Impact | Fix |
|---------|--------|-----|
| **No Optional Support** | Can't handle custom node-managed models (like rife49.pth) | Add [o] option to strategies (Phase 2) |
| **Truncated Errors** | "Pkg-c..." instead of full message | max_hint_length=300 (Phase 1) |
| **Silent Conflicts** | Empty error for facerestore_cf | Fallback warning (Phase 1) |
| **No Preview Mode** | Can't see all issues before starting | --dry-run flag (Phase 3) |

### Current Data Flow

```
WorkflowManager
├── analyze_workflow() → WorkflowDependencies
├── resolve_workflow() → ResolutionResult (auto-resolved)
├── fix_resolution() → ResolutionResult (strategy-resolved)
└── apply_resolution() → Updates pyproject.toml + workflow JSON
    ├── Writes to [tool.comfydock.workflows.<name>]
    ├── Writes to [tool.comfydock.models.required]
    └── Updates workflow JSON model paths
```

**Key Insight**: `apply_resolution()` is ONLY called after ALL resolutions complete. This is the bottleneck.

---

## Why Current Architecture is Good

### Clean Separation (Already Exists!)

**Core (packages/core)**: Business logic only
- Environment class provides high-level API
- WorkflowManager handles resolution orchestration
- No print() or input() in core

**CLI (packages/cli)**: Presentation only
- Creates strategies (InteractiveNodeStrategy, InteractiveModelStrategy)
- Calls Environment.resolve_workflow(name, node_strategy, model_strategy)
- Renders results to user
- Strategies contain all UI logic (prompts, choices)

**Why This Works:**
- ✅ Clean separation: Core has no UI coupling
- ✅ Testable: Core logic can be tested without mocking input()
- ✅ Flexible: Different UIs can provide different strategies
- ✅ Simple: No complex result objects, just use existing models

### Resumability (Through Git Checkpoints!)

**User Workflow:**
```bash
# Start resolving
$ comfydock workflow resolve "my_workflow"
⚠️  Model not found: rife49.pth
Choice: o  # Marks as optional → SAVED

⚠️  Node not found: CustomNode
Choice: ^C  # Ctrl+C (in-memory work lost, that's OK!)

# Checkpoint progress
$ comfydock commit -m "WIP: partial resolution" --allow-issues
✅ Commit successful (git checkpoint created)

# Later, resume
$ comfydock workflow resolve "my_workflow"
# Auto-resolves from pyproject.toml (rife49.pth cached!)
# Only asks about CustomNode
```

**Why This is Better Than "Incremental Persistence":**
- ✅ Uses git (already tested, already works)
- ✅ Explicit checkpointing (user controls when to save)
- ✅ No state management complexity
- ✅ Aligns with "simple, elegant" MVP philosophy

---

## Implementation Phases

### Phase 1: Error Handling Improvements (Low Risk)
**Goal**: Fix truncated errors and silent conflicts
**Estimated Effort**: 2-4 hours
**Files Changed**: 2-3

- [ ] Increase `max_hint_length` to 300 in `uv_error_handler.py`
- [ ] Add fallback warning in `resolution_tester.py` when `parse_uv_conflicts()` fails
- [ ] Test with known error cases (facerestore_cf, pycairo)

### Phase 2: Optional Dependency Support ✅ **COMPLETE**
**Goal**: Add "optional" option to resolution strategies
**Actual Effort**: ~6 hours (completed in previous session)
**Files Changed**: 7

**Core Package (comfydock-core)**:
- ✅ Updated `ModelResolutionStrategy` protocol documentation (protocols.py:59-71)
- ✅ Updated `fix_resolution()` to handle `("optional_unresolved", "")` action (workflow_manager.py)
- ✅ Updated `apply_resolution()` to separate models by category (workflow_manager.py)
- ✅ Updated `resolve_workflow()` to recognize optional resolutions (workflow_manager.py)
- ✅ Updated `model_resolver.py` to check models.optional section
- ✅ ModelHandler already supports category="optional" via **metadata

**CLI Package (comfydock-cli)**:
- ✅ Updated `InteractiveModelStrategy.handle_missing_model()` - adds `[o]` option (line 373, 382)
- ✅ Updated `InteractiveModelStrategy._show_fuzzy_results()` - adds `[o]` in prompt (line 416, 429)
- ✅ Updated `InteractiveModelStrategy.resolve_ambiguous_model()` - adds `[o]` option (line 329, 349-356)
- ✅ Updated `_unified_choice_prompt()` to accept 'o' choice (line 44)

**What Works**:
- Type 1 optional (unresolved): Models not in index can be marked optional via `[o]` → stored as `{unresolved = true}`
- Type 2 optional (nice-to-have): Ambiguous models can be selected and marked optional → stored with full metadata
- Optional nodes: Handled via `node_mappings` with `false` value
- Resolution counting: Optional dependencies count as "resolved" (workflow can commit)

### Phase 3: Dry-Run Mode (Low Risk) - PLANNED
**Goal**: Add --dry-run preview mode
**Estimated Effort**: 2-3 hours
**Files Changed**: 2-3

- [ ] Add `fix=False` parameter to `env.resolve_workflow()` (skip fix_resolution if dry-run)
- [ ] Pass `dry_run` from CLI args to env method
- [ ] Add `--dry-run` flag to argparse in workflow resolve command
- [ ] Display summary of what would be resolved without prompting

---

## Detailed Changes by Component

### 0. New Environment API Methods (`environment.py`)

#### New Method: `resolve_workflow()`
```python
def resolve_workflow(
    self,
    name: str,
    node_strategy: NodeResolutionStrategy | None = None,
    model_strategy: ModelResolutionStrategy | None = None,
    dry_run: bool = False
) -> WorkflowResolutionResult:
    """Resolve a workflow's dependencies with incremental persistence.

    This is the high-level API that CLI calls. Handles all orchestration
    internally and returns a rich result object for rendering.

    Args:
        name: Workflow name
        node_strategy: Strategy for interactive node resolution
        model_strategy: Strategy for interactive model resolution
        dry_run: If True, preview issues without persisting

    Returns:
        WorkflowResolutionResult with all info needed for CLI rendering
    """
    # Orchestrate resolution internally
    dependencies = self.workflow_manager.analyze_workflow(name)

    # Auto-resolve with cache (persist immediately if not dry_run)
    resolution = self.workflow_manager.resolve_workflow(dependencies)
    if not dry_run and (resolution.nodes_resolved or resolution.models_resolved):
        self.workflow_manager.apply_resolution(
            resolution=resolution,
            workflow_name=name,
            model_refs=dependencies.found_models
        )

    # Interactive resolution for remaining issues (with incremental persistence)
    if node_strategy or model_strategy:
        resolution = self.workflow_manager.fix_resolution(
            workflow_name=name,
            resolution=resolution,
            node_strategy=node_strategy,
            model_strategy=model_strategy,
            dry_run=dry_run
        )

    # Return rich result object for CLI rendering
    return WorkflowResolutionResult(
        workflow_name=name,
        dependencies=dependencies,
        resolution=resolution,
        auto_resolved_count=len(resolution.nodes_resolved) + len(resolution.models_resolved),
        unresolved_count=len(resolution.nodes_unresolved) + len(resolution.models_unresolved),
        is_fully_resolved=(
            not resolution.nodes_unresolved and
            not resolution.nodes_ambiguous and
            not resolution.models_unresolved and
            not resolution.models_ambiguous
        ),
        dry_run=dry_run
    )
```

#### New Method: `commit_workflows()`
```python
def commit_workflows(
    self,
    message: str,
    allow_issues: bool = False
) -> CommitResult:
    """Commit all workflows (non-interactive).

    Runs full resolution on all workflows (using cached resolutions),
    validates commit safety, and creates git commit if safe.

    Args:
        message: Commit message
        allow_issues: Allow committing with unresolved issues

    Returns:
        CommitResult with all info needed for CLI rendering

    Raises:
        CDEnvironmentError: If commit unsafe and allow_issues=False
    """
    # Get workflow status
    workflow_status = self.workflow_manager.get_workflow_status()

    # Check if there are any committable changes
    if not self.has_committable_changes():
        return CommitResult(
            success=False,
            message="No changes to commit",
            workflows_changed=0
        )

    # Run full resolution on all workflows (non-interactive)
    # This ensures pyproject.toml is up-to-date with current workflow state
    # Uses cached resolutions from previous interactive sessions
    for workflow in workflow_status.analyzed_workflows:
        # Re-resolve to catch any workflow changes since last resolve
        dependencies = self.workflow_manager.analyze_workflow(workflow.name)
        resolution = self.workflow_manager.resolve_workflow(dependencies)

        # Apply auto-resolved items (no interactive prompts)
        if resolution.nodes_resolved or resolution.models_resolved:
            self.workflow_manager.apply_resolution(
                resolution=resolution,
                workflow_name=workflow.name,
                model_refs=dependencies.found_models
            )

    # Re-check commit safety after resolution
    workflow_status = self.workflow_manager.get_workflow_status()

    # Validate commit safety
    if not workflow_status.is_commit_safe and not allow_issues:
        return CommitResult(
            success=False,
            message="Cannot commit with unresolved issues",
            workflows_with_issues=workflow_status.workflows_with_issues,
            allow_issues_required=True
        )

    # Copy workflows and commit
    self.workflow_manager.copy_all_workflows()
    self.commit(message)

    # Return success result
    return CommitResult(
        success=True,
        message=message,
        workflows_changed=len(workflow_status.sync_status.new) +
                        len(workflow_status.sync_status.modified),
        workflows_added=workflow_status.sync_status.new,
        workflows_modified=workflow_status.sync_status.modified,
        workflows_deleted=workflow_status.sync_status.deleted,
        has_unresolved_issues=not workflow_status.is_commit_safe,
        workflows_with_issues=workflow_status.workflows_with_issues if not workflow_status.is_commit_safe else []
    )
```

#### New Result Objects (`models/workflow.py` or new file `models/results.py`)
```python
@dataclass
class WorkflowResolutionResult:
    """Result of workflow resolution for CLI rendering."""
    workflow_name: str
    dependencies: WorkflowDependencies
    resolution: ResolutionResult
    auto_resolved_count: int
    unresolved_count: int
    is_fully_resolved: bool
    dry_run: bool

    def get_summary(self) -> str:
        """Get human-readable summary."""
        if self.dry_run:
            return f"Preview: {self.auto_resolved_count} auto-resolvable, {self.unresolved_count} need interaction"
        elif self.is_fully_resolved:
            return "✅ All dependencies resolved"
        else:
            return f"⚠️  {self.unresolved_count} issue(s) remain unresolved"

@dataclass
class CommitResult:
    """Result of commit operation for CLI rendering."""
    success: bool
    message: str
    workflows_changed: int = 0
    workflows_added: list[str] = field(default_factory=list)
    workflows_modified: list[str] = field(default_factory=list)
    workflows_deleted: list[str] = field(default_factory=list)
    has_unresolved_issues: bool = False
    workflows_with_issues: list = field(default_factory=list)
    allow_issues_required: bool = False
```

**Rationale**: These methods hide all internal complexity from CLI. CLI just calls them and renders the results.

---

### 1. Resolution Tester (`resolution_tester.py`)

#### Current Code (Lines 86-91):
```python
except Exception as e:
    self.logger.error(f"Error during resolution test: {e}")
    # result.warnings.append(f"Could not test resolution: {str(e)}")  # COMMENTED OUT!
    conflicts = parse_uv_conflicts(str(e))
    result.conflicts.extend(conflicts)
    return result
```

#### Proposed Change:
```python
except Exception as e:
    self.logger.error(f"Error during resolution test: {e}")

    # Try to extract structured conflicts
    conflicts = parse_uv_conflicts(str(e))
    if conflicts:
        result.conflicts.extend(conflicts)
    else:
        # Fallback: Add raw error as warning if parsing failed
        # This ensures users ALWAYS see SOME error message
        result.warnings.append(f"Resolution failed: {str(e)[:500]}")

    return result
```

**Rationale**: Guarantees users see error details even when parsing fails.

---

### 2. UV Error Handler (`uv_error_handler.py`)

#### Current Code (Line 74):
```python
def format_uv_error_for_user(error: UVCommandError, max_hint_length: int = 100) -> str:
```

#### Proposed Change:
```python
def format_uv_error_for_user(error: UVCommandError, max_hint_length: int = 300) -> str:
```

**Rationale**: 100 chars is too short for most UV errors. 300 provides context while staying readable.

**Alternative**: Make it configurable per call-site:
```python
# node_manager.py:272
user_msg = format_uv_error_for_user(e, max_hint_length=300)
```

---

### 3. Model Resolution Strategy Protocol (`protocols.py`)

#### Current Code (Lines 59-71):
```python
def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
    """Handle completely missing model.

    Returns:
        Tuple of ("action", "data") or None to skip
        - ("select", "path/to/model.safetensors"): User selected from index
        - ("skip", ""): User chose to skip
        - None: Cancelled (Ctrl+C)
    """
    ...
```

#### Proposed Change:
```python
def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
    """Handle completely missing model.

    Returns:
        Tuple of ("action", "data") or None to skip
        - ("select", "path/to/model.safetensors"): User selected from index
        - ("optional_unresolved", ""): Mark as Type 1 optional (unresolved, no hash)
        - ("skip", ""): User chose to skip (leave unresolved)
        - None: Cancelled (Ctrl+C)
    """
    ...

def resolve_ambiguous_model(
    self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
) -> ModelWithLocation | None:
    """Choose from multiple model matches.

    Returns:
        ModelWithLocation or None
        - ModelWithLocation: User selected this model
          - If model._mark_as_optional = True: Add to models.optional (Type 2)
          - Otherwise: Add to models.required
        - None: User skipped
    """
    ...
```

#### Node Resolution Strategy Updates
```python
def resolve_unknown_node(self, node_type: str, possible: List[ResolvedNodePackage]) -> ResolvedNodePackage | None:
    """Resolve unknown node.

    Returns:
        ResolvedNodePackage with resolved package, or None for special cases.

        Special return values:
        - None: User skipped (node stays unresolved)
        - ResolvedNodePackage(package_id="__OPTIONAL__", ...): Mark as optional
    """
    ...
```

**Rationale**:
- "optional" models stored in `[tool.comfydock.models.optional]`
- "optional" nodes stored in `[tool.comfydock.node_mappings]` with `false` value
- Both count as "resolved" (workflow can be committed)
- "skip" stays unresolved (workflow has issues)

---

### 4. Interactive Model Strategy (`interactive.py`)

#### Current Code (Lines 371-378):
```python
# No matches - offer manual entry or skip
print("\nNo models found.")
choice = self._unified_choice_prompt("Choice [m]/s: ", num_options=0, has_browse=False)

if choice == 'm':
    path = input("Enter model path: ").strip()
    if path:
        return ("select", path)
return ("skip", "")
```

#### Proposed Change (Handles Both Missing and Found Models):
```python
def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
    """Handle missing model - offers Type 1 optional (unresolved)."""
    print(f"\n⚠️  Model not found: {reference.widget_value}")
    print(f"  in node #{reference.node_id} ({reference.node_type})")

    # Try fuzzy search if available
    if self.search_fn:
        similar = self.search_fn(missing_ref=reference.widget_value, ...)
        if similar:
            return self._show_fuzzy_results(reference, similar)

    # No matches - offer manual entry, optional (Type 1), or skip
    print("\nNo models found.")
    print("  [m] - Manually enter model path")
    print("  [o] - Mark as optional (unresolved)")
    print("  [s] - Skip (leave unresolved)")
    choice = self._unified_choice_prompt("Choice [m]/o/s: ", num_options=0)

    if choice == 'm':
        path = input("Enter model path: ").strip()
        if path:
            return ("select", path)
    elif choice == 'o':
        return ("optional_unresolved", "")  # Type 1: {unresolved = true}
    return ("skip", "")

def resolve_ambiguous_model(
    self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
) -> ModelWithLocation | None:
    """Resolve ambiguous model - offers Type 2 optional (nice-to-have)."""
    print(f"\n🔍 Multiple matches for: {reference.widget_value}")

    # Show candidates...
    for i, model in enumerate(candidates[:10], 1):
        print(f"  {i}. {model.relative_path} ({model.file_size / 1024 / 1024:.1f} MB)")

    print("  [r] - Mark as required (select from above)")
    print("  [o] - Mark as optional nice-to-have (select from above)")
    print("  [s] - Skip")

    choice = self._unified_choice_prompt("Choice [r]/o/s: ", num_options=len(candidates))

    if choice == 's':
        return None
    elif choice == 'o':
        # Select which candidate, but mark as optional
        idx = int(input("Which model? [1]: ").strip() or "1") - 1
        selected = candidates[idx]
        selected._mark_as_optional = True  # Signal to caller
        return selected
    elif choice == 'r':
        idx = int(input("Which model? [1]: ").strip() or "1") - 1
        return candidates[idx]
    else:
        # Numeric choice defaults to required
        idx = int(choice) - 1
        return candidates[idx]
```

**Key Changes**:
1. **Type 1 (Unresolved)**: `handle_missing_model()` returns `("optional_unresolved", "")`
   - Creates `"filename" = {unresolved = true}` in models.optional
2. **Type 2 (Nice-to-have)**: `resolve_ambiguous_model()` adds `[o]` option
   - User selects model from candidates but marks as optional
   - Creates hash-based entry with full metadata in models.optional
3. **Clear distinction**: Different return values signal which type of optional

---

### 5. Workflow Manager - New Incremental Persistence Methods

#### New Method: `apply_single_node_resolution()`
```python
def apply_single_node_resolution(
    self,
    workflow_name: str,
    node_package: ResolvedNodePackage,
    dry_run: bool = False
) -> None:
    """Apply a single node resolution immediately to pyproject.toml.

    This enables incremental persistence - each user decision is saved
    as soon as it's made, not batched at the end.

    Args:
        workflow_name: Name of workflow being resolved
        node_package: The resolved node package
        dry_run: If True, skip actual persistence (preview mode)
    """
    if dry_run:
        logger.debug(f"[DRY-RUN] Would save node: {node_package.package_id}")
        return

    # Normalize GitHub URLs to registry IDs
    normalized_id = self._normalize_package_id(node_package.package_id)

    # Save custom mapping if user-resolved
    if node_package.match_type in ("user_confirmed", "manual", "heuristic"):
        self.pyproject.node_mappings.add_mapping(
            node_package.node_type,
            normalized_id
        )
        logger.info(f"Saved mapping: {node_package.node_type} -> {normalized_id}")

    # Add to workflow's node pack list
    self.pyproject.workflows.add_node_pack(workflow_name, normalized_id)
    logger.info(f"Added node pack '{normalized_id}' to workflow '{workflow_name}'")
```

#### New Method: `apply_single_model_resolution()`
```python
def apply_single_model_resolution(
    self,
    workflow_name: str,
    model_ref: WorkflowNodeWidgetRef,
    model: ModelWithLocation | None,
    is_optional_unresolved: bool = False,
    is_optional_nice_to_have: bool = False,
    dry_run: bool = False
) -> None:
    """Apply a single model resolution immediately to pyproject.toml.

    Handles three cases:
    1. Required model (model provided, both flags False)
    2. Type 1 optional - unresolved (model=None, is_optional_unresolved=True)
    3. Type 2 optional - nice-to-have (model provided, is_optional_nice_to_have=True)

    Args:
        workflow_name: Name of workflow being resolved
        model_ref: The model reference from workflow
        model: The resolved model (None if Type 1 optional or skipped)
        is_optional_unresolved: Type 1 - mark as optional unresolved (filename key)
        is_optional_nice_to_have: Type 2 - mark as optional nice-to-have (hash key)
        dry_run: If True, skip actual persistence (preview mode)
    """
    if dry_run:
        if is_optional_unresolved:
            action = "optional (unresolved)"
        elif is_optional_nice_to_have:
            action = "optional (nice-to-have)"
        elif model:
            action = "required"
        else:
            action = "skipped"
        logger.debug(f"[DRY-RUN] Would save model as {action}: {model_ref.widget_value}")
        return

    if model and not is_optional_nice_to_have:
        # Case 1: Required model (hash key, full metadata)
        self.pyproject.models.add_model(
            model_hash=model.hash,
            filename=model.filename,
            file_size=model.file_size,
            category="required",
            relative_path=model.relative_path
        )

        # Add mapping to workflow (hash as key)
        self.pyproject.workflows.add_model_mapping(
            workflow_name=workflow_name,
            model_hash=model.hash,
            node_id=model_ref.node_id,
            widget_idx=model_ref.widget_index
        )

        # Update workflow JSON with resolved path
        self.update_workflow_model_paths(
            workflow_name=workflow_name,
            resolution=ResolutionResult(models_resolved={model_ref: model})
        )

        logger.info(f"Resolved model: {model_ref.widget_value} -> {model.filename}")

    elif is_optional_nice_to_have and model:
        # Case 2: Type 2 optional - nice-to-have (hash key, full metadata)
        self.pyproject.models.add_model(
            model_hash=model.hash,
            filename=model.filename,
            file_size=model.file_size,
            category="optional",  # Different category!
            relative_path=model.relative_path,
            # Include sources if available for export
            sources=getattr(model, 'sources', [])
        )

        # Add mapping to workflow (hash as key, same as required)
        self.pyproject.workflows.add_model_mapping(
            workflow_name=workflow_name,
            model_hash=model.hash,
            node_id=model_ref.node_id,
            widget_idx=model_ref.widget_index
        )

        # Update workflow JSON with resolved path
        self.update_workflow_model_paths(
            workflow_name=workflow_name,
            resolution=ResolutionResult(models_resolved={model_ref: model})
        )

        logger.info(f"Resolved as optional (nice-to-have): {model_ref.widget_value}")

    elif is_optional_unresolved:
        # Case 3: Type 1 optional - unresolved (filename key, minimal data)
        self.pyproject.models.add_model(
            model_hash=model_ref.widget_value,  # Filename as key!
            filename=model_ref.widget_value,
            file_size=0,
            category="optional",
            unresolved=True  # Minimal data
        )

        # Add mapping to workflow (filename as key for unresolved)
        self.pyproject.workflows.add_model_mapping(
            workflow_name=workflow_name,
            model_hash=model_ref.widget_value,  # Filename as key!
            node_id=model_ref.node_id,
            widget_idx=model_ref.widget_index
        )

        # Do NOT update workflow JSON (leave original filename)

        logger.info(f"Marked as optional (unresolved): {model_ref.widget_value}")

    else:
        # Skipped - don't persist anything
        logger.debug(f"Skipped model: {model_ref.widget_value}")
```

#### Refactored Method: `fix_resolution()`

**Current Code (Lines 525-636)**: Collects ALL resolutions, then calls `apply_resolution()` once at end

**Proposed Change**:
```python
def fix_resolution(
    self,
    workflow_name: str,  # NEW: Need workflow name for incremental saves
    resolution: ResolutionResult,
    node_strategy: NodeResolutionStrategy | None = None,
    model_strategy: ModelResolutionStrategy | None = None,
    dry_run: bool = False,  # NEW: Support dry-run mode
) -> ResolutionResult:
    """Fix remaining issues using strategies with INCREMENTAL PERSISTENCE.

    Each resolution decision is saved immediately to pyproject.toml, allowing
    users to Ctrl+C and resume later without losing progress.

    Args:
        workflow_name: Name of workflow (for incremental saves)
        resolution: Result from resolve_workflow()
        node_strategy: Strategy for handling unresolved/ambiguous nodes
        model_strategy: Strategy for handling ambiguous/missing models
        dry_run: If True, preview issues without persisting

    Returns:
        Updated ResolutionResult with fixes applied
    """
    nodes_to_add = list(resolution.nodes_resolved)
    models_to_add = dict(resolution.models_resolved)

    remaining_nodes_ambiguous = []
    remaining_nodes_unresolved = []
    remaining_models_ambiguous = []
    remaining_models_unresolved = []

    # Fix ambiguous nodes - SAVE EACH IMMEDIATELY
    if node_strategy:
        for packages in resolution.nodes_ambiguous:
            selected = node_strategy.resolve_unknown_node(packages[0].node_type, packages)
            if selected:
                # INCREMENTAL SAVE - persist immediately!
                self.apply_single_node_resolution(
                    workflow_name=workflow_name,
                    node_package=selected,
                    dry_run=dry_run
                )
                nodes_to_add.append(selected)
                logger.info(f"✓ Resolved ambiguous node: {selected.package_id}")
            else:
                remaining_nodes_ambiguous.append(packages)
    else:
        remaining_nodes_ambiguous = list(resolution.nodes_ambiguous)

    # Handle unresolved nodes - SAVE EACH IMMEDIATELY
    if node_strategy:
        for node in resolution.nodes_unresolved:
            selected = node_strategy.resolve_unknown_node(node.type, [])
            if selected:
                # INCREMENTAL SAVE - persist immediately!
                self.apply_single_node_resolution(
                    workflow_name=workflow_name,
                    node_package=selected,
                    dry_run=dry_run
                )
                nodes_to_add.append(selected)
                logger.info(f"✓ Resolved unresolved node: {selected.package_id}")
            else:
                remaining_nodes_unresolved.append(node)
    else:
        remaining_nodes_unresolved = list(resolution.nodes_unresolved)

    # Fix ambiguous models - SAVE EACH IMMEDIATELY
    if model_strategy:
        for model_ref, candidates in resolution.models_ambiguous:
            resolved = model_strategy.resolve_ambiguous_model(model_ref, candidates)
            if resolved:
                # Check if user wants this as optional (Type 2: nice-to-have)
                is_optional = getattr(resolved, '_mark_as_optional', False)

                # INCREMENTAL SAVE - persist immediately!
                self.apply_single_model_resolution(
                    workflow_name=workflow_name,
                    model_ref=model_ref,
                    model=resolved,
                    is_optional_nice_to_have=is_optional,
                    dry_run=dry_run
                )
                models_to_add[model_ref] = resolved

                if is_optional:
                    logger.info(f"✓ Resolved as optional: {resolved.filename}")
                else:
                    logger.info(f"✓ Resolved ambiguous model: {resolved.filename}")
            else:
                remaining_models_ambiguous.append((model_ref, candidates))
    else:
        remaining_models_ambiguous = list(resolution.models_ambiguous)

    # Handle missing models - SAVE EACH IMMEDIATELY
    if model_strategy:
        for model_ref in resolution.models_unresolved:
            try:
                result = model_strategy.handle_missing_model(model_ref)

                if result is None:
                    # Cancelled or skipped
                    remaining_models_unresolved.append(model_ref)
                    continue

                action, data = result

                if action == "select":
                    # User provided explicit path
                    path = data
                    model = self.model_repository.find_by_exact_path(path)

                    if model:
                        # INCREMENTAL SAVE - persist immediately!
                        self.apply_single_model_resolution(
                            workflow_name=workflow_name,
                            model_ref=model_ref,
                            model=model,
                            dry_run=dry_run
                        )
                        models_to_add[model_ref] = model
                        logger.info(f"✓ Resolved: {model_ref.widget_value} -> {path}")
                    else:
                        logger.warning(f"Model not found in index: {path}")
                        remaining_models_unresolved.append(model_ref)

                elif action == "optional_unresolved":
                    # NEW: Mark as Type 1 optional (unresolved, no hash)
                    # INCREMENTAL SAVE - persist immediately!
                    self.apply_single_model_resolution(
                        workflow_name=workflow_name,
                        model_ref=model_ref,
                        model=None,
                        is_optional_unresolved=True,
                        dry_run=dry_run
                    )
                    logger.info(f"✓ Marked as optional (unresolved): {model_ref.widget_value}")

                elif action == "skip":
                    remaining_models_unresolved.append(model_ref)
                    logger.info(f"Skipped: {model_ref.widget_value}")

            except KeyboardInterrupt:
                logger.info("Cancelled - remaining models stay unresolved")
                remaining_models_unresolved.append(model_ref)
                # Re-raise to exit the loop
                raise
    else:
        remaining_models_unresolved = list(resolution.models_unresolved)

    return ResolutionResult(
        nodes_resolved=nodes_to_add,
        nodes_unresolved=remaining_nodes_unresolved,
        nodes_ambiguous=remaining_nodes_ambiguous,
        models_resolved=models_to_add,
        models_unresolved=remaining_models_unresolved,
        models_ambiguous=remaining_models_ambiguous,
    )
```

**Key Changes**:
1. Added `workflow_name` parameter (required for incremental saves)
2. Added `dry_run` parameter (for preview mode)
3. Call `apply_single_node_resolution()` after EACH node decision
4. Call `apply_single_model_resolution()` after EACH model decision
5. Handle new "optional" action from model strategy
6. Preserve KeyboardInterrupt behavior (allows Ctrl+C to exit cleanly)

---

### 6. CLI Workflow Resolve Command (`env_commands.py`)

#### Current Code: Too complex, leaks workflow_manager abstractions

#### Proposed Change (CLEAN API):
```python
def workflow_resolve(self, args, logger=None):
    """Resolve workflow dependencies (CLI just renders results)."""
    env = self._get_env(args)

    # Choose strategies (only thing CLI does besides rendering)
    if getattr(args, 'auto', False):
        from comfydock_core.strategies.auto import AutoNodeStrategy, AutoModelStrategy
        node_strategy = AutoNodeStrategy()
        model_strategy = AutoModelStrategy()
    else:
        node_strategy = InteractiveNodeStrategy(
            search_fn=lambda **kwargs: env.search_node_packages(**kwargs),
            installed_packages=env.get_installed_nodes()
        )
        model_strategy = InteractiveModelStrategy(
            search_fn=lambda **kwargs: env.search_models(**kwargs)
        )

    # Call Environment API (all business logic hidden)
    try:
        result = env.resolve_workflow(
            name=args.name,
            node_strategy=node_strategy,
            model_strategy=model_strategy,
            dry_run=getattr(args, 'dry_run', False)
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Resolution interrupted")
        print(f"\n💡 Progress saved! Run again to continue:")
        print(f"   comfydock workflow resolve \"{args.name}\"")
        sys.exit(0)
    except Exception as e:
        if logger:
            logger.error(f"Resolution failed: {e}", exc_info=True)
        print(f"✗ Failed to resolve: {e}", file=sys.stderr)
        sys.exit(1)

    # Render results (presentation only)
    self._render_resolution_result(result)

    # Optional: Prompt for node installation
    if result.is_fully_resolved and not result.dry_run:
        self._maybe_install_nodes(env, args, logger)

def _render_resolution_result(self, result: WorkflowResolutionResult):
    """Render resolution results to user."""
    if result.dry_run:
        print(f"\n🔍 Preview for '{result.workflow_name}':")
        print(f"  • {result.auto_resolved_count} auto-resolvable")
        print(f"  • {result.unresolved_count} need interaction\n")
        # Show detailed breakdown...
    elif result.is_fully_resolved:
        print(f"\n✅ All dependencies resolved for '{result.workflow_name}'!")
        print("\n💡 Next: comfydock commit -m 'Add workflow'")
    else:
        print(f"\n⚠️  {result.unresolved_count} issue(s) remain")
        print("\n💡 Run again to continue or commit with --allow-issues")

def _maybe_install_nodes(self, env, args, logger):
    """Prompt to install missing node packs."""
    uninstalled = env.get_uninstalled_nodes()
    if not uninstalled:
        return

    print(f"\n📦 {len(uninstalled)} node pack(s) need installation:")
    for node_id in uninstalled:
        print(f"  • {node_id}")

    if getattr(args, 'install', False) or input("\nInstall? (Y/n): ").lower() in ['', 'y']:
        for node_id in uninstalled:
            try:
                print(f"  Installing {node_id}...", end=" ")
                env.add_node(node_id)
                print("✓")
            except Exception as e:
                print(f"✗ ({e})")
```

**Key Improvements**:
- **60 lines** instead of 270+ lines
- **No leaked abstractions** - doesn't touch `workflow_manager`, `pyproject`, etc.
- **Clean API** - just calls `env.resolve_workflow()` and renders result
- **Separation of concerns** - Environment handles business logic, CLI renders
- **Search functions provided by Environment** - no direct manager access

---

### 7. CLI Commit Command (`env_commands.py`)

#### Current Code: Too complex, re-prompts user, leaks abstractions

#### Proposed Change (CLEAN API):
```python
def commit(self, args, logger=None):
    """Commit workflows (non-interactive)."""
    env = self._get_env(args)

    print("📋 Analyzing workflows...")

    # Call Environment API (all business logic hidden)
    try:
        result = env.commit_workflows(
            message=args.message or "Update workflows",
            allow_issues=getattr(args, 'allow_issues', False)
        )
    except Exception as e:
        if logger:
            logger.error(f"Commit failed: {e}", exc_info=True)
        print(f"✗ Commit failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Render results (presentation only)
    if not result.success:
        if result.allow_issues_required:
            print("\n⚠ Cannot commit - workflows have unresolved issues:\n")
            for wf in result.workflows_with_issues:
                print(f"  • {wf.name}: {wf.issue_summary}")
            print("\n💡 Options:")
            print("  1. Resolve: comfydock workflow resolve \"<workflow>\"")
            print("  2. Force: comfydock commit -m 'msg' --allow-issues")
        else:
            print(f"✓ {result.message}")
        sys.exit(0 if not result.allow_issues_required else 1)

    # Success
    print(f"✅ {result.message}")
    if result.workflows_added:
        print(f"  • Added {len(result.workflows_added)} workflow(s)")
    if result.workflows_modified:
        print(f"  • Updated {len(result.workflows_modified)} workflow(s)")
    if result.workflows_deleted:
        print(f"  • Deleted {len(result.workflows_deleted)} workflow(s)")

    # Warn if committed with issues
    if result.has_unresolved_issues:
        print("\n⚠️  Committed with unresolved issues")
        print("💡 You can rollback and try different resolutions later")
```

**Key Improvements**:
- **30 lines** instead of 100+ lines
- **No leaked abstractions** - doesn't touch `workflow_manager` or `workflow_status`
- **Clean API** - just calls `env.commit_workflows()` and renders result
- **Separation of concerns** - Environment handles all resolution logic
- **No strategy injection** - commit is purely non-interactive

---

### 8. Environment.execute_commit() (`environment.py`)

#### Current Code (Lines 417-469):
```python
def execute_commit(
    self,
    workflow_status: DetailedWorkflowStatus,
    message: str,
    node_strategy: NodeResolutionStrategy | None = None,
    model_strategy: ModelResolutionStrategy | None = None,
    allow_issues: bool = False
) -> None:
    """Execute commit with workflow resolution."""

    # Safety check
    if not workflow_status.is_commit_safe and not allow_issues:
        raise CDEnvironmentError("Cannot commit with unresolved workflow issues")

    # Apply resolutions (may re-prompt user!)
    if workflow_status.is_commit_safe or allow_issues:
        logger.info("Committing all changes...")
        # Apply all resolutions to pyproject.toml (updates ComfyUI workflows)
        self.workflow_manager.apply_all_resolution(workflow_status)
        # Copy workflows AFTER resolution
        logger.info("Copying workflows from ComfyUI to .cec...")
        copy_results = self.workflow_manager.copy_all_workflows()
        copied_count = len([r for r in copy_results.values() if r and r != "deleted"])
        logger.debug(f"Copied {copied_count} workflow(s)")
        # TODO: Create message if not provided
        self.commit(message)
        return

    logger.error("No changes to commit")
```

#### Proposed Change:
```python
def execute_commit(
    self,
    workflow_status: DetailedWorkflowStatus,
    message: str,
    allow_issues: bool = False
) -> None:
    """Execute NON-INTERACTIVE commit (validation + persistence only).

    This method assumes all interactive resolution has already been done
    via `workflow resolve`. It simply validates commit safety and persists
    existing resolutions to .cec + git.

    Args:
        workflow_status: Current workflow analysis
        message: Commit message
        allow_issues: Whether to allow committing with unresolved issues

    Raises:
        CDEnvironmentError: If commit is unsafe and allow_issues=False
    """

    # Safety check (should already be done in CLI, but double-check)
    if not workflow_status.is_commit_safe and not allow_issues:
        raise CDEnvironmentError(
            "Cannot commit with unresolved workflow issues. "
            "Run 'workflow resolve' first or use --allow-issues."
        )

    logger.info("Committing all changes...")

    # Apply existing resolutions to pyproject.toml (NO PROMPTING)
    # This is idempotent - safe to call even if already applied
    self.workflow_manager.apply_all_resolution(workflow_status)

    # Copy workflows from ComfyUI to .cec
    logger.info("Copying workflows from ComfyUI to .cec...")
    copy_results = self.workflow_manager.copy_all_workflows()
    copied_count = len([r for r in copy_results.values() if r and r != "deleted"])
    logger.debug(f"Copied {copied_count} workflow(s)")

    # Git commit
    self.commit(message)
    logger.info(f"Committed with message: {message}")
```

**Key Changes**:
1. **REMOVED** `node_strategy` and `model_strategy` parameters
2. Made `apply_all_resolution()` idempotent (safe to call multiple times)
3. Clearer error message referencing `workflow resolve`
4. Added docstring clarifying non-interactive nature

---

## Data Model Changes

### PyprojectManager - New Methods

#### WorkflowHandler - New Method: `add_node_pack()`
```python
def add_node_pack(self, workflow_name: str, node_pack_id: str) -> None:
    """Add a single node pack to workflow's node list.

    Used for incremental persistence - adds one node at a time
    instead of replacing the entire list.

    Args:
        workflow_name: Name of workflow
        node_pack_id: Node package identifier to add
    """
    config = self.load()
    self.ensure_section(config, 'tool', 'comfydock', 'workflows', workflow_name)

    # Get existing nodes or create empty list
    existing = config['tool']['comfydock']['workflows'][workflow_name].get('nodes', [])

    # Add if not already present
    if node_pack_id not in existing:
        existing.append(node_pack_id)
        config['tool']['comfydock']['workflows'][workflow_name]['nodes'] = sorted(existing)
        self.save(config)
        logger.debug(f"Added node pack '{node_pack_id}' to workflow '{workflow_name}'")
```

#### WorkflowHandler - New Method: `add_model_mapping()`
```python
def add_model_mapping(
    self,
    workflow_name: str,
    model_hash: str,
    node_id: str,
    widget_idx: int
) -> None:
    """Add a single model mapping to workflow.

    Used for incremental persistence - adds one mapping at a time.

    Args:
        workflow_name: Name of workflow
        model_hash: Model hash (from ModelWithLocation)
        node_id: Node ID in workflow
        widget_idx: Widget index in node
    """
    config = self.load()
    self.ensure_section(config, 'tool', 'comfydock', 'workflows', workflow_name)

    # Get existing models table or create new
    if 'models' not in config['tool']['comfydock']['workflows'][workflow_name]:
        config['tool']['comfydock']['workflows'][workflow_name]['models'] = tomlkit.inline_table()

    models_table = config['tool']['comfydock']['workflows'][workflow_name]['models']

    # Get existing hash entry or create new
    if model_hash not in models_table:
        hash_entry = tomlkit.inline_table()
        hash_entry['nodes'] = []
        models_table[model_hash] = hash_entry

    # Add node reference if not already present
    node_ref = tomlkit.inline_table()
    node_ref['node_id'] = str(node_id)
    node_ref['widget_idx'] = int(widget_idx)

    # Check if already exists (avoid duplicates)
    existing_nodes = models_table[model_hash].get('nodes', [])
    for existing in existing_nodes:
        if existing['node_id'] == str(node_id) and existing['widget_idx'] == int(widget_idx):
            logger.debug(f"Model mapping already exists for {model_hash[:8]}...")
            return

    # Add new node reference
    existing_nodes.append(node_ref)
    models_table[model_hash]['nodes'] = existing_nodes

    self.save(config)
    logger.debug(f"Added model mapping: {model_hash[:8]}... to workflow '{workflow_name}'")
```

#### ModelHandler - Update: `add_model()` to support "note" field
```python
def add_model(
    self,
    model_hash: str,
    filename: str,
    file_size: int,
    category: str = "required",
    **metadata,
) -> None:
    """Add a model to the manifest.

    Args:
        model_hash: Model hash (short hash used as key)
        filename: Model filename
        file_size: File size in bytes
        category: 'required' or 'optional'
        **metadata: Additional metadata (blake3, sha256, sources, note, etc.)
    """
    config = self.load()

    # Lazy section creation - only when adding a model
    self.ensure_section(config, "tool", "comfydock", "models", category)

    # Use inline table for compact formatting
    model_entry = tomlkit.inline_table()
    model_entry["filename"] = filename
    model_entry["size"] = file_size
    for key, value in metadata.items():
        model_entry[key] = value

    config["tool"]["comfydock"]["models"][category][model_hash] = model_entry

    self.save(config)
    logger.info(f"Added {category} model: {filename} ({model_hash[:8]}...)")
```

**No changes needed** - already supports arbitrary metadata via `**metadata`, including "note" field.

---

### PyprojectManager - Schema Updates

#### Current Schema:
```toml
[tool.comfydock.workflows.my_workflow]
path = "workflows/my_workflow.json"
nodes = ["comfyui-impact-pack", "my-custom-node"]
models = {
  "abc123hash..." = { nodes = [{node_id = "3", widget_idx = "0"}] }
}

[tool.comfydock.models.required]
"abc123hash..." = { filename = "sd15.safetensors", size = 4200000000 }
```

#### New Schema (with Two Types of Optional Models):
```toml
[tool.comfydock.workflows.my_workflow]
path = "workflows/my_workflow.json"
nodes = ["comfyui-impact-pack", "rife-node"]

# Workflow mappings: Mix of hash keys (resolved) and filename keys (unresolved)
# NO optional flags here - keep it normalized (lookup in models.* sections to determine)
models = {
  # Required model (hash as key)
  "abc123hash..." = { nodes = [{node_id = "3", widget_idx = "0"}] },

  # Optional nice-to-have model (hash as key, looks same as required)
  "def456hash..." = { nodes = [{node_id = "7", widget_idx = "1"}] },

  # Optional unresolved model (filename as key, special case)
  "rife49.pth" = { nodes = [{node_id = "11", widget_idx = "0"}] }
}

# Required models (hash as key, full metadata)
[tool.comfydock.models.required]
"abc123hash..." = {
  filename = "sd15.safetensors",
  size = 4200000000,
  relative_path = "checkpoints/sd15.safetensors"
}

# NEW: Optional models section (supports TWO types)
[tool.comfydock.models.optional]

# Type 1: Unresolved optional (filename as key, minimal data)
"rife49.pth" = { unresolved = true }

# Type 2: Nice-to-have optional (hash as key, full metadata like required)
"def456hash..." = {
  filename = "artistic_lora_v2.safetensors",
  size = 143000000,
  relative_path = "loras/artistic/artistic_lora_v2.safetensors",
  sources = [{type = "civitai", url = "https://civitai.com/..."}]
}

"xyz789hash..." = {
  filename = "anime_checkpoint.safetensors",
  size = 4200000000,
  relative_path = "checkpoints/anime/anime_checkpoint.safetensors",
  sources = [{type = "huggingface", url = "https://huggingface.co/..."}]
}

# Optional nodes use node_mappings with false value (sentinel)
[tool.comfydock.node_mappings]
JWIntegerDiv = "comfyui-various"
SetNode = "comfyui-kjnodes"
SomeOptionalNode = false  # false = optional (not a string, won't map to package)

[tool.comfydock.nodes]
"comfyui-impact-pack" = { source = "registry", version = "4.18", ... }
"rife-node" = { source = "git", url = "https://github.com/...", ... }
```

**Schema Changes**:

1. **Optional models section supports TWO types**:
   - **Type 1 (Unresolved)**: Filename as key, `{unresolved = true}`
     - Not in developer's model index
     - May be managed by custom node or unavailable
     - Minimal data, no hash
   - **Type 2 (Nice-to-have)**: Hash as key, full metadata
     - In developer's model index with complete data
     - Same structure as required models
     - Includes sources for export/download
     - Just marked as "not strictly required"

2. **Workflow mappings are normalized**:
   - No `optional` flags in mappings (avoids data duplication)
   - Resolver determines if model is optional by checking which section contains it
   - Mix of hash keys (resolved models) and filename keys (unresolved models)

3. **Optional nodes**: Use existing `[tool.comfydock.node_mappings]` table with `false` value
   - Not a string (can't match a package ID)
   - Not omitted (resolver knows it was intentionally marked optional)
   - Reuses existing infrastructure

4. **Export behavior**: Optional items exported as-is, end users get identical resolution state

---

## User Experience Flows

### Flow 1: New Workflow with Missing Model

#### Current Behavior:
```bash
$ comfydock commit -m "Add workflow"
📋 Analyzing workflows...

⚠ Cannot commit - workflows have unresolved issues:
  • my_workflow: 1 model unresolved

💡 Options:
  1. Resolve issues: comfydock workflow resolve "my_workflow"
  2. Force commit: comfydock commit -m 'msg' --allow-issues

$ comfydock workflow resolve "my_workflow"
🔧 Resolving dependencies...

⚠️  Model not found: rife49.pth
  in node #11 (RIFE VFI)

No models found.
Choice [m]/s: s  # User skips

✓ Resolution complete
⚠️  1 model(s) remain unresolved

$ comfydock commit -m "Add workflow"
📋 Analyzing workflows...

⚠ Cannot commit - workflows have unresolved issues:
  • my_workflow: 1 model unresolved

# User forced to use --allow-issues
$ comfydock commit -m "Add workflow" --allow-issues
✅ Commit successful
```

#### New Behavior:
```bash
$ comfydock workflow resolve "my_workflow"
🔍 Analyzing workflow: my_workflow

🤖 Auto-resolving dependencies...
  ✓ Auto-resolved 3 node(s)
  ✓ Auto-resolved 5 model(s)

🔧 Resolving remaining issues interactively...

⚠️  Model not found: rife49.pth
  in node #11 (RIFE VFI)

🔍 Searching model index...
  No similar models found in index

No models found.
  [m] - Manually enter model path
  [o] - Mark as optional (custom node will provide)
  [s] - Skip (leave unresolved)
Choice [m]/o/s: o  # User marks as optional

✓ Marked as optional: rife49.pth

✅ All dependencies resolved!

💡 Next steps:
  • Review changes: comfydock status
  • Commit changes: comfydock commit -m 'Add workflow'

$ comfydock commit -m "Add workflow"
📋 Analyzing workflows...
✅ Commit successful: Add workflow
  • Added 1 workflow(s)
```

**Key Improvements**:
1. User can mark model as "optional" instead of being forced to skip or use --allow-issues
2. Workflow is fully resolved (no unresolved issues)
3. Commit succeeds without --allow-issues flag

---

### Flow 2: Interrupted Resolution (Ctrl+C)

#### Current Behavior:
```bash
$ comfydock workflow resolve "my_workflow"
🔧 Resolving dependencies...

⚠️  Node not found: CustomNode1
Choice [1]/m/s: 1  # User selects match

⚠️  Node not found: CustomNode2
Choice [1]/m/s: ^C  # User presses Ctrl+C

# Work lost - need to start over
$ comfydock workflow resolve "my_workflow"
# Asked about CustomNode1 AGAIN!
```

#### New Behavior:
```bash
$ comfydock workflow resolve "my_workflow"
🔍 Analyzing workflow: my_workflow

🤖 Auto-resolving dependencies...
  ✓ Auto-resolved 3 node(s)
  ✓ Auto-resolved 5 model(s)

🔧 Resolving remaining issues interactively...

⚠️  Node not found: CustomNode1
Choice [1]/m/s: 1  # User selects match
✓ Resolved: comfyui-custom-node-1

⚠️  Node not found: CustomNode2
Choice [1]/m/s: ^C  # User presses Ctrl+C

⚠️  Resolution interrupted by user

💡 Progress has been saved! Run this command again to continue:
   comfydock workflow resolve "my_workflow"

# Resume later
$ comfydock workflow resolve "my_workflow"
🔍 Analyzing workflow: my_workflow

🤖 Auto-resolving dependencies...
  ✓ Auto-resolved 4 node(s)  # CustomNode1 now auto-resolved!
  ✓ Auto-resolved 5 model(s)

🔧 Resolving remaining issues interactively...

⚠️  Node not found: CustomNode2  # Only asked about what's left!
Choice [1]/m/s: 2
✓ Resolved: comfyui-custom-node-2

✅ All dependencies resolved!
```

**Key Improvements**:
1. CustomNode1 resolution is SAVED immediately (not lost on Ctrl+C)
2. When resumed, only asks about remaining issues (CustomNode2)
3. Clear messaging about saved progress

---

### Flow 3: Dry-Run Preview

#### New Behavior:
```bash
$ comfydock workflow resolve "my_workflow" --dry-run
🔍 Analyzing workflow: my_workflow (DRY RUN)

📊 Auto-resolution preview:

  ✓ Would auto-resolve 3 node(s):
    • comfyui-impact-pack
    • comfyui-manager
    • comfyui-controlnet-aux

  ✓ Would auto-resolve 5 model(s):
    • sd15.safetensors → checkpoints/sd15.safetensors
    • vae.safetensors → vae/vae.safetensors
    • lora_style.safetensors → loras/style/lora_style.safetensors
    • control_depth.safetensors → controlnet/depth.safetensors
    • upscaler.pth → upscale_models/upscaler.pth

🔧 Issues requiring interactive resolution:

  ⚠️  2 ambiguous node(s):
    • CustomSampler (3 possible matches)
    • ImageFilter (2 possible matches)

  ⚠️  1 unresolved node(s):
    • UnknownNode

  ⚠️  1 missing model(s):
    • rife49.pth (in node #11)

💡 Run without --dry-run to resolve 4 issue(s) interactively
```

**Key Features**:
1. Shows what WOULD be auto-resolved
2. Shows what NEEDS interactive resolution
3. Doesn't persist anything (preview only)
4. Helps user understand scope before starting

---

### Flow 4: Commit with Unresolved Issues (Experimental)

#### New Behavior:
```bash
$ comfydock workflow resolve "my_workflow"
# User resolves some but not all issues...

⚠️  Some issues remain unresolved:
  • 1 node(s) unresolved
  • 1 model(s) unresolved

💡 Options:
  1. Run this command again to continue resolving
  2. Commit with issues: comfydock commit -m 'msg' --allow-issues

$ comfydock commit -m "WIP: partial resolution"
📋 Analyzing workflows...

⚠ Cannot commit - workflows have unresolved issues:
  • my_workflow: 1 node unresolved, 1 model unresolved

💡 Options:
  1. Resolve issues: comfydock workflow resolve "my_workflow"
  2. Force commit with issues: comfydock commit -m 'msg' --allow-issues

Note: Committing with --allow-issues allows you to rollback and
      try different resolutions later if you made a mistake.

# User confirms they want to commit with issues
$ comfydock commit -m "WIP: partial resolution" --allow-issues
✅ Commit successful: WIP: partial resolution
  • Added 1 workflow(s)

⚠️  Committed with unresolved issues:
  • my_workflow: 1 node unresolved, 1 model unresolved

💡 You can rollback and resolve differently later if needed

# Later, user realizes they want to try different resolution
$ comfydock rollback v3  # Back to before partial commit
$ comfydock workflow resolve "my_workflow"  # Try again with different choices
```

**Key Features**:
1. User can commit incomplete resolutions (for experimentation)
2. Clear warnings about what's unresolved
3. Reminder that rollback allows trying different choices
4. Enables "try different models, see which works best" workflow

---

## Testing Strategy

### Unit Tests

#### Phase 1: Error Handling
- [ ] Test `format_conflicts()` with empty parse result
- [ ] Test `format_conflicts()` with fallback warning
- [ ] Test `format_uv_error_for_user()` with 300-char limit
- [ ] Test truncation behavior at exactly 300 chars

#### Phase 2: Optional Dependencies
- [ ] Test `handle_missing_model()` returns `("optional", "")`
- [ ] Test `ModelHandler.add_model()` with `category="optional"`
- [ ] Test `fix_resolution()` handles "optional" action
- [ ] Test optional models appear in `models.optional` section
- [ ] Test workflow resolution counts optional as "resolved"

#### Phase 3: Dry-Run Mode
- [ ] Test `fix_resolution()` with `dry_run=True` doesn't persist
- [ ] Test `apply_single_node_resolution()` with `dry_run=True`
- [ ] Test `apply_single_model_resolution()` with `dry_run=True`
- [ ] Test dry-run preview output format

#### Phase 4: Incremental Persistence
- [ ] Test `apply_single_node_resolution()` persists immediately
- [ ] Test `apply_single_model_resolution()` persists immediately
- [ ] Test `fix_resolution()` calls apply methods after each prompt
- [ ] Test resume behavior after Ctrl+C (mock interrupt)
- [ ] Test idempotency of `apply_resolution()` (safe to call multiple times)

#### Phase 5: Non-Interactive Commit
- [ ] Test `execute_commit()` without strategy parameters
- [ ] Test commit fails when unresolved AND NOT --allow-issues
- [ ] Test commit succeeds when unresolved AND --allow-issues
- [ ] Test commit succeeds when fully resolved

### Integration Tests

#### End-to-End Scenarios
- [ ] **Scenario 1**: New workflow with optional model
  - Create workflow with custom node-managed model
  - Resolve and mark as optional
  - Commit successfully
  - Verify pyproject.toml has `models.optional` entry

- [ ] **Scenario 2**: Interrupted resolution
  - Start resolution, answer 2 prompts
  - Simulate Ctrl+C
  - Resume resolution
  - Verify only remaining issues are prompted

- [ ] **Scenario 3**: Dry-run preview
  - Run with --dry-run
  - Verify no changes to pyproject.toml
  - Run without --dry-run
  - Verify changes persisted

- [ ] **Scenario 4**: Commit with unresolved issues
  - Partially resolve workflow
  - Commit with --allow-issues
  - Rollback
  - Resolve differently
  - Verify new resolution applied

### Manual Testing Checklist

- [ ] Test error messages are readable (no truncation at bad points)
- [ ] Test Ctrl+C at various points in resolution flow
- [ ] Test resuming resolution multiple times
- [ ] Test workflow with mix of auto-resolved, optional, and interactive items
- [ ] Test --dry-run shows accurate preview
- [ ] Test commit blocking works correctly
- [ ] Test --allow-issues permits partial commits
- [ ] Test export with optional models (future - out of scope for this task)

---

## Migration & Rollout

### Backwards Compatibility

#### Existing Pyproject Files
- **No migration needed** - new optional sections are additive
- Existing `models.required` entries work as-is
- Existing workflows without optional models work as-is

#### Existing Workflows
- Users who previously skipped models will see them as "unresolved" (correct behavior)
- After update, they can re-run `workflow resolve` and mark as optional
- No automatic migration (intentional - user should review)

### Rollout Plan

#### Phase 1: Error Handling (Safe to deploy immediately)
- **Risk**: Very low
- **Impact**: Improves error messages
- **Rollback**: Simple (just revert)
- **Testing**: Unit tests + manual verification

#### Phase 2: Optional Dependencies (Low risk, high value)
- **Risk**: Low (additive feature)
- **Impact**: Enables new use case (custom node-managed models)
- **Rollback**: Simple (optional models ignored by old code)
- **Testing**: Unit + integration tests

#### Phase 3: Dry-Run Mode (Low risk)
- **Risk**: Very low (read-only feature)
- **Impact**: Improves UX (preview before commit)
- **Rollback**: Simple (just removes flag)
- **Testing**: Unit + manual testing

#### Phase 4: Incremental Persistence (HIGH RISK - needs thorough testing)
- **Risk**: HIGH (core refactor)
- **Impact**: Major UX improvement (resume support)
- **Rollback**: Complex (data structures changed)
- **Testing**: Extensive unit + integration + manual testing
- **Recommended**: Feature flag or beta testing period

#### Phase 5: Non-Interactive Commit (Medium risk)
- **Risk**: Medium (changes CLI contract)
- **Impact**: Simplifies commit flow
- **Rollback**: Medium (users may expect old behavior)
- **Testing**: Integration tests + documentation updates

### Feature Flags (Recommended for Phase 4)

```python
# environment.py or config
ENABLE_INCREMENTAL_PERSISTENCE = os.getenv("COMFYDOCK_INCREMENTAL_PERSIST", "false").lower() == "true"

if ENABLE_INCREMENTAL_PERSISTENCE:
    # Use new incremental flow
    self.workflow_manager.fix_resolution(..., incremental=True)
else:
    # Use old batch flow (existing behavior)
    self.workflow_manager.fix_resolution(..., incremental=False)
```

**Benefits**:
- Can test in production with subset of users
- Easy rollback if issues found
- Gradual migration path

---

## Design Decisions

### D1: Optional Nodes Implementation
**Decision**: Use existing `[tool.comfydock.node_mappings]` table with `false` boolean value as sentinel

**Rationale**:
- `false` is not a string (can't match a package ID)
- Not omitted (resolver knows it was intentionally marked optional)
- Reuses existing infrastructure (no new section needed)

**Example**:
```toml
[tool.comfydock.node_mappings]
JWIntegerDiv = "comfyui-various"
SomeOptionalNode = false  # Marked as optional
```

---

### D2: Optional Models Implementation (Two Types)
**Decision**: Use `[tool.comfydock.models.optional]` section supporting two distinct types

**Type 1 - Unresolved Optional Models** (like `rife49.pth`):
- **Key**: Filename (e.g., `"rife49.pth"`)
- **Data**: `{unresolved = true}` (minimal, no notes)
- **Use Case**: Models not in developer's index (may be custom node-managed or unavailable)
- **Resolution**: Counts as "resolved" (resolver won't complain)

**Type 2 - Nice-to-Have Optional Models** (like bonus LoRAs):
- **Key**: Hash (e.g., `"def456hash..."`)
- **Data**: Full metadata (same structure as required models)
- **Use Case**: Models in developer's index that enhance workflow but aren't required
- **Resolution**: Fully resolved with sources, sizes, etc. for export

**Rationale**:
- **Unified section**: Both types coexist naturally (different key types prevent conflicts)
- **Normalized schema**: No duplication in workflow mappings (just lookup which section contains the hash/filename)
- **Full metadata for Type 2**: Enables proper export with download sources
- **Simple minimal data for Type 1**: Just enough to mark as resolved

**Example**:
```toml
[tool.comfydock.models.optional]
# Type 1: Unresolved (filename key, minimal)
"rife49.pth" = { unresolved = true }

# Type 2: Nice-to-have (hash key, full metadata)
"abc123hash..." = {
  filename = "artistic_lora.safetensors",
  size = 143000000,
  relative_path = "loras/artistic_lora.safetensors",
  sources = [{type = "civitai", url = "..."}]
}
```

**Resolution Logic**:
```python
def check_model_resolution_status(model_ref: WorkflowNodeWidgetRef) -> tuple[bool, str, dict]:
    """Check if model is resolved and determine its category.

    Returns:
        (is_resolved, category, model_data)
        - is_resolved: True if found in required or optional sections
        - category: "required", "optional_resolved", "optional_unresolved", or "unresolved"
        - model_data: The model metadata dict or None
    """
    # Check required section (always hash-based lookup)
    required_models = pyproject.models.get_category("required")
    for model_hash, model_data in required_models.items():
        if model_data["filename"] == model_ref.widget_value:
            return (True, "required", model_data)

    # Check optional section (supports both hash and filename keys)
    optional_models = pyproject.models.get_category("optional")

    # Check Type 1: Unresolved (filename as key)
    if model_ref.widget_value in optional_models:
        entry = optional_models[model_ref.widget_value]
        if entry.get("unresolved"):
            return (True, "optional_unresolved", entry)

    # Check Type 2: Nice-to-have (hash as key, match by filename)
    for model_hash, model_data in optional_models.items():
        if not isinstance(model_hash, str) or model_hash == model_ref.widget_value:
            continue  # Skip unresolved entries (filename keys)
        if model_data.get("filename") == model_ref.widget_value:
            return (True, "optional_resolved", model_data)

    # Not found in any section
    return (False, "unresolved", None)
```

---

### D3: Export Handling of Optional Dependencies
**Decision**: Export optional items as-is, end users get identical resolution state

**Rationale**:
- Exported pyproject.toml includes `node_mappings` with false values
- Exported pyproject.toml includes `models.optional` section
- End users inherit same "optional" markings
- User responsible for ensuring optional resources available

---

### D4: Commit Always Runs Full Resolution
**Decision**: Commit runs full resolution (non-interactive) on every commit

**Rationale**:
- Can't know if workflow changed between `workflow resolve` and `commit`
- Resolution uses cached data from previous interactive sessions (fast)
- Ensures pyproject.toml always reflects current workflow state
- Future optimization: Add diff tool to only re-resolve changed nodes

**Implementation Note**: Resolution during commit is non-interactive (no strategies), just auto-resolves what it can using existing cache.

---

### D5: Optional Model Workflow JSON Handling
**Decision**: Leave workflow JSON unchanged when model marked optional

**Rationale**:
- Custom node expects original filename in widget value
- Workflow should work as-is if custom node downloads model
- Adding marker would break ComfyUI compatibility
- Optional status only tracked in pyproject.toml

---

### D6: Dry-Run Mode Behavior
**Decision**: Show summary of issues without interactive prompts

**Rationale**:
- Fast preview (user sees all issues at once)
- Non-blocking (no user input required)
- Clear purpose (preview before starting interactive session)
- Can add interactive simulation later if needed

---

## Implementation Checklist

### Phase 1: Error Handling Improvements ✅ (2-4 hours)
- [ ] Update `resolution_tester.py:86-91` with fallback warning
- [ ] Update `uv_error_handler.py:74` to use `max_hint_length=300`
- [ ] Update call sites to pass larger limit
- [ ] Write unit tests
- [ ] Manual testing with known error cases

### Phase 2: Optional Dependency Support 📋 (4-6 hours)
- [ ] Update `protocols.py` docstring to document "optional" action
- [ ] Update `InteractiveModelStrategy.handle_missing_model()` to add "o" option
- [ ] Update `InteractiveNodeStrategy.resolve_unknown_node()` to add "o" option
- [ ] Update `fix_resolution()` to handle "optional" action for models
- [ ] Update `fix_resolution()` to handle "optional" action for nodes (if Q1 = yes)
- [ ] Write unit tests
- [ ] Write integration test (end-to-end optional model flow)

### Phase 3: Dry-Run Mode 🔍 (3-5 hours)
- [ ] Add `dry_run` parameter to `fix_resolution()`
- [ ] Add `dry_run` parameter to new `apply_single_*` methods
- [ ] Implement `_dry_run_preview()` in CLI
- [ ] Add `--dry-run` flag to argparse
- [ ] Write unit tests
- [ ] Manual testing

### Phase 4: Incremental Persistence 🚨 (8-12 hours)
- [ ] Create `WorkflowHandler.add_node_pack()` method
- [ ] Create `WorkflowHandler.add_model_mapping()` method
- [ ] Create `WorkflowManager.apply_single_node_resolution()` method
- [ ] Create `WorkflowManager.apply_single_model_resolution()` method
- [ ] Refactor `fix_resolution()` to call `apply_single_*` after each prompt
- [ ] Update `fix_resolution()` to accept `workflow_name` parameter
- [ ] Make `apply_resolution()` idempotent
- [ ] Update CLI `workflow_resolve()` to use new flow
- [ ] Write unit tests (especially resume behavior)
- [ ] Write integration tests
- [ ] Extensive manual testing (Ctrl+C at various points)
- [ ] Consider feature flag for gradual rollout

### Phase 5: Non-Interactive Commit 🎯 (4-6 hours)
- [ ] Remove strategy parameters from `execute_commit()`
- [ ] Update `execute_commit()` validation logic
- [ ] Update CLI `commit()` to remove strategy injection
- [ ] Update error messages to reference `workflow resolve`
- [ ] Write integration tests
- [ ] Update documentation

---

## Success Criteria

### Must Have (MVP)
1. ✅ Users can mark models/nodes as "optional"
2. ✅ Resolution progress is saved incrementally (survives Ctrl+C)
3. ✅ Commit is non-interactive (no re-prompting)
4. ✅ Error messages are readable (not truncated)
5. ✅ --dry-run shows preview without persisting

### Should Have (Polish)
1. ✅ Clear messaging about resume capability
2. ✅ Helpful next-steps guidance
3. ✅ --allow-issues enables experimental workflows
4. ✅ Export/import handles optional dependencies gracefully

### Could Have (Future)
1. ⏱ Batch resolution (resolve multiple workflows at once)
2. ⏱ Interactive diff (show what changed between commits)
3. ⏱ Auto-retry with different strategies
4. ⏱ Resolution templates (save common choices)

---

## Estimated Timeline

| Phase | Effort | Risk | Priority |
|-------|--------|------|----------|
| Phase 1: Error Handling | 2-4 hours | Low | High |
| Phase 2: Optional Support | 4-6 hours | Low | High |
| Phase 3: Dry-Run Mode | 3-5 hours | Low | Medium |
| Phase 4: Incremental Persist | 8-12 hours | **HIGH** | **CRITICAL** |
| Phase 5: Non-Interactive Commit | 4-6 hours | Medium | High |
| **TOTAL** | **21-33 hours** | - | - |

**Recommended Order**:
1. Phase 1 (quick win, immediate value)
2. Phase 2 (enables key use case)
3. Phase 4 (highest value, highest risk - needs thorough testing)
4. Phase 3 (nice-to-have, low risk)
5. Phase 5 (depends on Phase 4 being stable)

---

## Next Steps

1. **Review this plan** and design decisions
2. **Start with Phase 1** (error handling - low risk, high value)
3. **Implement Phase 2** (optional support - enables rife49.pth use case)
4. **Add Environment API methods** (resolve_workflow, commit_workflows, search helpers)
5. **Carefully implement Phase 4** with extensive testing
6. **Simplify CLI commands** to use new Environment API
7. **Consider beta testing** for Phase 4 before full rollout
8. **Update documentation** after each phase

---

## Related Documents

- [PRD](../prd.md) - Overall system design
- [Layer Hierarchy](../layer-hierarchy.md) - Code organization
- [Workflow Commit Integration Issues](./workflow-commit-integration-issues.md) - Previous issue analysis

---

**Document Status**: Phases 1-2 Complete, Planning Remaining Phases
**Last Updated**: 2025-10-08
**Author**: Claude Code Assistant
**Reviewed By**: User

---

## Current Implementation Status

### ✅ Phase 1: Error Handling - COMPLETE
- UV error truncation fixed
- Silent conflict fallback warnings added
- All tests passing

### ✅ Phase 2: Optional Dependencies - COMPLETE
**Core Package**:
- Protocol documentation updated
- `workflow_manager.py` handles both Type 1 and Type 2 optional models
- `model_resolver.py` checks models.optional section
- Resolution flow recognizes optional as "resolved"

**CLI Package**:
- Interactive strategy offers `[o]` option in all relevant prompts
- Type 1: `handle_missing_model()` returns `("optional_unresolved", "")`
- Type 2: `resolve_ambiguous_model()` sets `model._mark_as_optional = True`
- Unified choice prompt accepts 'o' input

**Test Coverage**:
- 5 passing integration tests
- 1 skipped test (test fixture limitation, not code issue)
- Type 1 and Type 2 flows verified

### 📋 Phase 3: Dry-Run Mode - PLANNED
- Design complete (see document above)
- Implementation not started

### 📋 Phase 4: Incremental Persistence - PLANNED
- Design complete (see document above)
- HIGH RISK - requires careful testing
- Implementation not started

### 📋 Phase 5: Non-Interactive Commit - PLANNED
- Design complete (see document above)
- Depends on Phase 4
- Implementation not started

---

**Key Decisions Made**: All design questions resolved (see Design Decisions section)
