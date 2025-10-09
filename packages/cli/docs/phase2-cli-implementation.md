# Phase 2: CLI Interactive Strategy Implementation

**Status**: ✅ COMPLETE
**Date**: 2025-10-08

## Summary

Phase 2 CLI implementation adds interactive user prompts for marking dependencies as optional during workflow resolution. This complements the core Phase 2 implementation which handles the persistence and resolution logic.

## Changes Made

### 1. InteractiveModelStrategy Updates

#### `handle_missing_model()` - Type 1 Optional
**Already Implemented** (from previous session):
- Added `[o]` option to mark missing models as optional (Type 1: unresolved)
- Returns `("optional_unresolved", "")` when user chooses 'o'
- Displays helpful text: "Mark as optional (workflow works without it)"

**Location**: `packages/cli/comfydock_cli/strategies/interactive.py:370-383`

```python
# No matches - offer manual entry, optional, or skip
print("\nNo models found.")
print("  [m] - Manually enter model path")
print("  [o] - Mark as optional (workflow works without it)")
print("  [s] - Skip (leave unresolved)")
choice = self._unified_choice_prompt("Choice [m]/o/s: ", num_options=0, has_browse=False)

if choice == 'o':
    return ("optional_unresolved", "")
```

#### `resolve_ambiguous_model()` - Type 2 Optional
**Newly Implemented** (this session):
- Added `[o]` option to mark ambiguous models as optional (Type 2: nice-to-have)
- Prompts user to select which model when 'o' is chosen
- Sets `_mark_as_optional = True` attribute on selected model
- Preserves backward compatibility (numeric choice defaults to required)

**Location**: `packages/cli/comfydock_cli/strategies/interactive.py:315-362`

```python
print("\n  [1-9] - Select model as required")
print("  [o]   - Mark as optional nice-to-have (select from above)")
print("  [m]   - Manually enter model path")
print("  [s]   - Skip (leave unresolved)")

choice = self._unified_choice_prompt("Choice [1]/o/m/s: ", ...)

if choice == 'o':
    model_choice = input("  Which model? [1]: ").strip() or "1"
    idx = int(model_choice) - 1
    selected = candidates[idx]
    selected._mark_as_optional = True  # Signal to WorkflowManager
    print(f"  ✓ Selected as optional: {selected.relative_path}")
    return selected
```

#### `_show_fuzzy_results()` - Fuzzy Search Optional
**Already Implemented** (from previous session):
- Added `[o]` option when showing fuzzy search results
- Returns `("optional_unresolved", "")` when user chooses 'o'

**Location**: `packages/cli/comfydock_cli/strategies/interactive.py:401-415`

### 2. Updated `_unified_choice_prompt()`

**Already Implemented**:
- Added 'o' to accepted choices: `if choice in ('m', 's', 'o')`
- Handles 'o' like other special options

**Location**: `packages/cli/comfydock_cli/strategies/interactive.py:281-313`

## User Experience

### Type 1: Unresolved Optional (Missing Model)
```bash
⚠️  Model not found: rife49.pth
  in node #11 (RIFE VFI)

No models found.
  [m] - Manually enter model path
  [o] - Mark as optional (workflow works without it)
  [s] - Skip (leave unresolved)
Choice [m]/o/s: o

✅ Marked as optional (unresolved)
```

**Result in pyproject.toml**:
```toml
[tool.comfydock.models.optional]
"rife49.pth" = { filename = "rife49.pth", unresolved = true }
```

### Type 2: Nice-to-Have Optional (Ambiguous Model)
```bash
🔍 Multiple matches for model in node #7:
  Looking for: lora.safetensors
  Found matches:
  1. loras/style_v1.safetensors (136.4 MB)
  2. loras/style_v2.safetensors (143.2 MB)

  [1-9] - Select model as required
  [o]   - Mark as optional nice-to-have (select from above)
  [m]   - Manually enter model path
  [s]   - Skip (leave unresolved)
Choice [1]/o/m/s: o

  Which model? [1]: 1
  ✓ Selected as optional: loras/style_v1.safetensors
```

**Result in pyproject.toml**:
```toml
[tool.comfydock.models.optional]
"abc123hash..." = {
  filename = "style_v1.safetensors",
  size = 143000000,
  relative_path = "loras/style_v1.safetensors"
}
```

## Test Coverage

### New Tests Added
**File**: `packages/cli/tests/test_interactive_optional_strategy.py`

