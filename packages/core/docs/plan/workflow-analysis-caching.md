# Workflow Analysis Caching Implementation Plan

## Problem Statement

Currently, every `status`, `commit`, or `workflow resolve` command rescans all workflow JSON files and re-analyzes dependencies, even when workflows haven't changed. This leads to poor performance as the number of workflows scales:

**Performance Impact:**
- 1 workflow (100 nodes): ~200ms per scan
- 10 workflows (1000 nodes): ~2s per scan
- 50 workflows (5000 nodes): ~10s+ per scan

**Wasted Work:**
- Re-parsing JSON (1000+ nodes for large workflows)
- Re-classifying every node as builtin/custom
- Re-extracting model references from widget values
- Re-resolving nodes (even if already in pyproject.toml)
- Re-resolving models (even if already in pyproject.toml)

**User Impact:**
- Users run `status` multiple times while working → every scan is slow
- `commit` after `status` rescans everything → double penalty
- Iterative workflow development → constant rescanning

## Solution: Content-Addressed SQLite Cache with Session Optimization

Implement a persistent cache that:
1. **Stores workflow analysis results** in SQLite database
2. **Uses content hashing** for accurate invalidation
3. **Optimizes with mtime + size** heuristic for fast common case
4. **Maintains session cache** for multi-scan within same CLI invocation

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ CLI Command (status/commit/resolve)                            │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ WorkflowManager.analyze_workflow(name)                         │
├─────────────────────────────────────────────────────────────────┤
│  1. Check session cache (in-memory)          ← Same invocation │
│  2. Check SQLite cache (persistent)          ← Across commands │
│     - Fast path: mtime + size match          (~1µs)            │
│     - Fallback: content hash comparison      (~20ms)           │
│  3. Cache miss → Full analysis               (~200-500ms)      │
│  4. Store in both caches                                        │
└─────────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Cache Storage (workspace/comfydock_cache/workflows.db)         │
├─────────────────────────────────────────────────────────────────┤
│  workflow_cache table:                                          │
│    - environment_name + workflow_name (PK)                      │
│    - content_hash (normalized workflow hash)                    │
│    - workflow_mtime + workflow_size (fast check)                │
│    - dependencies_json (serialized WorkflowDependencies)        │
│    - cached_at (timestamp)                                      │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Plan

### Phase 1: Core Cache Infrastructure

#### 1.1 Create Workflow Hash Utility

**File:** `packages/core/src/comfydock_core/utils/workflow_hash.py` (NEW)

**Purpose:** Compute content-based hash for workflows with normalization

**Key Functions:**
- `compute_workflow_hash(workflow_path: Path) -> str`
  - Load workflow JSON via WorkflowRepository
  - Normalize volatile fields (UI state, revision counters, random seeds)
  - Compute blake3 hash (16-char hex = 64-bit)
  - Returns: `"a1b2c3d4e5f6g7h8"`

- `_normalize_workflow_for_hashing(workflow: dict) -> dict`
  - **Reuse existing logic** from `workflow_manager.py:_normalize_workflow_for_comparison()`
  - Remove: `extra.ds`, `extra.frontendVersion`, `revision`
  - Normalize: KSampler seed values when `randomize`/`increment` mode set
  - Sort keys for deterministic JSON serialization

**Dependencies:**
- `blake3` (already in project)
- `WorkflowRepository.load_raw_json()` (@packages/core/src/comfydock_core/repositories/workflow_repository.py:41)
- Extract normalization from `WorkflowManager._normalize_workflow_for_comparison()` (@packages/core/src/comfydock_core/managers/workflow_manager.py:356)

**Rationale:**
- Content hashing ensures 100% accuracy (no false positives)
- Normalization prevents cache misses from UI-only changes
- blake3 is fast (~20ms for 1MB workflow) and already available
- 64-bit hash provides sufficient collision resistance for workflow scale

---

#### 1.2 Create SQLite Cache Repository

**File:** `packages/core/src/comfydock_core/caching/workflow_cache.py` (NEW)

**Purpose:** Persistent storage for workflow analysis results

