# Implementation Plan: Git Pull/Push/Remote Commands

## Overview

Add `comfydock pull`, `comfydock push`, and `comfydock remote` commands to provide git-aware workflow management with automatic environment synchronization.

**Problem Solved:** After `git pull` in `.cec/`, users currently get misleading status messages and may run `workflow resolve` which reads from the wrong direction and deletes model metadata. These commands provide the correct git→ComfyDock integration.

**Key Design Decisions:**
1. **Auto-add remote on import** - When importing from git URL, automatically set that URL as `origin` remote
2. **Push requires clean state** - `push` has NO `-m` flag; users must commit all changes first before pushing
3. **Remote management wrapper** - `comfydock remote add/remove/list` wraps git remote operations for UX

---

## User Experience

### Workflow After Implementation

```bash
# First-time setup
comfydock import https://github.com/user/my-setup.git --name my-env
# → Auto-adds github URL as 'origin' remote ✅

# Make changes in ComfyUI
comfydock commit -m "Add upscaler workflow"

# Push to remote (no -m flag needed!)
comfydock push
# → Fails if uncommitted changes exist ✅
# → Auto-pushes committed changes ✅

# On another machine
comfydock pull
# → Fetch + merge + auto-repair ✅
```

### Command Specifications

#### `comfydock pull`
```bash
comfydock pull [-r/--remote origin] [--models all|required|skip] [--force] [-e env]
```

**Behavior:**
1. Check for uncommitted changes → Error unless `--force`
2. Check remote exists → Error with setup guidance
3. `git fetch origin`
4. `git merge --ff-only origin/main` (fast-forward only for safety)
5. Auto-run `repair` to sync environment
6. Print summary

**Error Cases:**
- No remote configured → Guide user to add remote
- Uncommitted changes → Suggest commit/rollback/force
- Merge conflicts → Guide user to manual resolution
- Network errors → Clear error messages

---

#### `comfydock push`
```bash
comfydock push [-r/--remote origin] [--allow-issues] [-e env]
```

**Behavior:**
1. Check for uncommitted changes → **Error if any exist**
2. Check remote exists → Error with setup guidance
3. Check for unresolved workflow issues → Error unless `--allow-issues`
4. `git push origin main`
5. Print summary with remote URL

**Important:** NO `-m/--message` flag! Users MUST run `comfydock commit -m "msg"` first.

**Error Cases:**
- Uncommitted changes exist → "Run: comfydock commit -m 'message' first"
- No changes to push → "Already up to date"
- No remote configured → Guide user to add remote
- Push rejected (conflicts) → Guide to pull first
- Authentication failure → Guide to SSH/HTTPS setup

---

#### `comfydock remote`
```bash
comfydock remote add <name> <url> [-e env]
comfydock remote remove <name> [-e env]
comfydock remote list [-e env]
```

**Behavior:**
- Wraps git remote operations
- Validates remote URL format
- Shows helpful error messages
- Operates on current environment's `.cec/.git`

**Examples:**
```bash
# Add origin remote
comfydock remote add origin https://github.com/user/my-setup.git

# List remotes
comfydock remote list
# Output:
# origin  https://github.com/user/my-setup.git (fetch)
# origin  https://github.com/user/my-setup.git (push)

# Remove remote
comfydock remote remove origin
```

---

## Implementation Phases

### Phase 1: Core Git Utilities (packages/core/src/comfydock_core/utils/git.py)

**File:** `packages/core/src/comfydock_core/utils/git.py`

**Add these functions:**

