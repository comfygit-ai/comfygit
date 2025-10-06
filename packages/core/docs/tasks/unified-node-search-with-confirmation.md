# Task: Unified Node Search with User Confirmation

## Status
- **Priority**: High
- **Complexity**: Medium
- **Estimated Effort**: 3-4 hours
- **Type**: Enhancement + Safety Improvement

## Problem Statement

### Current Behavior

The current node resolution system has a **critical trust issue**: heuristic matches are auto-resolved without user confirmation.

**Example from production logs:**
```
DEBUG - Trying to resolve node: Mute / Bypass Repeater (rgthree)
DEBUG - No match found for Mute / Bypass Repeater (rgthree)
DEBUG - Heuristic match for Mute / Bypass Repeater (rgthree): rgthree-comfy
```

The node was automatically resolved to `rgthree-comfy` based on the parenthetical hint `(rgthree)`. **The user never saw this decision**.

### Root Cause

**Priority 5 in `resolve_single_node_with_context()`** auto-resolves heuristic matches:

```python
# Priority 5: Heuristic match against installed packages
for pkg_id in context.installed_packages.keys():
    if self._likely_provides_node(pkg_id, node_type):
        # AUTO-RESOLVES! User never sees it
        return [self._create_resolved_package_from_id(pkg_id, node_type, "heuristic")]
```

### Why This Is Problematic

1. **Silent failures**: If heuristic picks the wrong package, user won't know until workflow fails
2. **Multiple matches ignored**: Only returns first match, no ambiguity detection
3. **No user confirmation**: User never gets to verify the choice
4. **Trust erosion**: One false positive destroys confidence in the system
5. **Limited hint patterns**: Only handles `(hint)` format, not `| hint` or other formats

**Examples of failure cases:**
- `"Custom Node (custom)"` matches BOTH `custom-nodes-1` AND `my-custom-pack` → picks first
- `"CLIP Encode (clip)"` matches `clip-vision`, `clip-interrogator`, `clip-models` → might pick wrong one
- `"My Node (mypackage)"` matches `my-other-package` → false positive

### The Core Issue

**Heuristics and fuzzy search are fundamentally the same problem** (matching node names to packages using imperfect information), but they're implemented as separate systems:

| Aspect | Heuristic | Fuzzy Search |
|--------|-----------|--------------|
| Approach | Binary (match/no match) | Scored (0.0-1.0) |
| Search space | Installed packages only | All registry packages |
| User interaction | Auto-resolves | Shows options |
| Extensibility | Hard-coded patterns | Statistical matching |
| Result | First match or None | Ranked list |

This fragmentation leads to:
- Duplicate logic
- Inconsistent behavior
- Missed opportunities to combine strengths

---

## Solution Architecture

### High-Level Design

**Consolidate heuristics and fuzzy search into a single unified search function** that:
1. Uses fuzzy matching as the base algorithm
2. **Boosts scores** for detected hint patterns (instead of binary matching)
3. Prioritizes installed packages via score bonus
4. Returns **ranked results** for user confirmation
5. **Never auto-resolves** - always goes through interactive strategy

### Key Principle

> **Heuristics are score boosters, not auto-resolvers**

Instead of:
```python
if has_hint:
    return package  # Auto-resolve
else:
    show_fuzzy_results()  # Interactive
```

Do:
```python
score = base_fuzzy_score
if has_hint:
    score += hint_bonus  # Boost the score
# Always show results for user confirmation
show_ranked_results()
```

---

## Proposed Architecture Changes

### Current Flow (Fragmented)

```
Priority 1: Session cache ─────────────────┐
Priority 2: Custom mappings ───────────────┤
Priority 3: Properties field ──────────────┼─► Auto-resolved
Priority 4: Global table ──────────────────┤
Priority 5: Heuristic (binary) ────────────┘
                │
                │ if None
                ▼
Strategy: fuzzy_search_packages() ────────────► Interactive
```

**Problems:**
- Heuristic auto-resolves (no user confirmation)
- Fuzzy search is separate (no hint awareness)
- Two search functions with different approaches

### Proposed Flow (Unified)

