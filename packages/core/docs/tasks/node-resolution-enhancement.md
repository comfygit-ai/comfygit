# Task: Enhanced Node Resolution with Context and Interactive Fallback

## Status
- **Priority**: High
- **Complexity**: Medium
- **Estimated Effort**: 3-4 hours
- **Type**: Enhancement + Bug Fix

## Problem Statement

### Current Behavior

After successfully resolving and installing custom nodes for a workflow, the `status` command continues to show those nodes as "missing" or "unresolved". This creates a confusing user experience where installed nodes appear to still have issues.

**Example from user session:**

```bash
$ cfd workflow resolve depthflow_showcase_v2_1
🔧 Resolving dependencies...

📦 Found 4 missing node packs:
  • comfyui-depthanythingv2
  • comfyui-videohelpersuite
  • rgthree-comfy
  • comfyui-depthflow-nodes

[User installs all 4 packages successfully]

✅ Resolution complete!
  • Resolved 1 models
  • Resolved 46 nodes

$ cfd status
Environment: test4

📋 Workflows:
  ✓ test1
  ⚠️  depthflow_showcase_v2_1 (new)
      Missing node: Mute / Bypass Repeater (rgthree)  # ❌ Still shows as missing!
      Missing node: Mute / Bypass Repeater (rgthree)
      ... and 40 more nodes
```

### Root Cause

The global node resolver uses a pre-computed lookup table (`node_mappings.json`) that maps node types to package IDs. **The table is incomplete** - it doesn't have entries for all node types.

**From debug logs:**

```
# This node is NOT in the global table:
DEBUG - No match found for Mute / Bypass Repeater (rgthree)
→ Added to nodes_unresolved[]

# But this node from the SAME package IS in the table:
DEBUG - Exact key for Any Switch (rgthree): Any Switch (rgthree)::85fd84b5
DEBUG - Type-only match for Any Switch (rgthree): rgthree-comfy
→ Resolved to rgthree-comfy package
```

**The issue:** When `status` re-analyzes the workflow, it tries to resolve ALL custom nodes again. Nodes not in the global table remain "unresolved" forever, even though the package providing them is already installed.

### Why This Happens

The `GlobalNodeResolver` is **stateless** and has **no context** about:
1. What packages are already installed in the environment
2. What nodes were resolved earlier in this session (deduplication)
3. User's manual resolution mappings from previous sessions
4. What node types each installed package provides
5. **The `properties` field in workflow JSON** (which contains authoritative package info!)

It only checks the static lookup table on every call.

### The Missing Piece: Workflow Properties Field

ComfyUI workflows contain a `properties` field in each node with authoritative package information:

```json
{
  "nodes": [{
    "type": "Mute / Bypass Repeater (rgthree)",
    "properties": {
      "Node name for S&R": "Mute / Bypass Repeater (rgthree)",
      "cnr_id": "rgthree-comfy",           // Comfy Node Registry ID!
      "ver": "f754c4765849aa748abb35a..."  // Git commit hash!
    }
  }]
}
```

**This field is the solution!** It tells us:
- Exact package ID (`cnr_id`) the node came from
- Exact version (`ver` = git commit hash) when workflow was saved

We're currently **not extracting or using this data**, causing false negatives.

### Current Resolution Flow

```
analyze_workflow()
  → classify all nodes
    → builtin → builtin_nodes[]
    → custom → non_builtin_nodes[]

resolve_workflow()
  → for each non_builtin_node:
      → global_node_resolver.resolve_single_node()
        1. Try exact match (with input signature)
        2. Try type-only match
        3. Try fuzzy substring match
        4. Return None if no match
```

**Problem:** Steps 1-3 only check the global table. There's no step 4, 5, 6 to check context.

## Solution Architecture

### High-Level Design

Enhance the node resolution system to be **context-aware** and provide **interactive fallback** for unresolved nodes, mirroring the existing model resolution pattern.

### Resolution Priority Order

**Updated order optimized for speed and accuracy:**

```
Priority 1: Session-resolved mappings (FASTEST - in-memory cache, dedupe within session)
  ↓ (if not found)
Priority 2: Pyproject custom mappings (FAST - user's explicit previous choices)
  ↓ (if not found)
Priority 3: Workflow properties field (AUTHORITATIVE - cnr_id + ver from ComfyUI)
  ↓ (if not found)
Priority 4: Global mapping table (COMPREHENSIVE - existing static lookup)
  ↓ (if not found)
Priority 5: Heuristic matching (FALLBACK - naming patterns from installed packages)
  ↓ (if not found)
Priority 6: Interactive resolution (LAST RESORT - fuzzy search → manual → skip)
```

**Rationale for priority order:**
1. **Session cache first**: Fastest, already resolved in this run
2. **Custom mappings second**: User's explicit choices should be respected
3. **Properties field third**: Most authoritative source (direct from ComfyUI when workflow saved)
4. **Global table fourth**: Comprehensive but may have gaps (incomplete node coverage)
5. **Heuristics fifth**: Inference-based, less reliable
6. **Interactive last**: User intervention required

