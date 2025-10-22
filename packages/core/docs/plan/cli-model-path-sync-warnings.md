# CLI Integration: Model Path Sync Warnings

## Overview

Integrate the core model path sync detection feature into the CLI status display to warn users when workflow model paths need updating.

**Problem**: Users create workflows in ComfyUI with incorrect model paths (e.g., `models--SD1.5/model.safetensors`). Status shows "no issues" because the model resolves by filename, but ComfyUI fails when run because the workflow JSON still contains the wrong path.

**Solution**: Display warnings in CLI status output when models are resolved but paths differ from workflow JSON, with actionable suggestions to run `resolve`.

## Core Implementation (Complete ✅)

The core detection logic is already implemented in:
- `packages/core/src/comfydock_core/models/workflow.py:493` - `ResolvedModel.needs_path_sync` field
- `packages/core/src/comfydock_core/models/workflow.py:661-669` - `WorkflowAnalysisStatus` properties
- `packages/core/src/comfydock_core/managers/workflow_manager.py:618-624` - Workflow loading for comparison
- `packages/core/src/comfydock_core/managers/workflow_manager.py:694-699` - Path sync detection in `resolve_workflow()`
- `packages/core/src/comfydock_core/managers/workflow_manager.py:1180-1214` - `_check_path_needs_sync()` helper

**Tests**: `/packages/core/tests/integration/test_model_path_sync_detection.py` (3 tests, all passing)

## CLI Integration Required

### Files to Modify

#### 1. `/packages/cli/comfydock_cli/env_commands.py`

**Location**: Line 306-329 (`_print_workflow_issues` method)

**Current behavior**:
```python
def _print_workflow_issues(self, wf_analysis: WorkflowAnalysisStatus):
    """Print compact workflow issues summary using model properties only."""
    parts = []

    # Use the uninstalled_count property (populated by core)
    if wf_analysis.uninstalled_count > 0:
        parts.append(f"{wf_analysis.uninstalled_count} packages needed for installation")

    # Resolution issues
    if wf_analysis.resolution.nodes_unresolved:
        parts.append(f"{len(wf_analysis.resolution.nodes_unresolved)} nodes couldn't be resolved")
    if wf_analysis.resolution.models_unresolved:
        parts.append(f"{len(wf_analysis.resolution.models_unresolved)} models not found")
    if wf_analysis.resolution.models_ambiguous:
        parts.append(f"{len(wf_analysis.resolution.models_ambiguous)} ambiguous models")

    # Show download intents as pending work
    download_intents = [m for m in wf_analysis.resolution.models_resolved if m.match_type == "download_intent"]
    if download_intents:
        parts.append(f"{len(download_intents)} models queued for download")

    # Print compact issue line
    if parts:
        print(f"      • {', '.join(parts)}")
```

**Required change**: Add path sync warnings at the TOP of the parts list (most actionable):

```python
def _print_workflow_issues(self, wf_analysis: WorkflowAnalysisStatus):
    """Print compact workflow issues summary using model properties only."""
    parts = []

    # NEW: Path sync warnings (FIRST - most actionable fix)
    if wf_analysis.models_needing_path_sync_count > 0:
        parts.append(
            f"{wf_analysis.models_needing_path_sync_count} model paths need syncing"
        )

    # Use the uninstalled_count property (populated by core)
    if wf_analysis.uninstalled_count > 0:
        parts.append(f"{wf_analysis.uninstalled_count} packages needed for installation")

    # ... rest unchanged ...
```

**Why first**: Path sync is the most actionable - user just needs to run `resolve`. Shows up before other issues that might require more work.

---

**Location**: Line 302 (`_show_smart_suggestions` method within `status` command)

**Current behavior**:
```python
# Suggested actions - smart and contextual
self._show_smart_suggestions(status, dev_drift)
```

The `_show_smart_suggestions` method doesn't currently exist in the visible code, but based on the pattern, we need to add path sync suggestions.

**Required change**: Add path sync suggestions to the suggestions flow:

