# Test Implementation Summary: Node Resolution Enhancement

## Status: ✅ Tests Implemented and Failing as Expected

All MVP tests have been successfully implemented and are failing in the expected ways, validating that the new functionality needs to be added.

---

## Test Files Created

### Unit Tests
**File:** `tests/unit/test_node_resolution_context.py`
**Total:** 9 tests across 5 test classes
**Status:** All failing with `AttributeError: 'GlobalNodeResolver' object has no attribute 'resolve_single_node_with_context'`

### Integration Tests
**File:** `tests/integration/test_context_aware_node_resolution.py`
**Total:** 6 tests across 6 test classes
**Status:** 5 failing (expected), 1 passing (deduplication already works)

### Workflow Fixtures
Created 3 new workflow fixtures with properties field:
- `workflow_with_properties.json` - Nodes with cnr_id and ver fields
- `workflow_without_properties.json` - Same structure, empty properties
- `workflow_with_duplicates.json` - 10 nodes for deduplication testing

---

## Unit Test Breakdown

### 1. TestPropertiesFieldResolution (2 tests)
**Purpose:** Test resolution using properties.cnr_id from workflow

**Tests:**
- ✅ `test_properties_field_with_cnr_id_resolves_directly` - Properties should resolve directly
- ✅ `test_properties_with_invalid_cnr_id_falls_through` - Invalid cnr_id should fall through

**Expected Failure:** `resolve_single_node_with_context()` doesn't exist yet

---

### 2. TestSessionCacheDeduplication (1 test)
**Purpose:** Test session-level caching to avoid re-resolving

**Tests:**
- ✅ `test_duplicate_node_types_reuse_resolution` - Second resolution should hit cache

**Expected Failure:** `resolve_single_node_with_context()` doesn't exist yet

---

### 3. TestCustomMappingsOverride (2 tests)
**Purpose:** Test that user's custom mappings override global table

**Tests:**
- ✅ `test_custom_mapping_overrides_global_table` - Custom should win over global
- ✅ `test_custom_mapping_skip_returns_empty_list` - "skip" should return []

**Expected Failure:** `resolve_single_node_with_context()` doesn't exist yet

---

### 4. TestHeuristicMatching (2 tests)
**Purpose:** Test heuristic matching against installed packages

**Tests:**
- ✅ `test_heuristic_matches_parenthetical_hint` - "(rgthree)" should match "rgthree-comfy"
- ✅ `test_heuristic_without_hint_falls_through` - No hint should return None

**Expected Failure:** `resolve_single_node_with_context()` doesn't exist yet

---

### 5. TestResolutionPriorityOrder (2 tests)
**Purpose:** Test that resolution strategies are checked in correct order

**Tests:**
- ✅ `test_session_cache_has_highest_priority` - Session cache should win over all
- ✅ `test_fallthrough_order_when_higher_priorities_missing` - Should fall through in order

**Expected Failure:** `resolve_single_node_with_context()` doesn't exist yet

---

## Integration Test Breakdown

### 1. TestWorkflowWithPropertiesField (1 test)
**Purpose:** Full workflow lifecycle with properties field

**Tests:**
- ✅ `test_properties_field_resolves_end_to_end` - Properties should resolve automatically

**Expected Failure:**
```
AssertionError: Should have resolved nodes
assert 0 > 0
```
Resolution doesn't use properties field yet.

---

### 2. TestSessionDeduplication (1 test)
**Purpose:** Workflow with many duplicate node types

**Tests:**
- ✅ `test_duplicate_nodes_resolve_once` - 20 nodes should dedupe to 2 types

**Status:** ✅ **PASSING** - This already works! Deduplication is happening in current code.

---

### 3. TestCustomMappingPersistence (1 test)
**Purpose:** Custom mappings persist across workflows

**Tests:**
- ✅ `test_custom_mapping_reused_in_second_workflow` - Second workflow should reuse mapping

**Expected Failure:**
```
AttributeError: 'PyprojectManager' object has no attribute 'node_mappings'
```
The `CustomNodeMappingHandler` doesn't exist yet.

---

### 4. TestHeuristicFallback (1 test)
**Purpose:** Heuristic resolution when properties missing

**Tests:**
- ✅ `test_heuristic_resolves_without_properties` - Should use heuristics for old workflows

**Expected Failure:**
```
AssertionError: Should resolve via heuristic
assert 0 > 0
```
Heuristic matching not implemented yet.

---

### 5. TestStatusNoLongerShowsMissing (1 test)
**Purpose:** Status command shouldn't show resolved nodes as missing

**Tests:**
- ✅ `test_status_after_resolution_shows_no_missing_nodes` - Main bug fix validation

