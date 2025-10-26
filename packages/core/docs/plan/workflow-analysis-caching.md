# Workflow Analysis & Resolution Caching Implementation Plan

## Problem Statement

Currently, every `status`, `commit`, or `workflow resolve` command:
1. **Re-parses** all workflow JSON files (even when unchanged)
2. **Re-resolves** all custom nodes and models (even when already in pyproject.toml)

This leads to poor performance as the number of workflows scales:

**Performance Impact:**
- 1 workflow (100 nodes): ~250ms per command (100ms parse + 150ms resolve)
- 10 workflows (1000 nodes): ~2.5s per command
- 50 workflows (5000 nodes): ~12s+ per command

**Wasted Work:**
- Re-parsing JSON (1000+ workflow nodes for large workflows)
- Re-classifying every node as builtin/custom
- Re-extracting model references from widget values
- **Re-resolving custom nodes** (loading 37k global mappings, checking pyproject)
- **Re-resolving models** (querying model index, checking pyproject)

**The Critical Gap in Current Implementation:**
The existing cache implementation (already in codebase) only caches WorkflowDependencies (the parsing phase). It does NOT cache ResolutionResult (the resolution phase). This means:
- ✅ Workflow JSON parsing is cached (~100ms saved)
- ❌ Node resolution still runs every time (~150ms wasted)
- ❌ Model resolution still runs every time (~50ms wasted)
- ❌ Global mappings loaded on every status (~200ms wasted on first workflow)

**User Impact:**
- Users run `status` multiple times while working → every scan is slow
- `commit` after `status` rescans everything → double penalty
- Iterative workflow development → constant rescanning
- **Most time is spent re-resolving, not re-parsing**

---

## Solution: Full Workflow Analysis + Resolution Caching with Context-Aware Invalidation

Enhance the existing cache to store BOTH analysis AND resolution results, with smart invalidation based on workflow-specific changes to pyproject.toml.

### Key Concepts

**Terminology Clarification:**
- **Workflow Node** = A single element in a workflow (e.g., "Mute / Bypass Repeater (rgthree)")
- **Custom Node Package** = A ComfyUI extension/plugin (e.g., "rgthree-comfy" git repo)
- **Resolution** = Mapping workflow nodes → custom node packages (using registries, pyproject, etc.)
- **Model** = AI model file referenced by workflow (e.g., "v1-5-pruned-emaonly.safetensors")

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ CLI Command (status/commit/resolve)                            │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ WorkflowManager.analyze_workflow_cached(name)                  │
├─────────────────────────────────────────────────────────────────┤
│  1. Check session cache (in-memory)          ← Same invocation │
│  2. Check SQLite cache (persistent)          ← Across commands │
│     - Phase 1: Workflow mtime + size         (~1µs)            │
│     - Phase 2: Pyproject mtime check         (~1µs)            │
│     - Phase 3: Resolution context hash       (~7ms)            │
│     - Phase 4: Workflow content hash         (~20ms)           │
│  3. Cache miss → Full analysis + resolution  (~250ms)          │
│  4. Store BOTH analysis AND resolution                          │
└─────────────────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Cache Storage (workspace/comfydock_cache/workflows.db)         │
├─────────────────────────────────────────────────────────────────┤
│  workflow_cache table:                                          │
│    - environment_name + workflow_name (PK)                      │
│    - workflow_hash (normalized workflow content)                │
│    - workflow_mtime + workflow_size (fast check)                │
│    - resolution_context_hash (workflow-specific pyproject)      │
│    - pyproject_mtime (fast reject path)                         │
│    - dependencies_json (WorkflowDependencies)                   │
│    - resolution_json (ResolutionResult) ← NEW                   │
│    - comfydock_version (global invalidator)                     │
│    - cached_at (timestamp)                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## What Needs to Be Cached

### Current Implementation (Phase 1 - DONE ✅)
```python
@dataclass
class WorkflowDependencies:
    workflow_name: str
    builtin_nodes: list[WorkflowNode]       # ✅ Cached
    non_builtin_nodes: list[WorkflowNode]   # ✅ Cached
    found_models: list[WorkflowNodeWidgetRef]  # ✅ Cached
```

**This caches the PARSING result** (~100ms saved)