### New Data Structures

#### 1. NodeResolutionContext (Core)

```python
@dataclass
class NodeResolutionContext:
    """Context for enhanced node resolution with state tracking."""

    # Existing packages in environment
    installed_packages: dict[str, NodeInfo]  # From pyproject.nodes.get_existing()

    # Session tracking (for deduplication within single resolve call)
    session_resolved: dict[str, str]  # node_type -> package_id

    # User-defined mappings (persisted in pyproject.toml)
    custom_mappings: dict[str, str]  # node_type -> package_id or "skip"

    # Current workflow context
    workflow_name: str
```

#### 2. ScoredPackageMatch (Core)

Move to `models/workflow.py` to be parallel with `ScoredMatch`:

```python
@dataclass
class ScoredPackageMatch:
    """A fuzzy-matched package for an unresolved node."""
    package_id: str
    package_data: GlobalNodePackage
    score: float  # 0.0 to 1.0
    confidence: str  # "high", "medium", "low"
```

#### 3. Enhanced WorkflowNode (Core)

Add properties field to `models/workflow.py`:

```python
@dataclass
class WorkflowNode:
    id: str
    type: str
    # ... existing fields ...
    properties: dict[str, Any] = field(default_factory=dict)  # NEW: Extract from workflow JSON
```

#### 4. CustomNodeMappingHandler (Pyproject Manager)

New handler for managing persistent node mappings:

```toml
[tool.comfydock.node_mappings]
# User-specified mappings for nodes not in global table
"Mute / Bypass Repeater (rgthree)" = "rgthree-comfy"
"Some Experimental Node" = "https://github.com/user/repo"
"Unused Node Type" = "skip"  # Special value to ignore

[tool.comfydock.nodes]
"rgthree-comfy" = {
    source = "github",
    registry_id = "rgthree-comfy",
    version = "4.18",
    commit_hash = "f754c4765849..."  # NEW: Store exact commit from properties.ver
}
```

**Note:** The `commit_hash` field enables exact version reproducibility when rolling back or exporting.

### Component Changes

#### Files to Modify

1. **`packages/core/src/comfydock_core/models/workflow.py`**
   - Add `properties: dict[str, Any]` field to `WorkflowNode` dataclass
   - Move `ScoredPackageMatch` here (parallel to `ScoredMatch`)

2. **`packages/core/src/comfydock_core/analyzers/workflow_dependency_parser.py`**
   - Extract `properties` field when parsing nodes from workflow JSON

3. **`packages/core/src/comfydock_core/resolvers/global_node_resolver.py`**
   - Add `NodeResolutionContext` dataclass
   - Add `resolve_single_node_with_context()` method (with properties field support)
   - Add `fuzzy_search_packages()` method
   - Add helper methods: `_resolve_from_properties()`, `_likely_provides_node()`, `_create_resolved_package()`

4. **`packages/core/src/comfydock_core/managers/pyproject_manager.py`**
   - Add `CustomNodeMappingHandler` class
   - Add `node_mappings` property to `PyprojectManager`
   - Update `NodeHandler` to store/retrieve `commit_hash` field

5. **`packages/core/src/comfydock_core/managers/workflow_manager.py`**
   - Update `resolve_workflow()` to build and use context
   - Pass fuzzy search function to strategies
   - Deduplicate node types with preference for nodes with properties
   - Persist custom mappings after resolution

6. **`packages/cli/comfydock_cli/strategies/interactive.py`**
   - Enhance `InteractiveNodeStrategy.__init__()` to accept fuzzy search function and context
   - Add `_show_fuzzy_results()` method (similar to model strategy)
   - Add `_assign_to_existing()` method
   - Add `_show_manual_options()` method
   - Add `_browse_all_packages()` method

7. **`packages/cli/comfydock_cli/env_commands.py`**
   - Update `workflow_resolve()` to pass fuzzy search function to strategy

#### Files to Create

1. **`packages/core/tests/unit/resolvers/test_node_resolution_context.py`**
   - Tests for context-aware resolution logic
   - Tests for properties field resolution

2. **`packages/core/tests/unit/managers/test_custom_node_mapping_handler.py`**
   - Tests for pyproject mapping storage/retrieval
   - Tests for commit hash storage/retrieval

3. **`packages/core/tests/integration/test_node_resolution_with_context.py`**
   - End-to-end tests for the full resolution flow
   - Tests for properties-based resolution in real workflows

## Implementation Plan (TDD Approach)

### Phase 1: Core Infrastructure (1 hour)

**Step 1.1: Add Properties Field to WorkflowNode**

Location: `packages/core/src/comfydock_core/models/workflow.py`