1. ✅ `test_handle_missing_model_with_optional_choice()` - Type 1 basic
2. ✅ `test_handle_missing_model_fuzzy_results_with_optional()` - Type 1 with fuzzy search
3. ✅ `test_resolve_ambiguous_model_with_optional_choice()` - Type 2 optional
4. ✅ `test_resolve_ambiguous_model_required_choice()` - Explicit required (deprecated 'r' flow)
5. ✅ `test_resolve_ambiguous_model_numeric_defaults_to_required()` - Backward compatibility
6. ✅ `test_optional_node_not_implemented_in_phase_2()` - Documents node behavior

**All tests passing**: 6/6 ✅

### Integration with Core
- Core tests verify that `("optional_unresolved", "")` and `_mark_as_optional` attribute are handled correctly
- WorkflowManager processes optional markers and persists to correct sections in pyproject.toml
- Model resolver recognizes optional models and doesn't mark workflows as unresolved

## Design Decisions

### 1. Two-Prompt Flow for Type 2 Optional
**Decision**: When user selects 'o' for ambiguous models, prompt again for which model.

**Rationale**:
- Clearer UX: User explicitly chooses "optional" then selects from list
- Consistent with manual entry flow (also two prompts)
- Avoids complex single-prompt syntax like "o1" (optional + number)

### 2. Backward Compatibility
**Decision**: Numeric choice without 'r' prefix defaults to required.

**Rationale**:
- Preserves existing muscle memory
- 'r' prefix is deprecated but still works
- No breaking changes for users

### 3. Explicit Optional Indicator
**Decision**: Use `_mark_as_optional = True` attribute on ModelWithLocation.

**Rationale**:
- Simple signal from strategy to WorkflowManager
- No need to modify ModelWithLocation class
- Temporary attribute only lives during resolution flow

## Files Modified

1. ✅ `packages/cli/comfydock_cli/strategies/interactive.py`
   - Updated `resolve_ambiguous_model()` with [o] option
   - Already had `handle_missing_model()` and `_show_fuzzy_results()` with [o]

2. ✅ `packages/cli/tests/test_interactive_optional_strategy.py` (new)
   - Comprehensive test coverage for all optional scenarios

## Integration Points

### With Core (comfydock-core)
- **Input**: Strategy methods conform to protocols in `comfydock_core.models.protocols`
- **Output**: Returns tuple actions and sets model attributes as documented
- **Contracts**:
  - `handle_missing_model()` → `("optional_unresolved", "")` for Type 1
  - `resolve_ambiguous_model()` → `ModelWithLocation` with `_mark_as_optional = True` for Type 2

### With WorkflowManager
- WorkflowManager's `fix_resolution()` handles both optional types
- `apply_resolution()` separates models into required/optional categories
- Model paths are updated (or skipped) appropriately

## Known Limitations

1. **No fuzzy search optional for ambiguous models**:
   - Ambiguous models don't trigger fuzzy search (they already have candidates)
   - Only missing models get fuzzy search with [o] option

2. **Manual path entry returns None**:
   - Current implementation doesn't create ModelWithLocation from manual paths
   - This is pre-existing behavior, not changed in Phase 2

3. **Optional nodes not interactive**:
   - Optional nodes are handled via node_mappings (False value)
   - No interactive strategy changes needed
   - Resolution happens at resolver level, not strategy level

## Future Enhancements

### Phase 3 Considerations
- Dry-run mode would show "Would mark as optional" preview
- Could display what's in models.required vs models.optional

### Phase 4 Considerations
- Incremental persistence would save optional choices immediately
- Could allow toggling between required/optional after initial choice

## Testing Commands

```bash
# Run CLI tests
uv run pytest packages/cli/tests/test_interactive_optional_strategy.py -v

# Run all CLI tests
uv run pytest packages/cli/tests/ -v

# Run core integration tests
uv run pytest packages/core/tests/integration/test_optional_dependencies.py -v
```

## Documentation Updates

### Updated Files
- ✅ This document (phase2-cli-implementation.md)
- ✅ Protocol docstrings already updated in core (previous session)

### Pending Updates
- ⏱ User guide should explain [o] option for workflows
- ⏱ CLI help text could mention optional dependencies

## Conclusion

Phase 2 CLI implementation is **complete and fully functional**. The interactive strategy now provides users with clear, intuitive options to mark dependencies as optional during workflow resolution. All tests pass, backward compatibility is maintained, and the implementation integrates seamlessly with the core Phase 2 functionality.

**Ready for production use** ✅