### What's Missing (Phase 2 - TO BE IMPLEMENTED)
```python
@dataclass
class ResolutionResult:
    workflow_name: str
    nodes_resolved: list[ResolvedNodePackage]      # ❌ NOT cached
    nodes_unresolved: list[WorkflowNode]           # ❌ NOT cached
    nodes_ambiguous: list[list[ResolvedNodePackage]]  # ❌ NOT cached
    models_resolved: list[ResolvedModel]           # ❌ NOT cached
    models_unresolved: list[WorkflowNodeWidgetRef] # ❌ NOT cached
    models_ambiguous: list[list[ResolvedModel]]    # ❌ NOT cached
```

**This is the RESOLUTION result** (~200ms wasted by not caching)

---

## Resolution Context: What Affects Resolution Results

Resolution results depend on external state beyond the workflow file itself. We need to track this "resolution context" to know when to invalidate the cache.

### 1. Custom Node Resolution Inputs

#### 1.1 Custom Node Mappings (from pyproject.toml)
**Location:** `[tool.comfydock.workflows.<workflow_name>.custom_node_map]`

```toml
[tool.comfydock.workflows.my_workflow.custom_node_map]
"Mute / Bypass Repeater (rgthree)" = "rgthree-comfy"
"Optional Node" = false  # marked as optional
```

**Impact:** Priority 1 resolution - overrides all other methods
**Invalidation:** Change to ANY mapping for nodes in THIS workflow

#### 1.2 Declared Custom Node Packages (from pyproject.toml)
**Source:** `PyprojectManager.nodes.get_existing()`

Returns custom node packages declared in `[project.dependencies]` or `[tool.uv.sources]`

**Impact:** When multiple packages could provide a node, prefer already-declared ones
**Invalidation:** Change to package declarations for nodes THIS workflow uses

#### 1.3 Node Properties (embedded in workflow JSON)
**Source:** `WorkflowNode.properties.cnr_id`

```json
{
  "properties": {
    "cnr_id": "rgthree-comfy",
    "ver": "f754c4765849aa748abb35a1f030a5ed6474a69b"
  }
}
```

**Impact:** Priority 2 resolution - embedded package ID
**Invalidation:** Part of workflow content hash (already handled ✅)

#### 1.4 Global Node Mappings (static data)
**Source:** `global_node_mappings.json.gz` (37,437 node signatures → 3,706 packages)

**Impact:** Priority 3 resolution - fallback lookup
**Invalidation:** Only changes with comfydock version upgrade

### 2. Model Resolution Inputs

#### 2.1 Previous Model Resolutions (from pyproject.toml)
**Location:** `[tool.comfydock.workflows.<workflow_name>.models]`

```toml
[[tool.comfydock.workflows.my_workflow.models]]
hash = "b83fd660ccfcf796"
relative_path = "checkpoints/v1-5.safetensors"
status = "resolved"
nodes = [{node_id = "4", node_type = "CheckpointLoaderSimple", ...}]
```

**Impact:** Priority 0 resolution - return cached model resolution
**Invalidation:** Change to ANY model entry for THIS workflow

#### 2.2 Model Repository Index (SQLite database)
**Source:** `ModelRepository.get_all_models()`

**Impact:** Fallback strategies (exact path, case-insensitive, filename match)
**Invalidation:** New models added/removed that match THIS workflow's references

### 3. What Doesn't Need Invalidation

- **Global node mappings** - static data, only changes with package upgrade
- **Model config** - static data, only changes with package upgrade
- **Node properties** - embedded in workflow JSON (already in content hash)

**Solution:** Include `comfydock_core.__version__` as global invalidator

---

## Resolution Context Hashing Strategy

Instead of invalidating ALL workflows when pyproject.toml changes, compute a **workflow-specific** hash of only the parts that affect THIS workflow.

### Context Hash Components