**Database Schema:**
```sql
CREATE TABLE IF NOT EXISTS workflow_cache (
    workflow_name TEXT NOT NULL,
    environment_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    workflow_mtime REAL NOT NULL,      -- Fast invalidation check
    workflow_size INTEGER NOT NULL,    -- Fast invalidation check
    dependencies_json TEXT NOT NULL,   -- Serialized WorkflowDependencies
    cached_at INTEGER NOT NULL,        -- Unix timestamp
    PRIMARY KEY (environment_name, workflow_name)
);

CREATE INDEX IF NOT EXISTS idx_workflow_hash
ON workflow_cache(environment_name, content_hash);
```

**Class: `WorkflowCacheRepository`**

Methods:
- `__init__(db_path: Path)`
  - Initialize SQLiteManager
  - Create schema (versioned like model_repository)
  - Initialize session cache dict

- `get(env_name: str, workflow_name: str, workflow_path: Path) -> WorkflowDependencies | None`
  - **Phase 1:** Check session cache (same CLI invocation)
    - Key: `f"{env_name}:{workflow_name}"`
    - Return if found

  - **Phase 2:** Fast heuristic check (mtime + size)
    ```python
    stat = workflow_path.stat()
    query = """
        SELECT content_hash, dependencies_json
        FROM workflow_cache
        WHERE environment_name = ? AND workflow_name = ?
          AND workflow_mtime = ? AND workflow_size = ?
    """
    # If match → deserialize and return
    ```

  - **Phase 3:** Content hash fallback
    ```python
    current_hash = compute_workflow_hash(workflow_path)
    query = """
        SELECT dependencies_json
        FROM workflow_cache
        WHERE environment_name = ? AND workflow_name = ?
          AND content_hash = ?
    """
    # If match → deserialize, update session cache, return
    ```

  - **Return:** `None` on cache miss

- `set(env_name: str, workflow_name: str, workflow_path: Path, dependencies: WorkflowDependencies)`
  - Compute content hash
  - Get file stats (mtime, size)
  - Serialize WorkflowDependencies to JSON
  - INSERT OR REPLACE into database
  - Update session cache

- `invalidate(env_name: str, workflow_name: str | None = None)`
  - Delete specific workflow or all workflows in environment
  - Clear session cache

- `get_stats(env_name: str | None = None) -> dict`
  - Return cache statistics (hit rate, entry count, total size)
  - Useful for debugging and monitoring

**Dependencies:**
- `SQLiteManager` (@packages/core/src/comfydock_core/infrastructure/sqlite_manager.py)
- `WorkflowDependencies` (@packages/core/src/comfydock_core/models/workflow.py:473)
- `compute_workflow_hash()` from workflow_hash.py

**Serialization Strategy:**
```python
# Store
dependencies_json = json.dumps(asdict(dependencies))

# Load
dependencies = WorkflowDependencies(**json.loads(dependencies_json))
```

**Rationale:**
- SQLite provides ACID guarantees (no corruption)
- Indexed queries are O(log n) fast
- Consistent with existing model_repository pattern
- Session cache eliminates redundant SQLite queries within same command
- mtime + size heuristic provides ~1µs fast path for 99% of cases

---

### Phase 2: Integration with WorkflowManager

#### 2.1 Inject Cache into WorkflowManager

**File:** `packages/core/src/comfydock_core/managers/workflow_manager.py`

**Changes:**

1. **Constructor Update** (@workflow_manager.py:55)
```python
def __init__(
    self,
    comfyui_path: Path,
    cec_path: Path,
    pyproject: PyprojectManager,
    model_repository: ModelRepository,
    node_mapping_repository: NodeMappingsRepository,
    model_downloader: ModelDownloader,
    workflow_cache: WorkflowCacheRepository,  # NEW
    environment_name: str,                     # NEW - for cache keys
):
    # ... existing init ...
    self.workflow_cache = workflow_cache
    self.environment_name = environment_name
```

