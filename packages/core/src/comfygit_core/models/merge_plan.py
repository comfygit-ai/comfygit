"""Data models for merge planning and execution."""

from dataclasses import dataclass, field
from typing import Literal

Resolution = Literal["take_base", "take_target"]


@dataclass
class NodeVersionConflict:
    """Detected node version conflict during pre-merge validation."""

    node_id: str
    node_name: str
    base_version: str | None
    target_version: str | None
    affected_workflows: list[tuple[str, str]]  # (workflow_name, "base"|"target")


@dataclass
class MergeValidation:
    """Result of merge compatibility validation."""

    is_compatible: bool
    conflicts: list[NodeVersionConflict]
    merged_workflow_set: list[str]


@dataclass
class MergePlan:
    """Complete plan for executing a merge, built after user resolution."""

    target_branch: str
    base_ref: str  # Usually "HEAD"

    # Workflow resolutions
    workflow_resolutions: dict[str, Resolution]

    # Computed from resolutions
    final_workflow_set: list[str]

    # Validation results
    node_conflicts: list[NodeVersionConflict] = field(default_factory=list)
    is_compatible: bool = True

    # Merge strategy (computed)
    pyproject_strategy: Literal["take_base", "take_target", "semantic_merge"] = (
        "semantic_merge"
    )


@dataclass
class MergeResult:
    """Result of merge execution."""

    success: bool
    merge_commit: str | None = None
    workflows_merged: list[str] = field(default_factory=list)
    nodes_added: list[str] = field(default_factory=list)
    nodes_removed: list[str] = field(default_factory=list)
    nodes_updated: list[tuple[str, str, str]] = field(
        default_factory=list
    )  # (name, old_ver, new_ver)
    models_added: list[str] = field(default_factory=list)
    models_requiring_download: list[str] = field(
        default_factory=list
    )  # Models without local copy
    error: str | None = None