```
Priority 1: Session cache ─────────────────┐
Priority 2: Custom mappings ───────────────┤
Priority 3: Properties field ──────────────┼─► Auto-resolved
Priority 4: Global table ──────────────────┘
                │
                │ if None
                ▼
Strategy: search_packages(boost_hints=True) ──► Interactive
          ├─ Installed packages (boosted)
          ├─ Hint bonuses (parentheses, pipe, etc.)
          └─ Registry packages (normal)
```

**Benefits:**
- Single search function
- User confirms all heuristic matches
- Hints boost scores instead of auto-resolving
- Installed packages naturally prioritized
- Easy to add new hint patterns

---

## Implementation Details

### Phase 1: Unified Search Function

**Location:** `packages/core/src/comfydock_core/resolvers/global_node_resolver.py`

**Replace:** `fuzzy_search_packages()` and heuristic logic

**New method:**

```python
def search_packages(
    self,
    node_type: str,
    installed_packages: dict[str, NodeInfo] | None = None,
    include_registry: bool = True,
    limit: int = 10
) -> List[ScoredPackageMatch]:
    """Unified search with heuristic boosting.

    Combines fuzzy matching with hint pattern detection to rank packages.
    Installed packages receive priority boosting.

    Args:
        node_type: Node type to search for
        installed_packages: Already installed packages (prioritized)
        include_registry: Also search full registry
        limit: Maximum results

    Returns:
        Scored matches sorted by relevance (highest first)
    """
    from difflib import SequenceMatcher

    scored = []
    node_type_lower = node_type.lower()

    # Build candidate pool
    candidates = {}

    # Phase 1: Installed packages (always checked first)
    if installed_packages:
        for pkg_id, node_info in installed_packages.items():
            pkg_data = self.global_mappings.packages.get(pkg_id)
            if pkg_data:
                candidates[pkg_id] = (pkg_data, True)  # True = installed

    # Phase 2: Registry packages
    if include_registry:
        for pkg_id, pkg_data in self.global_mappings.packages.items():
            if pkg_id not in candidates:
                candidates[pkg_id] = (pkg_data, False)  # False = not installed

    # Score each candidate
    for pkg_id, (pkg_data, is_installed) in candidates.items():
        score = self._calculate_match_score(
            node_type=node_type,
            node_type_lower=node_type_lower,
            pkg_id=pkg_id,
            pkg_data=pkg_data,
            is_installed=is_installed
        )

        if score > 0.3:  # Minimum threshold
            confidence = self._score_to_confidence(score)
            scored.append(ScoredPackageMatch(
                package_id=pkg_id,
                package_data=pkg_data,
                score=score,
                confidence=confidence
            ))

    # Sort by score descending
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:limit]

def _calculate_match_score(
    self,
    node_type: str,
    node_type_lower: str,
    pkg_id: str,
    pkg_data: GlobalNodePackage,
    is_installed: bool
) -> float:
    """Calculate comprehensive match score with bonuses.

    Scoring pipeline:
    1. Base fuzzy score (SequenceMatcher)
    2. Keyword overlap bonus
    3. Hint pattern bonuses (heuristics!)
    4. Installed package bonus
    """
    from difflib import SequenceMatcher

    pkg_id_lower = pkg_id.lower()

    # 1. Base fuzzy score
    base_score = SequenceMatcher(None, node_type_lower, pkg_id_lower).ratio()

    # Also check display name
    if pkg_data.display_name:
        name_score = SequenceMatcher(
            None, node_type_lower, pkg_data.display_name.lower()
        ).ratio()
        base_score = max(base_score, name_score)

    # 2. Keyword overlap bonus
    node_keywords = set(re.findall(r'\w+', node_type_lower))
    pkg_keywords = set(re.findall(r'\w+', pkg_id_lower))
    if pkg_data.display_name:
        pkg_keywords.update(re.findall(r'\w+', pkg_data.display_name.lower()))

    keyword_overlap = len(node_keywords & pkg_keywords) / max(len(node_keywords), 1)
    keyword_bonus = keyword_overlap * 0.20

    # 3. Hint pattern bonuses (THE HEURISTICS!)
    hint_bonus = self._detect_hint_patterns(node_type, node_type_lower, pkg_id_lower)

    # 4. Installed package bonus
    installed_bonus = 0.10 if is_installed else 0.0

    # Combine and cap at 1.0
    final_score = base_score + keyword_bonus + hint_bonus + installed_bonus
    return min(1.0, final_score)

def _detect_hint_patterns(
    self,
    node_type: str,
    node_type_lower: str,
    pkg_id_lower: str
) -> float:
    """Detect hint patterns and return bonus score.

    This is where heuristics live - as score boosters!
    """
    max_bonus = 0.0

    # Pattern 1: Parenthetical hint
    # "Node Name (package)" → "package"
    if "(" in node_type and ")" in node_type:
        hint = node_type.split("(")[-1].rstrip(")").strip().lower()
        if len(hint) >= 3:  # Minimum length to avoid false positives
            if hint == pkg_id_lower:
                max_bonus = max(max_bonus, 0.70)  # Exact match
            elif hint in pkg_id_lower:
                max_bonus = max(max_bonus, 0.60)  # Substring match

    # Pattern 2: Pipe separator
    # "Node Name | PackageName" → "PackageName"
    if "|" in node_type:
        parts = node_type.split("|")
        if len(parts) == 2:
            hint = parts[1].strip().lower()
            if hint in pkg_id_lower:
                max_bonus = max(max_bonus, 0.55)

    # Pattern 3: Dash/Colon separator
    # "Node Name - Package" or "Node: Package"
    for sep in [" - ", ": "]:
        if sep in node_type:
            parts = node_type.split(sep)
            if len(parts) >= 2:
                hint = parts[-1].strip().lower()
                if len(hint) >= 3 and hint in pkg_id_lower:
                    max_bonus = max(max_bonus, 0.50)
                    break

    # Pattern 4: Fragment match (weakest)
    # "DepthAnythingV2" → "depthanythingv2" in package
    pkg_parts = re.split(r'[-_]', pkg_id_lower)
    for part in pkg_parts:
        if len(part) > 4 and part in node_type_lower:
            max_bonus = max(max_bonus, 0.40)
            break

    return max_bonus

def _score_to_confidence(self, score: float) -> str:
    """Convert numeric score to confidence label."""
    if score >= 0.85:
        return "high"
    elif score >= 0.65:
        return "good"
    elif score >= 0.45:
        return "possible"
    else:
        return "low"
```

