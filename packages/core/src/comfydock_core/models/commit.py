"""Commit operation result models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from ..models.shared import ModelWithLocation
    from ..models.workflow import ModelResolutionResult

@dataclass
class ModelResolutionRequest:
    """Request for resolving ambiguous model matches."""
    workflow_name: str
    node_id: str
    node_type: str
    widget_index: int
    original_value: str
    candidates: list[ModelWithLocation]

@dataclass
class WorkflowCommitResult:
    """Result of workflow commit operation."""
    workflows_copied: dict[str, Path | None] = field(default_factory=dict)  # name -> status
    models_resolved: dict[str, ModelWithLocation] = field(default_factory=dict)  # hash -> model
    models_needing_resolution: list[ModelResolutionRequest] = field(default_factory=list)
    models_unresolved: list[dict] = field(default_factory=list)  # Failed to resolve
    workflow_resolutions: dict[str, list[ModelResolutionResult]] = field(default_factory=dict)
    success: bool = True
    no_changes: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def has_ambiguous_models(self) -> bool:
        """Check if there are models needing user resolution."""
        return len(self.models_needing_resolution) > 0

    @property
    def summary(self) -> str:
        """Generate commit summary message."""
        copied = len([s for s in self.workflows_copied.values() if s == "copied"])
        resolved = len(self.models_resolved)

        if copied and resolved:
            return f"Update {copied} workflow(s) with {resolved} models"
        elif copied:
            return f"Update {copied} workflow(s)"
        else:
            return "Update workflows"