```python
def git_fetch(
    repo_path: Path,
    remote: str = "origin",
    timeout: int = 30,
) -> str:
    """Fetch from remote.

    Args:
        repo_path: Path to git repository
        remote: Remote name (default: origin)
        timeout: Command timeout in seconds

    Returns:
        Fetch output

    Raises:
        ValueError: If remote doesn't exist
        OSError: If fetch fails (network, auth, etc.)
    """
    # Validate remote exists first
    remote_url = git_remote_get_url(repo_path, remote)
    if not remote_url:
        raise ValueError(
            f"Remote '{remote}' not configured. "
            f"Add with: comfydock remote add {remote} <url>"
        )

    cmd = ["fetch", remote]
    result = _git(cmd, repo_path, timeout=timeout)
    return result.stdout


def git_merge(
    repo_path: Path,
    ref: str,
    ff_only: bool = True,
    timeout: int = 30,
) -> str:
    """Merge a ref into current branch.

    Args:
        repo_path: Path to git repository
        ref: Ref to merge (e.g., "origin/main")
        ff_only: Only allow fast-forward merges (default: True)
        timeout: Command timeout in seconds

    Returns:
        Merge output

    Raises:
        ValueError: If merge would conflict (when ff_only=True)
        OSError: If merge fails
    """
    cmd = ["merge"]
    if ff_only:
        cmd.append("--ff-only")
    cmd.append(ref)

    try:
        result = _git(cmd, repo_path, timeout=timeout)
        return result.stdout
    except CDProcessError as e:
        if ff_only and "not possible to fast-forward" in str(e).lower():
            raise ValueError(
                f"Cannot fast-forward merge {ref}. "
                "Remote has diverged - resolve manually."
            ) from e
        raise OSError(f"Merge failed: {e}") from e


def git_pull(
    repo_path: Path,
    remote: str = "origin",
    branch: str = "main",
    ff_only: bool = True,
    timeout: int = 30,
) -> dict:
    """Fetch and merge from remote (pull operation).

    Args:
        repo_path: Path to git repository
        remote: Remote name (default: origin)
        branch: Branch name (default: main)
        ff_only: Only allow fast-forward merges (default: True)
        timeout: Command timeout in seconds

    Returns:
        Dict with keys: 'fetch_output', 'merge_output'

    Raises:
        ValueError: If remote doesn't exist or merge conflicts
        OSError: If fetch/merge fails
    """
    # Fetch first
    fetch_output = git_fetch(repo_path, remote, timeout)

    # Then merge
    merge_ref = f"{remote}/{branch}"
    merge_output = git_merge(repo_path, merge_ref, ff_only, timeout)

    return {
        'fetch_output': fetch_output,
        'merge_output': merge_output,
    }


def git_push(
    repo_path: Path,
    remote: str = "origin",
    branch: str | None = None,
    force: bool = False,
    timeout: int = 30,
) -> str:
    """Push commits to remote.

    Args:
        repo_path: Path to git repository
        remote: Remote name (default: origin)
        branch: Branch to push (default: current branch)
        force: Use --force-with-lease (default: False)
        timeout: Command timeout in seconds

    Returns:
        Push output

    Raises:
        ValueError: If remote doesn't exist
        OSError: If push fails (auth, conflicts, network)
    """
    # Validate remote exists
    remote_url = git_remote_get_url(repo_path, remote)
    if not remote_url:
        raise ValueError(
            f"Remote '{remote}' not configured. "
            f"Add with: comfydock remote add {remote} <url>"
        )

    cmd = ["push", remote]

    if branch:
        cmd.append(branch)

    if force:
        cmd.append("--force-with-lease")

    try:
        result = _git(cmd, repo_path, timeout=timeout)
        return result.stdout
    except CDProcessError as e:
        error_msg = str(e).lower()
        if "permission denied" in error_msg or "authentication" in error_msg:
            raise OSError(
                "Authentication failed. Check SSH key or HTTPS credentials."
            ) from e
        elif "rejected" in error_msg:
            raise OSError(
                "Push rejected - remote has changes. Run: comfydock pull first"
            ) from e
        raise OSError(f"Push failed: {e}") from e


def git_current_branch(repo_path: Path) -> str:
    """Get current branch name.

    Args:
        repo_path: Path to git repository

    Returns:
        Branch name (e.g., "main")

    Raises:
        ValueError: If in detached HEAD state
    """
    result = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
    branch = result.stdout.strip()

    if branch == "HEAD":
        raise ValueError(
            "Detached HEAD state - cannot pull/push. "
            "Checkout a branch: git checkout main"
        )

    return branch


def git_remote_add(repo_path: Path, name: str, url: str) -> None:
    """Add a git remote.

    Args:
        repo_path: Path to git repository
        name: Remote name (e.g., "origin")
        url: Remote URL

    Raises:
        OSError: If remote already exists or add fails
    """
    # Check if remote already exists
    existing_url = git_remote_get_url(repo_path, name)
    if existing_url:
        raise OSError(f"Remote '{name}' already exists: {existing_url}")

    _git(["remote", "add", name, url], repo_path)


def git_remote_remove(repo_path: Path, name: str) -> None:
    """Remove a git remote.

    Args:
        repo_path: Path to git repository
        name: Remote name (e.g., "origin")

    Raises:
        ValueError: If remote doesn't exist
        OSError: If removal fails
    """
    # Check if remote exists
    existing_url = git_remote_get_url(repo_path, name)
    if not existing_url:
        raise ValueError(f"Remote '{name}' not found")

    _git(["remote", "remove", name], repo_path)


def git_remote_list(repo_path: Path) -> list[tuple[str, str, str]]:
    """List all git remotes.

    Args:
        repo_path: Path to git repository

    Returns:
        List of tuples: [(name, url, type), ...]
        Example: [("origin", "https://...", "fetch"), ("origin", "https://...", "push")]
    """
    result = _git(["remote", "-v"], repo_path, check=False)

    if result.returncode != 0:
        return []

    remotes = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 3:
            name = parts[0]
            url = parts[1]
            remote_type = parts[2].strip('()')
            remotes.append((name, url, remote_type))

    return remotes
```

