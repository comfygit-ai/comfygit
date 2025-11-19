"""Simplified Environment - owns everything about a single ComfyUI environment."""
from __future__ import annotations

import shutil
import subprocess
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

from ..analyzers.status_scanner import StatusScanner
from ..factories.uv_factory import create_uv_for_environment
from ..logging.logging_config import get_logger
from ..managers.environment_git_orchestrator import EnvironmentGitOrchestrator
from ..managers.environment_model_manager import EnvironmentModelManager
from ..managers.git_manager import GitManager
from ..managers.model_symlink_manager import ModelSymlinkManager
from ..managers.node_manager import NodeManager
from ..managers.pyproject_manager import PyprojectManager
from ..managers.user_content_symlink_manager import UserContentSymlinkManager
from ..managers.uv_project_manager import UVProjectManager
from ..managers.workflow_manager import WorkflowManager
from ..models.environment import EnvironmentStatus
from ..models.shared import (
    ModelSourceResult,
    ModelSourceStatus,
    NodeInfo,
    NodeRemovalResult,
    UpdateResult,
)
from ..models.sync import SyncResult
from ..strategies.confirmation import ConfirmationStrategy
from ..utils.common import run_command
from ..utils.pytorch import extract_pip_show_package_version
from ..validation.resolution_tester import ResolutionTester

if TYPE_CHECKING:
    from comfygit_core.core.workspace import Workspace
    from comfygit_core.models.protocols import (
        ExportCallbacks,
        ImportCallbacks,
        ModelResolutionStrategy,
        NodeResolutionStrategy,
        RollbackStrategy,
        SyncCallbacks,
    )

    from ..caching.workflow_cache import WorkflowCacheRepository
    from ..models.workflow import (
        BatchDownloadCallbacks,
        DetailedWorkflowStatus,
        NodeInstallCallbacks,
        ResolutionResult,
        WorkflowSyncStatus,
    )
    from ..services.node_lookup_service import NodeLookupService

logger = get_logger(__name__)