```python
def _show_smart_suggestions(self, status, dev_drift):
    """Generate smart, actionable suggestions based on environment state."""
    suggestions = []

    # NEW: Path sync warnings (prioritize this - quick fix!)
    workflows_needing_sync = [
        w for w in status.workflow.analyzed_workflows
        if w.has_path_sync_issues
    ]

    if workflows_needing_sync:
        workflow_names = [w.name for w in workflows_needing_sync]
        if len(workflow_names) == 1:
            suggestions.append(
                f"Sync model paths: comfydock workflow resolve {workflow_names[0]}"
            )
        else:
            suggestions.append(
                f"Sync model paths in {len(workflow_names)} workflows: comfydock workflow resolve <name>"
            )

    # ... existing suggestions (uninstalled packages, etc.) ...

    if suggestions:
        print("\n💡 Suggested actions:")
        for suggestion in suggestions:
            print(f"  • {suggestion}")
```

**Why prioritize**: Path sync is a non-blocking quick fix that prevents runtime errors. Show it before more complex suggestions.

---

### Expected Output Examples

#### Before Implementation

```bash
$ comfydock status

Environment: my-env

📋 Workflows:
  ✓ my_workflow (synced)

✓ No uncommitted changes
```

User runs ComfyUI → **BOOM! Model not found error** 💥

---

#### After Implementation - With Path Sync Issues

```bash
$ comfydock status

Environment: my-env

📋 Workflows:
  ⚠️  my_workflow (synced)
      • 2 model paths need syncing

💡 Suggested actions:
  • Sync model paths: comfydock workflow resolve my_workflow
```

User sees warning → runs `resolve` → paths fixed → ComfyUI works ✅

---

#### After Running Resolve

```bash
$ comfydock workflow resolve my_workflow
✓ Resolved 2 models
✓ Updated workflow JSON paths

$ comfydock status

Environment: my-env

📋 Workflows:
  ✓ my_workflow (synced)

✓ No uncommitted changes
```

Clean! 🎉

---

### Test Strategy

#### Unit Test (Optional)

Create `/packages/cli/tests/test_status_path_sync_display.py`:

```python
"""Test that CLI status displays path sync warnings correctly."""

def test_status_displays_path_sync_warning(test_env, capsys):
    """Verify path sync warnings appear in status output."""
    # ARRANGE: Create workflow with wrong model path
    # (use existing test infrastructure from core)

    # ACT: Run status command
    from comfydock_cli.env_commands import EnvironmentCommands
    cmd = EnvironmentCommands()
    # ... mock args ...
    cmd.status(args)

    # ASSERT: Check output
    captured = capsys.readouterr()
    assert "model paths need syncing" in captured.out
    assert "comfydock workflow resolve" in captured.out
```

#### Integration Test (Better)

Extend existing CLI integration tests to verify output formatting. Can be added to existing test files that test the `status` command.

---

## Implementation Checklist

- [ ] **Step 1**: Update `_print_workflow_issues()` in `/packages/cli/comfydock_cli/env_commands.py:306`
  - Add path sync warning to `parts` list (at the top)
  - Use `wf_analysis.models_needing_path_sync_count`

- [ ] **Step 2**: Update suggestions logic in same file (likely around line 302)
  - Check for `w.has_path_sync_issues` on analyzed workflows
  - Add suggestion: `"Sync model paths: comfydock workflow resolve {name}"`
  - Handle single vs. multiple workflows

- [ ] **Step 3**: Manual test with real workflow
  - Create workflow in ComfyUI with wrong model path
  - Run `comfydock status` → should see warning
  - Run `comfydock workflow resolve <name>` → should fix
  - Run `comfydock status` again → warning should disappear

- [ ] **Step 4**: Add CLI test (optional but recommended)
  - Create test file or extend existing status tests
  - Verify warning appears in output
  - Verify suggestion appears

---

## Design Decisions & Rationale

### 1. **Path sync is NOT a blocking issue**