```python
def compute_resolution_context_hash(
    dependencies: WorkflowDependencies,
    workflow_name: str
) -> str:
    """Compute hash of resolution context for this specific workflow.

    Only includes pyproject data that affects THIS workflow's resolution.
    """
    context = {}

    # 1. Custom node mappings for nodes in THIS workflow
    node_types = {n.type for n in dependencies.non_builtin_nodes}
    custom_map = pyproject.workflows.get_custom_node_map(workflow_name)
    context["custom_mappings"] = {
        node_type: custom_map[node_type]
        for node_type in node_types
        if node_type in custom_map
    }

    # 2. Declared packages for nodes THIS workflow uses
    # (Need to map node types to packages first)
    declared_packages = pyproject.nodes.get_existing()

    relevant_packages = set()
    for node in dependencies.non_builtin_nodes:
        # Check custom mapping
        if node.type in context["custom_mappings"]:
            pkg = context["custom_mappings"][node.type]
            if isinstance(pkg, str):
                relevant_packages.add(pkg)
        # Check cnr_id in properties
        elif node.properties and node.properties.get('cnr_id'):
            relevant_packages.add(node.properties['cnr_id'])

    context["declared_packages"] = {
        pkg: {
            "version": declared_packages[pkg].version,
            "git_ref": declared_packages[pkg].git_ref
        }
        for pkg in relevant_packages
        if pkg in declared_packages
    }

    # 3. Model entries from pyproject for THIS workflow
    workflow_models = pyproject.workflows.get_workflow_models(workflow_name)
    model_pyproject_data = {}
    for manifest_model in workflow_models:
        for ref in manifest_model.nodes:
            ref_key = f"{ref.node_id}_{ref.widget_index}"
            model_pyproject_data[ref_key] = {
                "hash": manifest_model.hash,
                "status": manifest_model.status,
                "criticality": manifest_model.criticality,
                "sources": manifest_model.sources
            }
    context["workflow_models_pyproject"] = model_pyproject_data

    # 4. Model index subset (only models THIS workflow references)
    model_index_subset = {}
    for model_ref in dependencies.found_models:
        filename = Path(model_ref.widget_value).name
        models = model_repository.find_by_filename(filename)
        if models:
            model_index_subset[filename] = [m.hash for m in models]
    context["model_index_subset"] = model_index_subset

    # 5. Comfydock version (global invalidator)
    context["comfydock_version"] = comfydock_core.__version__

    # Hash the normalized context
    context_json = json.dumps(context, sort_keys=True)
    return blake3(context_json.encode()).hexdigest()[:16]
```

### Cache Lookup Strategy with Context Checking

```python
def get_cached_workflow_analysis(
    env_name: str,
    workflow_name: str,
    workflow_path: Path
) -> CachedWorkflowAnalysis | None:
    """Get cached analysis + resolution with smart invalidation."""

    # Phase 1: Session cache check
    session_key = f"{env_name}:{workflow_name}"
    if session_key in self._session_cache:
        return self._session_cache[session_key]

    # Phase 2: Check workflow mtime + size (fast path)
    stat = workflow_path.stat()
    cached = self._query_by_mtime_size(env_name, workflow_name, stat)

    if not cached:
        # Workflow file changed - check content hash
        workflow_hash = compute_workflow_hash(workflow_path)
        cached = self._query_by_content_hash(env_name, workflow_name, workflow_hash)

        if not cached:
            return None  # Cache miss - workflow content changed

    # Phase 3: Workflow content matched, now check resolution context

    # Quick reject: If pyproject.toml hasn't been touched, context can't have changed
    pyproject_mtime = self.pyproject_path.stat().st_mtime
    if pyproject_mtime == cached.pyproject_mtime:
        # Nothing changed - instant hit
        self._session_cache[session_key] = cached
        return cached

    # Pyproject changed - need to check if it affects THIS workflow
    current_context_hash = compute_resolution_context_hash(
        cached.dependencies,
        workflow_name
    )

    if current_context_hash == cached.resolution_context_hash:
        # Pyproject changed but not for THIS workflow - still valid
        # Update pyproject_mtime to avoid future recomputation
        self._update_pyproject_mtime(env_name, workflow_name, pyproject_mtime)
        self._session_cache[session_key] = cached
        return cached

    # Context changed - resolution is stale
    # Return dependencies (still valid) but signal resolution needed
    return CachedWorkflowAnalysis(
        dependencies=cached.dependencies,
        resolution=None,  # Stale - needs re-resolution
        needs_reresolution=True
    )
```

---

## Updated Database Schema