```python
@dataclass
class WorkflowNode:
    id: str
    type: str
    # ... existing fields ...
    properties: dict[str, Any] = field(default_factory=dict)  # NEW: Extract from workflow JSON

@dataclass
class ScoredPackageMatch:
    """Fuzzy-matched package result."""
    package_id: str
    package_data: GlobalNodePackage
    score: float
    confidence: str  # "high", "medium", "low"
```

**Step 1.2: Extract Properties in Parser**

Location: `packages/core/src/comfydock_core/analyzers/workflow_dependency_parser.py`

```python
# When parsing nodes from workflow JSON
node = WorkflowNode(
    id=node_id,
    type=node_type,
    # ... other fields ...
    properties=node_dict.get('properties', {})  # EXTRACT properties field
)
```

**Step 1.3: Add NodeResolutionContext**

Location: `packages/core/src/comfydock_core/resolvers/global_node_resolver.py`

```python
@dataclass
class NodeResolutionContext:
    """Context for enhanced node resolution."""
    installed_packages: dict[str, NodeInfo] = field(default_factory=dict)
    session_resolved: dict[str, str] = field(default_factory=dict)
    custom_mappings: dict[str, str] = field(default_factory=dict)
    workflow_name: str = ""
```

**Step 1.4: Add CustomNodeMappingHandler**

Location: `packages/core/src/comfydock_core/managers/pyproject_manager.py`

```python
class CustomNodeMappingHandler(BaseHandler):
    """Handles custom node type -> package mappings."""

    def add_mapping(self, node_type: str, package_id: str) -> None:
        """Add a custom mapping for unresolved node."""
        config = self.load()
        self.ensure_section(config, 'tool', 'comfydock', 'node_mappings')
        config['tool']['comfydock']['node_mappings'][node_type] = package_id
        self.save(config)

    def get_mapping(self, node_type: str) -> str | None:
        """Get custom mapping if exists."""
        config = self.load()
        mappings = config.get('tool', {}).get('comfydock', {}).get('node_mappings', {})
        return mappings.get(node_type)

    def get_all_mappings(self) -> dict[str, str]:
        """Get all custom mappings."""
        config = self.load()
        return config.get('tool', {}).get('comfydock', {}).get('node_mappings', {})

    def remove_mapping(self, node_type: str) -> bool:
        """Remove a custom mapping."""
        config = self.load()
        mappings = config.get('tool', {}).get('comfydock', {}).get('node_mappings', {})
        if node_type in mappings:
            del mappings[node_type]
            self.save(config)
            return True
        return False
```

Add property to PyprojectManager:

```python
@property
def node_mappings(self) -> CustomNodeMappingHandler:
    """Get custom node mapping handler."""
    if self._node_mappings is None:
        self._node_mappings = CustomNodeMappingHandler(self)
    return self._node_mappings
```

**Tests for Phase 1:**

```python
# test_custom_node_mapping_handler.py
def test_add_mapping(tmp_path):
    """Should add custom node mapping to pyproject."""
    pyproject_path = tmp_path / "pyproject.toml"
    # Create minimal pyproject
    ...

    manager = PyprojectManager(pyproject_path)
    manager.node_mappings.add_mapping("Test Node", "test-package")

    config = manager.load()
    assert config['tool']['comfydock']['node_mappings']['Test Node'] == "test-package"

def test_get_all_mappings(tmp_path):
    """Should retrieve all custom mappings."""
    # Setup pyproject with mappings
    ...

    manager = PyprojectManager(pyproject_path)
    mappings = manager.node_mappings.get_all_mappings()

    assert len(mappings) == 2
    assert mappings['Node A'] == 'package-a'
    assert mappings['Node B'] == 'skip'
```

### Phase 2: Enhanced Resolution Logic (1.5 hours)

**Step 2.1: Add Context-Aware Resolution**

Location: `packages/core/src/comfydock_core/resolvers/global_node_resolver.py`

