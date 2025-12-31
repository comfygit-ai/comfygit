"""Workflow synchronization manager - handles sync between ComfyUI and .cec directories."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..models.workflow import WorkflowSyncStatus
from ..repositories.workflow_repository import WorkflowRepository
from ..utils.workflow_hash import normalize_workflow

if TYPE_CHECKING:
    from ..caching.workflow_cache import WorkflowCacheRepository

logger = get_logger(__name__)


class WorkflowSyncManager:
    """Manages workflow synchronization between ComfyUI and .cec directories."""

    def __init__(
        self,
        comfyui_path: Path,
        cec_path: Path,
        workflow_cache: WorkflowCacheRepository,
        environment_name: str
    ):
        self.comfyui_path = comfyui_path
        self.cec_path = cec_path
        self.workflow_cache = workflow_cache
        self.environment_name = environment_name

        self.comfyui_workflows = comfyui_path / "user" / "default" / "workflows"
        self.cec_workflows = cec_path / "workflows"

        # Ensure directories exist
        self.comfyui_workflows.mkdir(parents=True, exist_ok=True)
        self.cec_workflows.mkdir(parents=True, exist_ok=True)

    def get_workflow_path(self, name: str) -> Path:
        """Check if workflow exists in ComfyUI directory and return path.

        Args:
            name: Workflow name

        Returns:
            Path to workflow file if it exists

        Raises:
            FileNotFoundError
        """
        workflow_path = self.comfyui_workflows / f"{name}.json"
        if workflow_path.exists():
            return workflow_path
        else:
            raise FileNotFoundError(f"Workflow '{name}' not found in ComfyUI directory")

    def get_workflow_sync_status(self) -> WorkflowSyncStatus:
        """Get file-level sync status between ComfyUI and .cec.

        Returns:
            WorkflowSyncStatus with categorized workflow lists
        """
        # Get all workflows from ComfyUI
        comfyui_workflows = set()
        if self.comfyui_workflows.exists():
            for workflow_file in self.comfyui_workflows.glob("*.json"):
                comfyui_workflows.add(workflow_file.stem)

        # Get all workflows from .cec
        cec_workflows = set()
        if self.cec_workflows.exists():
            for workflow_file in self.cec_workflows.glob("*.json"):
                cec_workflows.add(workflow_file.stem)

        # Categorize workflows
        new_workflows = []
        modified_workflows = []
        deleted_workflows = []
        synced_workflows = []

        # Check each ComfyUI workflow
        for name in comfyui_workflows:
            if name not in cec_workflows:
                new_workflows.append(name)
            else:
                # Compare contents to detect modifications
                if self._workflows_differ(name):
                    modified_workflows.append(name)
                else:
                    synced_workflows.append(name)

        # Check for deleted workflows (in .cec but not ComfyUI)
        for name in cec_workflows:
            if name not in comfyui_workflows:
                deleted_workflows.append(name)

        return WorkflowSyncStatus(
            new=sorted(new_workflows),
            modified=sorted(modified_workflows),
            deleted=sorted(deleted_workflows),
            synced=sorted(synced_workflows),
        )

    def _workflows_differ(self, name: str) -> bool:
        """Check if workflow differs between ComfyUI and .cec.

        Args:
            name: Workflow name

        Returns:
            True if workflows differ or .cec copy doesn't exist
        """
        # TODO: This will fail if workflow is in a subdirectory in ComfyUI
        comfyui_file = self.comfyui_workflows / f"{name}.json"
        cec_file = self.cec_workflows / f"{name}.json"

        if not cec_file.exists():
            return True

        if not comfyui_file.exists():
            return False

        try:
            # Compare file contents, ignoring volatile metadata fields
            with open(comfyui_file, encoding='utf-8') as f:
                comfyui_content = json.load(f)
            with open(cec_file, encoding='utf-8') as f:
                cec_content = json.load(f)

            # Normalize by removing volatile fields that change between saves
            comfyui_normalized = normalize_workflow(comfyui_content)
            cec_normalized = normalize_workflow(cec_content)

            return comfyui_normalized != cec_normalized
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Error comparing workflows '{name}': {e}")
            return True

    def copy_all_workflows(self) -> dict[str, Path | None]:
        """Copy ALL workflows from ComfyUI to .cec for commit.

        Returns:
            Dictionary of workflow names to Path
        """
        results = {}

        if not self.comfyui_workflows.exists():
            logger.info("No ComfyUI workflows directory found")
            return results

        # Copy every workflow from ComfyUI to .cec
        for workflow_file in self.comfyui_workflows.glob("*.json"):
            name = workflow_file.stem
            source = self.comfyui_workflows / f"{name}.json"
            dest = self.cec_workflows / f"{name}.json"

            # Check if workflow was actually modified (not just UI changes)
            was_modified = self._workflows_differ(name)

            try:
                shutil.copy2(source, dest)
                results[name] = dest
                logger.debug(f"Copied workflow '{name}' to .cec")

                # Invalidate cache for truly modified workflows
                if was_modified:
                    self.workflow_cache.invalidate(
                        env_name=self.environment_name,
                        workflow_name=name
                    )
                    logger.debug(f"Invalidated cache for modified workflow '{name}'")

            except Exception as e:
                results[name] = None
                logger.error(f"Failed to copy workflow '{name}': {e}")

        # Remove workflows from .cec that no longer exist in ComfyUI
        if self.cec_workflows.exists():
            comfyui_names = {f.stem for f in self.comfyui_workflows.glob("*.json")}
            for cec_file in self.cec_workflows.glob("*.json"):
                name = cec_file.stem
                if name not in comfyui_names:
                    try:
                        cec_file.unlink()
                        results[name] = "deleted"

                        # Invalidate cache for deleted workflows
                        self.workflow_cache.invalidate(
                            env_name=self.environment_name,
                            workflow_name=name
                        )
                        logger.debug(
                            f"Deleted workflow '{name}' from .cec (no longer in ComfyUI)"
                        )
                    except Exception as e:
                        logger.error(f"Failed to delete workflow '{name}': {e}")

        return results

    def restore_from_cec(self, name: str) -> bool:
        """Restore a workflow from .cec to ComfyUI directory.

        Args:
            name: Workflow name

        Returns:
            True if successful, False if workflow not found
        """
        source = self.cec_workflows / f"{name}.json"
        dest = self.comfyui_workflows / f"{name}.json"

        if not source.exists():
            return False

        try:
            shutil.copy2(source, dest)
            logger.info(f"Restored workflow '{name}' to ComfyUI")
            return True
        except Exception as e:
            logger.error(f"Failed to restore workflow '{name}': {e}")
            return False

    def restore_all_from_cec(self, preserve_uncommitted: bool = False) -> dict[str, str]:
        """Restore all workflows from .cec to ComfyUI.

        Args:
            preserve_uncommitted: If True, don't delete workflows not in .cec.
                                 This enables git-like behavior where uncommitted
                                 changes are preserved during branch switches.
                                 If False, force ComfyUI to match .cec exactly
                                 (current behavior for rollback operations).

        Returns:
            Dictionary of workflow names to restore status
        """
        results = {}

        # Phase 1: Restore workflows that exist in .cec
        if self.cec_workflows.exists():
            # Get uncommitted workflows if we need to preserve them
            uncommitted_workflows = set()
            if preserve_uncommitted:
                status = self.get_workflow_sync_status()
                uncommitted_workflows = set(status.new + status.modified)

            # Copy workflows from .cec to ComfyUI (skip uncommitted if preserving)
            for workflow_file in self.cec_workflows.glob("*.json"):
                name = workflow_file.stem

                # Skip if this workflow has uncommitted changes and we're preserving
                if preserve_uncommitted and name in uncommitted_workflows:
                    results[name] = "preserved"
                    logger.debug(f"Preserved uncommitted changes to workflow '{name}'")
                    continue

                if self.restore_from_cec(name):
                    results[name] = "restored"
                else:
                    results[name] = "failed"

        # Phase 2: Cleanup (ALWAYS run, even if .cec/workflows/ doesn't exist!)
        # This ensures git semantics: switching to branch without workflows deletes them
        if not preserve_uncommitted and self.comfyui_workflows.exists():
            # Determine what workflows SHOULD exist
            if self.cec_workflows.exists():
                cec_names = {f.stem for f in self.cec_workflows.glob("*.json")}
            else:
                # No .cec/workflows/ directory = no workflows should exist
                # This happens when switching to branches that never had workflows committed
                cec_names = set()

            # Remove workflows that shouldn't exist
            for comfyui_file in self.comfyui_workflows.glob("*.json"):
                name = comfyui_file.stem
                if name not in cec_names:
                    try:
                        comfyui_file.unlink()
                        results[name] = "removed"
                        logger.debug(
                            f"Removed workflow '{name}' from ComfyUI (not in .cec)"
                        )
                    except Exception as e:
                        logger.error(f"Failed to remove workflow '{name}': {e}")

        return results