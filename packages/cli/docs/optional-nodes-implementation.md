# Optional Nodes Implementation - Interactive Strategy

**Status**: ✅ COMPLETE
**Date**: 2025-10-08

## Summary

Added `[o]` option to `InteractiveNodeStrategy` to allow users to mark nodes as optional during interactive resolution. This completes the optional dependency UX, making it consistent with models.

---

## Problem Statement

**User Issue**: "Why is there no 'optional' option in the unified interface for nodes?"

When resolving ambiguous/unresolved nodes, users saw:
```
🔍 Found 3 matches for 'JWIntegerDiv':
  1. ComfyLiterals
  2. ComfyUI-Logic
  3. primitive-types
Choice [1]/m/s:  # ❌ No [o] option!
```

**Inconsistency**:
- ✅ Models: Full optional support via `[o]` option
- ❌ Nodes: No interactive option, users had to manually edit `pyproject.toml`

---

## Implementation

### 1. **Interactive Strategy Updates** (`cli/strategies/interactive.py`)

**Added `_last_choice` tracking**:
```python
class InteractiveNodeStrategy:
    def __init__(self, search_fn=None, installed_packages=None):
        self._last_choice = None  # Track user choice for optional detection
```

**Updated all three resolution methods**:

#### `_resolve_ambiguous()` - Ambiguous nodes
```python
print("\n  [1-9] - Select package to install")
print("  [o]   - Mark as optional (workflow works without it)")
print("  [m]   - Manually enter package ID")
print("  [s]   - Skip (leave unresolved)")

choice = self._unified_choice_prompt("Choice [1]/o/m/s: ", ...)

if choice == 'o':
    self._last_choice = 'optional'
    print(f"  ✓ Marked '{node_type}' as optional")
    return None
```

#### `_show_search_results()` - Search results
```python
choice = self._unified_choice_prompt("Choice [1]/o/m/s: ", ...)

if choice == 'o':
    self._last_choice = 'optional'
    print(f"  ✓ Marked '{node_type}' as optional")
    return None
```

#### `resolve_unknown_node()` - No matches
```python
print("\nNo packages found.")
print("  [m] - Manually enter package ID")
print("  [o] - Mark as optional (workflow works without it)")
print("  [s] - Skip (leave unresolved)")

choice = self._unified_choice_prompt("Choice [m]/o/s: ", ...)

if choice == 'o':
    self._last_choice = 'optional'
    print(f"  ✓ Marked '{node_type}' as optional")
    return None
```

### 2. **Core Workflow Manager Updates** (`core/managers/workflow_manager.py`)

**Collect optional nodes in `fix_resolution()`**:
```python
# Collect optional node types that user marked
optional_node_types: list[str] = []

# Fix ambiguous nodes
if node_strategy:
    for packages in resolution.nodes_ambiguous:
        selected = node_strategy.resolve_unknown_node(...)
        if selected:
            nodes_to_add.append(selected)
        elif hasattr(node_strategy, '_last_choice') and node_strategy._last_choice == 'optional':
            optional_node_types.append(packages[0].node_type)
            logger.info(f"Marked node '{packages[0].node_type}' as optional")
        else:
            remaining_nodes_ambiguous.append(packages)

# Handle unresolved nodes
if node_strategy:
    for node in resolution.nodes_unresolved:
        selected = node_strategy.resolve_unknown_node(...)
        if selected:
            nodes_to_add.append(selected)
        elif hasattr(node_strategy, '_last_choice') and node_strategy._last_choice == 'optional':
            optional_node_types.append(node.type)
            logger.info(f"Marked node '{node.type}' as optional")
        else:
            remaining_nodes_unresolved.append(node)
```

**Attach optional nodes to result**:
```python
result = ResolutionResult(...)
result._optional_node_types = optional_node_types
return result
```

**Persist optional mappings in `apply_resolution()`**:
```python
# Save optional node mappings (False value means optional)
optional_node_types = getattr(resolution, '_optional_node_types', [])
for node_type in optional_node_types:
    self.pyproject.node_mappings.add_mapping(node_type, False)
    logger.info(f"Marked node '{node_type}' as optional in node_mappings")
```

---

## How It Works

### User Experience

**Before** (manual editing required):
```bash
$ comfydock workflow resolve "my_workflow"
🔍 Found 3 matches for 'JWIntegerDiv':
Choice [1]/m/s: s  # User skips

# Then manually edit pyproject.toml:
[tool.comfydock.node_mappings]
JWIntegerDiv = false  # Add this line manually
```

