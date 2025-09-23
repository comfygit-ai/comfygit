"""Sync-related models and protocols for ComfyDock."""

from dataclasses import dataclass, field
from typing import Dict, List, Protocol, Tuple, TypeAlias

from .workflow import ModelResolutionResult
from .shared import ModelWithLocation

# Type alias for model resolutions mapping
ModelResolutionMap: TypeAlias = Dict[Tuple[str, int], ModelWithLocation]
"""Maps (node_id, widget_index) to resolved model for ambiguous references."""


class ModelResolutionStrategy(Protocol):
    """Strategy for resolving ambiguous model references.

    This allows different UIs (CLI, Web, API) to handle model
    disambiguation in their own way.
    """

    def resolve_ambiguous(
        self,
        results: List[ModelResolutionResult]
    ) -> ModelResolutionMap:
        """Resolve ambiguous model references.

        Args:
            results: List of model resolution results from workflow analysis

        Returns:
            ModelResolutionMap mapping (node_id, widget_index) to chosen model
            Empty dict or partial dict is valid - unresolved models remain unresolved
        """
        ...

    def show_summary(self, results: List[ModelResolutionResult]) -> None:
        """Optional: Show resolution summary to user.

        Args:
            results: Model resolution results to summarize
        """
        pass


@dataclass
class WorkflowResolution:
    """Result of resolving models for a single workflow."""

    name: str
    resolved_count: int = 0
    unresolved_count: int = 0
    ambiguous_count: int = 0
    action: str = "in_sync"  # sync action taken


@dataclass
class SyncResult:
    """Structured result from environment sync operation."""

    # Package sync
    packages_synced: bool = False

    # Node sync
    nodes_installed: List[str] = field(default_factory=list)
    nodes_removed: List[str] = field(default_factory=list)
    nodes_updated: List[str] = field(default_factory=list)

    # Workflow sync
    workflows_synced: Dict[str, str] = field(default_factory=dict)  # name -> action
    workflow_resolutions: List[WorkflowResolution] = field(default_factory=list)

    # Model paths
    model_paths_configured: bool = False

    # Overall status
    success: bool = True
    errors: List[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if any changes were made during sync."""
        return (
            self.packages_synced or
            bool(self.nodes_installed) or
            bool(self.nodes_removed) or
            bool(self.nodes_updated) or
            any(action != "in_sync" for action in self.workflows_synced.values()) or
            bool(self.workflow_resolutions)
        )

    @property
    def has_unresolved_models(self) -> bool:
        """Check if any workflows have unresolved models."""
        return any(
            wr.unresolved_count > 0
            for wr in self.workflow_resolutions
        )


class NoOpResolver(ModelResolutionStrategy):
    """Default resolver that leaves all ambiguous models unresolved."""

    def resolve_ambiguous(
        self,
        results: List[ModelResolutionResult]
    ) -> ModelResolutionMap:
        """Return empty dict - leave all unresolved."""
        return {}


class AutoResolver(ModelResolutionStrategy):
    """Automatically resolve to first candidate for each ambiguous model."""

    def resolve_ambiguous(
        self,
        results: List[ModelResolutionResult]
    ) -> ModelResolutionMap:
        """Auto-select first candidate for each ambiguous model."""
        resolutions: ModelResolutionMap = {}
        for result in results:
            if result.resolution_type == "ambiguous" and result.candidates:
                ref = result.reference
                resolutions[(ref.node_id, ref.widget_index)] = result.candidates[0]
        return resolutions