```sql
CREATE TABLE IF NOT EXISTS workflow_cache (
    workflow_name TEXT NOT NULL,
    environment_name TEXT NOT NULL,

    -- Workflow content tracking
    workflow_hash TEXT NOT NULL,              -- Content hash (normalized)
    workflow_mtime REAL NOT NULL,             -- Fast path check
    workflow_size INTEGER NOT NULL,           -- Fast path check

    -- Resolution context tracking (NEW)
    resolution_context_hash TEXT NOT NULL,    -- Workflow-specific pyproject hash
    pyproject_mtime REAL NOT NULL,            -- Fast reject path
    comfydock_version TEXT NOT NULL,          -- Global invalidator

    -- Cached data
    dependencies_json TEXT NOT NULL,          -- WorkflowDependencies
    resolution_json TEXT NOT NULL,            -- ResolutionResult (NEW)

    -- Metadata
    cached_at INTEGER NOT NULL,

    PRIMARY KEY (environment_name, workflow_name)
);

CREATE INDEX IF NOT EXISTS idx_workflow_hash
ON workflow_cache(environment_name, workflow_hash);

CREATE INDEX IF NOT EXISTS idx_resolution_context
ON workflow_cache(environment_name, resolution_context_hash);
```

---

## Cache Invalidation Scenarios

### Scenario 1: User adds unrelated custom node package
```
Workflow A uses: ["rgthree-comfy"]
Workflow B uses: ["comfyui-depthflow-nodes"]

User runs: comfydock add comfyui-animatediff
```

**Workflow A context:**
```python
{
    "declared_packages": {"rgthree-comfy": {...}},  # unchanged
    "workflow_models_pyproject": {...}  # unchanged
}
```
**Result:** Hash UNCHANGED → Cache HIT ✅

### Scenario 2: User updates git ref for package workflow uses
```
Workflow A uses custom node from: rgthree-comfy @ abc123

User edits pyproject: rgthree-comfy @ def456
```

**Workflow A context:**
```python
{
    "declared_packages": {
        "rgthree-comfy": {"git_ref": "def456"}  # CHANGED
    }
}
```
**Result:** Hash CHANGED → Re-resolve ✅

### Scenario 3: User marks model as optional
```
Workflow A model entry changes:
  criticality: null → "optional"
```

**Workflow A context:**
```python
{
    "workflow_models_pyproject": {
        "ref_10_0": {"criticality": "optional"}  # CHANGED
    }
}
```
**Result:** Hash CHANGED → Re-resolve ✅

### Scenario 4: User downloads new model
```
Workflow A references: "v1-5.safetensors" (currently missing)

User downloads: v1-5.safetensors
```

**Workflow A context:**
```python
{
    "model_index_subset": {
        "v1-5.safetensors": ["abc123"]  # NEW
    }
}
```
**Result:** Hash CHANGED → Re-resolve ✅

---

## Implementation Plan

### Phase 1: Enhance Cache Schema (v1 → v2 migration)

**File:** `packages/core/src/comfydock_core/caching/workflow_cache.py`

**Changes:**
1. Update schema to v2 with new fields:
   - `resolution_context_hash TEXT NOT NULL`
   - `pyproject_mtime REAL NOT NULL`
   - `resolution_json TEXT NOT NULL`
   - `comfydock_version TEXT NOT NULL`

2. Add migration logic:
```python
def migrate_schema(self, from_version: int, to_version: int):
    if from_version < 2:
        # Drop v1 cache (resolution not cached - safe to rebuild)
        self.sqlite.execute_write("DROP TABLE IF EXISTS workflow_cache")
        self._create_v2_schema()
```

3. Update `set()` method to store resolution:
```python
def set(
    self,
    env_name: str,
    workflow_name: str,
    workflow_path: Path,
    dependencies: WorkflowDependencies,
    resolution: ResolutionResult,  # NEW
    resolution_context_hash: str,  # NEW
):
    # ... existing code ...
    resolution_json = self._serialize_resolution(resolution)
    pyproject_mtime = self.pyproject_path.stat().st_mtime
    comfydock_version = comfydock_core.__version__

    # Store all data
    # ...
```

4. Update `get()` method with context checking:
```python
def get(...) -> CachedWorkflowAnalysis | None:
    # Phase 1: Session cache
    # Phase 2: mtime + size check
    # Phase 3: Content hash fallback
    # Phase 4: Resolution context check (NEW)
    # Phase 5: Return result or signal re-resolution needed
```

### Phase 2: Add Resolution Context Computation

**File:** `packages/core/src/comfydock_core/managers/workflow_manager.py`

**Changes:**

1. Add method to compute resolution context:
```python
def _compute_resolution_context_hash(
    self,
    dependencies: WorkflowDependencies,
    workflow_name: str
) -> str:
    """Compute workflow-specific resolution context hash."""
    # Implementation as shown above
```