---

### Phase 2: Remove Auto-Resolution

**Location:** `packages/core/src/comfydock_core/resolvers/global_node_resolver.py`

**In `resolve_single_node_with_context()`**, remove Priority 5:

```python
# OLD - Priority 5: Heuristic match (AUTO-RESOLVE)
for pkg_id in context.installed_packages.keys():
    if self._likely_provides_node(pkg_id, node_type):
        result = [self._create_resolved_package_from_id(pkg_id, node_type, "heuristic")]
        context.session_resolved[node_type] = pkg_id
        return result

# NEW - Priority 5: Removed
# No auto-resolution - return None to trigger strategy
logger.debug(f"No resolution found for {node_type} - will use interactive strategy")
return None
```

**Delete methods:**
- `_likely_provides_node()` - replaced by hint detection in unified search
- `fuzzy_search_packages()` - replaced by `search_packages()`

---

### Phase 3: Update Interactive Strategy

**Location:** `packages/cli/comfydock_cli/strategies/interactive.py`

**Update `InteractiveNodeStrategy`:**

```python
class InteractiveNodeStrategy(NodeResolutionStrategy):
    """Interactive node resolution with unified search."""

    def __init__(self, search_fn=None, installed_packages=None):
        """Initialize with search function and installed packages.

        Args:
            search_fn: GlobalNodeResolver.search_packages function
            installed_packages: Dict of installed packages for prioritization
        """
        self.search_fn = search_fn
        self.installed_packages = installed_packages or {}

    def resolve_unknown_node(
        self,
        node_type: str,
        possible: List[ResolvedNodePackage]
    ) -> ResolvedNodePackage | None:
        """Prompt user to resolve unknown node."""

        # Case 1: Ambiguous from global table
        if possible and len(possible) > 1:
            return self._resolve_ambiguous(node_type, possible)

        # Case 2: Single match from global table
        # Show for confirmation (could be wrong)
        if len(possible) == 1:
            pkg = possible[0]
            print(f"\n✓ Found in registry: {pkg.package_id}")
            print(f"  For node: {node_type}")

            choice = input("Accept? [Y/n]: ").strip().lower()
            if choice in ('', 'y', 'yes'):
                return pkg
            # User rejected - fall through to search

        # Case 3: No matches - use unified search
        if not possible or len(possible) == 1:  # Rejected single match
            print(f"\n⚠️  Node not found in registry: {node_type}")

            if self.search_fn:
                print("🔍 Searching packages...")

                results = self.search_fn(
                    node_type=node_type,
                    installed_packages=self.installed_packages,
                    include_registry=True,
                    limit=10
                )

                if results:
                    return self._show_search_results(node_type, results)
                else:
                    print("  No matches found")

            # No matches - manual or skip
            return self._show_manual_options(node_type)

        return None

    def _show_search_results(
        self,
        node_type: str,
        results: List[ScoredPackageMatch]
    ) -> ResolvedNodePackage | None:
        """Show unified search results to user.

        NOTE: Don't show confidence scores to user - let ordering speak for itself.
        """
        print(f"\nFound {len(results)} potential matches:\n")

        display_count = min(5, len(results))
        for i, match in enumerate(results[:display_count], 1):
            pkg_id = match.package_id
            desc = (match.package_data.description or "No description")[:60] if match.package_data else ""

            # Show if installed (useful context)
            installed_marker = " (installed)" if pkg_id in self.installed_packages else ""

            print(f"  {i}. {pkg_id}{installed_marker}")
            if desc:
                print(f"     {desc}")
            print()

        if len(results) > 5:
            print(f"  6. [Browse all {len(results)} matches...]\n")

        print("  0. Other options (manual, skip)\n")

        while True:
            choice = input("Choice [1]: ").strip() or "1"

            if choice == "0":
                return self._show_manual_options(node_type)

            elif choice == "6" and len(results) > 5:
                selected = self._browse_all_packages(results)
                if selected:
                    print(f"\n✓ Selected: {selected.package_id}")
                    return self._create_resolved_from_match(node_type, selected)
                return None

            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < display_count:
                    selected = results[idx]
                    print(f"\n✓ Selected: {selected.package_id}")
                    return self._create_resolved_from_match(node_type, selected)

            print("  Invalid choice, try again")

    def _create_resolved_from_match(
        self,
        node_type: str,
        match: ScoredPackageMatch
    ) -> ResolvedNodePackage:
        """Create ResolvedNodePackage from user-confirmed match."""
        from comfydock_core.models.workflow import ResolvedNodePackage

        return ResolvedNodePackage(
            package_id=match.package_id,
            package_data=match.package_data,
            node_type=node_type,
            versions=[],
            match_type="user_confirmed",
            match_confidence=match.score
        )

    def _browse_all_packages(self, results: List[ScoredPackageMatch]):
        """Browse all matches with pagination."""
        # Similar to _browse_all_models in InteractiveModelStrategy
        # Implementation omitted for brevity - mirror the model strategy
        pass

    def _show_manual_options(self, node_type: str):
        """Show manual entry or skip options."""
        print("\nOptions:")
        print("  1. Enter package ID manually")
        print("  2. Skip (resolve later)")

        choice = input("\nChoice [2]: ").strip() or "2"

        if choice == "1":
            pkg_id = input("Enter package ID: ").strip()
            if pkg_id:
                # Create manual package (need to look up in registry)
                pkg_data = self.global_mappings.packages.get(pkg_id)
                if pkg_data:
                    return ResolvedNodePackage(
                        package_id=pkg_id,
                        package_data=pkg_data,
                        node_type=node_type,
                        versions=[],
                        match_type="manual",
                        match_confidence=1.0
                    )
                else:
                    print(f"⚠️  Package '{pkg_id}' not found in registry")

        return None  # Skip
```

