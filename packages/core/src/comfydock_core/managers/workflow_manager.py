"""Simple workflow tracking - no sync, no metadata, just registration and copying."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..models.exceptions import CDEnvironmentError

if TYPE_CHECKING:
    from .pyproject_manager import PyprojectManager

logger = get_logger(__name__)


class WorkflowManager:
    """Manages workflow tracking with one-way copying only."""

    def __init__(
        self,
        env_path: Path,
        pyproject: PyprojectManager,
    ):
        self.env_path = env_path
        self.pyproject = pyproject

        self.comfyui_workflows = env_path / "ComfyUI" / "user" / "default" / "workflows"
        self.tracked_workflows = env_path / ".cec" / "workflows"

        # Ensure directories exist
        self.comfyui_workflows.mkdir(parents=True, exist_ok=True)
        self.tracked_workflows.mkdir(parents=True, exist_ok=True)

    def track_workflow(self, name: str) -> None:
        """Register a workflow for tracking - no analysis, just registration.

        Args:
            name: Workflow name (without .json extension)
        """
        workflow_file = self.comfyui_workflows / f"{name}.json"
        if not workflow_file.exists():
            raise CDEnvironmentError(f"Workflow '{name}' not found in ComfyUI workflows")

        # Check if already tracked
        tracked = self.pyproject.workflows.get_tracked()
        if name in tracked:
            raise CDEnvironmentError(f"Workflow '{name}' is already tracked")

        # Just register it - no analysis, no copying
        workflow_config = {"tracked": True}
        self.pyproject.workflows.add(name, workflow_config)

        logger.info(f"Started tracking workflow '{name}'")

    def untrack_workflow(self, name: str) -> None:
        """Stop tracking a workflow.

        Args:
            name: Workflow name
        """
        tracked = self.pyproject.workflows.get_tracked()
        if name not in tracked:
            raise CDEnvironmentError(f"Workflow '{name}' is not tracked")

        # Remove from pyproject.toml
        self.pyproject.workflows.remove(name)

        # Remove from tracked directory if it exists
        tracked_file = self.tracked_workflows / f"{name}.json"
        if tracked_file.exists():
            tracked_file.unlink()

        logger.info(f"Stopped tracking workflow '{name}'")

    def copy_to_cec(self, name: str) -> None:
        """Copy a single workflow from ComfyUI to .cec directory.

        Args:
            name: Workflow name
        """
        source = self.comfyui_workflows / f"{name}.json"
        dest = self.tracked_workflows / f"{name}.json"

        if not source.exists():
            logger.warning(f"Workflow '{name}' not found in ComfyUI, skipping")
            return

        shutil.copy2(source, dest)
        logger.debug(f"Copied workflow '{name}' to .cec")

    def copy_all_tracked(self) -> dict[str, str]:
        """Copy all tracked workflows from ComfyUI to .cec for commit.

        Returns:
            Dictionary of workflow names to copy status
        """
        tracked = self.pyproject.workflows.get_tracked()
        results = {}

        for name in tracked:
            source = self.comfyui_workflows / f"{name}.json"
            dest = self.tracked_workflows / f"{name}.json"

            if source.exists():
                shutil.copy2(source, dest)
                results[name] = "copied"
                logger.debug(f"Copied workflow '{name}'")
            else:
                results[name] = "missing"
                logger.warning(f"Workflow '{name}' not found in ComfyUI")

        return results

    def restore_from_cec(self, name: str) -> None:
        """Restore a workflow from .cec to ComfyUI directory.

        Args:
            name: Workflow name
        """
        source = self.tracked_workflows / f"{name}.json"
        dest = self.comfyui_workflows / f"{name}.json"

        if not source.exists():
            raise CDEnvironmentError(f"Workflow '{name}' not found in tracked files")

        shutil.copy2(source, dest)
        logger.info(f"Restored workflow '{name}' to ComfyUI")
        print("⚠️ Please reload the workflow in your ComfyUI browser tab")

    def list_tracked(self) -> list[str]:
        """List all tracked workflow names.

        Returns:
            List of tracked workflow names
        """
        tracked = self.pyproject.workflows.get_tracked()
        return list(tracked.keys())

    def get_untracked(self) -> list[str]:
        """List workflows in ComfyUI that aren't tracked.

        Returns:
            List of untracked workflow names
        """
        tracked = set(self.pyproject.workflows.get_tracked().keys())
        untracked = []

        if self.comfyui_workflows.exists():
            for workflow_file in self.comfyui_workflows.glob("*.json"):
                name = workflow_file.stem
                if name not in tracked:
                    untracked.append(name)

        return sorted(untracked)