2. Update workflow analysis to cache BOTH:
```python
def analyze_workflow_cached(self, name: str) -> tuple[WorkflowDependencies, ResolutionResult]:
    """Analyze and resolve workflow with full caching."""

    # Check cache
    cached = self.workflow_cache.get(...)

    if cached and not cached.needs_reresolution:
        return (cached.dependencies, cached.resolution)

    if cached and cached.needs_reresolution:
        # Workflow content valid, but resolution stale
        dependencies = cached.dependencies
    else:
        # Full miss - analyze workflow
        dependencies = self._analyze_workflow_impl(name)

    # Resolve (either from cache miss or stale resolution)
    resolution = self.resolve_workflow(dependencies)

    # Compute context and cache
    context_hash = self._compute_resolution_context_hash(dependencies, name)
    self.workflow_cache.set(
        env_name=self.environment_name,
        workflow_name=name,
        workflow_path=workflow_path,
        dependencies=dependencies,
        resolution=resolution,
        resolution_context_hash=context_hash
    )

    return (dependencies, resolution)
```

3. Update callers to use new method:
```python
# OLD
def analyze_single_workflow_status(self, name: str):
    dependencies = self.analyze_workflow(name)  # Only cached parsing
    resolution = self.resolve_workflow(dependencies)  # Always runs

# NEW
def analyze_single_workflow_status(self, name: str):
    dependencies, resolution = self.analyze_workflow_cached(name)  # Both cached!
```

### Phase 3: Pass Dependencies to Cache

**File:** `packages/core/src/comfydock_core/caching/workflow_cache.py`

The cache needs access to pyproject and model_repository to compute resolution context.

**Option A:** Pass managers to cache constructor:
```python
def __init__(
    self,
    db_path: Path,
    pyproject_manager: PyprojectManager,  # NEW
    model_repository: ModelRepository      # NEW
):
```

**Option B:** Compute context in WorkflowManager, pass to cache:
```python
# In workflow_manager.py
context_hash = self._compute_resolution_context_hash(dependencies, workflow_name)

# Pass pre-computed hash to cache
cache.set(..., resolution_context_hash=context_hash)
```

**Recommendation:** Option B - keeps cache layer simple, computation in manager

---

## Expected Performance Improvements

### Benchmark Targets (Updated)

**Scenario:** 10 workflows, each with 100 nodes

| Operation | Current (Partial Cache) | With Full Cache | Speedup |
|-----------|------------------------|-----------------|---------|
| First status | 2500ms (parse only cached) | 2500ms | 1x |
| Second status (no changes) | 1500ms (still resolves) | 10ms | 150x |
| Second status (pyproject changed, different workflow) | 1500ms | 70ms (context check) | 21x |
| Second status (pyproject changed, affects workflow) | 1500ms | 300ms (re-resolve only) | 5x |
| Edit 1 workflow, status | 2300ms | 250ms | 9x |

### Performance Breakdown

**Current Implementation (v1 - parsing only):**
```
Parse workflow JSON:        0ms    (✅ cached)
Resolve 31 nodes:          200ms   (❌ runs every time)
  - Load global mappings:  200ms   (one-time per session)
  - Actual resolution:      30ms   (per workflow)
Resolve models:             50ms   (❌ runs every time)
Total:                     250ms   (per workflow, after first)
```

**With Full Cache (v2 - parsing + resolution):**
```
Check workflow mtime:        1µs   (✅ instant)
Check pyproject mtime:       1µs   (✅ instant, 99% of cases)
Return cached resolution:    0ms   (✅ instant)
Total:                      <1ms   (250x improvement!)
```

**When pyproject changes (but not for this workflow):**
```
Check workflow mtime:        1µs
Check pyproject mtime:       1µs   (changed!)
Compute context hash:        7ms   (extract relevant pyproject data)
Context matches:             ✅
Return cached resolution:    0ms
Total:                      ~7ms   (35x improvement)
```

**When context changes (affects this workflow):**
```
Check workflow mtime:        1µs
Check pyproject mtime:       1µs   (changed!)
Compute context hash:        7ms
Context changed:             ✅ need re-resolve
Return cached dependencies:  0ms   (parsing still cached!)
Re-resolve workflow:        50ms   (no global mappings load)
Update cache:                1ms
Total:                     ~59ms   (4x improvement)
```