```python
class GlobalNodeResolver:

    def resolve_single_node_with_context(
        self,
        node: WorkflowNode,
        context: NodeResolutionContext | None = None
    ) -> List[ResolvedNodePackage] | None:
        """Enhanced resolution with context awareness.

        Resolution priority (optimized order):
        1. Session-resolved mappings (fastest - in-memory)
        2. Custom mappings from pyproject (user's explicit choices)
        3. Workflow properties field (authoritative - cnr_id + ver)
        4. Global mapping table (comprehensive static lookup)
        5. Heuristic matching (inference from installed packages)
        6. None (trigger interactive resolution)
        """

        # Priority 1: Session cache (fastest - already resolved in THIS run)
        if context and node.type in context.session_resolved:
            pkg_id = context.session_resolved[node.type]
            logger.debug(f"Session cache hit for {node.type}: {pkg_id}")
            return [self._create_resolved_package_from_id(pkg_id, node.type, "session_cache")]

        # Priority 2: Custom mappings (user's previous explicit choices)
        if context and node.type in context.custom_mappings:
            mapping = context.custom_mappings[node.type]
            if mapping == "skip":
                logger.debug(f"Skipping {node.type} (user-configured)")
                return []  # Empty list = skip
            logger.debug(f"Custom mapping for {node.type}: {mapping}")
            return [self._create_resolved_package_from_id(mapping, node.type, "custom_mapping")]

        # Priority 3: Workflow properties field (authoritative - from ComfyUI)
        if node.properties:
            cnr_id = node.properties.get('cnr_id')
            ver = node.properties.get('ver')  # Git commit hash

            if cnr_id:
                logger.debug(f"Found cnr_id in properties: {cnr_id} @ {ver[:8] if ver else 'unknown'}")

                # Validate package exists in global mappings
                if cnr_id in self.global_mappings.packages:
                    pkg_data = self.global_mappings.packages[cnr_id]

                    result = [ResolvedNodePackage(
                        package_id=cnr_id,
                        package_data=pkg_data,
                        node_type=node.type,
                        versions=[ver] if ver else [],  # Store exact commit hash!
                        match_type="properties",
                        match_confidence=1.0  # Highest confidence - direct from ComfyUI
                    )]

                    if context:
                        context.session_resolved[node.type] = cnr_id

                    return result
                else:
                    logger.warning(
                        f"cnr_id '{cnr_id}' from properties not found in registry. "
                        f"Falling back to other resolution methods."
                    )

        # Priority 4: Global table (existing comprehensive lookup)
        result = self._resolve_from_global_table(node)
        if result:
            if context:
                context.session_resolved[node.type] = result[0].package_id
            return result

        # Priority 5: Heuristic match against installed packages (inference)
        if context:
            for pkg_id in context.installed_packages.keys():
                if self._likely_provides_node(pkg_id, node.type):
                    logger.debug(f"Heuristic match for {node.type}: {pkg_id}")
                    result = [self._create_resolved_package_from_id(pkg_id, node.type, "heuristic")]
                    context.session_resolved[node.type] = pkg_id
                    return result

        # Priority 6: No match - return None to trigger interactive strategy
        logger.debug(f"No resolution found for {node.type}")
        return None

    def _resolve_from_global_table(self, node: WorkflowNode) -> List[ResolvedNodePackage] | None:
        """Existing resolution logic (strategies 1-3)."""
        # This is the current resolve_single_node() logic
        # Extract it into this method
        ...

    def _likely_provides_node(self, pkg_id: str, node_type: str) -> bool:
        """Multi-strategy heuristic matching for node-package correlation.

        Uses multiple strategies to infer if a package provides a node type.
        """
        import re

        node_lower = node_type.lower()
        pkg_lower = pkg_id.lower()

        # Strategy 1: Extract parenthetical hint
        # e.g., "Mute / Bypass Repeater (rgthree)" -> "rgthree"
        if "(" in node_type and ")" in node_type:
            suffix = node_type.split("(")[-1].rstrip(")").strip().lower()
            if suffix in pkg_lower:
                logger.debug(f"Heuristic match (parenthetical): {suffix} in {pkg_id}")
                return True

        # Strategy 2: Check if node type contains package name fragments
        # e.g., "DepthAnythingV2" matches "comfyui-depthanythingv2"
        pkg_parts = re.split(r'[-_]', pkg_lower)
        for part in pkg_parts:
            if len(part) > 4 and part in node_lower:  # Min 4 chars to avoid false positives
                logger.debug(f"Heuristic match (fragment): {part} in {node_type}")
                return True

        # Strategy 3: Check if package contains node type fragments (CamelCase split)
        # e.g., "ImpactWildcardProcessor" -> ["Impact", "Wildcard", "Processor"]
        node_parts = re.findall(r'[A-Z][a-z]+', node_type)
        if len(node_parts) >= 2:
            combined = ''.join(node_parts).lower()
            if combined in pkg_lower:
                logger.debug(f"Heuristic match (camelCase): {combined} in {pkg_id}")
                return True

        return False

    def _create_resolved_package_from_id(
        self,
        pkg_id: str,
        node_type: str,
        match_type: str
    ) -> ResolvedNodePackage:
        """Create ResolvedNodePackage from package ID."""
        pkg_data = self.global_mappings.packages.get(pkg_id)

        return ResolvedNodePackage(
            package_id=pkg_id,
            package_data=pkg_data,
            node_type=node_type,
            versions=[],
            match_type=match_type,
            match_confidence=1.0 if match_type != "heuristic" else 0.8
        )

    def fuzzy_search_packages(self, node_type: str, limit: int = 10) -> List[ScoredPackageMatch]:
        """Fuzzy search for packages that might provide this node.

        Similar to model fuzzy search in workflow_manager.find_similar_models()
        """
        from difflib import SequenceMatcher

        scored = []
        node_type_lower = node_type.lower()

        # Extract keywords from node type
        import re
        keywords = set(re.findall(r'\w+', node_type_lower))

        for pkg_id, pkg_data in self.global_mappings.packages.items():
            # Compute similarity scores
            id_score = SequenceMatcher(None, node_type_lower, pkg_id.lower()).ratio()

            name_score = 0
            if pkg_data.display_name:
                name_score = SequenceMatcher(
                    None, node_type_lower, pkg_data.display_name.lower()
                ).ratio()

            # Keyword matching boost
            pkg_keywords = set(re.findall(r'\w+', pkg_id.lower()))
            if pkg_data.display_name:
                pkg_keywords.update(re.findall(r'\w+', pkg_data.display_name.lower()))

            keyword_overlap = len(keywords & pkg_keywords) / max(len(keywords), 1)

            # Combined score (70% string similarity, 30% keyword overlap)
            final_score = max(id_score, name_score) * 0.7 + keyword_overlap * 0.3

            if final_score > 0.3:  # Minimum threshold
                confidence = (
                    "high" if final_score > 0.7
                    else "medium" if final_score > 0.5
                    else "low"
                )
                scored.append(ScoredPackageMatch(
                    package_id=pkg_id,
                    package_data=pkg_data,
                    score=final_score,
                    confidence=confidence
                ))

        # Sort by score descending
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:limit]
```