**Why these functions?**
- `git_fetch` + `git_merge` provide granular control (vs. `git pull` which combines both)
- `git_current_branch` prevents push/pull on detached HEAD
- `git_remote_*` functions provide remote management
- All functions validate inputs and provide ComfyDock-specific error messages

---

### Phase 2: Git Manager High-Level Methods (packages/core/src/comfydock_core/managers/git_manager.py)

**File:** `packages/core/src/comfydock_core/managers/git_manager.py`

**Add these methods to GitManager class:**

```python
def pull(self, remote: str = "origin", branch: str | None = None) -> dict:
    """Pull from remote (fetch + fast-forward merge).

    Args:
        remote: Remote name (default: origin)
        branch: Branch to pull (default: current branch)

    Returns:
        Dict with keys: 'fetch_output', 'merge_output', 'branch'

    Raises:
        ValueError: If no remote, detached HEAD, or merge conflicts
        OSError: If fetch/merge fails
    """
    from ..utils.git import git_pull, git_current_branch

    # Get current branch if not specified
    if not branch:
        branch = git_current_branch(self.repo_path)

    logger.info(f"Pulling {remote}/{branch}")

    result = git_pull(self.repo_path, remote, branch, ff_only=True)
    result['branch'] = branch

    return result


def push(self, remote: str = "origin", branch: str | None = None) -> str:
    """Push commits to remote.

    Args:
        remote: Remote name (default: origin)
        branch: Branch to push (default: current branch)

    Returns:
        Push output

    Raises:
        ValueError: If no remote or detached HEAD
        OSError: If push fails
    """
    from ..utils.git import git_push, git_current_branch

    # Get current branch if not specified
    if not branch:
        branch = git_current_branch(self.repo_path)

    logger.info(f"Pushing to {remote}/{branch}")

    return git_push(self.repo_path, remote, branch)


def add_remote(self, name: str, url: str) -> None:
    """Add a git remote.

    Args:
        name: Remote name (e.g., "origin")
        url: Remote URL

    Raises:
        OSError: If remote already exists
    """
    from ..utils.git import git_remote_add

    logger.info(f"Adding remote '{name}': {url}")
    git_remote_add(self.repo_path, name, url)


def remove_remote(self, name: str) -> None:
    """Remove a git remote.

    Args:
        name: Remote name (e.g., "origin")

    Raises:
        ValueError: If remote doesn't exist
    """
    from ..utils.git import git_remote_remove

    logger.info(f"Removing remote '{name}'")
    git_remote_remove(self.repo_path, name)


def list_remotes(self) -> list[tuple[str, str, str]]:
    """List all git remotes.

    Returns:
        List of tuples: [(name, url, type), ...]
    """
    from ..utils.git import git_remote_list

    return git_remote_list(self.repo_path)


def has_remote(self, name: str = "origin") -> bool:
    """Check if a remote exists.

    Args:
        name: Remote name (default: origin)

    Returns:
        True if remote exists
    """
    from ..utils.git import git_remote_get_url

    url = git_remote_get_url(self.repo_path, name)
    return bool(url)
```