**After** (interactive option):
```bash
$ comfydock workflow resolve "my_workflow"
🔍 Found 3 matches for 'JWIntegerDiv':
  1. ComfyLiterals
  2. ComfyUI-Logic
  3. primitive-types

  [1-9] - Select package to install
  [o]   - Mark as optional (workflow works without it)
  [m]   - Manually enter package ID
  [s]   - Skip (leave unresolved)

Choice [1]/o/m/s: o
  ✓ Marked 'JWIntegerDiv' as optional
```

### Data Flow

1. **User chooses `[o]`** → Strategy sets `_last_choice = 'optional'`, returns `None`
2. **WorkflowManager detects** → Checks `_last_choice`, adds to `optional_node_types` list
3. **Apply resolution** → Persists to `pyproject.node_mappings` with `False` value
4. **Future resolution** → GlobalNodeResolver sees `False` mapping, skips node (counts as resolved)

### Result in pyproject.toml

```toml
[tool.comfydock.node_mappings]
JWIntegerDiv = false  # Optional node - workflow works without it
```

---

## Design Decisions

### 1. **`_last_choice` Attribute Pattern**
**Decision**: Track user's last choice in strategy via `_last_choice` attribute

**Rationale**:
- Simple, no protocol changes needed
- Already used for models (`_mark_as_optional`)
- WorkflowManager can check attribute after strategy returns
- Avoids complex return value signatures

**Alternatives considered**:
- Return special value (requires protocol change)
- Add to protocol (breaking change for all strategies)
- Use callback pattern (overly complex)

### 2. **Attach Optional Nodes to ResolutionResult**
**Decision**: Store optional nodes as `_optional_node_types` on ResolutionResult

**Rationale**:
- Passes data from `fix_resolution()` to `apply_resolution()`
- Avoids global state or additional parameters
- Consistent with model handling pattern

### 3. **Persist as `False` in node_mappings**
**Decision**: Save optional nodes as `node_type = false` in pyproject.toml

**Rationale**:
- Consistent with Phase 2 spec (documented behavior)
- GlobalNodeResolver already handles `False` value (returns empty list = resolved)
- Simple boolean sentinel (can't match a package ID)

---

## Test Coverage

**New Tests** (`test_interactive_optional_strategy.py`):

1. ✅ `test_resolve_ambiguous_node_with_optional_choice()` - Ambiguous nodes
2. ✅ `test_resolve_unknown_node_no_matches_with_optional()` - No matches
3. ✅ `test_resolve_unknown_node_search_results_with_optional()` - Search results

**All tests passing**: 8/8 ✅

---

## Files Modified

### CLI Package
1. ✅ `packages/cli/comfydock_cli/strategies/interactive.py`
   - Added `_last_choice` tracking
   - Added `[o]` option to all three resolution methods
   - Updated prompts with help text

2. ✅ `packages/cli/tests/test_interactive_optional_strategy.py`
   - Added 3 comprehensive node optional tests

### Core Package
3. ✅ `packages/core/src/comfydock_core/managers/workflow_manager.py`
   - Collect optional nodes in `fix_resolution()`
   - Attach to ResolutionResult
   - Persist to `node_mappings` in `apply_resolution()`

---

## Integration Points

### With GlobalNodeResolver
- Resolver checks `node_mappings` for each node type
- `False` value → returns empty list (counts as resolved, not unresolved)
- Next resolution automatically skips optional nodes

### With WorkflowManager
- `fix_resolution()` collects optional node types
- `apply_resolution()` persists to pyproject.toml
- Same pattern as model optional handling

---

## Future Enhancements

### Potential Improvements (not in scope)
- Allow toggling node between optional/required
- Show which nodes are optional in `comfydock status`
- Dry-run mode preview (Phase 3)

---

## Summary

**Complete feature parity** between models and nodes for optional dependency support:

| Feature | Models | Nodes |
|---------|--------|-------|
| Missing/unresolved | ✅ `[o]` | ✅ `[o]` |
| Ambiguous | ✅ `[o]` | ✅ `[o]` |
| Search results | ✅ `[o]` | ✅ `[o]` |
| Persistence | ✅ `models.optional` | ✅ `node_mappings = false` |
| Future resolution | ✅ Skipped | ✅ Skipped |

**Ready for production use** ✅

The optional dependency UX is now complete and consistent across both models and nodes!