**Tests for Phase 2:**

```python
# test_node_resolution_context.py
def test_session_cache_deduplication():
    """Should use session cache to deduplicate same node type."""
    resolver = GlobalNodeResolver(mappings_path)
    context = NodeResolutionContext()

    node1 = WorkflowNode(id="1", type="Test Node", ...)
    node2 = WorkflowNode(id="2", type="Test Node", ...)  # Same type

    # First resolution
    result1 = resolver.resolve_single_node_with_context(node1, context)
    # Should add to session cache

    # Second resolution - should hit cache
    result2 = resolver.resolve_single_node_with_context(node2, context)

    assert result1[0].package_id == result2[0].package_id
    assert node1.type in context.session_resolved

def test_custom_mapping_resolution():
    """Should resolve using custom pyproject mappings."""
    resolver = GlobalNodeResolver(mappings_path)
    context = NodeResolutionContext(
        custom_mappings={"Unknown Node": "custom-package"}
    )

    node = WorkflowNode(id="1", type="Unknown Node", ...)
    result = resolver.resolve_single_node_with_context(node, context)

    assert result[0].package_id == "custom-package"
    assert result[0].match_type == "custom_mapping"

def test_skip_mapping():
    """Should return empty list for skip mappings."""
    resolver = GlobalNodeResolver(mappings_path)
    context = NodeResolutionContext(
        custom_mappings={"Ignored Node": "skip"}
    )

    node = WorkflowNode(id="1", type="Ignored Node", ...)
    result = resolver.resolve_single_node_with_context(node, context)

    assert result == []

def test_fuzzy_search_packages():
    """Should find similar packages using fuzzy matching."""
    resolver = GlobalNodeResolver(mappings_path)

    results = resolver.fuzzy_search_packages("rgthree bypass", limit=5)

    assert len(results) > 0
    # Should find rgthree-comfy with high confidence
    assert any(r.package_id == "rgthree-comfy" for r in results)
    assert results[0].score > results[-1].score  # Sorted by score

def test_resolution_from_properties_field():
    """Should resolve using cnr_id and ver from workflow properties."""
    resolver = GlobalNodeResolver(mappings_path)
    context = NodeResolutionContext()

    # Node with properties field containing authoritative package info
    node = WorkflowNode(
        id="1",
        type="Some Obscure Node",
        properties={
            "cnr_id": "rgthree-comfy",
            "ver": "f754c4765849aa748abb35a1f030a5ed6474a69b"
        }
    )

    result = resolver.resolve_single_node_with_context(node, context)

    assert result is not None
    assert result[0].package_id == "rgthree-comfy"
    assert result[0].versions == ["f754c4765849aa748abb35a1f030a5ed6474a69b"]
    assert result[0].match_type == "properties"
    assert result[0].match_confidence == 1.0  # Highest confidence

def test_properties_preferred_in_deduplication():
    """Should prefer node instances with properties during deduplication."""
    node_with_props = WorkflowNode(
        id="1",
        type="KSampler",
        properties={"cnr_id": "comfyui-core", "ver": "abc123"}
    )
    node_without_props = WorkflowNode(
        id="2",
        type="KSampler",
        properties={}
    )

    # Test deduplication logic prefers nodes with properties
    unique = {}
    for node in [node_without_props, node_with_props]:  # Without first
        if node.type not in unique:
            unique[node.type] = node
        else:
            has_cnr = node.properties.get('cnr_id')
            existing_has_cnr = unique[node.type].properties.get('cnr_id')
            if has_cnr and not existing_has_cnr:
                unique[node.type] = node

    assert unique["KSampler"].id == "1"  # Preferred the one with properties
```

### Phase 3: Interactive Strategy Enhancement (1 hour)

**Step 3.1: Update InteractiveNodeStrategy**

Location: `packages/cli/comfydock_cli/strategies/interactive.py`