---

### Phase 3: Environment API (packages/core/src/comfydock_core/core/environment.py)

**File:** `packages/core/src/comfydock_core/core/environment.py`

**Add these methods to Environment class:**

```python
def pull_and_repair(
    self,
    remote: str = "origin",
    branch: str | None = None,
    model_strategy: str = "all"
) -> dict:
    """Pull from remote and auto-repair environment.

    Args:
        remote: Remote name (default: origin)
        branch: Branch to pull (default: current)
        model_strategy: Model download strategy ("all", "required", "skip")

    Returns:
        Dict with pull results

    Raises:
        CDEnvironmentError: If uncommitted changes exist
        ValueError: If merge conflicts
        OSError: If pull or repair fails
    """
    # Check for uncommitted changes
    if self.git_manager.has_uncommitted_changes():
        raise CDEnvironmentError(
            "Cannot pull with uncommitted changes.\n"
            "  • Commit: comfydock commit -m 'message'\n"
            "  • Discard: comfydock rollback"
        )

    # Pull
    logger.info("Pulling from remote...")
    pull_result = self.git_manager.pull(remote, branch)

    # Auto-repair (restores workflows, installs nodes, downloads models)
    logger.info("Repairing environment after pull...")
    self.sync(model_strategy=model_strategy)

    return pull_result


def push_commits(self, remote: str = "origin", branch: str | None = None) -> str:
    """Push commits to remote (requires clean working directory).

    Args:
        remote: Remote name (default: origin)
        branch: Branch to push (default: current)

    Returns:
        Push output

    Raises:
        CDEnvironmentError: If uncommitted changes exist
        ValueError: If no remote or workflow issues
        OSError: If push fails
    """
    # Check for uncommitted changes
    if self.has_committable_changes():
        raise CDEnvironmentError(
            "Cannot push with uncommitted changes.\n"
            "  Run: comfydock commit -m 'message' first"
        )

    # Check for unresolved workflow issues
    workflow_status = self.workflow_manager.get_workflow_status()
    if not workflow_status.is_commit_safe:
        issues = workflow_status.workflows_with_issues
        issue_summary = "\n".join(f"  • {w.name}: {w.issue_summary}" for w in issues[:3])
        raise CDEnvironmentError(
            f"Cannot push with unresolved workflow issues:\n{issue_summary}\n\n"
            "  Resolve: comfydock workflow resolve <name>"
        )

    # Push
    logger.info("Pushing commits to remote...")
    return self.git_manager.push(remote, branch)
```

**Location:** Add after existing `sync()` method around line 280

---

### Phase 4: Auto-Add Remote on Import (packages/core/src/comfydock_core/factories/environment_factory.py)

**File:** `packages/core/src/comfydock_core/factories/environment_factory.py`

**Modify `import_from_git()` method** (around line 221):

**Current code:**
```python
# Line 276-277
git_clone(base_url, cec_path, ref=branch)
```

**Replace with:**
```python
# Line 276-285
git_clone(base_url, cec_path, ref=branch)

# Auto-add the clone URL as 'origin' remote
# Note: git clone automatically sets up 'origin', but we validate it exists
from ..utils.git import git_remote_get_url, git_remote_add

origin_url = git_remote_get_url(cec_path, "origin")
if not origin_url:
    # Should not happen after git clone, but add as safety
    logger.info(f"Adding 'origin' remote: {base_url}")
    git_remote_add(cec_path, "origin", base_url)
else:
    logger.info(f"Remote 'origin' already configured: {origin_url}")
```

**Why this works:**
- `git clone` automatically sets the clone URL as `origin`
- We add validation to ensure it's set
- Users can immediately `comfydock push` after import

**Note for subdirectory imports:**

For `git_clone_subdirectory()` (around line 271-273), we need to handle this differently because the subdirectory extraction loses git history:

**After line 273:**
```python
if subdir:
    logger.info(f"Cloning {base_url} and extracting subdirectory '{subdir}' to {cec_path}")
    git_clone_subdirectory(base_url, cec_path, subdir, ref=branch)

    # Subdirectory imports lose git history, need to init new repo
    from ..utils.git import git_init, git_remote_add
    if not (cec_path / ".git").exists():
        logger.info("Initializing git repository for subdirectory import")
        git_init(cec_path)
        git_remote_add(cec_path, "origin", base_url)
        # Note: User will need to manually set up correct remote if needed
```

**Add `git_init()` utility to git.py:**
```python
def git_init(repo_path: Path) -> None:
    """Initialize a new git repository.

    Args:
        repo_path: Path to initialize as git repo
    """
    _git(["init"], repo_path)
```

---

### Phase 5: CLI Commands (packages/cli/comfydock_cli/env_commands.py)

**File:** `packages/cli/comfydock_cli/env_commands.py`

**Add these command handlers to EnvironmentCommands class:**

```python
@with_env_logging("env pull")
def pull(self, args, logger=None):
    """Pull from remote and repair environment."""
    env = self._get_env(args)

    # Check for uncommitted changes first
    if env.has_committable_changes() and not getattr(args, 'force', False):
        print("⚠️  You have uncommitted changes")
        print()
        print("💡 Options:")
        print("  • Commit: comfydock commit -m 'message'")
        print("  • Discard: comfydock rollback")
        print("  • Force: comfydock pull --force")
        sys.exit(1)

    # Check remote exists
    if not env.git_manager.has_remote(args.remote):
        print(f"✗ Remote '{args.remote}' not configured")
        print()
        print("💡 Set up a remote first:")
        print(f"   comfydock remote add {args.remote} <url>")
        sys.exit(1)

    try:
        print(f"📥 Pulling from {args.remote}...")

        # Pull and repair
        pull_result = env.pull_and_repair(
            remote=args.remote,
            model_strategy=getattr(args, 'models', 'all')
        )

        print(f"   ✓ Pulled changes from {args.remote}")
        print()
        print("⚙️  Environment synced successfully")

    except ValueError as e:
        # Merge conflicts
        if logger:
            logger.error(f"Pull failed: {e}", exc_info=True)
        print(f"✗ Pull failed: {e}", file=sys.stderr)
        print()
        print("💡 Resolve conflicts manually:")
        print(f"   cd {env.cec_path}")
        print("   git status")
        sys.exit(1)
    except OSError as e:
        # Network, auth, or other git errors
        if logger:
            logger.error(f"Pull failed: {e}", exc_info=True)
        print(f"✗ Pull failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if logger:
            logger.error(f"Pull failed: {e}", exc_info=True)
        print(f"✗ Pull failed: {e}", file=sys.stderr)
        sys.exit(1)


@with_env_logging("env push")
def push(self, args, logger=None):
    """Push commits to remote."""
    env = self._get_env(args)

    # Check for uncommitted changes
    if env.has_committable_changes():
        print("⚠️  You have uncommitted changes")
        print()
        print("💡 Commit first:")
        print("   comfydock commit -m 'your message'")
        sys.exit(1)

    # Check remote exists
    if not env.git_manager.has_remote(args.remote):
        print(f"✗ Remote '{args.remote}' not configured")
        print()
        print("💡 Set up a remote first:")
        print(f"   comfydock remote add {args.remote} <url>")
        sys.exit(1)

    try:
        print(f"📤 Pushing to {args.remote}...")

        # Push
        push_output = env.push_commits(remote=args.remote)

        print(f"   ✓ Pushed commits to {args.remote}")

        # Show remote URL
        from comfydock_core.utils.git import git_remote_get_url
        remote_url = git_remote_get_url(env.cec_path, args.remote)
        if remote_url:
            print()
            print(f"💾 Remote: {remote_url}")

    except ValueError as e:
        # No remote or workflow issues
        if logger:
            logger.error(f"Push failed: {e}", exc_info=True)
        print(f"✗ Push failed: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        # Network, auth, or git errors
        if logger:
            logger.error(f"Push failed: {e}", exc_info=True)
        print(f"✗ Push failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if logger:
            logger.error(f"Push failed: {e}", exc_info=True)
        print(f"✗ Push failed: {e}", file=sys.stderr)
        sys.exit(1)


@with_env_logging("env remote")
def remote(self, args, logger=None):
    """Manage git remotes."""
    env = self._get_env(args)

    subcommand = args.remote_command

    try:
        if subcommand == "add":
            # Add remote
            if not args.name or not args.url:
                print("✗ Usage: comfydock remote add <name> <url>")
                sys.exit(1)

            env.git_manager.add_remote(args.name, args.url)
            print(f"✓ Added remote '{args.name}': {args.url}")

        elif subcommand == "remove":
            # Remove remote
            if not args.name:
                print("✗ Usage: comfydock remote remove <name>")
                sys.exit(1)

            env.git_manager.remove_remote(args.name)
            print(f"✓ Removed remote '{args.name}'")

        elif subcommand == "list":
            # List remotes
            remotes = env.git_manager.list_remotes()

            if not remotes:
                print("No remotes configured")
                print()
                print("💡 Add a remote:")
                print("   comfydock remote add origin <url>")
            else:
                print("Remotes:")
                for name, url, remote_type in remotes:
                    print(f"  {name}\t{url} ({remote_type})")

        else:
            print(f"✗ Unknown remote command: {subcommand}")
            print("   Usage: comfydock remote [add|remove|list]")
            sys.exit(1)

    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        if logger:
            logger.error(f"Remote operation failed: {e}", exc_info=True)
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
```