2. **Update analyze_workflow()** (@workflow_manager.py:592)
```python
def analyze_workflow(self, name: str) -> WorkflowDependencies:
    """Analyze a single workflow for dependencies - with caching.

    Args:
        name: Workflow name

    Returns:
        WorkflowDependencies

    Raises:
        FileNotFoundError if workflow not found
    """
    workflow_path = self.get_workflow_path(name)

    # Check cache first
    cached = self.workflow_cache.get(
        env_name=self.environment_name,
        workflow_name=name,
        workflow_path=workflow_path
    )

    if cached is not None:
        logger.debug(f"Cache HIT for workflow '{name}'")
        return cached

    logger.debug(f"Cache MISS for workflow '{name}' - running full analysis")

    # Cache miss - run full analysis
    dependencies = self._analyze_workflow_impl(name, workflow_path)

    # Store in cache
    self.workflow_cache.set(
        env_name=self.environment_name,
        workflow_name=name,
        workflow_path=workflow_path,
        dependencies=dependencies
    )

    return dependencies

def _analyze_workflow_impl(
    self,
    name: str,
    workflow_path: Path
) -> WorkflowDependencies:
    """Internal implementation - extracted from analyze_workflow().

    This is the existing analysis logic, now private.
    """
    parser = WorkflowDependencyParser(workflow_path)
    deps = parser.analyze_dependencies()
    return deps
```

3. **Cache Invalidation Hooks**

Add cache invalidation when workflows change:

```python
def copy_all_workflows(self) -> dict[str, Path | None]:
    """Copy ALL workflows from ComfyUI to .cec for commit.

    Returns:
        Dictionary of workflow names to Path
    """
    results = {}

    # ... existing copy logic ...

    # NEW: Invalidate cache for modified/deleted workflows
    for name in results:
        if results[name] is None or results[name] == "deleted":
            self.workflow_cache.invalidate(
                env_name=self.environment_name,
                workflow_name=name
            )

    return results
```

**Rationale:**
- Minimal changes to existing API (analyze_workflow signature unchanged)
- Cache logic isolated to single method
- Invalidation ensures cache accuracy
- Logger output provides visibility for debugging

---

#### 2.2 Update Factory to Provide Cache

**File:** `packages/core/src/comfydock_core/factories/environment_factory.py`

**Changes:**

1. **Import cache repository** (top of file)
```python
from comfydock_core.caching.workflow_cache import WorkflowCacheRepository
```

2. **Create cache instance in factory** (@environment_factory.py - in create method)
```python
def create(
    self,
    name: str,
    comfyui_path: Path,
    cec_path: Path,
    # ... other params ...
) -> Environment:
    # ... existing code ...

    # NEW: Create workflow cache
    cache_db_path = self.workspace.paths.cache / "workflows.db"
    workflow_cache = WorkflowCacheRepository(cache_db_path)

    # Create workflow manager with cache
    workflow_manager = WorkflowManager(
        comfyui_path=comfyui_path,
        cec_path=cec_path,
        pyproject=pyproject,
        model_repository=model_repository,
        node_mapping_repository=node_mapping_repository,
        model_downloader=model_downloader,
        workflow_cache=workflow_cache,        # NEW
        environment_name=name,                 # NEW
    )

    # ... rest of factory code ...
```

**Dependencies:**
- `Workspace.paths.cache` (@packages/core/src/comfydock_core/core/workspace.py:89)

**Rationale:**
- Factory handles dependency injection
- Cache is workspace-scoped (shared across all environments)
- Environment name provides cache namespace

---

### Phase 3: Testing & Validation

#### 3.1 Unit Tests

**File:** `packages/core/tests/caching/test_workflow_cache.py` (NEW)

**Test Cases:**

1. **test_cache_miss_returns_none**
   - Query cache for non-existent workflow
   - Verify returns None

2. **test_cache_hit_after_set**
   - Set workflow analysis in cache
   - Query same workflow
   - Verify returns cached data
   - Verify session cache populated

3. **test_cache_invalidation_on_content_change**
   - Cache workflow analysis
   - Modify workflow content (change node)
   - Query cache
   - Verify returns None (cache miss)

