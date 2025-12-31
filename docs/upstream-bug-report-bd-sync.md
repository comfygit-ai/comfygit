# Draft Bug Report: `bd sync` skips CommitToSyncBranch when .beads is gitignored

**Repository:** https://github.com/steveyegge/beads
**Related Issue:** #810 (similar symptoms, different root cause)

---

## Title

`bd sync` says "No changes to commit" when sync-branch is configured and .beads/ is fully gitignored on code branches

## Description

When using `sync-branch` configuration with a `.beads/.gitignore` that ignores ALL data files on code branches (using `*` pattern), `bd sync` never calls `CommitToSyncBranch()` because `gitHasBeadsChanges()` checks the main repo where files are gitignored.

### Important Context

The beads project itself does NOT use this pattern - it tracks `issues.jsonl` on all branches and uses `sync-branch` for multi-clone syncing. However, this "code-branches-ignore-beads-data" pattern is a valid use case discussed in issues #797 and #801, which implemented gitignore noise elimination for non-sync branches.

This bug report documents an edge case where `sync-branch` + aggressive gitignore on code branches causes sync to silently skip commits.

## Environment

- beads version: 0.40.0 (6f00e482)
- OS: Ubuntu 25.10 (Docker container)
- Git version: 2.x
- Configuration: `sync-branch: beads-sync` in `.beads/config.yaml`

## Setup That Triggers the Bug

**On code branches (main, feature/*):**
```gitignore
# .beads/.gitignore
# ... standard ignores for db, daemon files, etc ...

# On code branches, ignore all data files.
# The beads-sync branch tracks issues.jsonl, metadata.json, etc.
*
!.gitignore
```

**On beads-sync branch:**
```gitignore
# .beads/.gitignore (standard pattern)
# ... standard ignores ...

# Keep JSONL exports and config
!issues.jsonl
!interactions.jsonl
!metadata.json
```

This setup keeps beads data commits completely separate from code commits - only the `beads-sync` branch tracks the actual issue data.

## Steps to Reproduce

1. Set up a project with `sync-branch: beads-sync` configured
2. On code branches, configure `.beads/.gitignore` to ignore all data files (using `*` pattern)
3. Create or modify an issue: `bd update <id> --status in_progress`
4. Run `bd sync --verbose`

## Expected Behavior

- `bd sync` should copy `.beads/issues.jsonl` to the worktree at `.git/beads-worktrees/beads-sync/.beads/`
- Detect changes in the worktree (which has different gitignore - keeps `!issues.jsonl`)
- Commit and push to the sync branch

## Actual Behavior

```
auto-import skipped, JSONL unchanged (hash match)
→ Exporting pending changes to JSONL...
→ No changes to commit           <-- BUG: should call CommitToSyncBranch
→ Pulling from sync branch 'beads-sync'...
✓ Pulled from beads-sync
...
✓ Sync complete
```

The local `.beads/issues.jsonl` has the updated data, but the worktree and remote `beads-sync` branch still have old data.

## Root Cause Analysis

In `cmd/bd/sync.go` around line 396:

```go
// Step 2: Check if there are changes to commit (check entire .beads/ directory)
hasChanges, err := gitHasBeadsChanges(ctx)
if err != nil {
    FatalError("checking git status: %v", err)
}
// ...
if hasChanges {
    // ...
    } else if useSyncBranch {
        // Use worktree to commit to sync branch
        result, err := syncbranch.CommitToSyncBranch(ctx, repoRoot, syncBranchName, jsonlPath, !noPush)
        // ...
    }
} else {
    fmt.Println("→ No changes to commit")  // <-- Always hits this when .beads is gitignored
}
```

The problem:

1. `gitHasBeadsChanges()` runs `git status --porcelain .beads/` on the **main repo**
2. Since `.beads/` is gitignored on code branches, git reports no changes
3. `hasChanges` is `false`, so the entire commit block is skipped
4. `CommitToSyncBranch()` is never called, but it's the function that:
   - Copies `.beads/issues.jsonl` to the worktree via `SyncJSONLToWorktree()`
   - Checks for changes **in the worktree** (where gitignore keeps `!issues.jsonl`)
   - Commits if there are changes

## Suggested Fix

When `useSyncBranch` is true, bypass the `gitHasBeadsChanges()` check and always call `CommitToSyncBranch()`. Let it handle the "no changes" case internally, which it already does correctly at lines 128-135 of `worktree.go`:

```go
// Check for changes in worktree
hasChanges, err := hasChangesInWorktree(ctx, worktreePath, worktreeJSONLPath)
if err != nil {
    return nil, fmt.Errorf("failed to check for changes in worktree: %w", err)
}
if !hasChanges {
    return result, nil // No changes to commit
}
```

**Proposed patch:**

```go
// Step 2: Check if there are changes to commit
// When using sync-branch, skip this check - CommitToSyncBranch handles it internally
// The main repo's .beads may be gitignored on code branches (valid per #797/#801)
var hasChanges bool
if !useSyncBranch {
    hasChanges, err = gitHasBeadsChanges(ctx)
    if err != nil {
        FatalError("checking git status: %v", err)
    }
} else {
    hasChanges = true  // Let CommitToSyncBranch determine if there are actual changes
}
```

## Workaround

**Option 1:** Use the same gitignore pattern as the beads project (track `issues.jsonl` on all branches)

**Option 2:** Manual sync when using divergent gitignore:
```bash
cp .beads/issues.jsonl .git/beads-worktrees/beads-sync/.beads/
git -C .git/beads-worktrees/beads-sync add .beads/issues.jsonl
git -C .git/beads-worktrees/beads-sync commit -m "bd sync: manual"
git -C .git/beads-worktrees/beads-sync push origin beads-sync
```

## Relationship to Other Issues

- **#810**: Similar symptoms ("No changes to commit") but different cause (bare repo path resolution)
- **#797/#801**: Implemented gitignore patterns for non-sync branches - this bug is a gap in that feature
- Both #810 and this issue result in local changes not reaching the sync branch, via different code paths