---

### Phase 4: Wire Together in CLI

**Location:** `packages/cli/comfydock_cli/env_commands.py`

**Update `workflow_resolve` command:**

```python
# In workflow_resolve()

# Choose strategy
if args.auto:
    from comfydock_core.strategies.auto import AutoNodeStrategy, AutoModelStrategy
    node_strategy = AutoNodeStrategy()
    model_strategy = AutoModelStrategy()
else:
    node_strategy = InteractiveNodeStrategy(
        search_fn=env.workflow_manager.global_node_resolver.search_packages,
        installed_packages=env.pyproject.nodes.get_existing()
    )
    model_strategy = InteractiveModelStrategy(
        fuzzy_search_fn=env.workflow_manager.find_similar_models
    )
```

---

## Expected UX Changes

### Before (Auto-Resolve)

**User sees:**
```
🔧 Resolving dependencies...
✅ Resolution complete!
  • Resolved 46 nodes
```

**What actually happened (hidden):**
```
DEBUG - Heuristic match for Mute / Bypass Repeater (rgthree): rgthree-comfy
DEBUG - Heuristic match for Any Switch (rgthree): rgthree-comfy
DEBUG - Heuristic match for Custom Node (custom): custom-nodes-1  ← MIGHT BE WRONG!
```

### After (User Confirmation)

