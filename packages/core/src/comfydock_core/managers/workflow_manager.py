"""Auto workflow tracking - all workflows in ComfyUI are automatically managed."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models.commit import ModelResolutionRequest, WorkflowCommitResult
from ..utils.workflow_dependency_parser import WorkflowDependencyParser
from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from .pyproject_manager import PyprojectManager
    from .model_index_manager import ModelIndexManager
    from ..models.shared import ModelWithLocation

logger = get_logger(__name__)


class WorkflowManager:
    """Manages all workflows automatically - no explicit tracking needed."""

    def __init__(
        self,
        comfyui_path: Path,
        cec_path: Path,
        pyproject: PyprojectManager,
        model_index_manager: ModelIndexManager,
    ):
        self.comfyui_path = comfyui_path
        self.cec_path = cec_path
        self.pyproject = pyproject
        self.model_index_manager = model_index_manager

        self.comfyui_workflows = comfyui_path / "user" / "default" / "workflows"
        self.cec_workflows = cec_path / "workflows"

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

            try:
                shutil.copy2(source, dest)
                results[name] = dest
                logger.debug(f"Copied workflow '{name}' to .cec")
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
                        logger.debug(f"Deleted workflow '{name}' from .cec (no longer in ComfyUI)")
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
            if self.restore_from_cec(name):
                results[name] = "restored"
            else:
                results[name] = "failed"

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
        
    def analyze_commit(self) -> WorkflowCommitResult:
        """Analyze workflows and prepare commit data WITHOUT user interaction.

        Returns:
            WorkflowCommitResult with all data needed for commit
        """
        result = WorkflowCommitResult()

        # Step 1: Copy workflows
        result.workflows_copied = self.copy_all_workflows()
        logger.info(f"Copied {len(result.workflows_copied)} workflows")

        # Step 2: Parse each workflow for models
        for workflow_name, workflow_path in result.workflows_copied.items():
            if workflow_path is None or not workflow_path.exists():
                continue

            try:
                # Parse for models
                parser = WorkflowDependencyParser(
                    workflow_path,
                    self.model_index_manager,
                    pyproject=self.pyproject
                )

                # Analyze models with enhanced strategies
                resolution_results = parser.analyze_models_enhanced()
                result.workflow_resolutions[workflow_name] = resolution_results

                # Categorize results
                for res in resolution_results:
                    if res.resolution_type in ["exact", "reconstructed", "metadata", "case_insensitive", "filename", "pyproject"]:
                        # Automatically resolved
                        if res.reference.resolved_model:
                            model = res.reference.resolved_model
                            result.models_resolved[model.hash] = model

                    elif res.resolution_type == "ambiguous":
                        # Needs user input
                        result.models_needing_resolution.append(
                            ModelResolutionRequest(
                                workflow_name=workflow_name,
                                node_id=res.reference.node_id,
                                node_type=res.reference.node_type,
                                widget_index=res.reference.widget_index,
                                original_value=res.reference.widget_value,
                                candidates=res.candidates
                            )
                        )

                    elif res.resolution_type == "not_found":
                        # Couldn't resolve
                        result.models_unresolved.append({
                            'workflow': workflow_name,
                            'node_id': res.reference.node_id,
                            'node_type': res.reference.node_type,
                            'value': res.reference.widget_value
                        })

            except Exception as e:
                logger.error(f"Failed to parse workflow {workflow_name}: {e}")
                result.errors.append(f"Failed to parse workflow {workflow_name}: {e}")

        logger.info(
            f"Resolved {len(result.models_resolved)} models, "
            f"{len(result.models_needing_resolution)} need user input, "
            f"{len(result.models_unresolved)} unresolved"
        )

        return result

    def apply_resolutions(
        self,
        commit_result: WorkflowCommitResult,
        user_resolutions: dict[str, ModelWithLocation] | None = None
    ) -> None:
        """Apply model resolutions and update pyproject.toml.

        Args:
            commit_result: Result from analyze_commit()
            user_resolutions: Optional dict mapping request key to selected model
        """
        # Process user resolutions if provided
        if user_resolutions:
            for selected_model in user_resolutions.values():
                commit_result.models_resolved[selected_model.hash] = selected_model

        # Update pyproject.toml with all resolved models
        for model_hash, model in commit_result.models_resolved.items():
            self.pyproject.models.add_model(
                model_hash=model_hash,
                filename=model.filename,
                file_size=model.file_size,
                relative_path=model.relative_path,
                category="required"
            )

        # Update workflow resolutions in pyproject.toml
        for workflow_name, resolutions in commit_result.workflow_resolutions.items():
            model_mappings = {}

            for res in resolutions:
                if res.reference.resolved_model:
                    model = res.reference.resolved_model
                    if model.hash not in model_mappings:
                        model_mappings[model.hash] = {"nodes": []}

                    model_mappings[model.hash]["nodes"].append({
                        "node_id": res.reference.node_id,
                        "widget_idx": res.reference.widget_index
                    })

            if model_mappings:
                self.pyproject.workflows.set_model_resolutions(
                    workflow_name,
                    model_mappings
                )

        logger.info(f"Updated pyproject.toml with {len(commit_result.models_resolved)} models")

    def _generate_request_key(self, req: ModelResolutionRequest) -> str:
        """Generate unique key for resolution request."""
        return f"{req.workflow_name}:{req.node_id}:{req.widget_index}"