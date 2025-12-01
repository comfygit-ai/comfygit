"""Data models for ref-to-ref diffing.

These dataclasses represent the complete diff between two git refs,
used for preview_pull() and preview_merge() operations.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Conflict:
    """Base conflict with resolution state."""

    category: Literal["node", "workflow", "dependency"]
    identifier: str
    conflict_type: Literal["both_modified", "delete_modify"]
    resolution: Literal["take_base", "take_target", "unresolved"] = "unresolved"


@dataclass
class NodeConflict(Conflict):
    """Node version conflict."""

    category: Literal["node"] = field(default="node", init=False)
    base_version: str | None = None
    target_version: str | None = None
    base_deleted: bool = False
    target_deleted: bool = False


@dataclass
class WorkflowConflict(Conflict):
    """Workflow file conflict with content hashes."""

    category: Literal["workflow"] = field(default="workflow", init=False)
    base_hash: str | None = None
    target_hash: str | None = None


@dataclass
class DependencyConflict(Conflict):
    """Dependency version conflict."""

    category: Literal["dependency"] = field(default="dependency", init=False)
    base_spec: str | None = None
    target_spec: str | None = None


@dataclass
class NodeChange:
    """A node that changed between refs."""

    identifier: str
    name: str
    change_type: Literal["added", "removed", "version_changed"]
    base_version: str | None = None
    target_version: str | None = None
    is_development: bool = False
    conflict: NodeConflict | None = None


@dataclass
class ModelChange:
    """A model that changed between refs."""

    hash: str
    filename: str
    category: str
    change_type: Literal["added", "removed"]
    size: int
    sources: list[str] = field(default_factory=list)


@dataclass
class WorkflowChange:
    """A workflow file that changed between refs."""

    name: str
    change_type: Literal["added", "modified", "deleted"]
    conflict: WorkflowConflict | None = None


@dataclass
class DependencyChanges:
    """Python dependency changes."""

    added: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    updated: list[dict] = field(default_factory=list)
    constraints_added: list[str] = field(default_factory=list)
    constraints_removed: list[str] = field(default_factory=list)
    conflicts: list[DependencyConflict] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added
            or self.removed
            or self.updated
            or self.constraints_added
            or self.constraints_removed
        )


@dataclass
class RefDiff:
    """Complete diff between two git refs."""

    base_ref: str
    target_ref: str
    merge_base: str | None
    node_changes: list[NodeChange]
    model_changes: list[ModelChange]
    workflow_changes: list[WorkflowChange]
    dependency_changes: DependencyChanges

    @property
    def has_conflicts(self) -> bool:
        """True if any unresolved conflicts exist."""
        return (
            any(
                c.conflict and c.conflict.resolution == "unresolved"
                for c in self.node_changes
            )
            or any(
                c.conflict and c.conflict.resolution == "unresolved"
                for c in self.workflow_changes
            )
            or any(c.resolution == "unresolved" for c in self.dependency_changes.conflicts)
        )

    @property
    def has_changes(self) -> bool:
        """True if any changes detected."""
        return bool(
            self.node_changes
            or self.model_changes
            or self.workflow_changes
            or self.dependency_changes.has_changes
        )

    @property
    def is_fast_forward(self) -> bool:
        """True if target is strictly ahead of base (no divergence)."""
        return self.merge_base == self.base_ref

    @property
    def is_already_merged(self) -> bool:
        """True if target is already merged into base.

        This means target is an ancestor of base, or they point to the same commit.
        In git terms: merge_base == target_ref means target is reachable from base.
        """
        return self.merge_base == self.target_ref

    def summary(self) -> dict:
        """Summary counts for display."""
        return {
            "nodes_added": sum(1 for c in self.node_changes if c.change_type == "added"),
            "nodes_removed": sum(1 for c in self.node_changes if c.change_type == "removed"),
            "models_added": sum(1 for c in self.model_changes if c.change_type == "added"),
            "models_removed": sum(1 for c in self.model_changes if c.change_type == "removed"),
            "models_added_size": sum(
                c.size for c in self.model_changes if c.change_type == "added"
            ),
            "workflows_added": sum(
                1 for c in self.workflow_changes if c.change_type == "added"
            ),
            "workflows_modified": sum(
                1 for c in self.workflow_changes if c.change_type == "modified"
            ),
            "workflows_deleted": sum(
                1 for c in self.workflow_changes if c.change_type == "deleted"
            ),
            "conflicts": len(
                [c for c in self.all_conflicts if c.resolution == "unresolved"]
            ),
        }

    @property
    def all_conflicts(self) -> list[Conflict]:
        """All conflicts flattened for UI iteration."""
        conflicts: list[Conflict] = []
        for c in self.node_changes:
            if c.conflict:
                conflicts.append(c.conflict)
        for c in self.workflow_changes:
            if c.conflict:
                conflicts.append(c.conflict)
        conflicts.extend(self.dependency_changes.conflicts)
        return conflicts
