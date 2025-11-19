"""Environment-aware git orchestration manager.

Coordinates git operations with environment state synchronization.
Handles node reconciliation, package syncing, and workflow restoration
around git operations like checkout, rollback, merge, etc.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from ..models.protocols import RollbackStrategy
    from .git_manager import GitManager
    from .node_manager import NodeManager
    from .pyproject_manager import PyprojectManager
    from .uv_project_manager import UVProjectManager
    from .workflow_manager import WorkflowManager

logger = get_logger(__name__)


class EnvironmentGitOrchestrator:
    """Orchestrates git operations with environment synchronization.

    Responsibilities:
    - Coordinate git operations with environment state
    - Handle node reconciliation (add/remove nodes based on git changes)
    - Sync Python packages after git operations
    - Restore workflows from .cec to ComfyUI
    - Manage uncommitted change validation
    """

    def __init__(
        self,
        git_manager: GitManager,
        node_manager: NodeManager,
        pyproject_manager: PyprojectManager,
        uv_manager: UVProjectManager,
        workflow_manager: WorkflowManager,
    ):
        self.git = git_manager
        self.node_manager = node_manager
        self.pyproject = pyproject_manager
        self.uv = uv_manager
        self.workflow_manager = workflow_manager

    def checkout(
        self,
        ref: str,
        strategy: RollbackStrategy | None = None,
        force: bool = False
    ) -> None:
        """Checkout commit/branch without auto-committing (git-native exploration).

        Args:
            ref: Git reference (commit hash, branch, tag)
            strategy: Optional strategy for confirming destructive checkout
            force: If True, discard uncommitted changes without confirmation

        Raises:
            ValueError: If ref doesn't exist
            OSError: If git commands fail
            CDEnvironmentError: If uncommitted changes exist and no strategy/force
        """
        from ..models.exceptions import CDEnvironmentError

        # Check for uncommitted changes
        if not force:
            has_git_changes = self.git.has_uncommitted_changes()
            has_workflow_changes = self.workflow_manager.get_workflow_sync_status().has_changes

            if has_git_changes or has_workflow_changes:
                if strategy is None:
                    raise CDEnvironmentError(
                        "Cannot checkout with uncommitted changes.\n"
                        "Uncommitted changes detected:\n"
                        + ("  • Git changes in .cec/\n" if has_git_changes else "")
                        + ("  • Workflow changes in ComfyUI\n" if has_workflow_changes else "")
                    )

                if not strategy.confirm_destructive_rollback(
                    git_changes=has_git_changes,
                    workflow_changes=has_workflow_changes
                ):
                    raise CDEnvironmentError("Checkout cancelled by user")

        # Snapshot old state
        old_nodes = self.pyproject.nodes.get_existing()

        # Git checkout (restore both HEAD and working tree)
        from ..utils.git import _git
        _git(["checkout", "--force", ref], self.git.repo_path)
        if force:
            _git(["clean", "-fd"], self.git.repo_path)

        # Reload pyproject and sync environment
        self._sync_environment_after_git(old_nodes)

        logger.info(f"Checkout complete: HEAD now at {ref}")

    def reset(
        self,
        ref: str | None = None,
        mode: str = "hard",
        strategy: RollbackStrategy | None = None,
        force: bool = False
    ) -> None:
        """Reset HEAD to ref with git reset semantics.

        Modes:
        - hard: Discard all changes, move HEAD (auto-commits for history)
        - mixed: Keep changes in working tree, unstage
        - soft: Keep changes staged

        Args:
            ref: Git reference to reset to (None = HEAD)
            mode: Reset mode (hard/mixed/soft)
            strategy: Optional strategy for confirming destructive reset
            force: If True, skip confirmation

        Raises:
            ValueError: If ref doesn't exist or invalid mode
            CDEnvironmentError: If uncommitted changes exist (hard mode only)
        """
        from ..models.exceptions import CDEnvironmentError

        if mode not in ("hard", "mixed", "soft"):
            raise ValueError(f"Invalid reset mode: {mode}. Must be hard, mixed, or soft")

        ref = ref or "HEAD"

        # Hard mode requires confirmation for uncommitted changes
        if mode == "hard" and not force:
            has_git_changes = self.git.has_uncommitted_changes()
            has_workflow_changes = self.workflow_manager.get_workflow_sync_status().has_changes

            if has_git_changes or has_workflow_changes:
                if strategy is None:
                    raise CDEnvironmentError(
                        "Cannot reset with uncommitted changes.\n"
                        "Uncommitted changes detected:\n"
                        + ("  • Git changes in .cec/\n" if has_git_changes else "")
                        + ("  • Workflow changes in ComfyUI\n" if has_workflow_changes else "")
                    )

                if not strategy.confirm_destructive_rollback(
                    git_changes=has_git_changes,
                    workflow_changes=has_workflow_changes
                ):
                    raise CDEnvironmentError("Reset cancelled by user")

        # Perform git reset
        if mode == "hard":
            old_nodes = self.pyproject.nodes.get_existing()
            self.git.reset_to(ref, mode="hard")
            self._sync_environment_after_git(old_nodes)
            logger.info(f"Hard reset complete: HEAD now at {ref}")
        else:
            self.git.reset_to(ref, mode=mode)
            logger.info(f"Reset ({mode}) complete: HEAD now at {ref}")

    def create_branch(self, name: str, start_point: str = "HEAD") -> None:
        """Create new branch at start_point.

        Args:
            name: Branch name
            start_point: Commit to branch from (default: HEAD)
        """
        self.git.create_branch(name, start_point)
        logger.info(f"Created branch '{name}' at {start_point}")

    def delete_branch(self, name: str, force: bool = False) -> None:
        """Delete branch.

        Args:
            name: Branch name
            force: Force delete even if unmerged
        """
        self.git.delete_branch(name, force)
        logger.info(f"Deleted branch '{name}'")

    def switch_branch(self, branch: str, create: bool = False) -> None:
        """Switch to branch and sync environment.

        Args:
            branch: Branch name
            create: Create branch if it doesn't exist

        Raises:
            CDEnvironmentError: If uncommitted workflow changes would be overwritten
        """
        from ..models.exceptions import CDEnvironmentError

        # Check for uncommitted workflow changes
        preserve_uncommitted = False

        if not create:
            status = self.workflow_manager.get_workflow_sync_status()
            has_workflow_changes = status.has_changes

            if has_workflow_changes:
                would_overwrite = self._would_overwrite_workflows(branch, status)

                if would_overwrite:
                    raise CDEnvironmentError(
                        f"Cannot switch to branch '{branch}' with uncommitted workflow changes.\n"
                        "Your changes to the following workflows would be overwritten:\n" +
                        "\n".join(f"  • {wf}" for wf in status.new + status.modified) +
                        "\n\nPlease commit your changes or use --force to discard them:\n"
                        "  • Commit: cg commit -m '<message>'\n"
                        "  • Force: cg switch <branch> --force"
                    )
                else:
                    preserve_uncommitted = True
        else:
            preserve_uncommitted = True

        # Snapshot old state
        old_nodes = self.pyproject.nodes.get_existing()

        # Switch branch
        self.git.switch_branch(branch, create)

        # Sync environment
        self._sync_environment_after_git(old_nodes, preserve_uncommitted=preserve_uncommitted)

        logger.info(f"Switched to branch '{branch}'")

    def merge_branch(self, branch: str, message: str | None = None) -> None:
        """Merge branch into current branch and sync environment.

        Args:
            branch: Branch to merge
            message: Custom merge commit message
        """
        old_nodes = self.pyproject.nodes.get_existing()
        self.git.merge_branch(branch, message)
        self._sync_environment_after_git(old_nodes)
        logger.info(f"Merged branch '{branch}'")

    def revert_commit(self, commit: str) -> None:
        """Revert a commit by creating new commit that undoes it.

        Args:
            commit: Commit hash to revert
        """
        old_nodes = self.pyproject.nodes.get_existing()
        self.git.revert_commit(commit)
        self._sync_environment_after_git(old_nodes)
        logger.info(f"Reverted commit {commit}")

    def _sync_environment_after_git(
        self,
        old_nodes: dict,
        preserve_uncommitted: bool = False
    ) -> None:
        """Sync environment state after git operation.

        Args:
            old_nodes: Node state before git operation
            preserve_uncommitted: Whether to preserve uncommitted workflows
        """
        # Reload pyproject
        self.pyproject.reset_lazy_handlers()

        # Override PyTorch config with what's actually installed
        self._override_pytorch_config_from_installed()

        new_nodes = self.pyproject.nodes.get_existing()

        # Reconcile nodes
        self.node_manager.reconcile_nodes_for_rollback(old_nodes, new_nodes)

        # Sync Python environment
        self.uv.sync_project(all_groups=True)

        # Restore workflows
        self.workflow_manager.restore_all_from_cec(preserve_uncommitted=preserve_uncommitted)

    def _override_pytorch_config_from_installed(self) -> None:
        """Override pyproject.toml with currently installed PyTorch config.

        This method:
        1. Detects PyTorch installed in the venv
        2. Checks if config already matches installed version
        3. Only modifies file if changes are needed

        Called after every git operation to ensure pyproject.toml
        matches what's actually installed.
        """
        from ..constants import PYTORCH_CORE_PACKAGES
        from ..utils.pytorch import get_installed_pytorch_info, get_pytorch_index_url

        # Detect installed PyTorch
        pytorch_info = get_installed_pytorch_info(
            self.uv, self.uv.python_executable
        )

        if "torch" not in pytorch_info:
            logger.debug("No PyTorch installed in venv, skipping config override")
            return

        backend = pytorch_info["backend"]

        # Check if current config already matches installed PyTorch
        if self._pytorch_config_matches_installed(pytorch_info, backend):
            logger.debug(f"PyTorch config already matches installed backend: {backend}")
            return

        logger.info(f"Overriding PyTorch config with installed backend: {backend}")

        # Strip existing PyTorch configuration and save
        config = self.pyproject.load()

        if "tool" in config and "uv" in config["tool"]:
            # Remove PyTorch indexes
            indexes = config["tool"]["uv"].get("index", [])
            if isinstance(indexes, list):
                config["tool"]["uv"]["index"] = [
                    idx for idx in indexes
                    if not any(p in idx.get("name", "").lower() for p in ["pytorch-", "torch-"])
                ]

            # Remove PyTorch sources
            sources = config.get("tool", {}).get("uv", {}).get("sources", {})
            for pkg in PYTORCH_CORE_PACKAGES:
                sources.pop(pkg, None)

            # Remove PyTorch constraints
            constraints = config["tool"]["uv"].get("constraint-dependencies", [])
            if isinstance(constraints, list):
                config["tool"]["uv"]["constraint-dependencies"] = [
                    c for c in constraints
                    if not any(pkg in c for pkg in PYTORCH_CORE_PACKAGES)
                ]

        # Save stripped config
        self.pyproject.save(config)

        # Add new config (these methods load/save internally)
        if backend != "cpu":
            index_name = f"pytorch-{backend}"
            self.pyproject.uv_config.add_index(
                name=index_name,
                url=get_pytorch_index_url(backend),
                explicit=True
            )

            # Add sources pointing to new index
            for pkg in PYTORCH_CORE_PACKAGES:
                self.pyproject.uv_config.add_source(pkg, {"index": index_name})

        # Add constraints for installed versions
        for pkg in PYTORCH_CORE_PACKAGES:
            if pkg in pytorch_info:
                self.pyproject.uv_config.add_constraint(f"{pkg}=={pytorch_info[pkg]}")

        logger.debug("PyTorch config override complete")

    def _pytorch_config_matches_installed(self, pytorch_info: dict, backend: str) -> bool:
        """Check if current pyproject.toml matches installed PyTorch.

        Args:
            pytorch_info: Dict with torch/torchvision/torchaudio versions and backend
            backend: Detected backend (e.g., 'cu128', 'cpu')

        Returns:
            True if config matches installed versions, False otherwise
        """
        from ..constants import PYTORCH_CORE_PACKAGES

        config = self.pyproject.load()
        uv_config = config.get("tool", {}).get("uv", {})

        # Check constraints match installed versions
        constraints = uv_config.get("constraint-dependencies", [])
        for pkg in PYTORCH_CORE_PACKAGES:
            if pkg not in pytorch_info:
                continue
            expected = f"{pkg}=={pytorch_info[pkg]}"
            if expected not in constraints:
                return False

        # Check index exists for non-cpu backends
        if backend != "cpu":
            expected_index_name = f"pytorch-{backend}"
            indexes = uv_config.get("index", [])
            if not isinstance(indexes, list):
                indexes = [indexes] if indexes else []

            has_index = any(
                idx.get("name") == expected_index_name
                for idx in indexes
            )
            if not has_index:
                return False

            # Check sources point to correct index
            sources = uv_config.get("sources", {})
            for pkg in PYTORCH_CORE_PACKAGES:
                pkg_source = sources.get(pkg, {})
                if pkg_source.get("index") != expected_index_name:
                    return False

        return True

    def _would_overwrite_workflows(self, target_branch: str, status) -> bool:
        """Check if switching to target branch would overwrite uncommitted workflows.

        Args:
            target_branch: Branch name to check
            status: Current workflow sync status

        Returns:
            True if any uncommitted workflow exists in target branch's .cec
        """
        from ..utils.git import _git

        uncommitted = set(status.new + status.modified)
        if not uncommitted:
            return False

        try:
            result = _git(
                ["ls-tree", "-r", "--name-only", target_branch, "workflows/"],
                self.git.repo_path,
                capture_output=True
            )

            target_workflows = set()
            for line in result.stdout.strip().split('\n'):
                if line.startswith('workflows/') and line.endswith('.json'):
                    name = line[len('workflows/'):-len('.json')]
                    target_workflows.add(name)

            conflicts = uncommitted & target_workflows
            if conflicts:
                logger.debug(f"Conflicting workflows detected: {conflicts}")
                return True

            return False

        except Exception as e:
            logger.warning(f"Could not check target branch workflows: {e}")
            return True