4. **test_cache_hit_on_mtime_match**
   - Cache workflow
   - Query again without changing file
   - Verify fast path (mtime match)
   - Measure query time < 1ms

5. **test_cache_hit_after_touch_only**
   - Cache workflow
   - Touch file (change mtime, same content)
   - Query cache
   - Verify returns cached (hash fallback works)

6. **test_session_cache_isolation**
   - Create two cache instances
   - Set in cache A
   - Query in cache B
   - Verify SQLite shared, session cache isolated

7. **test_multi_environment_isolation**
   - Cache same workflow name in env1 and env2
   - Verify independent cache entries
   - Verify no cross-contamination

8. **test_normalization_ignores_ui_changes**
   - Cache workflow
   - Change only UI state (pan/zoom)
   - Query cache
   - Verify cache hit (normalization worked)

9. **test_cache_survives_restart**
   - Cache workflow in instance A
   - Create new instance B (same db_path)
   - Query in instance B
   - Verify cache persisted

10. **test_invalidate_specific_workflow**
    - Cache multiple workflows
    - Invalidate one workflow
    - Verify others still cached

---

#### 3.2 Integration Tests

**File:** `packages/core/tests/integration/test_workflow_caching_integration.py` (NEW)

**Test Cases:**

1. **test_status_command_uses_cache**
   - Create environment with workflows
   - Run status command (cold cache)
   - Run status again (warm cache)
   - Verify second run faster (log inspection)

2. **test_commit_after_status_uses_cache**
   - Run status command
   - Run commit command immediately
   - Verify commit doesn't re-analyze (session cache)

3. **test_cache_invalidation_on_workflow_edit**
   - Run status (cache workflows)
   - Edit workflow JSON
   - Run status again
   - Verify edited workflow re-analyzed
   - Verify other workflows still cached

4. **test_resolve_command_uses_cache**
   - Run workflow resolve
   - Run status after
   - Verify status uses cache from resolve

5. **test_cache_performance_with_many_workflows**
   - Create 20 workflows
   - Run status (cold cache) - measure time
   - Run status again (warm cache) - measure time
   - Verify warm cache >10x faster

---

#### 3.3 Performance Benchmarks

**File:** `packages/core/tests/benchmarks/test_workflow_cache_performance.py` (NEW)

**Benchmarks:**

1. **benchmark_cache_hit_latency**
   - Measure time for cache hit
   - Target: < 1ms (mtime path)

2. **benchmark_hash_computation**
   - Measure hash computation for various workflow sizes
   - 100 nodes: < 10ms
   - 500 nodes: < 30ms
   - 1000 nodes: < 50ms

3. **benchmark_full_analysis_vs_cache**
   - Compare full analysis vs cache hit
   - Measure speedup factor
   - Target: >20x faster for cache hit

4. **benchmark_session_cache_effectiveness**
   - Simulate status → commit sequence
   - Measure cache reuse rate
   - Target: 100% cache hit for commit

---

### Phase 4: Migration & Rollout

#### 4.1 Database Migration Strategy

**Versioning:** Follow model_repository pattern

```python
# workflow_cache.py
SCHEMA_VERSION = 1

CREATE_SCHEMA_INFO_TABLE = """
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER PRIMARY KEY
)
"""

def ensure_schema(self):
    """Create database schema if needed."""
    # Create tables...

    # Check version
    current_version = self.get_schema_version()
    if current_version != SCHEMA_VERSION:
        self.migrate_schema(current_version, SCHEMA_VERSION)

def migrate_schema(self, from_version: int, to_version: int):
    """Migrate database schema between versions."""
    if from_version == to_version:
        return

    logger.info(f"Migrating workflow cache schema v{from_version} → v{to_version}")

    # For v0 → v1: Just drop and recreate (cache is ephemeral)
    self.sqlite.execute_write("DROP TABLE IF EXISTS workflow_cache")
    # ... recreate tables ...
```

**Rationale:**
- Cache is ephemeral (safe to drop/recreate)
- Versioning prevents corruption on schema changes
- Consistent with existing model_repository pattern

---

#### 4.2 Cache Management Commands

