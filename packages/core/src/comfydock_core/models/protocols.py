"""Resolution strategy protocols for dependency injection."""
from __future__ import annotations
from typing import TYPE_CHECKING,Protocol, Optional, List
from abc import abstractmethod

from .workflow import ModelResolutionContext, ResolvedModel, WorkflowNodeWidgetRef
from .shared import ModelWithLocation

if TYPE_CHECKING:
    from ..models.workflow import ResolvedNodePackage

class NodeResolutionStrategy(Protocol):
    """Protocol for resolving unknown custom nodes."""

    def resolve_unknown_node(
        self, node_type: str, possible: List[ResolvedNodePackage]
    ) -> ResolvedNodePackage | None:
        """Given node type and suggestions, return package ID or None.

        Args:
            node_type: The unknown node type (e.g. "MyCustomNode")
            suggestions: List of registry suggestions with package_id, confidence

        Returns:
            Package ID to install or None to skip
        """
        ...

    def confirm_node_install(self, package: ResolvedNodePackage) -> bool:
        """Confirm whether to install a node package.

        Args:
            package_id: Registry package ID
            node_type: The node type being resolved

        Returns:
            True to install, False to skip
        """
        ...


class ModelResolutionStrategy(Protocol):
    """Protocol for resolving model references."""

    def resolve_model(
        self,
        reference: WorkflowNodeWidgetRef,
        candidates: List["ResolvedModel"],
        context: "ModelResolutionContext",
    ) -> Optional["ResolvedModel"]:
        """Resolve a model reference (ambiguous or missing).

        Args:
            reference: The model reference from workflow
            candidates: List of potential matches (may be empty for missing models)
            context: Resolution context with search function and workflow info

        Returns:
            ResolvedModel with resolved_model filled (or None for optional unresolved)
            None to skip resolution

        Note:
            - For resolved models: Return ResolvedModel with resolved_model set
            - For optional unresolved: Return ResolvedModel with resolved_model=None, is_optional=True
            - To skip: Return None
        """
        ...


class RollbackStrategy(Protocol):
    """Protocol for confirming destructive rollback operations."""

    def confirm_destructive_rollback(
        self,
        git_changes: bool,
        workflow_changes: bool,
    ) -> bool:
        """Confirm rollback that will discard uncommitted changes.

        Args:
            git_changes: Whether there are uncommitted git changes in .cec/
            workflow_changes: Whether there are modified/new/deleted workflows

        Returns:
            True to proceed with rollback, False to cancel
        """
        ...
