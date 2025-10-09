# Workflow Resolution Improvements (SIMPLIFIED)

**Date:** 2025-10-08
**Status:** Phases 1-2 Complete, Phase 3 Planned
**Priority:** Medium

## Executive Summary

Simple, focused improvements to workflow resolution. The current architecture already works well - it supports resumability through git checkpoints (`commit --allow-issues`). We just need to:

1. ✅ **Phase 1 (DONE)**: Fix error message truncation
2. ✅ **Phase 2 (DONE)**: Add optional dependency support
3. **Phase 3 (TODO)**: Add dry-run preview mode

**What We're NOT Doing:**
- ❌ New Environment API methods (current architecture is clean)
- ❌ Incremental persistence (already works via `commit --allow-issues`)
- ❌ Major refactors or new abstractions

---

## Current Architecture (It's Good!)

### Resumability Already Works!

```bash
# Start resolving
$ comfydock workflow resolve "my_workflow"
⚠️  Model not found: rife49.pth
Choice: o  # Marks as optional → SAVED to pyproject.toml

⚠️  Node not found: CustomNode
Choice: ^C  # Ctrl+C (in-memory work lost, that's OK!)

# Checkpoint progress
$ comfydock commit -m "WIP" --allow-issues
✅ Saves pyproject.toml state (git checkpoint)

# Resume later
$ comfydock workflow resolve "my_workflow"
# Auto-resolves from pyproject.toml (rife49.pth cached!)
# Only asks about CustomNode
```

**Why This is Better:**
- ✅ Uses git (already tested, already works)
- ✅ Explicit checkpointing (user controls when)
- ✅ No state management complexity
- ✅ Simple, elegant, maintainable

---

## Phase 1: Error Handling ✅ COMPLETE

### Problem
- UV errors truncated to 100 chars ("Pkg-c..." instead of full message)
- Silent failures when conflict parsing fails

### Solution (2 small changes)

**1. Increase error hint length:**
```python
# uv_error_handler.py:74
def format_uv_error_for_user(error: UVCommandError, max_hint_length: int = 300):  # Was 100
```

**2. Add fallback warning:**
```python
# resolution_tester.py:86-91
except Exception as e:
    conflicts = parse_uv_conflicts(str(e))
    if conflicts:
        result.conflicts.extend(conflicts)
    else:
        # NEW: Fallback warning
        result.warnings.append(f"Resolution failed: {str(e)[:500]}")
    return result
```

---

## Phase 2: Optional Dependencies ✅ COMPLETE

### Problem
Custom node-managed models (like `rife49.pth`) can't be marked as "optional"

### Solution (Already Implemented!)

**Core changes:**
- `protocols.py` - Updated documentation for `("optional_unresolved", "")` return
- `workflow_manager.py` - Handles Type 1 & Type 2 optional models
- `model_resolver.py` - Checks `models.optional` section

**CLI changes (ALREADY DONE):**
- `InteractiveModelStrategy` - Added `[o]` option to all prompts
- Returns `("optional_unresolved", "")` for Type 1
- Sets `model._mark_as_optional = True` for Type 2

**Data Model:**
```toml
[tool.comfydock.models.optional]
# Type 1: Unresolved (filename key, minimal)
"rife49.pth" = { unresolved = true }

# Type 2: Nice-to-have (hash key, full metadata)
"abc123hash..." = {
  filename = "artistic_lora.safetensors",
  size = 143000000,
  relative_path = "loras/artistic_lora.safetensors"
}
```

**Test Coverage:**
- ✅ 5 passing integration tests
- ✅ Type 1 and Type 2 flows verified

---

## Phase 3: Dry-Run Mode (TODO)

### Goal
Add `--dry-run` flag to preview issues without prompting

### Implementation (Simple!)

**1. Add flag to CLI:**
```python
# env_commands.py - workflow_resolve()
parser.add_argument('--dry-run', action='store_true',
                   help='Preview issues without resolving')
```

**2. Skip fix_resolution if dry-run:**
```python
# env_commands.py - workflow_resolve()
if not args.dry_run and (node_strategy or model_strategy):
    resolution = env.resolve_workflow(
        name=args.name,
        node_strategy=node_strategy,
        model_strategy=model_strategy
    )
else:
    # Just analyze, don't prompt
    resolution = workflow_manager.resolve_workflow(dependencies)
```

**3. Display preview:**
```python
if args.dry_run:
    print(f"\n🔍 Preview for '{args.name}':")
    print(f"  • {len(resolution.nodes_resolved)} auto-resolvable nodes")
    print(f"  • {len(resolution.models_resolved)} auto-resolvable models")
    print(f"  • {len(resolution.nodes_unresolved)} unresolved nodes")
    print(f"  • {len(resolution.models_unresolved)} unresolved models")
    print("\n💡 Run without --dry-run to resolve interactively")
```

**Estimated Effort:** 2-3 hours
**Risk:** Very low (read-only feature)

---

## Testing

### Phase 1
- ✅ Tested with known error cases (facerestore_cf, pycairo)
- ✅ Verified 300-char hints display correctly

### Phase 2
- ✅ 5 integration tests passing
- ✅ Type 1 optional (unresolved) works
- ✅ Type 2 optional (nice-to-have) works
- ✅ Optional counts as "resolved" for commit safety

### Phase 3 (When Implemented)
- [ ] Test --dry-run shows preview without persisting
- [ ] Test normal resolution still works
- [ ] Verify no pyproject.toml changes in dry-run mode

---

## Timeline

| Phase | Status | Effort | Risk |
|-------|--------|--------|------|
| Phase 1: Error Handling | ✅ DONE | 2 hours | Low |
| Phase 2: Optional Support | ✅ DONE | 6 hours | Low |
| Phase 3: Dry-Run Mode | TODO | 2-3 hours | Low |
| **TOTAL** | - | **~10 hours** | **Low** |

---

## Success Criteria

### Must Have (MVP)
1. ✅ Users can mark models as "optional"
2. ✅ Error messages are readable
3. ✅ Resumability through git checkpoints works
4. [ ] --dry-run shows preview without persisting

### Nice to Have (Future)
- ⏱ Batch resolution (multiple workflows)
- ⏱ Model download queue
- ⏱ Resolution templates

---

## Key Design Decisions

### D1: Resumability via Git Checkpoints

**Decision:** Use `commit --allow-issues` for checkpointing, NOT incremental persistence

**Rationale:**
- Git already works, already tested
- Explicit user control (not automatic/implicit)
- No new state management needed
- Aligns with "simple, elegant" MVP philosophy

### D2: Optional Models (Two Types)

**Decision:** Support both unresolved and resolved optional models

**Type 1 (Unresolved):** Filename key, `{unresolved = true}`
- Use case: Custom node-managed (like `rife49.pth`)

**Type 2 (Nice-to-have):** Hash key, full metadata
- Use case: In index but not required (like bonus LoRAs)

### D3: No New Environment APIs

**Decision:** Keep current architecture, don't add new high-level methods

**Rationale:**
- Current separation is clean (Core = logic, CLI = UI)
- Adding new APIs would violate this separation
- Current approach is testable and maintainable

---

## Related Documents

- [PRD](../prd.md) - Overall system design
- [Layer Hierarchy](../layer-hierarchy.md) - Code organization

---

**Document Status:** Simplified, Phases 1-2 Complete
**Last Updated:** 2025-10-08
