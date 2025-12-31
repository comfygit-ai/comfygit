"""Model path manager - handles model path stripping and category management."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..configs.model_config import ModelConfig
from ..logging.logging_config import get_logger
from ..models.workflow import ResolvedModel, Workflow, WorkflowNodeWidgetRef
from ..repositories.workflow_repository import WorkflowRepository
from ..utils.model_categories import get_model_category

if TYPE_CHECKING:
    from ..models.workflow import ResolutionResult
    from ..repositories.model_repository import ModelRepository
    from ..resolvers.model_resolver import ModelResolver

logger = get_logger(__name__)

# Default criticality levels for different model categories
CATEGORY_CRITICALITY_DEFAULTS = {
    "checkpoints": "flexible",
    "vae": "flexible",
    "text_encoders": "flexible",
    "loras": "flexible",
    "controlnet": "required",
    "clip_vision": "required",
    "style_models": "flexible",
    "embeddings": "flexible",
    "upscale_models": "flexible",
}


class ModelPathManager:
    """Manages model paths, categories, and path stripping for ComfyUI nodes."""

    def __init__(
        self,
        model_repository: ModelRepository,
        model_resolver: ModelResolver
    ):
        self.model_repository = model_repository
        self.model_resolver = model_resolver
        self.model_config = ModelConfig.load()

    def get_default_criticality(self, category: str) -> str:
        """Determine smart default criticality based on model category.

        Args:
            category: Model category (checkpoints, loras, etc.)

        Returns:
            Criticality level: "required", "flexible", or "optional"
        """
        return CATEGORY_CRITICALITY_DEFAULTS.get(category, "required")

    def get_category_for_node_ref(self, node_ref: WorkflowNodeWidgetRef) -> str:
        """Get model category from node type.

        Args:
            node_ref: Node widget reference

        Returns:
            Model category string
        """
        # First see if node type is explicitly mapped to a category.
        node_type = node_ref.node_type
        directories = self.model_config.get_directories_for_node(node_type)
        if directories:
            logger.debug(f"Found directory mapping for node type '{node_type}': {directories}")
            return directories[0]  # Use first directory as category

        # Next check if widget value path can be converted to category:
        category = get_model_category(node_ref.widget_value)
        logger.debug(f"Found directory mapping for widget value '{node_ref.widget_value}': {category}")
        return category

    def strip_base_directory_for_node(self, node_type: str, relative_path: str) -> str:
        """Strip base directory prefix from path for BUILTIN ComfyUI node loaders.

        ⚠️ IMPORTANT: This function should ONLY be called for builtin node types that
        are in the node_directory_mappings. Custom nodes should skip path updates entirely.

        ComfyUI builtin node loaders automatically prepend their base directories:
        - CheckpointLoaderSimple prepends "checkpoints/"
        - LoraLoader prepends "loras/"
        - VAELoader prepends "vae/"

        The widget value should NOT include the base directory to avoid path doubling.

        See: docs/knowledge/comfyui-node-loader-base-directories.md for detailed explanation.

        Args:
            node_type: BUILTIN ComfyUI node type (e.g., "CheckpointLoaderSimple")
            relative_path: Full path relative to models/ (e.g., "checkpoints/SD1.5/model.safetensors")

        Returns:
            Path without base directory prefix (e.g., "SD1.5/model.safetensors")

        Examples:
            >>> strip_base_directory_for_node("CheckpointLoaderSimple", "checkpoints/sd15/model.ckpt")
            "sd15/model.ckpt"

            >>> strip_base_directory_for_node("LoraLoader", "loras/style.safetensors")
            "style.safetensors"

            >>> strip_base_directory_for_node("CheckpointLoaderSimple", "checkpoints/a/b/c/model.ckpt")
            "a/b/c/model.ckpt"  # Subdirectories preserved
        """
        # Normalize to forward slashes for cross-platform compatibility (Windows uses backslashes)
        relative_path = relative_path.replace('\\', '/')

        base_dirs = self.model_config.get_directories_for_node(node_type)

        # Warn if called for custom node (should be skipped in caller)
        if not base_dirs:
            logger.warning(
                f"strip_base_directory_for_node called for unknown/custom node type: {node_type}. "
                f"Custom nodes should skip path updates entirely. Returning path unchanged."
            )
            return relative_path

        for base_dir in base_dirs:
            prefix = base_dir + "/"
            if relative_path.startswith(prefix):
                # Strip the base directory but preserve subdirectories
                return relative_path[len(prefix):]

        # Path doesn't have expected prefix - return unchanged
        return relative_path

    def check_path_needs_sync(
        self,
        resolved: ResolvedModel,
        workflow: Workflow
    ) -> bool:
        """Check if a resolved model's path differs from workflow JSON.

        Args:
            resolved: ResolvedModel with reference and resolved_model
            workflow: Loaded workflow JSON

        Returns:
            True if workflow path differs from expected resolved path
        """
        ref = resolved.reference
        model = resolved.resolved_model

        # Only check builtin nodes (custom nodes manage their own paths)
        if not self.model_config.is_model_loader_node(ref.node_type):
            return False

        # Can't sync if model didn't resolve
        if not model:
            return False

        # Get expected path after stripping base directory (already normalized to forward slashes)
        expected_path = self.strip_base_directory_for_node(
            ref.node_type,
            model.relative_path
        )

        # Normalize current path for comparison (handles Windows backslashes)
        current_path = ref.widget_value.replace('\\', '/')

        # If paths differ, check if current path exists with same hash (duplicate models)
        if current_path != expected_path:
            # Try to find the current path in model repository
            # For builtin loaders, we need to reconstruct the full path
            all_models = self.model_repository.get_all_models()

            # Try exact match with current path
            current_matches = self.model_resolver._try_exact_match(current_path, all_models)

            # If not found, try reconstructing the path (for builtin loaders)
            if not current_matches and self.model_config.is_model_loader_node(ref.node_type):
                reconstructed_paths = self.model_config.reconstruct_model_path(
                    ref.node_type, current_path
                )
                for path in reconstructed_paths:
                    current_matches = self.model_resolver._try_exact_match(path, all_models)
                    if current_matches:
                        break

            # If current path exists and has same hash as resolved model, no sync needed
            if current_matches and current_matches[0].hash == model.hash:
                return False

        # Return True if paths differ and current path is invalid or has different hash
        return current_path != expected_path

    def check_category_mismatch(
        self,
        resolved: ResolvedModel,
    ) -> tuple[bool, list[str], str | None]:
        """Check if model is in wrong category directory for its loader node.

        This is a functional issue (not cosmetic like path sync) - ComfyUI cannot
        load a model that's in the wrong directory for the node type.

        When a model exists in multiple locations (e.g., copied from checkpoints/
        to loras/), this checks if ANY location satisfies the requirement.
        Only flags mismatch if NO location is in an expected directory.

        Args:
            resolved: ResolvedModel with reference and resolved_model

        Returns:
            Tuple of (has_mismatch, expected_categories, actual_category)
        """
        ref = resolved.reference
        model = resolved.resolved_model

        # Skip if no resolved model (nothing to check)
        if not model:
            return (False, [], None)

        # Skip custom nodes - we don't know what paths they scan
        if not self.model_config.is_model_loader_node(ref.node_type):
            return (False, [], None)

        # Get expected directories for this node type
        expected_dirs = self.model_config.get_directories_for_node(ref.node_type)
        if not expected_dirs:
            return (False, [], None)

        # Extract actual category from resolved model path (first path component)
        path_parts = model.relative_path.replace('\\', '/').split('/')
        actual_category = path_parts[0] if path_parts else None

        # If resolved location is in expected directory, no mismatch
        if actual_category in expected_dirs:
            return (False, expected_dirs, actual_category)

        # Resolved location is wrong, but check if model exists in ANY valid location
        # This handles the case where user copied (not moved) the model
        all_locations = self.model_repository.get_locations(model.hash)
        for location in all_locations:
            loc_path_parts = location['relative_path'].replace('\\', '/').split('/')
            loc_category = loc_path_parts[0] if loc_path_parts else None
            if loc_category in expected_dirs:
                # Model exists in a valid location - no functional mismatch
                return (False, expected_dirs, actual_category)

        # No location in expected directory - this is a real mismatch
        return (True, expected_dirs, actual_category)

    def update_workflow_model_paths(
        self,
        workflow_path: Path,
        resolution: ResolutionResult,
        workflow_cache,
        environment_name: str
    ) -> None:
        """Update workflow JSON files with resolved and stripped model paths.

        IMPORTANT: Only updates paths for BUILTIN ComfyUI nodes. Custom nodes are
        skipped to preserve their original widget values and avoid breaking validation.

        This strips the base directory prefix (e.g., 'checkpoints/') from model paths
        because ComfyUI builtin node loaders automatically prepend their base directories.

        See: docs/knowledge/comfyui-node-loader-base-directories.md for detailed explanation.

        Args:
            workflow_path: Path to workflow JSON file
            resolution: Resolution result with ref→model mapping
            workflow_cache: Workflow cache repository
            environment_name: Environment name for cache invalidation

        Raises:
            FileNotFoundError if workflow not found
        """
        workflow_name = resolution.workflow_name
        workflow = WorkflowRepository.load(workflow_path)

        updated_count = 0
        skipped_count = 0

        # Update each resolved model's path in the workflow
        for resolved in resolution.models_resolved:
            ref = resolved.reference
            model = resolved.resolved_model

            # Skip if model is None (Type 1 optional unresolved)
            if model is None:
                continue

            node_id = ref.node_id
            widget_idx = ref.widget_index

            # Skip custom nodes - they have undefined path behavior
            if not self.model_config.is_model_loader_node(ref.node_type):
                logger.debug(
                    f"Skipping path update for custom node '{ref.node_type}' "
                    f"(node_id={node_id}, widget={widget_idx}). "
                    f"Custom nodes manage their own model paths."
                )
                skipped_count += 1
                continue

            # Update the node's widget value with resolved path
            if node_id in workflow.nodes:
                node = workflow.nodes[node_id]
                if widget_idx < len(node.widgets_values):
                    old_path = node.widgets_values[widget_idx]
                    # Strip base directory prefix for ComfyUI BUILTIN node loaders
                    # e.g., "checkpoints/sd15/model.ckpt" → "sd15/model.ckpt"
                    display_path = self.strip_base_directory_for_node(ref.node_type, model.relative_path)
                    node.widgets_values[widget_idx] = display_path
                    logger.debug(f"Updated node {node_id} widget {widget_idx}: {old_path} → {display_path}")
                    updated_count += 1

        # Only save if we actually updated something
        if updated_count > 0:
            WorkflowRepository.save(workflow, workflow_path)

            # Invalidate cache since workflow content changed
            workflow_cache.invalidate(
                env_name=environment_name,
                workflow_name=workflow_name
            )

            logger.info(
                f"Updated workflow JSON: {workflow_path} "
                f"({updated_count} builtin nodes updated, {skipped_count} custom nodes preserved)"
            )
        else:
            logger.debug(f"No path updates needed for workflow '{workflow_name}'")

        # Note: We intentionally do NOT update .cec here
        # The .cec copy represents "committed state" and should only be updated during commit
        # This ensures workflow status correctly shows as "new" or "modified" until committed

    def update_single_workflow_node_path(
        self,
        workflow_path: Path,
        model_ref: WorkflowNodeWidgetRef,
        model,
        workflow_cache,
        environment_name: str
    ) -> None:
        """Update a single node's widget value in workflow JSON.

        Args:
            workflow_path: Path to workflow JSON
            model_ref: Node widget reference
            model: Resolved model with path
            workflow_cache: Workflow cache repository
            environment_name: Environment name
        """
        if not workflow_path.exists():
            return

        workflow = WorkflowRepository.load(workflow_path)

        if model_ref.node_id in workflow.nodes:
            node = workflow.nodes[model_ref.node_id]
            if model_ref.widget_index < len(node.widgets_values):
                display_path = self.strip_base_directory_for_node(
                    model_ref.node_type,
                    model.relative_path
                )
                node.widgets_values[model_ref.widget_index] = display_path
                WorkflowRepository.save(workflow, workflow_path)

                # Invalidate cache since workflow content changed
                workflow_cache.invalidate(
                    env_name=environment_name,
                    workflow_name=workflow_path.stem
                )

                logger.debug(f"Updated workflow JSON node {model_ref.node_id}")