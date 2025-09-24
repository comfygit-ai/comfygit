"""Auto workflow tracking - all workflows in ComfyUI are automatically managed."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from .pyproject_manager import PyprojectManager

logger = get_logger(__name__)


class WorkflowManager:
    """Manages all workflows automatically - no explicit tracking needed."""

    def __init__(
        self,
        env_path: Path,
        pyproject: PyprojectManager,
    ):
        self.env_path = env_path
        self.pyproject = pyproject

        self.comfyui_workflows = env_path / "ComfyUI" / "user" / "default" / "workflows"
        self.cec_workflows = env_path / ".cec" / "workflows"

        # Ensure directories exist
        self.comfyui_workflows.mkdir(parents=True, exist_ok=True)
        self.cec_workflows.mkdir(parents=True, exist_ok=True)

    def get_all_workflows(self) -> dict[str, list[str]]:
        """Get all workflows categorized by their sync status.

        Returns:
            Dict with categories: 'new', 'modified', 'deleted', 'synced'
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

        return {
            'new': sorted(new_workflows),
            'modified': sorted(modified_workflows),
            'deleted': sorted(deleted_workflows),
            'synced': sorted(synced_workflows)
        }

    def _workflows_differ(self, name: str) -> bool:
        """Check if workflow differs between ComfyUI and .cec.

        Args:
            name: Workflow name

        Returns:
            True if workflows differ or .cec copy doesn't exist
        """
        comfyui_file = self.comfyui_workflows / f"{name}.json"
        cec_file = self.cec_workflows / f"{name}.json"

        if not cec_file.exists():
            return True

        if not comfyui_file.exists():
            return False

        try:
            # Compare file contents
            with open(comfyui_file) as f:
                comfyui_content = json.load(f)
            with open(cec_file) as f:
                cec_content = json.load(f)

            return comfyui_content != cec_content
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error comparing workflows '{name}': {e}")
            return True

    def copy_all_workflows(self) -> dict[str, str]:
        """Copy ALL workflows from ComfyUI to .cec for commit.

        Returns:
            Dictionary of workflow names to copy status
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

            try:
                shutil.copy2(source, dest)
                results[name] = "copied"
                logger.debug(f"Copied workflow '{name}' to .cec")
            except Exception as e:
                results[name] = "failed"
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
                        logger.debug(f"Deleted workflow '{name}' from .cec (no longer in ComfyUI)")
                    except Exception as e:
                        logger.error(f"Failed to delete workflow '{name}': {e}")

        return results

    def restore_from_cec(self, name: str) -> None:
        """Restore a workflow from .cec to ComfyUI directory.

        Args:
            name: Workflow name
        """
        source = self.cec_workflows / f"{name}.json"
        dest = self.comfyui_workflows / f"{name}.json"

        if not source.exists():
            raise ValueError(f"Workflow '{name}' not found in .cec directory")

        shutil.copy2(source, dest)
        logger.info(f"Restored workflow '{name}' to ComfyUI")
        print("⚠️ Please reload the workflow in your ComfyUI browser tab")

    def restore_all_from_cec(self) -> dict[str, str]:
        """Restore all workflows from .cec to ComfyUI (for rollback).

        Returns:
            Dictionary of workflow names to restore status
        """
        results = {}

        if not self.cec_workflows.exists():
            logger.info("No .cec workflows directory found")
            return results

        # Copy every workflow from .cec to ComfyUI
        for workflow_file in self.cec_workflows.glob("*.json"):
            name = workflow_file.stem
            try:
                self.restore_from_cec(name)
                results[name] = "restored"
            except Exception as e:
                results[name] = "failed"
                logger.error(f"Failed to restore workflow '{name}': {e}")

        # Remove workflows from ComfyUI that don't exist in .cec (cleanup)
        if self.comfyui_workflows.exists():
            cec_names = {f.stem for f in self.cec_workflows.glob("*.json")}
            for comfyui_file in self.comfyui_workflows.glob("*.json"):
                name = comfyui_file.stem
                if name not in cec_names:
                    try:
                        comfyui_file.unlink()
                        results[name] = "removed"
                        logger.debug(f"Removed workflow '{name}' from ComfyUI (not in .cec)")
                    except Exception as e:
                        logger.error(f"Failed to remove workflow '{name}': {e}")

        return results

    def get_workflow_status(self) -> dict:
        """Get detailed status of all workflows.

        Returns:
            Status summary with counts and workflow lists
        """
        workflows = self.get_all_workflows()

        return {
            'total_workflows': sum(len(workflows[key]) for key in workflows),
            'has_changes': bool(workflows['new'] or workflows['modified'] or workflows['deleted']),
            'changes_summary': self._get_changes_summary(workflows),
            **workflows
        }

    def _get_changes_summary(self, workflows: dict[str, list[str]]) -> str:
        """Generate human-readable summary of workflow changes."""
        parts = []

        if workflows['new']:
            parts.append(f"{len(workflows['new'])} new")
        if workflows['modified']:
            parts.append(f"{len(workflows['modified'])} modified")
        if workflows['deleted']:
            parts.append(f"{len(workflows['deleted'])} deleted")

        if not parts:
            return "No workflow changes"

        return f"Workflow changes: {', '.join(parts)}"

    def get_full_status(self):
        """Get workflow status in the format expected by EnvironmentStatus."""
        from ..models.environment import WorkflowStatus

        workflows = self.get_all_workflows()

        return WorkflowStatus(
            new=workflows['new'],
            modified=workflows['modified'],
            deleted=workflows['deleted'],
            synced=workflows['synced']
        )