**Decision**: Don't add to `has_issues` property
- Path sync warnings are displayed but don't block commits
- Users can commit workflows with path warnings (they'll just fail at runtime)
- This keeps commit safety checks focused on true blockers (missing models, unresolved nodes)

**Code impact**: None - `has_issues` unchanged

---

### 2. **Show warnings at the TOP of issue list**

**Decision**: Path sync appears first in `_print_workflow_issues()`
- Most actionable fix (just run `resolve`)
- Prevents runtime failures
- Quick to fix, so show it prominently

**Code impact**: Add to `parts` list before other issues

---

### 3. **Separate warning from errors**

**Decision**: Use neutral language "need syncing" not "error"
- Models ARE resolved (not an error state)
- Paths just need updating (informational warning)
- Keeps tone helpful, not alarming

**Code impact**: Message text: `"2 model paths need syncing"`

---

### 4. **Prioritize in suggestions**

**Decision**: Show path sync suggestion before other actions
- Fast fix (just run `resolve`)
- Prevents immediate runtime errors
- Encourages good workflow hygiene

**Code impact**: Add to suggestions list at top

---

## Context for Implementation

### Key Core APIs to Use

```python
# Already available in WorkflowAnalysisStatus
wf_analysis.models_needing_path_sync_count  # Count of models needing sync
wf_analysis.has_path_sync_issues            # Boolean check

# Already in resolution results
for model in wf_analysis.resolution.models_resolved:
    if model.needs_path_sync:
        # This model's path differs from workflow JSON
        ...
```

### Existing Pattern to Follow

The CLI already displays warnings for:
- Uninstalled packages: `wf_analysis.uninstalled_count`
- Download intents: `[m for m in ... if m.match_type == "download_intent"]`

**Follow the same pattern** for path sync warnings - use the properties exposed by core.

### Files You'll Need to Read

1. `/packages/cli/comfydock_cli/env_commands.py` - Main status display logic
   - Read lines 179-329 to understand current flow
   - Modify `_print_workflow_issues()` at line 306
   - Add to suggestions (find where suggestions are shown)

2. `/packages/core/src/comfydock_core/models/workflow.py:590-669`
   - Review `WorkflowAnalysisStatus` properties you can use
   - Understand what data is available

3. `/packages/core/tests/integration/test_model_path_sync_detection.py`
   - See test scenarios for expected behavior
   - Use as reference for CLI testing

---

## Edge Cases to Handle

### 1. **Multiple workflows with path issues**

**Scenario**: 5 workflows all have path sync issues

**Display**:
```
📋 Workflows:
  ⚠️  workflow1 (synced)
      • 2 model paths need syncing
  ⚠️  workflow2 (synced)
      • 1 model paths need syncing
  ...

💡 Suggested actions:
  • Sync model paths in 5 workflows: comfydock workflow resolve <name>
```

**Implementation**: Use list comprehension to count workflows, aggregate suggestion

---

### 2. **Workflow has BOTH path issues AND other issues**

**Scenario**: Workflow needs path sync + has uninstalled packages

**Display**:
```
📋 Workflows:
  ⚠️  my_workflow (synced)
      • 2 model paths need syncing, 1 packages needed for installation
```

**Implementation**: Already handled by `parts` list - just add path sync to the list

---

### 3. **No workflows or no path issues**

**Scenario**: All paths are correct

**Display**:
```
📋 Workflows:
  ✓ my_workflow (synced)

✓ No uncommitted changes
```

**Implementation**: Check `if wf_analysis.models_needing_path_sync_count > 0` - no output if zero

---

## Success Criteria

✅ **Status output shows path sync warning** when model paths differ
✅ **Suggestion includes `resolve` command** with correct workflow name
✅ **Warning disappears** after running `resolve`
✅ **No false positives** (custom nodes not flagged)
✅ **Works with multiple workflows** (aggregates suggestion)
✅ **Doesn't block commits** (`has_issues` unchanged)

---

## Related Documentation

- Core implementation: `/packages/core/docs/plan/cli-model-path-sync-warnings.md` (this file)
- Core tests: `/packages/core/tests/integration/test_model_path_sync_detection.py`
- Model path behavior: `/packages/core/docs/knowledge/comfyui-node-loader-base-directories.md`
- Status scanner: `/packages/core/src/comfydock_core/analyzers/status_scanner.py`

---

## Estimated Effort

**Time**: 30-45 minutes
- 15 min: Update `_print_workflow_issues()`
- 15 min: Update suggestions logic
- 15 min: Manual testing with real workflow

**Complexity**: Low
- Simple property access (core already does detection)
- Follow existing pattern for other warnings
- No new business logic needed

**Risk**: Very Low
- Additive change only
- Core logic is tested
- Just displaying existing data