**Location:** Add after `commit()` method around line 1083

---

### Phase 6: CLI Argument Parsers (packages/cli/comfydock_cli/cli.py)

**File:** `packages/cli/comfydock_cli/cli.py`

**In `_add_env_commands()` function** (around line 150), add these subparsers:

```python
# After the 'commit' parser (around line 200)

# pull
pull_parser = subparsers.add_parser(
    "pull",
    help="Pull changes from remote and repair environment"
)
pull_parser.add_argument(
    "-r", "--remote",
    default="origin",
    help="Git remote name (default: origin)"
)
pull_parser.add_argument(
    "--models",
    choices=["all", "required", "skip"],
    default="all",
    help="Model download strategy (default: all)"
)
pull_parser.add_argument(
    "--force",
    action="store_true",
    help="Discard uncommitted changes and force pull"
)
pull_parser.set_defaults(func=env_cmds.pull)

# push
push_parser = subparsers.add_parser(
    "push",
    help="Push committed changes to remote"
)
push_parser.add_argument(
    "-r", "--remote",
    default="origin",
    help="Git remote name (default: origin)"
)
push_parser.add_argument(
    "--allow-issues",
    action="store_true",
    help="Allow push with unresolved workflow issues"
)
push_parser.set_defaults(func=env_cmds.push)

# remote
remote_parser = subparsers.add_parser(
    "remote",
    help="Manage git remotes"
)
remote_subparsers = remote_parser.add_subparsers(
    dest="remote_command",
    required=True
)

# remote add
remote_add_parser = remote_subparsers.add_parser(
    "add",
    help="Add a git remote"
)
remote_add_parser.add_argument(
    "name",
    help="Remote name (e.g., origin)"
)
remote_add_parser.add_argument(
    "url",
    help="Remote URL"
)

# remote remove
remote_remove_parser = remote_subparsers.add_parser(
    "remove",
    help="Remove a git remote"
)
remote_remove_parser.add_argument(
    "name",
    help="Remote name to remove"
)

# remote list
remote_list_parser = remote_subparsers.add_parser(
    "list",
    help="List all git remotes"
)

remote_parser.set_defaults(func=env_cmds.remote)
```

---

## Testing Strategy (MVP: 2-3 Happy Path Tests)

### Test Files to Create

#### 1. `tests/core/test_git_pull_push.py`
```python
"""Tests for git pull/push operations."""

def test_pull_fetches_and_merges():
    """Pull should fetch and fast-forward merge."""
    # Setup: environment with remote tracking
    # Action: pull
    # Assert: fetch called + merge called


def test_push_pushes_commits():
    """Push should push committed changes."""
    # Setup: environment with commits + remote
    # Action: push
    # Assert: push called + success


def test_pull_rejects_with_uncommitted_changes():
    """Pull should reject if uncommitted changes exist."""
    # Setup: environment with uncommitted changes
    # Action: pull
    # Assert: CDEnvironmentError raised
```