Pattern: Mirror `InteractiveModelStrategy` (lines 65-220)

```python
class InteractiveNodeStrategy(NodeResolutionStrategy):
    """Interactive node resolution with fuzzy search."""

    def __init__(self, fuzzy_search_fn=None, context: NodeResolutionContext = None):
        """Initialize with fuzzy search function and context.

        Args:
            fuzzy_search_fn: Function to fuzzy search packages (node_type, limit) -> List[ScoredPackageMatch]
            context: Resolution context for tracking and persistence
        """
        self.fuzzy_search_fn = fuzzy_search_fn
        self.context = context

    def resolve_unknown_node(
        self, node_type: str, possible: List[ResolvedNodePackage]
    ) -> ResolvedNodePackage | None:
        """Prompt user to resolve unknown node with fuzzy search.

        Pattern matches InteractiveModelStrategy.handle_missing_model()
        """

        # If we have ambiguous matches from global table, show them
        if possible and len(possible) > 1:
            return self._resolve_ambiguous(node_type, possible)

        # If no matches, try fuzzy search
        if not possible and self.fuzzy_search_fn:
            print(f"\n⚠️  Node not found in registry: {node_type}")
            print("🔍 Searching for similar packages...")

            similar = self.fuzzy_search_fn(node_type, limit=10)

            if similar:
                return self._show_fuzzy_results(node_type, similar)
            else:
                print("  No similar packages found")

        # Fallback to manual/skip options
        return self._show_manual_options(node_type)

    def _show_fuzzy_results(
        self, node_type: str, results: List[ScoredPackageMatch]
    ) -> ResolvedNodePackage | None:
        """Show fuzzy search results with pagination.

        Pattern matches InteractiveModelStrategy._show_fuzzy_results()
        """
        print(f"\nFound {len(results)} potential packages:\n")

        # Show top 5
        display_count = min(5, len(results))
        for i, match in enumerate(results[:display_count], 1):
            pkg = match.package_data
            confidence = match.confidence.capitalize()
            desc = (pkg.description or "No description")[:60]

            print(f"  {i}. {pkg.id}")
            print(f"     {desc}")
            print(f"     {confidence} confidence ({match.score:.2f})\n")

        if len(results) > 5:
            print(f"  6. [Browse all {len(results)} matches...]\n")

        # Option to assign to already-resolved/installed
        if self.context and (self.context.session_resolved or self.context.installed_packages):
            print(f"  7. [Assign to existing package...]\n")

        print("  0. Other options (manual, skip)\n")

        while True:
            choice = input("Choice [1]: ").strip() or "1"

            if choice == "0":
                return self._show_manual_options(node_type)

            elif choice == "6" and len(results) > 5:
                return self._browse_all_packages(node_type, results)

            elif choice == "7" and self.context:
                return self._assign_to_existing(node_type)

            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < display_count:
                    selected = results[idx]
                    print(f"\n✓ Selected: {selected.package_id}")

                    # Save to custom mappings for persistence
                    if self.context:
                        self.context.custom_mappings[node_type] = selected.package_id
                        self.context.session_resolved[node_type] = selected.package_id

                    return ResolvedNodePackage(
                        package_id=selected.package_id,
                        package_data=selected.package_data,
                        node_type=node_type,
                        versions=[],
                        match_type="user_selected",
                        match_confidence=selected.score
                    )

            print("  Invalid choice, try again")

    # Add other methods: _assign_to_existing, _browse_all_packages, _show_manual_options
    # Pattern: Follow InteractiveModelStrategy implementation
```

**Step 3.2: Wire Together in workflow_manager.py**

