"""Simplified Environment - owns everything about a single ComfyUI environment."""
from __future__ import annotations

import subprocess
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

from ..factories.uv_factory import create_uv_for_environment
from ..logging.logging_config import get_logger
from ..managers.environment_version_manager import EnvironmentVersionManager
from ..managers.git_manager import GitManager
from ..managers.model_path_manager import ModelPathManager
from ..managers.node_manager import NodeManager
from ..managers.pyproject_manager import PyprojectManager
from ..managers.resolution_tester import ResolutionTester
from ..managers.status_scanner import StatusScanner
from ..managers.uv_project_manager import UVProjectManager
from ..managers.workflow_manager import WorkflowManager
from ..models.commit import WorkflowCommitResult
from ..models.environment import EnvironmentStatus
from ..models.sync import SyncResult
from ..services.node_registry import NodeInfo, NodeRegistry
from ..utils.common import run_command

if TYPE_CHECKING:
    from ..models.shared import ModelWithLocation
    from ..managers.model_index_manager import ModelIndexManager
    from ..managers.workspace_config_manager import WorkspaceConfigManager
    from ..services.registry_data_manager import RegistryDataManager
    from .workspace import WorkspacePaths

logger = get_logger(__name__)


class Environment:
    """A ComfyUI environment - manages its own state through pyproject.toml."""

    def __init__(
        self,
        name: str,
        path: Path,
        workspace_paths: WorkspacePaths,
        model_index_manager: ModelIndexManager,
        workspace_config_manager: WorkspaceConfigManager,
        registry_data_manager: RegistryDataManager
    ):
        self.name = name
        self.path = path
        self.workspace_paths = workspace_paths
        self.model_index_manager = model_index_manager
        self.workspace_config_manager = workspace_config_manager
        self.registry_data_manager = registry_data_manager

        # Workspace-level paths
        self.global_models_path = self.workspace_config_manager.get_models_directory()

        # Core paths
        self.cec_path = path / ".cec"
        self.pyproject_path = self.cec_path / "pyproject.toml"
        self.comfyui_path = path / "ComfyUI"
        self.custom_nodes_path = self.comfyui_path / "custom_nodes"
        self.venv_path = path / ".venv"
        self.models_path = self.comfyui_path / "models"

        # Workflow paths
        self.workflows_active_path = self.comfyui_path / "user" / "default" / "workflows"
        self.workflows_cec_path = self.cec_path / "workflows"

    ## Cached properties ##

    @cached_property
    def uv_manager(self) -> UVProjectManager:
        return create_uv_for_environment(
            self.workspace_paths.root,
            cec_path=self.cec_path,
            venv_path=self.venv_path,
        )

    @cached_property
    def pyproject(self) -> PyprojectManager:
        return PyprojectManager(self.pyproject_path)

    @cached_property
    def node_registry(self) -> NodeRegistry:
        return NodeRegistry(
            workspace_path=self.workspace_paths.root,
            cache_path=self.workspace_paths.cache,
        )

    @cached_property
    def resolution_tester(self) -> ResolutionTester:
        return ResolutionTester(self.workspace_paths.root)

    @cached_property
    def node_manager(self) -> NodeManager:
        return NodeManager(
            self.pyproject,
            self.uv_manager,
            self.node_registry,
            self.resolution_tester,
            self.custom_nodes_path,
            self.registry_data_manager
        )

    @cached_property
    def model_path_manager(self) -> ModelPathManager:
        """Get model path manager."""
        return ModelPathManager(
            self.comfyui_path, self.global_models_path
        )

    @cached_property
    def workflow_manager(self) -> WorkflowManager:
        return WorkflowManager(
            self.comfyui_path,
            self.cec_path,
            self.pyproject,
            self.model_index_manager
        )

    @cached_property
    def git_manager(self) -> GitManager:
        # TODO: Wrap this into EnvironmentVersionManager
        return GitManager(self.cec_path)

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

        workflow_status = self.workflow_manager.get_full_status()

        # Assemble final status
        return EnvironmentStatus.create(
            comparison=comparison,
            git_status=git_status,
            workflow_status=workflow_status
        )

    def sync(
        self,
        dry_run: bool = False
    ) -> SyncResult:
        """Apply changes: sync packages and custom nodes with environment.

        Args:
            dry_run: If True, don't actually apply changes

        Returns:
            SyncResult with details of what was synced

        Raises:
            UVCommandError: If sync fails
        """
        result = SyncResult()

        logger.info("Syncing environment...")

        # Sync packages with UV
        try:
            self.uv_manager.sync_project(all_groups=True, dry_run=dry_run)
            result.packages_synced = True
        except Exception as e:
            logger.error(f"Package sync failed: {e}")
            result.errors.append(f"Package sync failed: {e}")
            result.success = False

        # Sync custom nodes to filesystem
        try:
            # TODO: Enhance node_manager to return what was changed
            self.node_manager.sync_nodes_to_filesystem()
            # For now, we just note it happened
        except Exception as e:
            logger.error(f"Node sync failed: {e}")
            result.errors.append(f"Node sync failed: {e}")
            result.success = False

        # No workflow sync in new architecture - workflows are handled separately

        # Sync model paths to ensure models are available
        try:
            self.model_path_manager.sync_model_paths()
            result.model_paths_configured = True
        except Exception as e:
            logger.warning(f"Failed to configure model paths: {e}")
            result.errors.append(f"Model path configuration failed: {e}")
            # Continue anyway - ComfyUI might still work

        if result.success:
            logger.info("Successfully synced environment")
        else:
            logger.warning(f"Sync completed with {len(result.errors)} errors")

        return result


    def rollback(self, target: str | None = None) -> None:
        """Rollback environment to a previous state and/or discard uncommitted changes.

        If target is provided: Apply files from that version to working directory (unstaged)
        If no target: Just discard uncommitted changes

        Args:
            target: Version identifier (e.g., "v1", "v2") or commit hash

        Raises:
            ValueError: If target version doesn't exist
            OSError: If git commands fail
        """
        version_mgr = EnvironmentVersionManager(self.git_manager)

        if target:
            version_mgr.rollback_to(target)
        else:
            self.git_manager.discard_uncommitted()

        logger.info("Successfully applied changes")

    def get_versions(self, limit: int = 10) -> list[dict]:
        """Get simplified version history for this environment.

        Args:
            limit: Maximum number of versions to return

        Returns:
            List of version info dicts with keys: version, hash, message, date
        """
        return self.git_manager.get_version_history(limit)

    def sync_model_paths(self) -> dict | None:
        """Configure model paths for this environment.

        Returns:
            Configuration statistics dictionary
        """
        logger.info(f"Configuring model paths for environment '{self.name}'")
        return self.model_path_manager.sync_model_paths()

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

    def add_node(self, identifier: str, is_local: bool = False, is_development: bool = False, no_test: bool = False) -> NodeInfo:
        """Add a custom node to the environment.

        Raises:
            CDNodeNotFoundError: If node not found
            CDNodeConflictError: If node has dependency conflicts
            CDEnvironmentError: If node with same name already exists
        """
        return self.node_manager.add_node(identifier, is_local, is_development, no_test)

    def remove_node(self, identifier: str):
        """Remove a custom node.

        Raises:
            CDNodeNotFoundError: If node not found
        """
        self.node_manager.remove_node(identifier)

    # =====================================================
    # Workflow Management
    # =====================================================

    def list_workflows(self) -> dict[str, list[str]]:
        """List all workflows categorized by sync status.

        Returns:
            Dict with 'new', 'modified', 'deleted', and 'synced' workflow names
        """
        return self.workflow_manager.get_all_workflows()



    def commit_workflows(
        self,
        message: str | None = None,
        user_resolutions: dict[str, ModelWithLocation] | None = None
    ) -> WorkflowCommitResult:
        """Commit workflows with model resolution.

        Args:
            message: Optional commit message
            user_resolutions: Optional pre-resolved ambiguous models

        Returns:
            WorkflowCommitResult with all commit details
        """
        from ..utils.git import git_commit, git_diff

        # Analyze workflows and models
        result = self.workflow_manager.analyze_commit()
        logger.debug(f"Commit result: {result}")
        
        # Do a git diff and see if the working directory is clean
        workflow_diffs = []
        for workflow_path in result.workflows_copied.values():
            if workflow_path is None or not workflow_path.exists():
                continue
            try:
                diff = git_diff(self.cec_path, workflow_path)
                if diff:
                    logger.debug(f"Workflow diff: {diff}")
                    workflow_diffs.append(diff)
            except Exception as e:
                result.success = False
                result.errors.append(f"Git diff failed: {e}")
                logger.error(f"Git diff failed: {e}")

        # If there are no workflows copied and no models resolved, short-circuit
        if not workflow_diffs:
            logger.info("No workflows found to commit")
            result.success = True
            result.no_changes = True
            return result

        # Apply resolutions
        self.workflow_manager.apply_resolutions(result, user_resolutions)

        # Generate message if needed
        if not message:
            message = result.summary

        # Git commit
        try:
            git_commit(self.cec_path, message, add_all=True)
            result.success = True
            logger.info(f"Committed workflows: {message}")
        except Exception as e:
            result.success = False
            result.errors.append(f"Git commit failed: {e}")
            logger.error(f"Git commit failed: {e}")

        return result

    def restore_workflow(self, name: str) -> bool:
        """Restore a workflow from .cec to ComfyUI directory.

        Args:
            name: Workflow name to restore

        Returns:
            True if successful, False if workflow not found
        """
        return self.workflow_manager.restore_from_cec(name)

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