#### 2. `tests/core/test_git_remote.py`
```python
"""Tests for git remote operations."""

def test_add_remote():
    """Add remote should configure origin."""
    # Setup: environment without remote
    # Action: add_remote("origin", "https://...")
    # Assert: remote exists + correct URL


def test_list_remotes():
    """List remotes should return all configured remotes."""
    # Setup: environment with origin remote
    # Action: list_remotes()
    # Assert: returns [("origin", url, "fetch"), ...]


def test_remove_remote():
    """Remove remote should delete configuration."""
    # Setup: environment with origin remote
    # Action: remove_remote("origin")
    # Assert: remote no longer exists
```

#### 3. `tests/core/test_import_auto_remote.py`
```python
"""Test auto-adding remote on import."""

def test_import_from_git_adds_origin_remote():
    """Import from git should auto-add origin remote."""
    # Setup: git repository URL
    # Action: workspace.import_from_git(url, "test-env")
    # Assert: .cec/.git has origin remote configured


def test_import_from_git_preserves_clone_url():
    """Import should preserve original clone URL as origin."""
    # Setup: git URL = "https://github.com/user/repo.git"
    # Action: import
    # Assert: git remote get-url origin == original URL
```

#### 4. `tests/cli/test_pull_push_commands.py`
```python
"""Test CLI pull/push commands."""

def test_pull_command():
    """CLI pull should fetch and repair."""
    # Setup: environment with remote + clean state
    # Action: run comfydock pull
    # Assert: output shows fetch + repair success


def test_push_command():
    """CLI push should push commits."""
    # Setup: environment with commits + remote
    # Action: run comfydock push
    # Assert: output shows push success


def test_push_rejects_uncommitted():
    """CLI push should reject if uncommitted changes."""
    # Setup: environment with uncommitted changes
    # Action: run comfydock push
    # Assert: exit code 1 + helpful error message
```

---

## Error Message Examples

### No Remote Configured
```
✗ Remote 'origin' not configured

💡 Set up a remote first:
   comfydock remote add origin <url>

   Example:
   comfydock remote add origin https://github.com/user/my-setup.git
```

### Uncommitted Changes on Pull
```
⚠️  You have uncommitted changes

💡 Options:
  • Commit: comfydock commit -m 'message'
  • Discard: comfydock rollback
  • Force: comfydock pull --force
```

### Uncommitted Changes on Push
```
⚠️  You have uncommitted changes

💡 Commit first:
   comfydock commit -m 'your message'
```

### Merge Conflicts
```
✗ Pull failed: Cannot fast-forward merge origin/main. Remote has diverged.

💡 Resolve conflicts manually:
   cd ~/.comfydock/environments/my-env/.cec
   git status
   git log --oneline --graph --all
```

### Push Rejected (Conflicts)
```
✗ Push failed: Push rejected - remote has changes.

💡 Pull first:
   comfydock pull
```

### Authentication Failure
```
✗ Push failed: Authentication failed. Check SSH key or HTTPS credentials.

💡 Set up authentication:
   • SSH: Add SSH key to GitHub/GitLab
   • HTTPS: Configure git credential helper
```

---

## File Modification Summary

### Core Package (`packages/core/`)

**New utilities:**
1. `src/comfydock_core/utils/git.py` - Add 10 new functions (~200 lines)
   - `git_fetch()`
   - `git_merge()`
   - `git_pull()`
   - `git_push()`
   - `git_current_branch()`
   - `git_init()`
   - `git_remote_add()`
   - `git_remote_remove()`
   - `git_remote_list()`

**Modified managers:**
2. `src/comfydock_core/managers/git_manager.py` - Add 6 methods (~100 lines)
   - `pull()`
   - `push()`
   - `add_remote()`
   - `remove_remote()`
   - `list_remotes()`
   - `has_remote()`

**Modified core:**
3. `src/comfydock_core/core/environment.py` - Add 2 methods (~60 lines)
   - `pull_and_repair()`
   - `push_commits()`

