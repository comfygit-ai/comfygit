# Model Source Preservation Tests - Summary

## Status: ✅ TESTS CREATED - ALL FAILING AS EXPECTED

## Test File
`tests/integration/test_model_source_preservation.py`

## Test Coverage (3 tests)

### 1. `test_progressive_resolution_preserves_sources_from_repository`
**Purpose**: Tests the progressive/interactive resolution path
**Code Path**: `_write_single_model_resolution()` in `workflow_manager.py:109-188`
**Bug Proven**: ✅ Sources=[] when should be ['https://civitai.com/api/download/models/12345']

**Failure Message**:
```
BUG: Expected source 'https://civitai.com/api/download/models/12345' in workflow model, got []
```

### 2. `test_bulk_resolution_preserves_sources_from_repository`
**Purpose**: Tests the bulk resolution path with multiple models
**Code Path**: `apply_resolution()` in `workflow_manager.py:1010-1027`
**Bug Proven**: ✅ Both checkpoint and lora have sources=[] instead of their URLs

**Failure Message**:
```
BUG: Checkpoint missing source. Got sources: []
```

### 3. `test_collaboration_scenario_fails_without_sources`
**Purpose**: Real-world scenario - Dev A adds model, Dev B can't download it
**Code Path**: Complete workflow resolution → commit → pyproject check
**Bug Proven**: ✅ Model committed to pyproject without sources

**Failure Message**:
```
BUG: Model committed without source! Dev B won't be able to download it.
Sources in pyproject: [], Expected: ['https://civitai.com/api/download/models/9999']
```

## What These Tests Validate

### ✅ Bug Confirmed
All tests fail because:
- Models exist in repository WITH source URLs ✓
- Models are resolved successfully ✓
- Sources are NOT written to pyproject.toml ✗ (BUG)

### ✅ Test Quality
- **Minimal & Focused**: 3 tests, ~220 lines
- **Clear Scenarios**: Progressive, bulk, and collaboration paths
- **Good Messages**: Each failure explains the bug
- **Proper Isolation**: Uses test fixtures, no shared state
- **AAA Pattern**: Clear Arrange/Act/Assert structure

### ✅ Ready for Implementation
When the fix is implemented, these tests should:
1. Pass immediately (no test changes needed)
2. Validate both code paths are fixed
3. Prevent regression

## Key Test Data

Each test:
1. Creates model files using `ModelIndexBuilder`
2. Indexes them (gets real BLAKE3 hash)
3. Adds source URL to repository
4. Resolves workflow
5. Asserts sources are in pyproject (FAILS)

## Running Tests

```bash
# Run all 3 tests
uv run pytest tests/integration/test_model_source_preservation.py -v

# Run specific test
uv run pytest tests/integration/test_model_source_preservation.py::TestModelSourcePreservation::test_progressive_resolution_preserves_sources_from_repository -v
```

## Expected Behavior After Fix

After implementing the fix in `workflow_manager.py`:
- `_write_single_model_resolution()` fetches sources from repository
- `apply_resolution()` fetches sources from repository
- `ManifestModel` and `ManifestWorkflowModel` are created WITH sources
- Tests pass ✅

## Implementation Hints

The fix needs to:
1. Call `self.model_repository.get_sources(model_hash)` before writing
2. Extract URLs from returned sources: `[s['url'] for s in sources]`
3. Pass sources to `ManifestWorkflowModel(sources=sources)`
4. Pass sources to `ManifestModel(sources=sources)`

See plan at: `packages/core/docs/plan/model-source-preservation.md`