```python
def resolve_workflow(self, analysis: WorkflowDependencies) -> ResolutionResult:
    """Phase 2: Resolve with context awareness."""

    # Build context
    context = NodeResolutionContext(
        installed_packages=self.pyproject.nodes.get_existing(),
        session_resolved={},
        custom_mappings=self.pyproject.node_mappings.get_all_mappings(),
        workflow_name=analysis.workflow_name
    )

    nodes_resolved = []
    nodes_unresolved = []
    nodes_ambiguous = []

    # Deduplicate node types with preference for nodes that have properties
    # Properties field contains authoritative package info (cnr_id + commit hash)
    unique_nodes = {}
    for node in analysis.non_builtin_nodes:
        if node.type not in unique_nodes:
            unique_nodes[node.type] = node
        else:
            # Prefer node WITH properties over one without
            existing = unique_nodes[node.type]
            has_cnr_id = node.properties.get('cnr_id') if node.properties else None
            existing_has_cnr_id = existing.properties.get('cnr_id') if existing.properties else None

            if has_cnr_id and not existing_has_cnr_id:
                logger.debug(f"Preferring node instance with properties for {node.type}")
                unique_nodes[node.type] = node

    logger.debug(
        f"Resolving {len(unique_nodes)} unique node types from "
        f"{len(analysis.non_builtin_nodes)} total nodes"
    )

    # Resolve each unique node type
    for node_type, node in unique_nodes.items():
        resolved = self.global_node_resolver.resolve_single_node_with_context(node, context)

        if resolved is None:
            nodes_unresolved.append(node)
        elif len(resolved) == 0:  # Skip
            logger.debug(f"Skipped node: {node_type}")
        elif len(resolved) == 1:
            nodes_resolved.append(resolved[0])
        else:
            nodes_ambiguous.append(resolved)

    # ... rest of model resolution logic

    return ResolutionResult(
        nodes_resolved=nodes_resolved,
        nodes_unresolved=nodes_unresolved,
        nodes_ambiguous=nodes_ambiguous,
        models_resolved=models_resolved,
        models_unresolved=models_unresolved,
        models_ambiguous=models_ambiguous,
    )

def apply_resolution(
    self,
    resolution: ResolutionResult,
    workflow_name: str | None = None,
    model_refs: list[WorkflowNodeWidgetRef] | None = None,
    context: NodeResolutionContext | None = None
) -> None:
    """Apply resolution and persist custom mappings."""

    # ... existing logic

    # Persist custom mappings from context
    if context:
        for node_type, pkg_id in context.custom_mappings.items():
            self.pyproject.node_mappings.add_mapping(node_type, pkg_id)
        logger.info(f"Persisted {len(context.custom_mappings)} custom node mappings")
```

**Step 3.3: Update CLI command**

Location: `packages/cli/comfydock_cli/env_commands.py`

```python
def workflow_resolve(self, args, logger=None):
    """Resolve workflow dependencies interactively."""
    env = self._get_env(args)

    # ...

    # Choose strategy with fuzzy search
    if args.auto:
        from comfydock_core.strategies.auto import AutoNodeStrategy, AutoModelStrategy
        node_strategy = AutoNodeStrategy()
        model_strategy = AutoModelStrategy()
    else:
        # Pass fuzzy search function to strategy
        node_strategy = InteractiveNodeStrategy(
            fuzzy_search_fn=env.workflow_manager.global_node_resolver.fuzzy_search_packages
        )
        model_strategy = InteractiveModelStrategy(
            fuzzy_search_fn=env.workflow_manager.find_similar_models
        )

    # ... rest of command
```

### Phase 4: Integration & Testing (30 minutes)

**Step 4.1: Integration Test**

```python
# test_node_resolution_with_context.py
def test_full_resolution_flow_with_unresolved_nodes(test_env):
    """Test complete flow from analysis to resolution with unresolved nodes."""

    # ARRANGE: Workflow with nodes not in global table
    workflow_data = create_workflow_with_unknown_nodes()
    simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

    # ACT: Resolve with auto strategy (skip unresolved)
    from comfydock_core.strategies.auto import AutoNodeStrategy
    result = test_env.resolve_workflow(
        name="test_workflow",
        node_strategy=AutoNodeStrategy(),
        model_strategy=None
    )

    # ASSERT: Should have some resolved and some unresolved
    assert len(result.nodes_resolved) > 0
    assert len(result.nodes_unresolved) > 0

    # Manually add custom mapping
    test_env.pyproject.node_mappings.add_mapping(
        "Unknown Node Type", "some-package-id"
    )

    # Re-resolve - should use custom mapping
    result2 = test_env.resolve_workflow(
        name="test_workflow",
        node_strategy=AutoNodeStrategy(),
        model_strategy=None
    )

    # Should have fewer unresolved (custom mapping worked)
    assert len(result2.nodes_unresolved) < len(result.nodes_unresolved)
```

## Success Criteria

1. ✅ **Properties field extraction**: Workflow nodes have `properties` field populated from JSON
2. ✅ **Properties-based resolution**: Nodes with `cnr_id` are resolved with highest priority
3. ✅ **Commit hash storage**: Exact git commit from `ver` field stored in pyproject.toml
4. ✅ **After installation**: Running `status` should NOT show installed nodes as missing
5. ✅ **Session deduplication**: Nodes resolved earlier in session reused for duplicate node types
6. ✅ **Custom mappings persistence**: User manual resolutions persisted to `[tool.comfydock.node_mappings]`
7. ✅ **Optimal priority order**: Session cache → custom mappings → properties → global table → heuristics
8. ✅ **Fuzzy search**: Ranked candidates presented for unresolved nodes
9. ✅ **Assignment to existing**: Users can assign unresolved nodes to already-resolved/installed packages
10. ✅ **Skip functionality**: Users can skip nodes with "skip" value in mappings
11. ✅ **Enhanced heuristics**: Multi-strategy matching (parenthetical, fragment, CamelCase)
12. ✅ **Deduplication preference**: Node instances with properties preferred during dedupe
13. ✅ **Test coverage**: All existing tests pass + new tests for properties-based resolution
14. ✅ **Backwards compatibility**: Workflows without properties still work (fallback to other methods)

## Testing Strategy

### Unit Tests (Core Package)

