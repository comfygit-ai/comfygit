"""Workflow dependency analysis and resolution manager."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from comfydock_core.services.workflow_repository import WorkflowRepository

from ..logging.logging_config import get_logger
from ..services.node_classifier import NodeClassifier
from ..configs.model_config import ModelConfig

if TYPE_CHECKING:
    from comfydock_core.managers.model_index_manager import ModelIndexManager
    from comfydock_core.models.shared import ModelWithLocation
    from ..models.workflow import Workflow, WorkflowNode

logger = get_logger(__name__)

@dataclass
class WorkflowDependencies:
    """Complete workflow dependency analysis results."""
    resolved_models: list[ModelWithLocation] = field(default_factory=list)
    missing_models: list[dict] = field(default_factory=list)
    builtin_nodes: list[WorkflowNode] = field(default_factory=list)
    custom_nodes: list[WorkflowNode] = field(default_factory=list)
    python_dependencies: list[str] = field(default_factory=list)

    @property
    def total_models(self) -> int:
        """Total number of model references found."""
        return len(self.resolved_models) + len(self.missing_models)

    @property
    def model_hashes(self) -> list[str]:
        """Get all resolved model hashes."""
        return [model.hash for model in self.resolved_models]


class WorkflowDependencyParser:
    """Manages workflow dependency analysis and resolution."""

    def __init__(self, workflow_path: Path, model_index: ModelIndexManager, model_config: ModelConfig | None = None):
        
        self.model_index = model_index
        self.model_config = model_config or ModelConfig.load()
        self.node_classifier = NodeClassifier()
        self.repository = WorkflowRepository()
        # Load workflow
        self.workflow = self.repository.load(workflow_path)
        logger.debug(f"Loaded workflow {self.workflow}")

        # Keep raw text for legacy string matching
        self.workflow_text = self.repository.load_raw_text(workflow_path)

    def analyze_dependencies(self) -> WorkflowDependencies:
        """Analyze workflow for all dependencies, including model information, node types, and Python dependencies."""
        try:
            nodes_data = self.workflow.nodes

            if not nodes_data:
                logger.warning("No nodes found in workflow")
                return WorkflowDependencies()

            resolved_models, missing_models = self._resolve_model_dependencies(nodes_data)

            # Extract custom and builtin nodes
            all_nodes = self.node_classifier.classify_nodes(self.workflow)
            logger.debug(f"Found {len(all_nodes.builtin_nodes)} builtin nodes and {len(all_nodes.custom_nodes)} custom nodes")
            builtin_nodes = all_nodes.builtin_nodes
            custom_nodes = all_nodes.custom_nodes

            # Log results
            if resolved_models:
                logger.info(f"Found {len(resolved_models)} models in workflow")
            if missing_models:
                logger.warning(f"Found {len(missing_models)} missing models in workflow")
            if custom_nodes:
                logger.info(f"Found {len(custom_nodes)} custom nodes in workflow")

            return WorkflowDependencies(
                resolved_models=resolved_models,
                missing_models=missing_models,
                builtin_nodes=builtin_nodes,
                custom_nodes=custom_nodes,
                python_dependencies=[]
            )

        except Exception as e:
            logger.error(f"Failed to analyze workflow dependencies: {e}")
            return WorkflowDependencies()

    def _resolve_model_dependencies(self, nodes_data) -> tuple[list[ModelWithLocation], list[dict]]:
        # Get model index data
        all_models = self.model_index.get_all_models()
        full_path_models = {model.relative_path: model for model in all_models}

        # Track processing state
        resolved_models: list[ModelWithLocation] = []
        missing_models: list[dict] = []
        processed_hashes = set()
        standard_nodes = set()

        # Process standard loader nodes first
        for node_id, node_info in nodes_data.items():
            node_type = node_info.type

            # Skip non-model loader nodes
            if not self.model_config.is_model_loader_node(node_type):
                continue
            
            standard_nodes.add(node_id)
            model_paths = self._extract_paths_from_node_info(node_type, node_info)

            # Try alternative paths until we find one that exists
            resolved = False
            for full_path in model_paths:
                if full_path in full_path_models:
                    model = full_path_models[full_path]
                    if model.hash not in processed_hashes:
                        resolved_models.append(model)
                        processed_hashes.add(model.hash)
                        logger.debug(
                            f"Resolved standard loader: {node_type} -> {full_path} -> {model.hash}"
                        )
                    else:
                        logger.debug(
                            f"Model already resolved by another node: {node_type} -> {full_path} -> {model.hash}"
                        )
                    resolved = True
                    break

            # Mark as missing if none of the alternatives worked
            if not resolved and model_paths:
                widget_values = node_info.widgets_values
                widget_index = self.model_config.get_widget_index_for_node(
                    node_type
                )
                widget_value = (
                    widget_values[widget_index]
                    if widget_index < len(widget_values)
                    else "unknown"
                )
                missing_models.append(
                    {
                        "relative_path": f"{node_type}:{widget_value}",
                        "attempted_paths": model_paths,
                    }
                )
                logger.warning(
                    f"Standard loader model not found: {node_type} with '{widget_value}' (tried: {model_paths})"
                )

        # Process remaining nodes for model references
        remaining_nodes = {
            k: v for k, v in nodes_data.items() if k not in standard_nodes
        }
        all_model_paths = {model.relative_path for model in all_models}

        for _node_id, node_info in remaining_nodes.items():
            for widget_value in node_info.widgets_values:
                if isinstance(widget_value, str) and widget_value in all_model_paths:
                    # Found direct model path match
                    matching_models = [
                        m for m in all_models if m.relative_path == widget_value
                    ]

                    if len(matching_models) == 1:
                        model = matching_models[0]
                        if model.hash not in processed_hashes:
                            resolved_models.append(model)
                            processed_hashes.add(model.hash)
                            logger.debug(
                                f"Resolved custom node: {node_info.type} -> {widget_value} -> {model.hash}"
                            )
                    elif len(matching_models) > 1:
                        # Disambiguation needed - pick first and warn
                        model = matching_models[0]
                        if model.hash not in processed_hashes:
                            resolved_models.append(model)
                            processed_hashes.add(model.hash)
                            logger.warning(
                                f"Ambiguous model reference in {node_info.type}: '{widget_value}' matches {len(matching_models)} models, using first: {model.hash}"
                            )

        return resolved_models, missing_models

    def _extract_paths_from_node_info(
        self, node_type: str, node_info: WorkflowNode
    ) -> list[str]:
        """Extract model paths from node info using standard loader mappings."""
        widgets_values = node_info.widgets_values if node_info.widgets_values else []
        if not widgets_values:
            return []

        widget_index = self.model_config.get_widget_index_for_node(node_type)
        if widget_index >= len(widgets_values):
            return []

        widget_value = widgets_values[widget_index]
        if not isinstance(widget_value, str) or not widget_value.strip():
            return []

        # Reconstruct full paths using directory mappings
        return self.model_config.reconstruct_model_path(node_type, widget_value)