---

## Implementation Checklist

### Phase 1: Schema Enhancement
- [ ] Update `workflow_cache.py` schema to v2
- [ ] Add `resolution_context_hash` field
- [ ] Add `pyproject_mtime` field
- [ ] Add `resolution_json` field
- [ ] Add `comfydock_version` field
- [ ] Implement v1 → v2 migration
- [ ] Add resolution serialization/deserialization

### Phase 2: Context Hashing
- [ ] Add `_compute_resolution_context_hash()` to WorkflowManager
- [ ] Extract custom node mappings for workflow nodes only
- [ ] Extract declared packages for workflow nodes only
- [ ] Extract model pyproject entries for workflow only
- [ ] Extract model index subset for workflow models only
- [ ] Include comfydock version in context

### Phase 3: Cache Integration
- [ ] Update `WorkflowManager.analyze_workflow_cached()` to cache resolution
- [ ] Update cache `set()` to accept resolution and context hash
- [ ] Update cache `get()` to check resolution context
- [ ] Add pyproject mtime fast-reject path
- [ ] Return partial cache hit (dependencies valid, resolution stale)

### Phase 4: Caller Updates
- [ ] Update `analyze_single_workflow_status()` to use new method
- [ ] Update all callers to handle `(dependencies, resolution)` tuple
- [ ] Remove redundant `resolve_workflow()` calls

### Phase 5: Testing
- [ ] Test context hash computation
- [ ] Test cache hit when workflow unchanged
- [ ] Test cache hit when pyproject changed (different workflow)
- [ ] Test re-resolution when context changed
- [ ] Test re-parsing when workflow changed
- [ ] Test version mismatch invalidation
- [ ] Benchmark before/after performance

---

## Risk Mitigation

### Risk 1: Context Hash Computation Cost
**Issue:** Computing context hash on every lookup adds 7ms overhead

**Mitigation:**
- pyproject_mtime fast-reject skips context computation 99% of time
- 7ms is still 35x faster than re-resolving (250ms)
- Only paid when pyproject actually changes
- Can optimize further if needed (cache context hash keyed by pyproject mtime)

### Risk 2: Incomplete Context Capture
**Issue:** Missing a dependency in context hash causes stale cache hits

**Mitigation:**
- Comprehensive test coverage of all resolution inputs
- Include version as global invalidator (catches any missed dependencies)
- Manual cache clear command available
- Monitor for user-reported issues

### Risk 3: Migration Complexity
**Issue:** Users lose cache on v1 → v2 migration

**Mitigation:**
- Cache is ephemeral (no data loss, just performance hit once)
- Migration happens automatically on first run
- Clear messaging in migration logs
- Warm cache rebuilds quickly (only affects first status after upgrade)

---

## Success Metrics

### Performance Goals
- [ ] Cache hit latency: < 1ms (pyproject unchanged)
- [ ] Cache hit latency: < 10ms (pyproject changed, different workflow)
- [ ] Cache hit latency: < 100ms (context changed, re-resolve only)
- [ ] status command with 10 cached workflows: < 50ms total
- [ ] Second status after first: >100x faster

### Quality Goals
- [ ] Zero false cache hits (wrong resolution returned)
- [ ] Context hash captures all resolution inputs
- [ ] Test coverage: >90% for context computation
- [ ] All benchmark targets met

### User Impact Goals
- [ ] Users report dramatically faster status/commit
- [ ] No surprises (cache invalidates when expected)
- [ ] Graceful handling of pyproject changes
- [ ] Clear logging of cache behavior

---

## Notes for Implementation

### Key Insights
1. **Resolution is 80% of the cost** - that's what we need to cache
2. **Workflow-specific invalidation** - don't invalidate all workflows for one pyproject change
3. **Lazy context computation** - only compute when pyproject mtime changes
4. **Partial cache hits** - dependencies valid but resolution stale is common

### Critical Path
1. Get context hash computation right (test thoroughly)
2. Ensure all resolution inputs are captured
3. Verify pyproject mtime fast-reject path works
4. Benchmark to prove actual speedup

### Implementation Order
1. Start with schema v2 and migration
2. Add context hash computation (isolated, testable)
3. Wire up cache integration
4. Update callers
5. Extensive testing and benchmarking