- `test_custom_node_mapping_handler.py`: CRUD operations on mappings
- `test_node_resolution_context.py`: Context-aware resolution logic
- `test_properties_field_resolution.py`: Properties field extraction and resolution
- `test_fuzzy_search_packages.py`: Fuzzy matching algorithm
- `test_enhanced_heuristics.py`: Multi-strategy heuristic matching
- `test_commit_hash_storage.py`: Git commit hash persistence in pyproject.toml

### Integration Tests (Core Package)

- `test_node_resolution_with_context.py`: End-to-end resolution flow
- Verify session deduplication
- Verify custom mapping persistence and reuse
- Verify heuristic matching
- Verify properties-based resolution in real workflows
- Verify deduplication preference for nodes with properties
- Verify commit hash roundtrip (workflow → pyproject → rollback)

### Manual Testing (CLI)

1. **Test properties field resolution**:
   - Use workflow with properties field (e.g., saved from ComfyUI frontend)
   - Run `workflow resolve` - should resolve instantly from properties
   - Verify `cnr_id` used without prompting
   - Check pyproject.toml - verify `commit_hash` stored

2. **Test fallback when properties missing**:
   - Create workflow with nodes not in global table (no properties)
   - Run `workflow resolve` - verify fuzzy search UI appears
   - Select package from fuzzy results
   - Run `status` - verify node no longer shows as missing

3. **Test custom mapping persistence**:
   - Check `pyproject.toml` - verify custom mapping was saved
   - Delete workflow, create new one with same node type
   - Run `workflow resolve` - verify custom mapping reused (no prompt)

4. **Test deduplication preference**:
   - Create workflow with duplicate node types (some with properties, some without)
   - Verify only prompted once per node type
   - Verify instance with properties was used for resolution

## References

### Existing Implementations to Follow

1. **Model Resolution Pattern**
   - `InteractiveModelStrategy._show_fuzzy_results()` (lines 135-184)
   - Shows how to present fuzzy results with pagination
   - Pattern for user selection and persistence

2. **Pyproject Handler Pattern**
   - `ModelHandler` class (pyproject_manager.py:790-978)
   - Shows CRUD operations on pyproject sections
   - Pattern for lazy handler initialization

3. **Fuzzy Search Pattern**
   - `WorkflowManager.find_similar_models()` (workflow_manager.py:715-775)
   - Shows fuzzy matching with SequenceMatcher
   - Pattern for scoring and ranking candidates

### Related Files

- **Core Resolution**: `packages/core/src/comfydock_core/resolvers/global_node_resolver.py`
- **Pyproject Management**: `packages/core/src/comfydock_core/managers/pyproject_manager.py`
- **Workflow Management**: `packages/core/src/comfydock_core/managers/workflow_manager.py`
- **Interactive Strategies**: `packages/cli/comfydock_cli/strategies/interactive.py`
- **Environment Orchestration**: `packages/core/src/comfydock_core/core/environment.py`

## Notes for Implementation

1. **Properties Field is Golden**: The `cnr_id` + `ver` fields are the most authoritative source - prioritize them!
2. **TDD Approach**: Write tests first, implement to make them pass
3. **Pattern Consistency**: Mirror model resolution flow for familiarity
4. **Simple & Elegant**: This is MVP - no over-engineering
5. **No Backwards Compatibility**: Feel free to break old code and fix it
6. **Deduplication is Key**: Same node type appears many times in workflows - dedupe BEFORE resolution
7. **Prefer Properties in Dedupe**: When deduplicating, prefer node instances that have `cnr_id` in properties
8. **Context is Mutable**: Context object accumulates mappings during resolution - this is intentional
9. **Empty List vs None**: `[]` = skip, `None` = trigger strategy
10. **Store Commit Hashes**: The `ver` field enables exact reproducibility - always persist to pyproject.toml
11. **Validate but Trust**: Validate `cnr_id` exists in registry, but trust it if valid (don't override with global table)

## Estimated Breakdown

- **Phase 1** (Core Infrastructure): 1.5 hours
  - Add properties field to WorkflowNode
  - Extract properties in parser
  - Add NodeResolutionContext
  - Add CustomNodeMappingHandler
  - Update NodeHandler for commit_hash storage

- **Phase 2** (Resolution Logic): 2 hours
  - Implement properties-based resolution (Priority 3)
  - Reorder existing resolution priorities
  - Enhance heuristic matching with multi-strategy approach
  - Update deduplication to prefer nodes with properties

- **Phase 3** (Interactive Strategy): 1 hour
  - Update InteractiveNodeStrategy with fuzzy search
  - Wire context through workflow_manager
  - Update CLI commands

- **Phase 4** (Integration & Testing): 1 hour
  - Unit tests for properties field
  - Unit tests for enhanced heuristics
  - Integration tests for full flow
  - Manual testing with real workflows

**Total**: 5-6 hours for complete implementation with tests (increased due to properties field integration)