**Future Enhancement:** Add CLI commands for cache management

```bash
# Clear workflow cache
comfydock cache clear workflows

# Show cache statistics
comfydock cache stats

# Rebuild cache for environment
comfydock cache rebuild
```

**Implementation location:** `packages/cli/comfydock_cli/global_commands.py`

---

### Phase 5: Monitoring & Observability

#### 5.1 Logging Strategy

**Log Levels:**
- `DEBUG`: Cache hits/misses, hash computation times
- `INFO`: Cache invalidation events, schema migrations
- `WARNING`: Cache errors (fallback to full analysis)

**Example Logs:**
```
DEBUG: Cache HIT for workflow 'my_workflow' (mtime match, 0.001ms)
DEBUG: Cache MISS for workflow 'new_workflow' - running full analysis
INFO: Invalidated cache for 3 modified workflows
WARNING: Cache read error - falling back to full analysis: <error>
```

---

#### 5.2 Performance Metrics

Track in cache repository:
- Total queries
- Cache hits / misses
- Average hit latency
- Average miss latency
- Session cache reuse rate

**Implementation:**
```python
class WorkflowCacheRepository:
    def __init__(self, db_path: Path):
        # ... existing init ...
        self._stats = {
            'queries': 0,
            'hits': 0,
            'misses': 0,
            'session_hits': 0,
        }

    def get_stats(self) -> dict:
        total = self._stats['queries']
        if total == 0:
            return self._stats

        return {
            **self._stats,
            'hit_rate': self._stats['hits'] / total,
            'session_hit_rate': self._stats['session_hits'] / total,
        }
```

---

## Expected Performance Improvements

### Benchmark Targets

**Scenario:** 10 workflows, each with 100 nodes

| Operation | Without Cache | With Cache (Cold) | With Cache (Warm) | Speedup |
|-----------|---------------|-------------------|-------------------|---------|
| First status | 2000ms | 2000ms | - | 1x |
| Second status | 2000ms | - | 10ms | 200x |
| Commit after status | 2000ms | - | 1ms | 2000x |
| Edit 1 workflow, status | 2000ms | - | 200ms | 10x |

**Session Cache Impact:**
- status → commit sequence: **100% cache reuse**
- status → resolve → status: **100% cache reuse**
- Multiple status calls: **>90% cache reuse**

---

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Create `utils/workflow_hash.py`
  - [ ] Implement `compute_workflow_hash()`
  - [ ] Extract `_normalize_workflow_for_hashing()` from workflow_manager
  - [ ] Add unit tests for normalization edge cases
  - [ ] Benchmark hash computation performance

- [ ] Create `caching/workflow_cache.py`
  - [ ] Implement SQLite schema with versioning
  - [ ] Implement `WorkflowCacheRepository` class
  - [ ] Add session cache dict
  - [ ] Implement `get()` with 3-phase lookup
  - [ ] Implement `set()` with dual cache update
  - [ ] Implement `invalidate()` method
  - [ ] Add stats tracking

### Phase 2: Integration
- [ ] Update `workflow_manager.py`
  - [ ] Add cache parameter to constructor
  - [ ] Add environment_name parameter
  - [ ] Extract `_analyze_workflow_impl()` private method
  - [ ] Update `analyze_workflow()` with cache logic
  - [ ] Add cache invalidation to `copy_all_workflows()`
  - [ ] Add cache invalidation to workflow modification methods

- [ ] Update `environment_factory.py`
  - [ ] Import `WorkflowCacheRepository`
  - [ ] Create cache instance in factory
  - [ ] Pass cache to WorkflowManager constructor
  - [ ] Pass environment name to WorkflowManager

### Phase 3: Testing
- [ ] Write unit tests (`test_workflow_cache.py`)
  - [ ] Test cache miss behavior
  - [ ] Test cache hit behavior
  - [ ] Test content invalidation
  - [ ] Test mtime fast path
  - [ ] Test hash fallback
  - [ ] Test session cache isolation
  - [ ] Test multi-environment isolation
  - [ ] Test normalization edge cases
  - [ ] Test cache persistence
  - [ ] Test invalidation

