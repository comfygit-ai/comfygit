"""ModelResolver - Resolve model requirements for environment import/export."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, List

from ..logging.logging_config import get_logger
from ..models.workflow import (
    WorkflowNodeWidgetRef,
    WorkflowNode,
    ModelResolutionResult,
    NodeResolutionResult,
    WorkflowDependencies,
)
from ..configs.model_config import ModelConfig

if TYPE_CHECKING:
    from ..managers.pyproject_manager import PyprojectManager
    from ..repositories.model_repository import ModelRepository
    from ..models.shared import ModelWithLocation

logger = get_logger(__name__)


class ModelResolver:
    """Resolve model requirements for environments using multiple strategies."""

    def __init__(
        self,
        model_repository: ModelRepository,
        pyproject_manager: PyprojectManager,
        model_config: ModelConfig | None = None, 
        download_manager=None,
    ):
        """Initialize ModelResolver.

        Args:
            index_manager: ModelIndexManager for lookups
            download_manager: Optional ModelDownloadManager for downloading
        """
        self.model_repository = model_repository
        self.model_config = model_config or ModelConfig.load()
        self.pyproject = pyproject_manager
        self.download_manager = download_manager

    def resolve_model(self, ref: WorkflowNodeWidgetRef, workflow_name: str) -> ModelResolutionResult | None:
        """Try multiple resolution strategies"""
        widget_value = ref.widget_value

        # Strategy 0: Check existing pyproject model data first
        pyproject_result = self._try_pyproject_resolution(workflow_name, ref)
        if pyproject_result:
            logger.debug(f"Resolved {ref} to {pyproject_result.resolved_model} from pyproject.toml")
            return pyproject_result

        # Strategy 1: Exact path match
        candidates = self._try_exact_match(widget_value)
        if len(candidates) == 1:
            logger.debug(f"Resolved {ref} to {candidates[0]} as exact match")
            return ModelResolutionResult(
                reference=ref,
                candidates=candidates,
                resolution_type="exact",
                resolved_model=candidates[0],
                resolution_confidence=1.0,
            )

        # Strategy 2: Reconstruct paths for native loaders
        if self.model_config.is_model_loader_node(ref.node_type):
            paths = self.model_config.reconstruct_model_path(ref.node_type, widget_value)
            for path in paths:
                candidates = self._try_exact_match(path)
                if len(candidates) == 1:
                    logger.debug(f"Resolved {ref} to {candidates[0]} as reconstructed match")
                    return ModelResolutionResult(
                        reference=ref,
                        candidates=candidates,
                        resolution_type="reconstructed",
                        resolved_model=candidates[0],
                        resolution_confidence=0.9,
                    )

        # Strategy 3: Case-insensitive match
        candidates = self._try_case_insensitive_match(widget_value)
        if len(candidates) == 1:
            logger.debug(f"Resolved {ref} to {candidates[0]} as case-insensitive match")
            return ModelResolutionResult(
                reference=ref,
                candidates=candidates,
                resolution_type="case_insensitive",
                resolved_model=candidates[0],
                resolution_confidence=0.8,
            )

        # Strategy 4: Filename-only match
        filename = Path(widget_value).name
        candidates = self.model_repository.find_by_filename(filename)
        if len(candidates) == 1:
            logger.debug(f"Resolved {ref} to {candidates[0]} as filename-only match")
            return ModelResolutionResult(
                reference=ref,
                candidates=candidates,
                resolution_type="filename",
                resolved_model=candidates[0],
                resolution_confidence=0.7,
            )
        elif len(candidates) > 1:
            # Multiple matches - need disambiguation
            logger.debug(f"Resolved {ref} to {candidates} as filename-only match, ambiguous")
            return ModelResolutionResult(
                reference=ref,
                candidates=candidates,
                resolution_type="ambiguous",
                resolved_model=None,
                resolution_confidence=0.0,
            )

        # No matches found
        logger.debug(f"No matches found in pyproject or model index for {ref}")
        return None

    def _try_exact_match(self, path: str) -> List["ModelWithLocation"]:
        """Try exact path match"""
        all_models = self.model_repository.get_all_models()
        return [m for m in all_models if m.relative_path == path]

    def _try_case_insensitive_match(self, path: str) -> List["ModelWithLocation"]:
        """Try case-insensitive path match"""
        all_models = self.model_repository.get_all_models()
        path_lower = path.lower()
        return [m for m in all_models if m.relative_path.lower() == path_lower]

    def _looks_like_model(self, value: Any) -> bool:
        """Check if value looks like a model path"""
        if not isinstance(value, str):
            return False
        extensions = self.model_config.default_extensions
        return any(value.endswith(ext) for ext in extensions)

    def _try_pyproject_resolution(self, workflow_name: str, ref: "WorkflowNodeWidgetRef") -> "ModelResolutionResult | None":
        """Try to resolve using existing model data in pyproject.toml if valid"""
        # No pyproject manager available, can't check existing resolutions
        if not self.pyproject:
            return None

        try:
            # Load the pyproject config
            config = self.pyproject.load()

            # Get models optional section FIRST (before checking workflow mappings)
            # This is critical to prevent optional models from being treated as required
            models_optional = config.get('tool', {}).get('comfydock', {}).get('models', {}).get('optional', {})
            workflow_ref = ref.widget_value

            # PRIORITY 1: Check if this is a Type 1 optional model (filename key, unresolved)
            # This must be checked BEFORE workflow mappings to prevent duplication in required section
            if workflow_ref in models_optional:
                optional_entry = models_optional[workflow_ref]
                if optional_entry.get('unresolved'):
                    # Type 1 optional: already marked as optional, return empty result (skip)
                    logger.debug(f"Model {workflow_ref} is marked as optional (unresolved), skipping resolution")
                    return ModelResolutionResult(
                        reference=ref,
                        candidates=[],
                        resolution_type="optional_unresolved",
                        resolved_model=None,
                        resolution_confidence=1.0,
                    )

            # PRIORITY 2: Check workflow mappings for hash-based resolution
            # Navigate to tool.comfydock.workflows section
            workflows = config.get('tool', {}).get('comfydock', {}).get('workflows', {})

            # Check if this workflow has entries
            workflow_entry = workflows.get(workflow_name, {})
            if not workflow_entry:
                return None

            # Get model mappings for this workflow
            models_section = workflow_entry.get('models', {})
            if not models_section:
                return None

            # Check if this widget_value (workflow reference) has a saved mapping
            if workflow_ref not in models_section:
                return None

            # Get the mapping for this workflow reference
            mapping = models_section[workflow_ref]

            # PRIORITY 3: Check hash-based resolution (Type 2 optional or required)
            model_hash = mapping.get('hash') if isinstance(mapping, dict) else None
            if not model_hash:
                return None

            # Check if hash-based model is in optional section (Type 2)
            if model_hash in models_optional:
                # Type 2 optional: has full metadata but marked as optional
                logger.debug(f"Model {workflow_ref} (hash {model_hash[:8]}...) is marked as optional, checking index")
                # Still try to resolve from index (Type 2 has full metadata)
                models = self.model_repository.find_model_by_hash(model_hash)
                if models and len(models) > 0:
                    model = models[0]
                    return ModelResolutionResult(
                        reference=ref,
                        candidates=models,
                        resolution_type="optional_resolved",
                        resolved_model=model,
                        resolution_confidence=1.0,
                    )
                else:
                    # Optional model not in index, but that's OK (mark as resolved anyway)
                    logger.debug(f"Optional model {workflow_ref} not in index, but already marked optional (skip)")
                    return ModelResolutionResult(
                        reference=ref,
                        candidates=[],
                        resolution_type="optional_missing",
                        resolved_model=None,
                        resolution_confidence=1.0,
                    )

            # Regular required model: Verify it exists in the index
            models = self.model_repository.find_model_by_hash(model_hash)
            if models and len(models) > 0:
                # Valid existing resolution - use it
                model = models[0]
                logger.debug(f"Resolved from pyproject: {ref.widget_value} -> {model_hash[:8]}...")
                return ModelResolutionResult(
                    reference=ref,
                    candidates=models,
                    resolution_type="pyproject",
                    resolved_model=model,
                    resolution_confidence=1.0,
                )
            else:
                # Hash no longer valid in index, need fresh resolution
                logger.debug(f"Pyproject hash {model_hash[:8]}... no longer in index for {ref.widget_value}")
                return None

        except Exception as e:
            logger.debug(f"Error checking pyproject resolution: {e}")
            return None