class Environment:
    """A ComfyUI environment - manages its own state through pyproject.toml."""

    def __init__(
        self,
        name: str,
        path: Path,
        workspace: Workspace,
        torch_backend: str | None = None,
    ):
        self.name = name
        self.path = path
        self.workspace = workspace
        self.torch_backend = torch_backend

        # Workspace-level paths
        self.workspace_paths = workspace.paths
        self.global_models_path = workspace.workspace_config_manager.get_models_directory()

        # Workspace-level services
        self.model_repository = workspace.model_repository
        self.node_mapping_repository = workspace.node_mapping_repository
        self.workspace_config_manager = workspace.workspace_config_manager
        self.model_downloader = workspace.model_downloader

        # Core paths
        self.cec_path = path / ".cec"
        self.pyproject_path = self.cec_path / "pyproject.toml"
        self.comfyui_path = path / "ComfyUI"
        self.custom_nodes_path = self.comfyui_path / "custom_nodes"
        self.venv_path = path / ".venv"
        self.models_path = self.comfyui_path / "models"

    ## Cached properties ##
    #
    # Orchestrators coordinate git and model operations with environment state:
    # - git_orchestrator: Wraps git operations with node reconciliation + package sync + workflow restore
    # - model_manager: Coordinates model operations across pyproject, repository, and downloader
    #
    # This pattern keeps environment.py thin by delegating complex multi-step operations.

    @cached_property
    def uv_manager(self) -> UVProjectManager:
        return create_uv_for_environment(
            self.workspace_paths.root,
            cec_path=self.cec_path,
            venv_path=self.venv_path,
            torch_backend=self.torch_backend,
        )

    @cached_property
    def pyproject(self) -> PyprojectManager:
        return PyprojectManager(self.pyproject_path)

    @cached_property
    def node_lookup(self) -> NodeLookupService:
        from ..services.node_lookup_service import NodeLookupService
        return NodeLookupService(
            cache_path=self.workspace_paths.cache,
            node_mappings_repository=self.node_mapping_repository,
            workspace_config_repository=self.workspace_config_manager,
        )

    @cached_property
    def resolution_tester(self) -> ResolutionTester:
        return ResolutionTester(self.workspace_paths.root)

    @cached_property
    def node_manager(self) -> NodeManager:
        return NodeManager(
            self.pyproject,
            self.uv_manager,
            self.node_lookup,
            self.resolution_tester,
            self.custom_nodes_path,
            self.node_mapping_repository
        )

    @cached_property
    def model_symlink_manager(self) -> ModelSymlinkManager:
        """Get model symlink manager."""
        return ModelSymlinkManager(
            self.comfyui_path, self.global_models_path
        )

    @cached_property
    def user_content_manager(self) -> UserContentSymlinkManager:
        """Get user content symlink manager for input/output directories."""
        return UserContentSymlinkManager(
            self.comfyui_path,
            self.name,
            self.workspace_paths.input,
            self.workspace_paths.output,
        )

    @cached_property
    def workflow_cache(self) -> WorkflowCacheRepository:
        """Get workflow cache repository."""
        from ..caching.workflow_cache import WorkflowCacheRepository
        cache_db_path = self.workspace_paths.cache / "workflows.db"
        return WorkflowCacheRepository(
            cache_db_path,
            pyproject_manager=self.pyproject,
            model_repository=self.model_repository,
            workspace_config_manager=self.workspace_config_manager
        )

    @cached_property
    def workflow_manager(self) -> WorkflowManager:
        return WorkflowManager(
            self.comfyui_path,
            self.cec_path,
            self.pyproject,
            self.model_repository,
            self.node_mapping_repository,
            self.model_downloader,
            self.workflow_cache,
            self.name
        )

    @cached_property
    def git_manager(self) -> GitManager:
        return GitManager(self.cec_path)

    @cached_property
    def git_orchestrator(self) -> EnvironmentGitOrchestrator:
        """Get environment-aware git orchestrator."""
        return EnvironmentGitOrchestrator(
            git_manager=self.git_manager,
            node_manager=self.node_manager,
            pyproject_manager=self.pyproject,
            uv_manager=self.uv_manager,
            workflow_manager=self.workflow_manager,
        )

    @cached_property
    def model_manager(self) -> EnvironmentModelManager:
        """Get environment model manager."""
        return EnvironmentModelManager(
            pyproject=self.pyproject,
            model_repository=self.model_repository,
            model_downloader=self.model_downloader,
        )

    ## Helper methods ##

    ## Public methods ##

    # =====================================================
    # Environment Management
    # =====================================================

    def status(self) -> EnvironmentStatus:
        """Get environment sync and git status."""
        # Each subsystem provides its complete status
        scanner = StatusScanner(
            comfyui_path=self.comfyui_path,
            venv_path=self.venv_path,
            uv=self.uv_manager,
            pyproject=self.pyproject
        )
        comparison = scanner.get_full_comparison()

        git_status = self.git_manager.get_status(self.pyproject)

        workflow_status = self.workflow_manager.get_workflow_status()

        # Detect missing models
        missing_models = self.model_manager.detect_missing_models()

        # Assemble final status
        return EnvironmentStatus.create(
            comparison=comparison,
            git_status=git_status,
            workflow_status=workflow_status,
            missing_models=missing_models
        )

    def sync(
        self,
        dry_run: bool = False,
        model_strategy: str = "skip",
        model_callbacks: BatchDownloadCallbacks | None = None,
        node_callbacks: NodeInstallCallbacks | None = None,
        remove_extra_nodes: bool = True,
        sync_callbacks: SyncCallbacks | None = None,
        verbose: bool = False
    ) -> SyncResult:
        """Apply changes: sync packages, nodes, workflows, and models with environment.

        Args:
            dry_run: If True, don't actually apply changes
            model_strategy: Model download strategy - "all", "required", or "skip" (default: skip)
            model_callbacks: Optional callbacks for model download progress
            node_callbacks: Optional callbacks for node installation progress
            remove_extra_nodes: If True, remove extra nodes. If False, only warn (default: True)
            verbose: If True, show uv output in real-time during dependency installation

        Returns:
            SyncResult with details of what was synced

        Raises:
            UVCommandError: If sync fails
        """
        result = SyncResult()

        logger.info("Syncing environment...")

        # Sync packages with UV - progressive installation
        try:
            sync_result = self.uv_manager.sync_dependencies_progressive(
                dry_run=dry_run,
                callbacks=sync_callbacks,
                verbose=verbose
            )
            result.packages_synced = sync_result["packages_synced"]
            result.dependency_groups_installed.extend(sync_result["dependency_groups_installed"])
            result.dependency_groups_failed.extend(sync_result["dependency_groups_failed"])
        except Exception as e:
            # Progressive sync handles optional groups gracefully
            # Only base or required groups cause this exception
            logger.error(f"Package sync failed: {e}")
            result.errors.append(f"Package sync failed: {e}")
            result.success = False

        # Sync custom nodes to filesystem
        try:
            # Pass remove_extra flag (default True for aggressive repair behavior)
            self.node_manager.sync_nodes_to_filesystem(
                remove_extra=remove_extra_nodes and not dry_run,
                callbacks=node_callbacks
            )
            # For now, we just note it happened
        except Exception as e:
            logger.error(f"Node sync failed: {e}")
            result.errors.append(f"Node sync failed: {e}")
            result.success = False

        # Restore workflows from .cec/ to ComfyUI (for git pull workflow)
        if not dry_run:
            try:
                self.workflow_manager.restore_all_from_cec()
                logger.info("Restored workflows from .cec/")
            except Exception as e:
                logger.warning(f"Failed to restore workflows: {e}")
                result.errors.append(f"Workflow restore failed: {e}")
                # Non-fatal - continue

        # Handle missing models
        if not dry_run and model_strategy != "skip":
            try:
                # Reuse existing import machinery
                workflows_with_intents = self.model_manager.prepare_import_with_model_strategy(
                    strategy=model_strategy
                )

                if workflows_with_intents:
                    logger.info(f"Downloading models for {len(workflows_with_intents)} workflow(s)")

                    # Resolve each workflow (triggers downloads)
                    from ..strategies.auto import AutoModelStrategy, AutoNodeStrategy

                    for workflow_name in workflows_with_intents:
                        try:
                            logger.debug(f"Resolving workflow: {workflow_name}")

                            # Resolve workflow (analyzes and prepares downloads)
                            resolution_result = self.resolve_workflow(
                                name=workflow_name,
                                model_strategy=AutoModelStrategy(),
                                node_strategy=AutoNodeStrategy(),
                                download_callbacks=model_callbacks
                            )

                            # Track downloads from actual download results (not stale ResolvedModel objects)
                            # Note: Download results are populated by _execute_pending_downloads() during resolve_workflow()
                            for dr in resolution_result.download_results:
                                if dr.success:
                                    result.models_downloaded.append(dr.filename)
                                else:
                                    result.models_failed.append((dr.filename, dr.error or "Download failed"))

                        except Exception as e:
                            logger.error(f"Failed to resolve {workflow_name}: {e}", exc_info=True)
                            result.errors.append(f"Failed to resolve {workflow_name}: {e}")

            except Exception as e:
                logger.warning(f"Model download failed: {e}", exc_info=True)
                result.errors.append(f"Model download failed: {e}")
                # Non-fatal - continue

        # Ensure model symlink exists
        try:
            self.model_symlink_manager.create_symlink()
            result.model_paths_configured = True
        except Exception as e:
            logger.warning(f"Failed to ensure model symlink: {e}")
            result.errors.append(f"Model symlink configuration failed: {e}")
            # Continue anyway - symlink might already exist from environment creation

        # Auto-migrate existing environments (one-time operation)
        # Check if input/output are real directories with content
        needs_migration = False
        if self.comfyui_path.exists():
            from ..utils.symlink_utils import is_link

            input_path = self.comfyui_path / "input"
            output_path = self.comfyui_path / "output"

            if input_path.exists() and not is_link(input_path):
                needs_migration = True
            if output_path.exists() and not is_link(output_path):
                needs_migration = True

        if needs_migration:
            logger.info("Detected pre-symlink environment, migrating user data...")
            try:
                migration_stats = self.user_content_manager.migrate_existing_data()
                total_moved = (
                    migration_stats["input_files_moved"] +
                    migration_stats["output_files_moved"]
                )
                if total_moved > 0:
                    logger.info(
                        f"Migration complete: {total_moved} files moved to workspace-level storage"
                    )
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                result.errors.append(f"User data migration failed: {e}")
                # Don't fail sync - user can migrate manually

        # Ensure user content symlinks exist
        try:
            self.user_content_manager.create_directories()
            self.user_content_manager.create_symlinks()
            logger.debug("User content symlinks configured")
        except Exception as e:
            logger.warning(f"Failed to ensure user content symlinks: {e}")
            result.errors.append(f"User content symlink configuration failed: {e}")
            # Continue anyway - symlinks might already exist

        # Mark environment as complete after successful sync (repair operation)
        # This ensures environments that lost .complete (e.g., from manual git pull) are visible
        if result.success and not dry_run:
            from ..utils.environment_cleanup import mark_environment_complete
            mark_environment_complete(self.cec_path)
            logger.debug("Marked environment as complete")

        if result.success:
            logger.info("Successfully synced environment")
        else:
            logger.warning(f"Sync completed with {len(result.errors)} errors")

        return result

    def pull_and_repair(
        self,
        remote: str = "origin",
        branch: str | None = None,
        model_strategy: str = "all",
        model_callbacks: BatchDownloadCallbacks | None = None,
        node_callbacks: NodeInstallCallbacks | None = None,
    ) -> dict:
        """Pull from remote and auto-repair environment (atomic operation).

        If sync fails, git changes are rolled back automatically.
        This ensures the environment is never left in a half-pulled state.

        Args:
            remote: Remote name (default: origin)
            branch: Branch to pull (default: current)
            model_strategy: Model download strategy ("all", "required", "skip")
            model_callbacks: Optional callbacks for model download progress
            node_callbacks: Optional callbacks for node installation progress

        Returns:
            Dict with pull results and sync_result

        Raises:
            CDEnvironmentError: If uncommitted changes exist or sync fails
            ValueError: If merge conflicts
            OSError: If pull or repair fails
        """
        from ..models.exceptions import CDEnvironmentError
        from ..utils.git import git_reset_hard, git_rev_parse

        # Check for uncommitted changes
        if self.git_manager.has_uncommitted_changes():
            raise CDEnvironmentError(
                "Cannot pull with uncommitted changes.\n"
                "  • Commit: comfygit commit -m 'message'\n"
                "  • Discard: comfygit reset --hard"
            )

        # Capture pre-pull state for atomic rollback
        pre_pull_commit = git_rev_parse(self.cec_path, "HEAD")
        if not pre_pull_commit:
            raise CDEnvironmentError(
                "Cannot determine current commit state.\n"
                "The .cec repository may be corrupted. Try:\n"
                "  • Check git status: cd .cec && git status\n"
                "  • Repair repository: cd .cec && git fsck"
            )

        try:
            # Pull (fetch + merge)
            logger.info("Pulling from remote...")
            pull_result = self.git_manager.pull(remote, branch)

            # Auto-repair (restores workflows, installs nodes, downloads models)
            logger.info("Syncing environment after pull...")
            sync_result = self.sync(
                model_strategy=model_strategy,
                model_callbacks=model_callbacks,
                node_callbacks=node_callbacks
            )

            # Check for sync failures
            if not sync_result.success:
                logger.error("Sync failed - rolling back git changes")
                git_reset_hard(self.cec_path, pre_pull_commit)
                raise CDEnvironmentError(
                    "Sync failed after pull. Git changes rolled back.\n"
                    f"Errors: {', '.join(sync_result.errors)}"
                )

            # Return both pull result and sync result for CLI to display
            return {
                **pull_result,
                'sync_result': sync_result
            }

        except Exception as e:
            # Any failure during sync - rollback git changes
            # (merge conflicts raise before this point, so don't rollback those)
            if "Merge conflict" not in str(e):
                logger.error(f"Pull failed: {e} - rolling back git changes")
                git_reset_hard(self.cec_path, pre_pull_commit)
            raise

    def push_commits(self, remote: str = "origin", branch: str | None = None, force: bool = False) -> str:
        """Push commits to remote (requires clean working directory).

        Args:
            remote: Remote name (default: origin)
            branch: Branch to push (default: current)
            force: Use --force-with-lease for force push (default: False)

        Returns:
            Push output

        Raises:
            CDEnvironmentError: If uncommitted changes exist
            ValueError: If no remote or detached HEAD
            OSError: If push fails
        """
        from ..models.exceptions import CDEnvironmentError

        # Check for uncommitted git changes (not workflow sync state)
        # Push only cares about git state in .cec/, not whether workflows are synced to ComfyUI
        if self.git_manager.has_uncommitted_changes():
            raise CDEnvironmentError(
                "Cannot push with uncommitted changes.\n"
                "  Run: comfygit commit -m 'message' first"
            )

        # Note: Workflow issue validation happens during commit (execute_commit checks is_commit_safe).
        # By the time we reach push, all committed changes have already been validated.
        # No need to re-check workflow issues here.

        # Push
        logger.info("Pushing commits to remote...")
        return self.git_manager.push(remote, branch, force=force)

    def checkout(
        self,
        ref: str,
        strategy: RollbackStrategy | None = None,
        force: bool = False
    ) -> None:
        """Checkout commit/branch without auto-committing.

        Args:
            ref: Git reference (commit hash, branch, tag)
            strategy: Optional strategy for confirming destructive checkout
            force: If True, discard uncommitted changes without confirmation

        Raises:
            ValueError: If ref doesn't exist
            CDEnvironmentError: If uncommitted changes exist and no strategy/force
        """
        self.git_orchestrator.checkout(ref, strategy, force)

    def reset(
        self,
        ref: str | None = None,
        mode: str = "hard",
        strategy: RollbackStrategy | None = None,
        force: bool = False
    ) -> None:
        """Reset HEAD to ref with git reset semantics.

        Args:
            ref: Git reference to reset to (None = HEAD)
            mode: Reset mode (hard/mixed/soft)
            strategy: Optional strategy for confirming destructive reset
            force: If True, skip confirmation

        Raises:
            ValueError: If ref doesn't exist or invalid mode
            CDEnvironmentError: If uncommitted changes exist (hard mode only)
        """
        self.git_orchestrator.reset(ref, mode, strategy, force)

    def create_branch(self, name: str, start_point: str = "HEAD") -> None:
        """Create new branch at start_point.

        Args:
            name: Branch name
            start_point: Commit to branch from (default: HEAD)
        """
        self.git_orchestrator.create_branch(name, start_point)

    def delete_branch(self, name: str, force: bool = False) -> None:
        """Delete branch.

        Args:
            name: Branch name
            force: Force delete even if unmerged
        """
        self.git_orchestrator.delete_branch(name, force)

    def switch_branch(self, branch: str, create: bool = False) -> None:
        """Switch to branch and sync environment.

        Args:
            branch: Branch name
            create: Create branch if it doesn't exist

        Raises:
            CDEnvironmentError: If uncommitted workflow changes would be overwritten
        """
        self.git_orchestrator.switch_branch(branch, create)

    def list_branches(self) -> list[tuple[str, bool]]:
        """List all branches with current branch marked.

        Returns:
            List of (branch_name, is_current) tuples
        """
        return self.git_manager.list_branches()

    def get_current_branch(self) -> str | None:
        """Get current branch name.

        Returns:
            Branch name or None if detached HEAD
        """
        return self.git_manager.get_current_branch()

    def merge_branch(self, branch: str, message: str | None = None) -> None:
        """Merge branch into current branch and sync environment.

        Args:
            branch: Branch to merge
            message: Custom merge commit message
        """
        self.git_orchestrator.merge_branch(branch, message)

    def revert_commit(self, commit: str) -> None:
        """Revert a commit by creating new commit that undoes it.

        Args:
            commit: Commit hash to revert
        """
        self.git_orchestrator.revert_commit(commit)

    def get_commit_history(self, limit: int = 10) -> list[dict]:
        """Get commit history for this environment.

        Args:
            limit: Maximum number of commits to return

        Returns:
            List of commit dicts with keys: hash, message, date, date_relative
        """
        return self.git_manager.get_version_history(limit)

    def sync_model_paths(self) -> dict | None:
        """Ensure model symlink is configured for this environment.

        Returns:
            Status dictionary
        """
        logger.info(f"Configuring model symlink for environment '{self.name}'")
        try:
            self.model_symlink_manager.create_symlink()
            return {
                "status": "linked",
                "target": str(self.global_models_path),
                "link": str(self.models_path)
            }
        except Exception as e:
            logger.error(f"Failed to configure model symlink: {e}")
            raise

    # TODO wrap subprocess completed process instance
    def run(self, args: list[str] | None = None) -> subprocess.CompletedProcess:
        """Run ComfyUI in this environment.

        Args:
            args: Arguments to pass to ComfyUI

        Returns:
            CompletedProcess
        """
        python = self.uv_manager.python_executable
        cmd = [str(python), "main.py"] + (args or [])

        logger.info(f"Starting ComfyUI with: {' '.join(cmd)}")
        return run_command(cmd, cwd=self.comfyui_path, capture_output=False, timeout=None)

    # =====================================================
    # Node Management
    # =====================================================

    def list_nodes(self) -> list[NodeInfo]:
        """List all custom nodes in this environment.

        Returns:
            List of NodeInfo objects for all installed custom nodes
        """
        nodes_dict = self.pyproject.nodes.get_existing()
        return list(nodes_dict.values())

    def add_node(
        self,
        identifier: str,
        is_development: bool = False,
        no_test: bool = False,
        force: bool = False,
        confirmation_strategy: ConfirmationStrategy | None = None
    ) -> NodeInfo:
        """Add a custom node to the environment.

        Args:
            identifier: Registry ID or GitHub URL (supports @version)
            is_development: Track as development node
            no_test: Skip dependency resolution testing
            force: Force replacement of existing nodes
            confirmation_strategy: Strategy for confirming replacements

        Raises:
            CDNodeNotFoundError: If node not found
            CDNodeConflictError: If node has dependency conflicts
            CDEnvironmentError: If node with same name already exists
        """
        return self.node_manager.add_node(identifier, is_development, no_test, force, confirmation_strategy)

    def install_nodes_with_progress(
        self,
        node_ids: list[str],
        callbacks: NodeInstallCallbacks | None = None
    ) -> tuple[int, list[tuple[str, str]]]:
        """Install multiple nodes with callback support for progress tracking.

        Args:
            node_ids: List of node identifiers to install
            callbacks: Optional callbacks for progress feedback

        Returns:
            Tuple of (success_count, failed_nodes)
            where failed_nodes is a list of (node_id, error_message) tuples

        Raises:
            CDNodeNotFoundError: If a node is not found
        """
        if callbacks and callbacks.on_batch_start:
            callbacks.on_batch_start(len(node_ids))

        success_count = 0
        failed = []

        for idx, node_id in enumerate(node_ids):
            if callbacks and callbacks.on_node_start:
                callbacks.on_node_start(node_id, idx + 1, len(node_ids))

            try:
                self.add_node(node_id)
                success_count += 1
                if callbacks and callbacks.on_node_complete:
                    callbacks.on_node_complete(node_id, True, None)
            except Exception as e:
                failed.append((node_id, str(e)))
                if callbacks and callbacks.on_node_complete:
                    callbacks.on_node_complete(node_id, False, str(e))

        if callbacks and callbacks.on_batch_complete:
            callbacks.on_batch_complete(success_count, len(node_ids))

        return success_count, failed

    def remove_node(self, identifier: str, untrack_only: bool = False) -> NodeRemovalResult:
        """Remove a custom node.

        Args:
            identifier: Node identifier or name
            untrack_only: If True, only remove from pyproject.toml without touching filesystem

        Returns:
            NodeRemovalResult: Details about the removal

        Raises:
            CDNodeNotFoundError: If node not found
        """
        return self.node_manager.remove_node(identifier, untrack_only=untrack_only)

    def remove_nodes_with_progress(
        self,
        node_ids: list[str],
        callbacks: NodeInstallCallbacks | None = None
    ) -> tuple[int, list[tuple[str, str]]]:
        """Remove multiple nodes with callback support for progress tracking.

        Args:
            node_ids: List of node identifiers to remove
            callbacks: Optional callbacks for progress feedback

        Returns:
            Tuple of (success_count, failed_nodes)
            where failed_nodes is a list of (node_id, error_message) tuples

        Raises:
            CDNodeNotFoundError: If a node is not found
        """
        if callbacks and callbacks.on_batch_start:
            callbacks.on_batch_start(len(node_ids))

        success_count = 0
        failed = []

        for idx, node_id in enumerate(node_ids):
            if callbacks and callbacks.on_node_start:
                callbacks.on_node_start(node_id, idx + 1, len(node_ids))

            try:
                self.remove_node(node_id)
                success_count += 1
                if callbacks and callbacks.on_node_complete:
                    callbacks.on_node_complete(node_id, True, None)
            except Exception as e:
                failed.append((node_id, str(e)))
                if callbacks and callbacks.on_node_complete:
                    callbacks.on_node_complete(node_id, False, str(e))

        if callbacks and callbacks.on_batch_complete:
            callbacks.on_batch_complete(success_count, len(node_ids))

        return success_count, failed

    def update_node(
        self,
        identifier: str,
        confirmation_strategy: ConfirmationStrategy | None = None,
        no_test: bool = False
    ) -> UpdateResult:
        """Update a node based on its source type.

        - Development nodes: Re-scan requirements.txt
        - Registry nodes: Update to latest version
        - Git nodes: Update to latest commit

        Args:
            identifier: Node identifier or name
            confirmation_strategy: Strategy for confirming updates (None = auto-confirm)
            no_test: Skip resolution testing

        Raises:
            CDNodeNotFoundError: If node not found
            CDEnvironmentError: If node cannot be updated
        """
        return self.node_manager.update_node(identifier, confirmation_strategy, no_test)

    def check_development_node_drift(self) -> dict[str, tuple[set[str], set[str]]]:
        """Check if development nodes have requirements drift.

        Returns:
            Dict mapping node_name -> (added_deps, removed_deps)
        """
        return self.node_manager.check_development_node_drift()

    # =====================================================
    # Workflow Management
    # =====================================================

    def list_workflows(self) -> WorkflowSyncStatus:
        """List all workflows categorized by sync status.

        Returns:
            Dict with 'new', 'modified', 'deleted', and 'synced' workflow names
        """
        return self.workflow_manager.get_workflow_sync_status()

    def resolve_workflow(
        self,
        name: str,
        node_strategy: NodeResolutionStrategy | None = None,
        model_strategy: ModelResolutionStrategy | None = None,
        fix: bool = True,
        download_callbacks: BatchDownloadCallbacks | None = None
    ) -> ResolutionResult:
        """Resolve workflow dependencies - orchestrates analysis and resolution.

        Args:
            name: Workflow name to resolve
            node_strategy: Strategy for resolving missing nodes
            model_strategy: Strategy for resolving ambiguous/missing models
            fix: Attempt to fix unresolved issues with strategies
            download_callbacks: Optional callbacks for batch download progress (CLI provides)

        Returns:
            ResolutionResult with changes made

        Raises:
            FileNotFoundError: If workflow not found
        """
        # Analyze and resolve workflow (both cached for performance)
        _, result = self.workflow_manager.analyze_and_resolve_workflow(name)

        # Apply auto-resolutions (reconcile with pyproject.toml)
        self.workflow_manager.apply_resolution(result)

        # Check if there are any unresolved issues
        if result.has_issues and fix:
            # Fix issues with strategies (progressive writes: models AND nodes saved immediately)
            result = self.workflow_manager.fix_resolution(
                result,
                node_strategy,
                model_strategy
            )

        # Execute pending downloads if any download intents exist
        if result.has_download_intents:
            result.download_results = self.workflow_manager.execute_pending_downloads(result, download_callbacks)

            # After successful downloads, update workflow JSON with resolved paths
            # Re-resolve to get fresh model data (cached, so minimal cost)
            if result.download_results and any(dr.success for dr in result.download_results):
                _, fresh_result = self.workflow_manager.analyze_and_resolve_workflow(name)
                self.workflow_manager.update_workflow_model_paths(fresh_result)

        return result

    def get_uninstalled_nodes(self, workflow_name: str | None = None) -> list[str]:
        """Get list of node package IDs referenced in workflows but not installed.

        Compares nodes referenced in workflow sections against installed nodes
        to identify which nodes need installation.

        Returns:
            List of node package IDs that are referenced in workflows but not installed.
            Empty list if all workflow nodes are already installed.

        Example:
            >>> env.resolve_workflow("my_workflow")
            >>> missing = env.get_uninstalled_nodes()
            >>> # ['rgthree-comfy', 'comfyui-depthanythingv2', ...]
        """
        # Get all node IDs referenced in workflows
        workflow_node_ids = set()
        if workflow_name:
            if workflow := self.pyproject.workflows.get_workflow(workflow_name):
                workflows = {workflow_name: workflow}
            else:
                logger.warning(f"Workflow '{workflow_name}' not found")
                return []
        else:
            workflows = self.pyproject.workflows.get_all_with_resolutions()

        for workflow_data in workflows.values():
            node_list = workflow_data.get('nodes', [])
            workflow_node_ids.update(node_list)

        logger.debug(f"Workflow node references: {workflow_node_ids}")

        # Get installed node IDs
        installed_nodes = self.pyproject.nodes.get_existing()
        installed_node_ids = set(installed_nodes.keys())
        logger.debug(f"Installed nodes: {installed_node_ids}")

        # Find nodes referenced in workflows but not installed
        uninstalled_ids = list(workflow_node_ids - installed_node_ids)
        logger.debug(f"Uninstalled nodes: {uninstalled_ids}")

        return uninstalled_ids

    def get_unused_nodes(self, exclude: list[str] | None = None) -> list[NodeInfo]:
        """Get installed nodes not referenced by any workflow.

        Uses the same auto-resolution flow as status command to ensure we capture
        all nodes actually needed by workflows, including those from custom_node_map.

        Args:
            exclude: Optional list of package IDs to exclude from pruning

        Returns:
            List of NodeInfo for unused nodes that can be safely removed

        Example:
            >>> unused = env.get_unused_nodes()
            >>> # [NodeInfo(registry_id='old-node'), ...]
            >>> # Or with exclusions:
            >>> unused = env.get_unused_nodes(exclude=['keep-this-node'])
        """
        # Get workflow status (triggers auto-resolution with caching)
        workflow_status = self.workflow_manager.get_workflow_status()

        # Aggregate packages from all workflows
        all_needed_packages = set()
        for workflow_analysis in workflow_status.analyzed_workflows:
            for resolved_node in workflow_analysis.resolution.nodes_resolved:
                # Only count non-optional nodes with actual package IDs
                if resolved_node.package_id and not resolved_node.is_optional:
                    all_needed_packages.add(resolved_node.package_id)

        logger.debug(f"Packages needed by workflows: {all_needed_packages}")

        # Get installed nodes
        installed_nodes = self.pyproject.nodes.get_existing()
        installed_node_ids = set(installed_nodes.keys())
        logger.debug(f"Installed nodes: {installed_node_ids}")

        # Calculate unused = installed - needed
        unused_ids = installed_node_ids - all_needed_packages

        # Apply exclusions
        if exclude:
            unused_ids -= set(exclude)
            logger.debug(f"After exclusions: {unused_ids}")

        return [installed_nodes[nid] for nid in unused_ids]

    def prune_unused_nodes(
        self,
        exclude: list[str] | None = None,
        callbacks: NodeInstallCallbacks | None = None
    ) -> tuple[int, list[tuple[str, str]]]:
        """Remove unused nodes from environment.

        Args:
            exclude: Package IDs to keep even if unused
            callbacks: Progress callbacks

        Returns:
            Tuple of (success_count, failed_removals)
        """
        unused = self.get_unused_nodes(exclude=exclude)

        if not unused:
            return (0, [])

        # Use existing batch removal
        node_ids = [node.registry_id or node.name for node in unused]
        return self.remove_nodes_with_progress(node_ids, callbacks)

    def has_committable_changes(self) -> bool:
        """Check if there are any committable changes (workflows OR git).

        This is the clean API for determining if a commit is possible.
        Checks both workflow file sync status AND git uncommitted changes.

        Returns:
            True if there are committable changes, False otherwise
        """
        # Check workflow file changes (new/modified/deleted workflows)
        workflow_status = self.workflow_manager.get_workflow_status()
        has_workflow_changes = workflow_status.sync_status.has_changes

        # Check git uncommitted changes (pyproject.toml, uv.lock, etc.)
        has_git_changes = self.git_manager.has_uncommitted_changes()

        return has_workflow_changes or has_git_changes

    def commit(self, message: str | None = None) -> None:
        """Commit changes to git repository.

        Args:
            message: Optional commit message

        Raises:
            OSError: If git commands fail
        """
        return self.git_manager.commit_all(message)

    def execute_commit(
        self,
        workflow_status: DetailedWorkflowStatus | None = None,
        message: str | None = None,
        allow_issues: bool = False,
    ) -> None:
        """Execute commit using cached or provided analysis.

        Args:
            message: Optional commit message
            allow_issues: Allow committing even with unresolved issues
        """
        # Use provided analysis or prepare a new one
        if not workflow_status:
            workflow_status = self.workflow_manager.get_workflow_status()

        # Check if there are any changes to commit (workflows OR git)
        has_workflow_changes = workflow_status.sync_status.has_changes
        has_git_changes = self.git_manager.has_uncommitted_changes()

        if not has_workflow_changes and not has_git_changes:
            logger.error("No changes to commit")
            return

        # Check if changes are safe to commit (no unresolved issues)
        if not workflow_status.is_commit_safe and not allow_issues:
            logger.error("Cannot commit with unresolved issues. Use --allow-issues to force.")
            return

        # Apply auto-resolutions to pyproject.toml for workflows with changes
        # BATCHED MODE: Load config once, pass through all operations, save once
        logger.info("Committing all changes...")
        config = self.pyproject.load()

        for wf_analysis in workflow_status.analyzed_workflows:
            if wf_analysis.sync_state in ("new", "modified"):
                # Apply resolution results to pyproject (in-memory mutations)
                self.workflow_manager.apply_resolution(wf_analysis.resolution, config=config)

        # Clean up deleted workflows from pyproject.toml
        if workflow_status.sync_status.deleted:
            logger.info("Cleaning up deleted workflows from pyproject.toml...")
            removed_count = self.pyproject.workflows.remove_workflows(
                workflow_status.sync_status.deleted,
                config=config
            )
            logger.debug(f"Removed {removed_count} workflow section(s)")

            # Clean up orphaned models (must run AFTER workflow sections are removed)
            self.pyproject.models.cleanup_orphans(config=config)

        # Save all changes at once
        self.pyproject.save(config)

        logger.info("Copying workflows from ComfyUI to .cec...")
        copy_results = self.workflow_manager.copy_all_workflows()
        copied_count = len([r for r in copy_results.values() if r and r != "deleted"])
        logger.debug(f"Copied {copied_count} workflow(s)")

        self.commit(message)

    # =====================================================
    # Model Source Management
    # =====================================================

    def add_model_source(self, identifier: str, url: str) -> ModelSourceResult:
        """Add a download source URL to a model.

        Args:
            identifier: Model hash or filename
            url: Download URL for the model

        Returns:
            ModelSourceResult with success status and model details
        """
        return self.model_manager.add_model_source(identifier, url)

    def get_models_without_sources(self) -> list[ModelSourceStatus]:
        """Get all models in pyproject that don't have download sources.

        Returns:
            List of ModelSourceStatus objects with model and local availability
        """
        return self.model_manager.get_models_without_sources()

    # =====================================================
    # Constraint Management
    # =====================================================

    def add_constraint(self, package: str) -> None:
        """Add a constraint dependency."""
        self.pyproject.uv_config.add_constraint(package)

    def remove_constraint(self, package: str) -> bool:
        """Remove a constraint dependency."""
        return self.pyproject.uv_config.remove_constraint(package)

    def list_constraints(self) -> list[str]:
        """List constraint dependencies."""
        return self.pyproject.uv_config.get_constraints()

    # ===== Python Dependency Management =====

    def add_dependencies(
        self,
        packages: list[str] | None = None,
        requirements_file: Path | None = None,
        upgrade: bool = False,
        group: str | None = None,
        dev: bool = False,
        editable: bool = False,
        bounds: str | None = None
    ) -> str:
        """Add Python dependencies to the environment.

        Uses uv add to add packages to [project.dependencies] and install them.

        Args:
            packages: List of package specifications (e.g., ['requests>=2.0.0', 'pillow'])
            requirements_file: Path to requirements.txt file to add packages from
            upgrade: Whether to upgrade existing packages
            group: Dependency group name (e.g., 'optional-cuda')
            dev: Add to dev dependencies
            editable: Install as editable (for local development)
            bounds: Version specifier style ('lower', 'major', 'minor', 'exact')

        Returns:
            UV command output

        Raises:
            UVCommandError: If uv add fails
            ValueError: If neither packages nor requirements_file is provided
        """
        if not packages and not requirements_file:
            raise ValueError("Either packages or requirements_file must be provided")

        return self.uv_manager.add_dependency(
            packages=packages,
            requirements_file=requirements_file,
            upgrade=upgrade,
            group=group,
            dev=dev,
            editable=editable,
            bounds=bounds
        )

    def remove_dependencies(self, packages: list[str]) -> dict:
        """Remove Python dependencies from the environment.

        Uses uv remove to remove packages from [project.dependencies] and uninstall them.
        Safely handles packages that don't exist in dependencies.

        Args:
            packages: List of package names to remove

        Returns:
            Dict with 'removed' (list of packages removed) and 'skipped' (list of packages not in deps)

        Raises:
            UVCommandError: If uv remove fails for existing packages
        """
        return self.uv_manager.remove_dependency(packages=packages)

    def list_dependencies(self, all: bool = False) -> dict[str, list[str]]:
        """List project dependencies.

        Args:
            all: If True, include all dependency groups. If False, only base dependencies.

        Returns:
            Dictionary mapping group name to list of dependencies.
            Base dependencies are always under "dependencies" key and appear first.
        """
        config = self.pyproject.load()
        base_deps = config.get('project', {}).get('dependencies', [])

        result = {"dependencies": base_deps}

        if all:
            dep_groups = self.pyproject.dependencies.get_groups()
            result.update(dep_groups)

        return result

    # =====================================================
    # Export/Import
    # =====================================================

    def export_environment(
        self,
        output_path: Path,
        callbacks: ExportCallbacks | None = None
    ) -> Path:
        """Export environment as .tar.gz bundle.

        Args:
            output_path: Path for output tarball
            callbacks: Optional callbacks for warnings/progress

        Returns:
            Path to created tarball

        Raises:
            CDExportError: If environment has uncommitted changes or unresolved issues
        """
        from ..managers.export_import_manager import ExportImportManager
        from ..models.exceptions import CDExportError, ExportErrorContext

        # Validation: Get workflow status first for comprehensive checks
        status = self.workflow_manager.get_workflow_status()

        # Check for uncommitted workflow changes (new, modified, or deleted)
        if status.sync_status.has_changes:
            context = ExportErrorContext(
                uncommitted_workflows=(
                    status.sync_status.new +
                    status.sync_status.modified +
                    status.sync_status.deleted
                )
            )
            raise CDExportError(
                "Cannot export with uncommitted workflow changes",
                context=context
            )

        # Validation: Check for uncommitted git changes in .cec/
        if self.git_manager.has_uncommitted_changes():
            context = ExportErrorContext(uncommitted_git_changes=True)
            raise CDExportError(
                "Cannot export with uncommitted git changes",
                context=context
            )

        # Validation: Check all workflows are resolved
        if not status.is_commit_safe:
            context = ExportErrorContext(has_unresolved_issues=True)
            raise CDExportError(
                "Cannot export - workflows have unresolved issues",
                context=context
            )

        # Check for models without sources and collect workflow usage
        from ..models.shared import ModelWithoutSourceInfo

        models_without_sources: list[ModelWithoutSourceInfo] = []
        models_by_hash = {m.hash: m for m in self.pyproject.models.get_all() if not m.sources}

        if models_by_hash:
            # Map models to workflows that use them
            all_workflows = self.pyproject.workflows.get_all_with_resolutions()
            for workflow_name in all_workflows.keys():
                workflow_models = self.pyproject.workflows.get_workflow_models(workflow_name)
                for wf_model in workflow_models:
                    if wf_model.hash and wf_model.hash in models_by_hash:
                        # Find or create entry for this model
                        existing = next((m for m in models_without_sources if m.hash == wf_model.hash), None)
                        if existing:
                            existing.workflows.append(workflow_name)
                        else:
                            model_data = models_by_hash[wf_model.hash]
                            models_without_sources.append(
                                ModelWithoutSourceInfo(
                                    filename=model_data.filename,
                                    hash=wf_model.hash,
                                    workflows=[workflow_name]
                                )
                            )

            # Notify callback with structured data
            if callbacks:
                callbacks.on_models_without_sources(models_without_sources)

        # Create export
        manager = ExportImportManager(self.cec_path, self.comfyui_path)
        return manager.create_export(output_path, self.pyproject)

    def finalize_import(
        self,
        model_strategy: str = "all",
        callbacks: ImportCallbacks | None = None
    ) -> None:
        """Complete import setup after .cec extraction.

        Assumes .cec directory is already populated (from tarball or git).

        Phases:
            1. Clone/restore ComfyUI from cache and configure PyTorch
            2. Initialize git repository
            3. Copy workflows to ComfyUI user directory
            4. Sync dependencies, custom nodes, and workflows (via sync())
            5. Prepare and resolve models based on strategy

        Args:
            model_strategy: "all", "required", or "skip"
            callbacks: Optional progress callbacks

        Raises:
            ValueError: If ComfyUI already exists or .cec not properly initialized
        """
        from ..caching.comfyui_cache import ComfyUICacheManager, ComfyUISpec
        from ..utils.comfyui_ops import clone_comfyui
        from ..utils.git import git_rev_parse

        logger.info(f"Finalizing import for environment: {self.name}")

        # Verify environment state
        if self.comfyui_path.exists():
            raise ValueError("Environment already has ComfyUI - cannot finalize import")

        # Phase 1: Clone or restore ComfyUI from cache
        comfyui_cache = ComfyUICacheManager(cache_base_path=self.workspace_paths.cache)

        # Read ComfyUI version from pyproject.toml
        comfyui_version = None
        comfyui_version_type = None
        try:
            pyproject_data = self.pyproject.load()
            comfygit_config = pyproject_data.get("tool", {}).get("comfygit", {})
            comfyui_version = comfygit_config.get("comfyui_version")
            comfyui_version_type = comfygit_config.get("comfyui_version_type")
        except Exception as e:
            logger.warning(f"Could not read comfyui_version from pyproject.toml: {e}")

        if comfyui_version:
            version_desc = f"{comfyui_version_type} {comfyui_version}" if comfyui_version_type else comfyui_version
            logger.debug(f"Using comfyui_version from pyproject: {version_desc}")

        # Auto-detect version type if not specified
        if not comfyui_version_type and comfyui_version:
            if comfyui_version.startswith('v'):
                comfyui_version_type = "release"
            elif comfyui_version in ("main", "master"):
                comfyui_version_type = "branch"
            else:
                comfyui_version_type = "commit"
            logger.debug(f"Auto-detected version type: {comfyui_version_type}")

        # Create version spec
        spec = ComfyUISpec(
            version=comfyui_version or "main",
            version_type=comfyui_version_type or "branch",
            commit_sha=None
        )

        # Check cache first
        cached_path = comfyui_cache.get_cached_comfyui(spec)

        if cached_path:
            if callbacks:
                callbacks.on_phase("restore_comfyui", f"Restoring ComfyUI {spec.version} from cache...")
            logger.info(f"Restoring ComfyUI {spec.version} from cache")
            shutil.copytree(cached_path, self.comfyui_path)
        else:
            if callbacks:
                callbacks.on_phase("clone_comfyui", f"Cloning ComfyUI {spec.version}...")
            logger.info(f"Cloning ComfyUI {spec.version}")
            clone_comfyui(self.comfyui_path, comfyui_version)

            # Cache the fresh clone
            commit_sha = git_rev_parse(self.comfyui_path, "HEAD")
            if commit_sha:
                spec.commit_sha = commit_sha
                comfyui_cache.cache_comfyui(spec, self.comfyui_path)
                logger.info(f"Cached ComfyUI {spec.version} ({commit_sha[:7]})")
            else:
                logger.warning(f"Could not determine commit SHA for ComfyUI {spec.version}")

        # Extract builtin nodes for imported environment
        from ..utils.builtin_extractor import extract_comfyui_builtins

        try:
            if callbacks:
                callbacks.on_phase("extract_builtins", "Extracting builtin nodes...")

            builtins_path = self.cec_path / "comfyui_builtins.json"

            # Check if already exists (from exported bundle)
            if builtins_path.exists():
                logger.debug("Builtin config already exists from export, skipping extraction")
            else:
                extract_comfyui_builtins(self.comfyui_path, builtins_path)
                logger.info(f"Extracted builtin nodes to {builtins_path.name}")
        except Exception as e:
            logger.warning(f"Failed to extract builtin nodes: {e}")
            logger.warning("Workflow resolution will fall back to global static config")

        # Remove ComfyUI's default models directory (will be replaced with symlink)
        models_dir = self.comfyui_path / "models"
        if models_dir.exists() and not models_dir.is_symlink():
            shutil.rmtree(models_dir)

        # Remove ComfyUI's default input/output directories (will be replaced with symlinks)
        from ..utils.symlink_utils import is_link

        input_dir = self.comfyui_path / "input"
        if input_dir.exists() and not is_link(input_dir):
            shutil.rmtree(input_dir)
            logger.debug("Removed ComfyUI's default input directory during import")

        output_dir = self.comfyui_path / "output"
        if output_dir.exists() and not is_link(output_dir):
            shutil.rmtree(output_dir)
            logger.debug("Removed ComfyUI's default output directory during import")

        # Phase 1.5: Create venv and optionally install PyTorch with specific backend
        # Read Python version from .python-version file
        python_version_file = self.cec_path / ".python-version"
        python_version = python_version_file.read_text(encoding='utf-8').strip() if python_version_file.exists() else None

        if self.torch_backend:
            if callbacks:
                callbacks.on_phase("configure_pytorch", f"Configuring PyTorch backend: {self.torch_backend}")

            # Strip imported PyTorch config BEFORE venv creation to avoid platform conflicts
            from ..constants import PYTORCH_CORE_PACKAGES

            logger.info("Stripping imported PyTorch configuration...")
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

                self.pyproject.save(config)

            # Remove PyTorch constraints
            for pkg in PYTORCH_CORE_PACKAGES:
                self.pyproject.uv_config.remove_constraint(pkg)

            logger.info(f"Creating venv with Python {python_version}")
            self.uv_manager.create_venv(self.venv_path, python_version=python_version, seed=True)

            logger.info(f"Installing PyTorch with backend: {self.torch_backend}")
            self.uv_manager.install_packages(
                packages=["torch", "torchvision", "torchaudio"],
                python=self.uv_manager.python_executable,
                torch_backend=self.torch_backend,
                verbose=True
            )

            # Detect installed backend and configure pyproject
            from ..utils.pytorch import extract_backend_from_version, get_pytorch_index_url

            first_version = extract_pip_show_package_version(
                self.uv_manager.show_package("torch", self.uv_manager.python_executable)
            )

            if first_version:
                backend = extract_backend_from_version(first_version)
                logger.info(f"Detected PyTorch backend from installed version: {backend}")

                # Store resolved backend (never "auto")
                config = self.pyproject.load()
                if "tool" not in config:
                    config["tool"] = {}
                if "comfygit" not in config["tool"]:
                    config["tool"]["comfygit"] = {}
                config["tool"]["comfygit"]["torch_backend"] = backend if backend else "cpu"
                self.pyproject.save(config)
                logger.info(f"Stored resolved torch_backend: {backend if backend else 'cpu'}")

                if backend:
                    # Add new index for detected backend
                    index_name = f"pytorch-{backend}"
                    self.pyproject.uv_config.add_index(
                        name=index_name,
                        url=get_pytorch_index_url(backend),
                        explicit=True
                    )

                    # Add sources pointing to new index
                    for pkg in PYTORCH_CORE_PACKAGES:
                        self.pyproject.uv_config.add_source(pkg, {"index": index_name})

                    logger.info(f"Configured PyTorch index: {index_name}")

            # Add constraints for installed versions
            for pkg in PYTORCH_CORE_PACKAGES:
                version = extract_pip_show_package_version(
                    self.uv_manager.show_package(pkg, self.uv_manager.python_executable)
                )
                if version:
                    self.pyproject.uv_config.add_constraint(f"{pkg}=={version}")
                    logger.info(f"Added constraint: {pkg}=={version}")

        # Phase 2: Setup git repository
        # For git imports: .git already exists with remote, just ensure gitignore
        # For tarball imports: .git doesn't exist, initialize fresh repo
        git_existed = (self.cec_path / ".git").exists()

        if callbacks:
            phase_msg = "Ensuring git configuration..." if git_existed else "Initializing git repository..."
            callbacks.on_phase("init_git", phase_msg)

        if git_existed:
            # Git import case: preserve existing repo, just ensure gitignore
            logger.info("Git repository already exists (imported from git), preserving remote and history")
            self.git_manager._create_gitignore()
            self.git_manager.ensure_git_identity()
        else:
            # Tarball import case: initialize fresh repo
            logger.info("Initializing new git repository")
            self.git_manager.initialize_environment_repo("Imported environment")

        # Phase 3: Copy workflows
        if callbacks:
            callbacks.on_phase("copy_workflows", "Setting up workflows...")

        workflows_src = self.cec_path / "workflows"
        workflows_dst = self.comfyui_path / "user" / "default" / "workflows"
        workflows_dst.mkdir(parents=True, exist_ok=True)

        if workflows_src.exists():
            for workflow_file in workflows_src.glob("*.json"):
                shutil.copy2(workflow_file, workflows_dst / workflow_file.name)
                if callbacks:
                    callbacks.on_workflow_copied(workflow_file.name)

        # Phase 4: Sync dependencies, custom nodes, and workflows
        # This single sync() call handles all dependency installation, node syncing, and workflow restoration
        if callbacks:
            callbacks.on_phase("sync_environment", "Syncing dependencies and custom nodes...")

        try:
            # During import, don't remove ComfyUI builtins (fresh clone has example files)
            # Enable verbose to show real-time uv output during dependency installation
            sync_result = self.sync(remove_extra_nodes=False, sync_callbacks=callbacks, verbose=True)
            if sync_result.success and sync_result.nodes_installed and callbacks:
                for node_name in sync_result.nodes_installed:
                    callbacks.on_node_installed(node_name)
            elif not sync_result.success and callbacks:
                for error in sync_result.errors:
                    callbacks.on_error(f"Node sync: {error}")
        except Exception as e:
            if callbacks:
                callbacks.on_error(f"Node sync failed: {e}")

        # Phase 5: Prepare and resolve models
        if callbacks:
            callbacks.on_phase("resolve_models", f"Resolving workflows ({model_strategy} strategy)...")

        # Always prepare models to copy sources from global table, even for "skip"
        # This ensures download intents are preserved for later resolution
        workflows_with_intents = self.model_manager.prepare_import_with_model_strategy(model_strategy)

        # Only auto-resolve if not "skip" strategy
        workflows_to_resolve = [] if model_strategy == "skip" else workflows_with_intents

        # Resolve workflows with download intents
        from ..models.workflow import BatchDownloadCallbacks
        from ..strategies.auto import AutoModelStrategy, AutoNodeStrategy

        download_failures = []

        # Create download callbacks adapter if import callbacks provided
        download_callbacks = None
        if callbacks:
            download_callbacks = BatchDownloadCallbacks(
                on_batch_start=callbacks.on_download_batch_start,
                on_file_start=callbacks.on_download_file_start,
                on_file_progress=callbacks.on_download_file_progress,
                on_file_complete=callbacks.on_download_file_complete,
                on_batch_complete=callbacks.on_download_batch_complete
            )

        for workflow_name in workflows_to_resolve:
            try:
                result = self.resolve_workflow(
                    name=workflow_name,
                    model_strategy=AutoModelStrategy(),
                    node_strategy=AutoNodeStrategy(),
                    download_callbacks=download_callbacks
                )

                # Track successful vs failed downloads from actual download results
                successful_downloads = sum(1 for dr in result.download_results if dr.success)
                failed_downloads = [
                    (workflow_name, dr.filename)
                    for dr in result.download_results
                    if not dr.success
                ]

                download_failures.extend(failed_downloads)

                if callbacks:
                    callbacks.on_workflow_resolved(workflow_name, successful_downloads)

            except Exception as e:
                if callbacks:
                    callbacks.on_error(f"Failed to resolve {workflow_name}: {e}")

        # Report download failures
        if download_failures and callbacks:
            callbacks.on_download_failures(download_failures)

        # Mark environment as fully initialized
        from ..utils.environment_cleanup import mark_environment_complete
        mark_environment_complete(self.cec_path)

        # Phase 7: Commit all changes from import process
        # This captures: workflows copied, nodes synced, models resolved, pyproject updates
        if self.git_manager.has_uncommitted_changes():
            self.git_manager.commit_with_identity("Imported environment", add_all=True)
            logger.info("Committed import changes")

        logger.info("Import finalization completed successfully")