**Expected Failure:**
```
AssertionError: All nodes should be resolved. Still unresolved: [...]
assert 1 == 0
```
Nodes with properties are still unresolved because properties aren't being used.

---

### 6. TestCommitPreservesResolutionContext (1 test)
**Purpose:** Commit preserves resolution mappings

**Tests:**
- ✅ `test_commit_preserves_custom_mappings` - pyproject should have node_mappings section

**Expected Failure:**
```
AttributeError: 'PyprojectManager' object has no attribute 'node_mappings'
```
The `CustomNodeMappingHandler` doesn't exist yet.

---

## Key Missing Components

Based on test failures, we need to implement:

### 1. **Data Structures** (Layer 0 - models/)
- ✅ `NodeResolutionContext` (defined in test file, needs to move to models)
- ✅ `ScoredPackageMatch` (needs to be added to models/workflow.py)

### 2. **Resolver Enhancements** (Layer 4 - resolvers/)
- ❌ `GlobalNodeResolver.resolve_single_node_with_context()` - Core new method
- ❌ `GlobalNodeResolver.fuzzy_search_packages()` - Fuzzy matching
- ❌ `GlobalNodeResolver._likely_provides_node()` - Heuristic helper

### 3. **Pyproject Handler** (Layer 6 - managers/)
- ❌ `CustomNodeMappingHandler` class in pyproject_manager.py
- ❌ `PyprojectManager.node_mappings` property

### 4. **Workflow Manager Updates** (Layer 6 - managers/)
- ❌ Update `resolve_workflow()` to build and use context
- ❌ Extract properties field from WorkflowNode during parsing

### 5. **Model Updates** (Layer 0 - models/)
- ❌ Add `properties` field to `WorkflowNode` dataclass

---

## Implementation Order Recommendation

Follow TDD approach with unit tests first:

1. **Phase 1: Data Structures**
   - Move `NodeResolutionContext` to models/workflow.py
   - Add `ScoredPackageMatch` to models/workflow.py
   - Add `properties` field to `WorkflowNode`

2. **Phase 2: Pyproject Handler**
   - Implement `CustomNodeMappingHandler`
   - Add `node_mappings` property to `PyprojectManager`
   - Run: Unit tests for custom mappings

3. **Phase 3: Core Resolution Logic**
   - Implement `resolve_single_node_with_context()` with all 5 priority levels
   - Implement heuristic helper `_likely_provides_node()`
   - Run: All unit tests should pass

4. **Phase 4: Workflow Manager Integration**
   - Update workflow parser to extract properties
   - Update `resolve_workflow()` to build and use context
   - Run: Integration tests should pass

5. **Phase 5: Fuzzy Search** (Optional for MVP)
   - Implement `fuzzy_search_packages()` for interactive strategy
   - This can be deferred if time-constrained

---

## Test Execution Commands

```bash
# Run all unit tests
uv run pytest packages/core/tests/unit/test_node_resolution_context.py -v

# Run all integration tests
uv run pytest packages/core/tests/integration/test_context_aware_node_resolution.py -v

# Run specific test
uv run pytest packages/core/tests/unit/test_node_resolution_context.py::TestPropertiesFieldResolution::test_properties_field_with_cnr_id_resolves_directly -v

# Run with output
uv run pytest packages/core/tests/unit/test_node_resolution_context.py -vv -s
```

---

## Success Metrics

When implementation is complete, we should see:

- ✅ **9/9 unit tests passing** - Core resolution logic works
- ✅ **6/6 integration tests passing** - Full flow works end-to-end
- ✅ **Properties field extracted** - WorkflowNode has properties
- ✅ **Custom mappings persist** - PyprojectManager has node_mappings
- ✅ **Resolution uses context** - Context-aware resolution working
- ✅ **Status shows correct state** - No false "missing nodes" reports

---

## Notes

### No Backwards Compatibility
Following MVP principles, there are **no backwards compatibility methods**. We directly extend existing methods:
- Use `resolve_single_node()` signature (existing)
- Add `resolve_single_node_with_context()` (new, optional context)
- Old code continues working, new code can opt into context

### Test Quality
Tests follow existing patterns from `tests/README.md`:
- AAA structure (Arrange, Act, Assert)
- Clear failure messages
- Function-scoped fixtures
- Real file operations, no mocking
- One thing per test

### Coverage
Tests cover:
- Happy paths (properties resolve)
- Edge cases (invalid properties, missing hints)
- Priority order (session > custom > properties > global)
- Persistence (custom mappings saved)
- User-facing bug (status command fix)

---

**Document Created:** 2025-10-06
**Status:** Ready for implementation
