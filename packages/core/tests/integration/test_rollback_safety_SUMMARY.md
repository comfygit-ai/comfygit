# Rollback Safety Bug - Test Summary

## Bug Description

When a user has **modified workflows in ComfyUI** (not yet committed to `.cec/`), running `comfydock rollback <version>` succeeds **without any warning or confirmation**, silently discarding the user's uncommitted workflow changes.

## Expected Behavior

Rollback should detect uncommitted workflow changes and either:
1. **Raise an error** (like it does for git changes in `.cec/`)
2. **Prompt the user for confirmation** (CLI layer)
3. Require `--force` flag to proceed

## Current Behavior (Bug)

1. User modifies workflow in ComfyUI browser
2. `comfydock status` correctly shows workflow as "modified"
3. User runs `comfydock rollback v1`
4. **No error, no warning, rollback succeeds**
5. User's workflow edits are lost

## Root Cause

The rollback safety check happens at **two layers** but both are incomplete:

### Git Manager Layer (`git_manager.py:505`)
```python
if self.has_uncommitted_changes():  # Only checks .cec/ git changes
    if not force:
        raise CDEnvironmentError("Cannot rollback with uncommitted changes...")
```
- ✅ Checks git changes in `.cec/`
- ❌ Does NOT check workflow state in `ComfyUI/user/default/workflows/`

### CLI Layer (`env_commands.py:730`)
```python
if uncommitted_files:  # Only runs when no target version
    print("⚠️  This will discard all uncommitted changes...")
    response = input("Are you sure? (y/N): ")
```
- ✅ Shows warning and prompts
- ❌ Only runs when `args.target` is None (no version specified)
- ❌ Does NOT check workflow modifications

## Test Case

**File:** `test_rollback_safety.py::test_rollback_blocks_with_modified_comfyui_workflows`

This test reproduces the exact user scenario:
1. Creates v1 with workflow
2. Creates v2 with updated workflow
3. Simulates user editing workflow in ComfyUI (not committed)
4. Verifies `status()` detects the modification
5. **Attempts rollback to v1**
6. Currently: rollback succeeds (BUG)
7. After fix: should raise `CDEnvironmentError`

## Test Status

✅ **Test currently PASSES** - proving the bug exists (rollback succeeds when it shouldn't)

When the fix is implemented, uncomment the expectation:
```python
# TODO: Uncomment this when fix is implemented
# with pytest.raises(CDEnvironmentError, match="uncommitted|workflow"):
#     test_env.rollback("v1")
```

## Fix Strategy

The check should happen at the **core Environment layer** (`environment.py:rollback()`):

```python
def rollback(self, target: str | None = None, force: bool = False) -> None:
    # 1. Check for uncommitted git changes (.cec/)
    if not force and self.git_manager.has_uncommitted_changes():
        raise CDEnvironmentError(...)

    # 2. Check for modified workflows (ComfyUI/)  <-- ADD THIS
    if not force:
        status = self.status()
        if status.workflow.sync_status.has_changes:
            raise CDEnvironmentError(
                "Cannot rollback with uncommitted workflow changes.\n"
                "Workflows modified:\n"
                f"  {', '.join(status.workflow.sync_status.modified)}\n"
                "Options:\n"
                "  • Commit: comfydock commit -m '<message>'\n"
                "  • Force rollback: comfydock rollback <version> --force"
            )

    # ... rest of rollback logic
```

This ensures:
- ✅ Both git changes AND workflow changes are checked
- ✅ Check happens at core layer (not just CLI)
- ✅ Consistent with existing uncommitted changes behavior
- ✅ Clear error message with actionable suggestions