**Modified factories:**
4. `src/comfydock_core/factories/environment_factory.py` - Modify 1 function (~15 lines)
   - Update `import_from_git()` to auto-add remote

### CLI Package (`packages/cli/`)

**Modified commands:**
5. `comfydock_cli/env_commands.py` - Add 3 command handlers (~150 lines)
   - `pull()`
   - `push()`
   - `remote()`

**Modified CLI:**
6. `comfydock_cli/cli.py` - Add 3 argument parsers (~60 lines)
   - `pull` subparser
   - `push` subparser
   - `remote` subparser with sub-subparsers (add/remove/list)

### Tests

**New test files:**
7. `tests/core/test_git_pull_push.py` - 3 tests
8. `tests/core/test_git_remote.py` - 3 tests
9. `tests/core/test_import_auto_remote.py` - 2 tests
10. `tests/cli/test_pull_push_commands.py` - 3 tests

**Total new code:** ~600 lines (excluding tests)

---

## Implementation Order

1. **Phase 1:** Git utilities (foundation)
2. **Phase 2:** Git manager methods (business logic)
3. **Phase 3:** Environment API (high-level operations)
4. **Phase 4:** Auto-add remote on import (critical UX improvement)
5. **Phase 5:** CLI commands (user interface)
6. **Phase 6:** CLI parsers (argument handling)
7. **Testing:** 2-3 happy path tests per component

---

## Open Questions / Future Enhancements

### Not in MVP:
- **Branch management** - For now, assume `main` branch
- **Force push** - Require manual git operations for now
- **Rebase support** - Only fast-forward merges
- **Multi-remote support** - Only `origin` in MVP
- **Pull request integration** - Out of scope
- **Conflict resolution UI** - Guide users to manual git

### Possible Future Additions:
- `comfydock sync` - Alias for `pull` + `commit` + `push`
- `comfydock clone <url>` - Shortcut for `import`
- Auto-detect main vs master branch
- Support for git tags/releases
- Better merge conflict detection and guidance

---

## Context for Next Session

### Key Files to Review
1. **`packages/core/src/comfydock_core/utils/git.py`** - Start here, add utilities
2. **`packages/core/src/comfydock_core/managers/git_manager.py`** - GitManager class (~line 50)
3. **`packages/core/src/comfydock_core/core/environment.py`** - Environment class, add methods after `sync()` (~line 280)
4. **`packages/core/src/comfydock_core/factories/environment_factory.py`** - Modify `import_from_git()` (~line 276)
5. **`packages/cli/comfydock_cli/env_commands.py`** - EnvironmentCommands class, add after `commit()` (~line 1083)
6. **`packages/cli/comfydock_cli/cli.py`** - `_add_env_commands()` function (~line 200)

### Related Knowledge Documents
- **`docs/knowledge/comfyui-node-loader-base-directories.md`** - Model path handling context
- **`docs/plan/git-import-implementation.md`** - Git import architecture reference
- **`docs/plan/export-import-ux.md`** - Import/export UX patterns

### Testing Strategy Reference
- **`tests/README.md`** - Testing guidelines
- **Existing tests:** Look at `tests/core/test_git_manager.py` for patterns
- **CLI tests:** Reference `tests/cli/test_status_displays_uninstalled_nodes.py`

### Design Philosophy Reminder
- **Simple, elegant, maintainable code**
- **No backwards compatibility** - Fix old code to use new code
- **2-3 happy path tests per file**
- **Clear, helpful error messages**
- **MVP-focused - no unnecessary features**

---

## Success Criteria

### User Experience
- ✅ User can run `comfydock pull` after git changes
- ✅ User can run `comfydock push` to sync to remote
- ✅ User can manage remotes with `comfydock remote`
- ✅ Import from git auto-adds origin remote
- ✅ Clear error messages for all failure cases

### Technical
- ✅ All git operations use low-level utilities
- ✅ GitManager provides high-level business logic
- ✅ Environment API is clean and simple
- ✅ CLI provides helpful guidance
- ✅ Tests cover happy paths

### Integration
- ✅ Works with existing commit/status/repair commands
- ✅ Preserves git history after import
- ✅ Handles network/auth errors gracefully
- ✅ No data loss scenarios