- [ ] Write integration tests (`test_workflow_caching_integration.py`)
  - [ ] Test status command caching
  - [ ] Test commit after status
  - [ ] Test cache invalidation on edit
  - [ ] Test resolve command caching
  - [ ] Test performance with many workflows

- [ ] Write performance benchmarks
  - [ ] Benchmark cache hit latency
  - [ ] Benchmark hash computation
  - [ ] Benchmark full analysis vs cache
  - [ ] Benchmark session cache effectiveness

### Phase 4: Documentation
- [ ] Update codebase-map.md with new cache files
- [ ] Add docstrings to all new methods
- [ ] Document cache invalidation strategy
- [ ] Add performance tuning guide

### Phase 5: Monitoring
- [ ] Add debug logging for cache operations
- [ ] Add performance metrics tracking
- [ ] Add cache statistics endpoint
- [ ] Test logging output in real usage

---

## File Reference Summary

### New Files
1. `packages/core/src/comfydock_core/utils/workflow_hash.py`
   - Hash computation and normalization

2. `packages/core/src/comfydock_core/caching/workflow_cache.py`
   - SQLite cache repository

3. `packages/core/tests/caching/test_workflow_cache.py`
   - Unit tests

4. `packages/core/tests/integration/test_workflow_caching_integration.py`
   - Integration tests

5. `packages/core/tests/benchmarks/test_workflow_cache_performance.py`
   - Performance benchmarks

### Modified Files
1. `packages/core/src/comfydock_core/managers/workflow_manager.py`
   - Lines to modify: 55 (constructor), 592 (analyze_workflow), 396 (copy_all_workflows)
   - Extract normalization logic from line 356

2. `packages/core/src/comfydock_core/factories/environment_factory.py`
   - Add cache creation in factory method

3. `packages/core/docs/codebase-map.md`
   - Add cache files to Caching section

### Existing Dependencies
1. `packages/core/src/comfydock_core/infrastructure/sqlite_manager.py`
   - Used by: workflow_cache.py

2. `packages/core/src/comfydock_core/repositories/workflow_repository.py`
   - Used by: workflow_hash.py (line 41: load_raw_json)

3. `packages/core/src/comfydock_core/models/workflow.py`
   - Used by: workflow_cache.py (line 473: WorkflowDependencies)

4. `packages/core/src/comfydock_core/core/workspace.py`
   - Used by: environment_factory.py (line 89: paths.cache)

---

## Risk Mitigation

### Risk 1: Cache Corruption
**Mitigation:**
- SQLite ACID guarantees prevent corruption
- Schema versioning allows clean migration
- Cache is ephemeral (can be dropped/rebuilt)
- Fallback to full analysis on any cache error

### Risk 2: Hash Collisions
**Mitigation:**
- 64-bit blake3 hash provides 1 in 2^64 collision probability
- For 1 million workflows: ~0.000000003% collision chance
- If collision: worst case is incorrect cache hit (detectable via testing)
- Can increase hash length if needed (blake3 supports any length)

### Risk 3: Cache Stale Data
**Mitigation:**
- Content hashing ensures accuracy (100% reliable)
- mtime + size heuristic is conservative (only trusts exact match)
- Hash fallback catches mtime-only changes
- Invalidation hooks on workflow modifications
- Users can clear cache manually if needed

### Risk 4: Performance Regression
**Mitigation:**
- Benchmarks verify cache is faster than no cache
- Session cache eliminates SQLite overhead for repeated scans
- mtime fast path is <1µs (negligible overhead)
- Hash computation only on cache miss (same cost as today)
- Gradual rollout with feature flag if needed

### Risk 5: Disk Space Usage
**Mitigation:**
- WorkflowDependencies JSON is small (~1-10KB per workflow)
- 100 workflows ≈ 1MB cache size
- SQLite compression reduces size further
- Add cache cleanup command for large workspaces
- Monitor cache size in stats

---

## Future Enhancements