**User sees:**
```
🔧 Resolving dependencies...

⚠️  Node not found in registry: Mute / Bypass Repeater (rgthree)
🔍 Searching packages...

Found 1 potential match:

  1. rgthree-comfy (installed)
     Provides nodes for ComfyUI workflow management

Choice [1]: ↵

✓ Selected: rgthree-comfy

⚠️  Node not found in registry: Custom Node (custom)
🔍 Searching packages...

Found 2 potential matches:

  1. my-custom-nodes (installed)
     Custom workflow utilities

  2. custom-node-pack
     General custom node collection

Choice [1]: 1

✓ Selected: my-custom-nodes

✅ Resolution complete!
  • Resolved 46 nodes
  • Saved 2 custom mappings
```

**Next time** these nodes appear in any workflow:
- Priority 2 (custom mappings) catches them
- Auto-resolves silently (user already confirmed)
- No re-prompting

---

## Files to Modify

### Core Package

1. **`packages/core/src/comfydock_core/resolvers/global_node_resolver.py`**
   - Add `search_packages()` method (replaces `fuzzy_search_packages`)
   - Add `_calculate_match_score()` helper
   - Add `_detect_hint_patterns()` helper
   - Add `_score_to_confidence()` helper
   - Remove `_likely_provides_node()` method
   - Remove `fuzzy_search_packages()` method
   - Update `resolve_single_node_with_context()` to remove Priority 5

2. **`packages/core/src/comfydock_core/models/workflow.py`**
   - No changes needed (ScoredPackageMatch already exists)

### CLI Package

3. **`packages/cli/comfydock_cli/strategies/interactive.py`**
   - Update `InteractiveNodeStrategy.__init__()` signature
   - Update `resolve_unknown_node()` logic
   - Add `_show_search_results()` method
   - Add `_create_resolved_from_match()` helper
   - Update `_browse_all_packages()` to work with ScoredPackageMatch

4. **`packages/cli/comfydock_cli/env_commands.py`**
   - Update `workflow_resolve()` to pass search function

---

## Testing Strategy

### Unit Tests

**Location:** `packages/core/tests/unit/test_unified_node_search.py`

```python
def test_hint_bonus_parenthetical():
    """Parenthetical hints should boost score."""
    resolver = GlobalNodeResolver(mappings_path)

    results = resolver.search_packages(
        node_type="Test Node (mypack)",
        installed_packages={"mypack-nodes": mock_node_info}
    )

    assert len(results) > 0
    assert results[0].package_id == "mypack-nodes"
    assert results[0].score >= 0.85  # High due to hint bonus

def test_hint_bonus_pipe_separator():
    """Pipe separator hints should boost score."""
    results = resolver.search_packages(
        node_type="My Node | AkatzNodes",
        installed_packages={"akatznodes": mock_node_info}
    )

    assert results[0].package_id == "akatznodes"
    assert results[0].score >= 0.85

def test_installed_package_priority():
    """Installed packages should rank higher."""
    results = resolver.search_packages(
        node_type="TestNode",
        installed_packages={"testnode-pack": mock_node_info},
        include_registry=True
    )

    # Installed should be first even with similar scores
    assert results[0].package_id == "testnode-pack"

def test_multiple_matches_ranked():
    """Multiple matches should be ranked by score."""
    results = resolver.search_packages(
        node_type="CLIP Encode (clip)",
        installed_packages={
            "clip-vision": mock_node_info,
            "clip-interrogator": mock_node_info,
            "comfyui-clip": mock_node_info
        }
    )

    assert len(results) >= 3
    # All should have similar scores (same hint)
    # User must choose
```

### Integration Tests

**Location:** `packages/core/tests/integration/test_unified_search_flow.py`

```python
def test_unified_search_with_confirmation(test_env):
    """End-to-end: search → user confirms → saves mapping."""
    # Create workflow with node that triggers search
    workflow_data = create_workflow_with_hint_node()

    # Mock user input (select first option)
    with patch('builtins.input', return_value='1'):
        result = test_env.resolve_workflow(
            name="test_workflow",
            node_strategy=InteractiveNodeStrategy(...),
            model_strategy=None
        )

    # Should be resolved
    assert len(result.nodes_resolved) > 0

    # Should be saved to custom mappings
    mappings = test_env.pyproject.node_mappings.get_all_mappings()
    assert "Test Node (hint)" in mappings

def test_second_workflow_reuses_mapping(test_env):
    """Second workflow should use saved mapping (no prompt)."""
    # First workflow - user confirms
    with patch('builtins.input', return_value='1'):
        result1 = test_env.resolve_workflow("workflow1", ...)

    # Second workflow - auto-resolves via custom mapping
    result2 = test_env.resolve_workflow("workflow2", ...)

    # Should resolve without user input
    assert len(result2.nodes_resolved) > 0
```

---

## Performance Considerations

### Search Space Optimization

**Two-phase search** to avoid scanning entire registry when unnecessary:

```python
# Phase 1: Quick search (installed only)
if installed_packages:
    installed_results = self._search_candidates(node_type, installed_packages)
    if installed_results and installed_results[0].score >= 0.85:
        # Strong match in installed - skip registry
        return installed_results[:limit]

# Phase 2: Broader search (if needed)
if include_registry:
    # Search all packages
    all_results = self._search_candidates(node_type, all_candidates)
    return all_results[:limit]
```

**Expected performance:**
- Most cases: scan ~10 installed packages (< 10ms)
- Weak matches: scan ~500 registry packages (< 100ms)
- Still much faster than network calls

---

## Migration Path

1. **Phase 1**: Implement `search_packages()` (keeps old code working)
2. **Phase 2**: Update `InteractiveNodeStrategy` to use it
3. **Phase 3**: Remove Priority 5 auto-resolution
4. **Phase 4**: Delete old methods (`_likely_provides_node`, `fuzzy_search_packages`)
5. **Phase 5**: Run full test suite
6. **Phase 6**: Manual testing with real workflows

---

## Success Criteria

- ✅ No auto-resolution of heuristic matches
- ✅ User confirms all node resolutions (except priorities 1-4)
- ✅ Single unified search function (no duplicate logic)
- ✅ Hint patterns boost scores appropriately
- ✅ Installed packages prioritized in results
- ✅ Confirmed choices persist to custom mappings
- ✅ Second workflow with same node auto-resolves (via mapping)
- ✅ All existing tests continue to pass
- ✅ New tests validate unified search behavior

---

## Benefits Summary

### User Trust
- **No silent failures** - user sees every decision
- **Confirm obvious matches** - builds confidence
- **Override capability** - user always in control

### Code Quality
- **Single search path** - simpler architecture
- **Extensible hints** - easy to add new patterns
- **Unified scoring** - consistent confidence levels

### User Experience
- **Learn over time** - custom mappings eliminate re-prompting
- **Familiar UX** - mirrors model resolution flow
- **Clear ordering** - best matches first, no confusing scores

### Safety
- **Multiple matches handled** - no auto-pick of first
- **Ambiguity detection** - user chooses when unclear
- **Rollback friendly** - custom mappings can be edited/removed

---

## Notes

### Design Decisions

1. **No confidence scores in UI** - ordering is sufficient
2. **Always show installed marker** - useful context for user
3. **Hint detection is additive** - multiple patterns can stack
4. **Minimum hint length (3 chars)** - avoid false positives
5. **Installed bonus (+0.10)** - small but meaningful

### Future Enhancements

- Add more hint patterns as discovered (bracket `[hint]`, etc.)
- Machine learning on user choices to improve ranking
- Confidence visualization (optional, off by default)
- Package popularity as ranking signal

---

**Document Created:** 2025-10-06
**Status:** Ready for implementation