### 1. Lazy Resolution Optimization
Once cache is working, add second-level optimization:
- Build lookup of known nodes/models from pyproject
- Skip resolution for known dependencies
- Only resolve unknowns
- **Expected impact:** 50-100x faster for resolved workflows

### 2. TTL-Based Invalidation
Add time-based invalidation for extra safety:
- Cache entries expire after N hours (configurable)
- Force re-analysis periodically
- Useful for catching external changes

### 3. Cache Warmup
Pre-populate cache on environment creation:
- Analyze all workflows during setup
- Background cache refresh on idle
- Parallel analysis for speed

### 4. Cache Sharing
Explore team-wide cache sharing:
- Hash-based cache is content-addressable
- Could share cache entries via git LFS
- Requires careful security review

### 5. Incremental Diffing
For very large workflows (1000+ nodes):
- Cache intermediate parsing results
- Diff against cached workflow structure
- Only re-analyze changed nodes
- **Complexity:** High, only add if profiling shows need

---

## Success Metrics

### Performance Goals
- [ ] Cache hit latency: < 1ms (mtime path)
- [ ] Cache hit latency: < 20ms (hash path)
- [ ] status command with 10 cached workflows: < 50ms total
- [ ] Second status after first: >20x faster
- [ ] Session cache reuse: >90% for commit after status

### Quality Goals
- [ ] Zero cache corruption incidents
- [ ] Zero false positive cache hits (wrong data returned)
- [ ] Cache accuracy: 100% (content hashing guarantee)
- [ ] Test coverage: >90% for cache code
- [ ] All benchmarks passing

### User Impact Goals
- [ ] Users report faster status/commit commands
- [ ] No user-facing behavior changes (transparent cache)
- [ ] No new error cases (graceful fallback)
- [ ] Improved UX for large workspace workflows

---

## Timeline Estimate

- **Phase 1 (Core Infrastructure):** 4-6 hours
  - workflow_hash.py: 1-2 hours
  - workflow_cache.py: 2-3 hours
  - Initial testing: 1 hour

- **Phase 2 (Integration):** 2-3 hours
  - workflow_manager.py changes: 1 hour
  - environment_factory.py changes: 30 min
  - Integration testing: 1-1.5 hours

- **Phase 3 (Testing):** 3-4 hours
  - Unit tests: 1-2 hours
  - Integration tests: 1 hour
  - Benchmarks: 1 hour

- **Phase 4 (Documentation):** 1 hour
  - Code documentation: 30 min
  - Update codebase map: 30 min

**Total:** 10-14 hours for complete implementation

---

## Notes for Implementation Session

### Key Decisions Made
1. **SQLite over JSON files:** Better consistency, performance, and consistency with existing code
2. **Session cache included:** Critical for status → commit performance
3. **mtime + size heuristic:** Provides fast path without complexity
4. **Content hashing required:** 100% accuracy guarantee
5. **Reuse normalization:** Extract from workflow_manager to avoid duplication

### Critical Path Items
1. Extract normalization logic cleanly (don't break existing code)
2. Test hash stability (same workflow = same hash)
3. Verify cache invalidation hooks catch all modifications
4. Benchmark before/after to prove performance gain
5. Test multi-environment isolation thoroughly

### Testing Focus Areas
1. Normalization edge cases (randomize seeds, UI state)
2. Cache invalidation on all workflow modifications
3. Session cache isolation between instances
4. Multi-environment cache isolation
5. Performance regression (cache shouldn't slow down misses)

### Potential Gotchas
1. **Normalization completeness:** Missing a field means false cache misses
2. **Session cache lifecycle:** Must be instance-scoped, not module-scoped
3. **Environment name propagation:** Must flow through all factory/manager chains
4. **SQLite concurrency:** Multiple processes (not threads) need careful testing
5. **Hash computation cost:** Ensure only done when necessary (mtime short-circuit)

### Debug Tips
1. Add `COMFYDOCK_CACHE_DEBUG=1` env var for verbose logging
2. Log cache hit/miss with timing info
3. Track cache stats in development
4. Add explicit cache clear command early for testing
5. Verify normalized workflow JSON in tests (snapshot testing)
