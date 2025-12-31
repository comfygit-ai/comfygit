"""Workflow resolver - handles node and model resolution for workflows."""

from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..models.manifest import ManifestModel, ManifestWorkflowModel
from ..models.protocols import ModelResolutionStrategy, NodeResolutionStrategy
from ..models.workflow import (
    ModelResolutionContext,
    NodeResolutionContext,
    ResolutionResult,
    ResolvedModel,
    ResolvedNodePackage,
    ScoredMatch,
    Workflow,
    WorkflowDependencies,
    WorkflowNode,
    WorkflowNodeWidgetRef,
)
from ..repositories.workflow_repository import WorkflowRepository
from ..resolvers.global_node_resolver import GlobalNodeResolver
from ..resolvers.model_resolver import ModelResolver
from ..utils.git import is_git_url

if TYPE_CHECKING:
    from ..caching.workflow_cache import WorkflowCacheRepository
    from ..models.shared import ModelWithLocation
    from ..repositories.model_repository import ModelRepository
    from ..repositories.node_mappings_repository import NodeMappingsRepository
    from .model_path_manager import ModelPathManager
    from .pyproject_manager import PyprojectManager

logger = get_logger(__name__)


class WorkflowResolver:
    """Handles node and model resolution for workflows."""

    def __init__(
        self,
        pyproject: PyprojectManager,
        model_repository: ModelRepository,
        node_mapping_repository: NodeMappingsRepository,
        workflow_cache: WorkflowCacheRepository,
        model_path_manager: ModelPathManager,
        environment_name: str
    ):
        self.pyproject = pyproject
        self.model_repository = model_repository
        self.node_mapping_repository = node_mapping_repository
        self.workflow_cache = workflow_cache
        self.model_path_manager = model_path_manager
        self.environment_name = environment_name

        # Create repository and inject into resolver
        self.global_node_resolver = GlobalNodeResolver(self.node_mapping_repository)
        self.model_resolver = ModelResolver(model_repository=self.model_repository)

    def normalize_package_id(self, package_id: str) -> str:
        """Normalize GitHub URLs to registry IDs if they exist in the registry.

        This prevents duplicate entries when users manually enter GitHub URLs
        for packages that exist in the registry.

        Args:
            package_id: Package ID (registry ID or GitHub URL)

        Returns:
            Normalized package ID (registry ID if URL matches, otherwise unchanged)
        """
        # Check if it's a GitHub URL
        if is_git_url(package_id):
            # Try to resolve to registry package
            if registry_pkg := self.global_node_resolver.resolve_github_url(package_id):
                return registry_pkg.id

        # Return as-is if not a GitHub URL or not in registry
        return package_id

    def resolve_workflow(self, analysis: WorkflowDependencies) -> ResolutionResult:
        """Attempt automatic resolution of workflow dependencies.

        Takes the provided analysis and tries to resolve:
        - Missing nodes → node packages from registry/GitHub using GlobalNodeResolver
        - Model references → actual model files in index

        Returns ResolutionResult showing what was resolved and what remains ambiguous.
        Does NOT modify pyproject.toml - that happens in fix_workflow().

        Args:
            analysis: Workflow dependencies from analyze_workflow()

        Returns:
            ResolutionResult with resolved and unresolved dependencies
        """
        nodes_resolved: list[ResolvedNodePackage] = []
        nodes_unresolved: list[WorkflowNode] = []
        nodes_ambiguous: list[list[ResolvedNodePackage]] = []

        models_resolved: list[ResolvedModel] = []
        models_unresolved: list[WorkflowNodeWidgetRef] = []
        models_ambiguous: list[list[ResolvedModel]] = []

        workflow_name = analysis.workflow_name

        # Load workflow JSON for path comparison
        try:
            workflow_path = Path(analysis.workflow_path)
            workflow = WorkflowRepository.load(workflow_path)
        except FileNotFoundError:
            workflow = None
            logger.warning(f"Could not load workflow '{workflow_name}' for path sync check")

        # Build node resolution context with per-workflow custom_node_map
        node_context = NodeResolutionContext(
            installed_packages=self.pyproject.nodes.get_existing(),
            custom_mappings=self.pyproject.workflows.get_custom_node_map(workflow_name),
            workflow_name=workflow_name,
            auto_select_ambiguous=True # TODO: Make configurable
        )

        # Deduplicate node types (same type appears multiple times in workflow)
        # Prefer nodes with properties when deduplicating
        unique_nodes: dict[str, WorkflowNode] = {}
        for node in analysis.non_builtin_nodes:
            if node.type not in unique_nodes:
                unique_nodes[node.type] = node
            else:
                # Prefer node with properties over one without
                if node.properties.get('cnr_id') and not unique_nodes[node.type].properties.get('cnr_id'):
                    # TODO: Log if the same node type already exists with a different cnr_id
                    unique_nodes[node.type] = node

        logger.debug(f"Resolving {len(unique_nodes)} unique node types from {len(analysis.non_builtin_nodes)} total non-builtin nodes")

        # Resolve each unique node type with context
        for node_type, node in unique_nodes.items():
            logger.debug(f"Trying to resolve node: {node}")
            resolved_packages = self.global_node_resolver.resolve_single_node_with_context(node, node_context)

            if resolved_packages is None:
                # Not resolved - trigger strategy
                logger.debug(f"Node not found: {node}")
                nodes_unresolved.append(node)
            elif len(resolved_packages) == 1:
                # Single match - cleanly resolved
                logger.debug(f"Resolved node: {resolved_packages[0]}")
                nodes_resolved.append(resolved_packages[0])
            else:
                # Multiple matches from registry (ambiguous)
                nodes_ambiguous.append(resolved_packages)

        # Build context with full ManifestWorkflowModel objects
        # This enables download intent detection and other advanced resolution logic
        previous_resolutions = {}
        workflow_models = self.pyproject.workflows.get_workflow_models(workflow_name)

        for manifest_model in workflow_models:
            # Store full ManifestWorkflowModel object for each node reference
            # This provides access to hash, sources, status, relative_path, etc.
            for ref in manifest_model.nodes:
                previous_resolutions[ref] = manifest_model

        # Get global models table for download intent creation
        global_models_dict = {}
        try:
            all_global_models = self.pyproject.models.get_all()
            for model in all_global_models:
                global_models_dict[model.hash] = model
        except Exception as e:
            logger.warning(f"Failed to load global models table: {e}")

        model_context = ModelResolutionContext(
            workflow_name=workflow_name,
            previous_resolutions=previous_resolutions,
            global_models=global_models_dict,
            auto_select_ambiguous=True # TODO: Make configurable
        )

        # Deduplicate model refs by (widget_value, node_type) before resolving
        # This ensures status reporting shows accurate counts (not inflated by duplicates)
        model_groups: dict[tuple[str, str], list[WorkflowNodeWidgetRef]] = {}
        for model_ref in analysis.found_models:
            key = (model_ref.widget_value, model_ref.node_type)
            if key not in model_groups:
                model_groups[key] = []
            model_groups[key].append(model_ref)

        # Resolve each unique model group (one resolution per unique model)
        for (widget_value, node_type), refs_in_group in model_groups.items():
            # Use first ref as representative for resolution
            primary_ref = refs_in_group[0]

            result = self.model_resolver.resolve_model(primary_ref, model_context)

            if result is None:
                # Model not found at all - add primary ref only (deduplicated)
                logger.debug(f"Failed to resolve model: {primary_ref}")
                models_unresolved.append(primary_ref)
            elif len(result) == 1:
                # Clean resolution (exact match or from pyproject cache)
                resolved_model = result[0]

                # Check if path needs syncing (only for builtin nodes with resolved models)
                if workflow and resolved_model.resolved_model:
                    resolved_model.needs_path_sync = self.model_path_manager.check_path_needs_sync(
                        resolved_model,
                        workflow
                    )

                # Check category mismatch (functional issue - model in wrong directory)
                if resolved_model.resolved_model:
                    has_mismatch, expected, actual = self.model_path_manager.check_category_mismatch(resolved_model)
                    resolved_model.has_category_mismatch = has_mismatch
                    resolved_model.expected_categories = expected
                    resolved_model.actual_category = actual

                logger.debug(f"Resolved model: {resolved_model}")
                models_resolved.append(resolved_model)
            elif len(result) > 1:
                # Ambiguous - multiple matches (use primary ref)
                logger.debug(f"Ambiguous model: {result}")
                models_ambiguous.append(result)
            else:
                # No resolution possible - add primary ref only (deduplicated)
                logger.debug(f"Failed to resolve model: {primary_ref}, result: {result}")
                models_unresolved.append(primary_ref)

        return ResolutionResult(
            workflow_name=workflow_name,
            nodes_resolved=nodes_resolved,
            nodes_unresolved=nodes_unresolved,
            nodes_ambiguous=nodes_ambiguous,
            models_resolved=models_resolved,
            models_unresolved=models_unresolved,
            models_ambiguous=models_ambiguous,
        )

    def fix_resolution(
        self,
        resolution: ResolutionResult,
        node_strategy: NodeResolutionStrategy | None = None,
        model_strategy: ModelResolutionStrategy | None = None
    ) -> ResolutionResult:
        """Fix remaining issues using strategies with progressive writes.

        Takes ResolutionResult from resolve_workflow() and uses strategies to resolve ambiguities.
        ALL user choices are written immediately (progressive mode):
        - Each model resolution writes to pyproject + workflow JSON
        - Each node mapping writes to per-workflow custom_node_map
        - Ctrl+C preserves partial progress

        Args:
            resolution: Result from resolve_workflow()
            node_strategy: Strategy for handling unresolved/ambiguous nodes
            model_strategy: Strategy for handling ambiguous/missing models

        Returns:
            Updated ResolutionResult with fixes applied
        """
        workflow_name = resolution.workflow_name

        # Start with what was already resolved
        nodes_to_add = list(resolution.nodes_resolved)
        models_to_add = list(resolution.models_resolved)

        remaining_nodes_ambiguous: list[list[ResolvedNodePackage]] = []
        remaining_nodes_unresolved: list[WorkflowNode] = []
        remaining_models_ambiguous: list[list[ResolvedModel]] = []
        remaining_models_unresolved: list[WorkflowNodeWidgetRef] = []

        # ========== NODE RESOLUTION (UNIFIED) ==========

        if not node_strategy:
            # No strategy - keep everything as unresolved
            remaining_nodes_ambiguous = list(resolution.nodes_ambiguous)
            remaining_nodes_unresolved = list(resolution.nodes_unresolved)
        else:
            # Build context with search function
            node_context = NodeResolutionContext(
                installed_packages=self.pyproject.nodes.get_existing(),
                custom_mappings=self.pyproject.workflows.get_custom_node_map(workflow_name),
                workflow_name=workflow_name,
                search_fn=self.global_node_resolver.search_packages,
                auto_select_ambiguous=True  # TODO: Make configurable
            )

            # Unified loop: handle both ambiguous and unresolved nodes
            all_unresolved_nodes: list[tuple[str, list[ResolvedNodePackage]]] = []

            # Ambiguous nodes (have candidates)
            for packages in resolution.nodes_ambiguous:
                if packages:
                    node_type = packages[0].node_type
                    all_unresolved_nodes.append((node_type, packages))

            # Missing nodes (no candidates)
            for node in resolution.nodes_unresolved:
                all_unresolved_nodes.append((node.type, []))

            # Resolve each node
            for node_type, candidates in all_unresolved_nodes:
                try:
                    selected = node_strategy.resolve_unknown_node(node_type, candidates, node_context)

                    if selected is None:
                        # User skipped - remains unresolved
                        if candidates:
                            remaining_nodes_ambiguous.append(candidates)
                        else:
                            # Create WorkflowNode for unresolved tracking
                            remaining_nodes_unresolved.append(WorkflowNode(id="", type=node_type))
                        logger.debug(f"Skipped: {node_type}")
                        continue

                    # Handle optional nodes
                    if selected.match_type == 'optional':
                        # PROGRESSIVE: Save optional node mapping
                        if workflow_name:
                            self.pyproject.workflows.set_custom_node_mapping(
                                workflow_name, node_type, None
                            )
                        logger.info(f"Marked node '{node_type}' as optional")
                        continue

                    # Handle resolved nodes
                    nodes_to_add.append(selected)
                    node_id = selected.package_data.id if selected.package_data else selected.package_id

                    if not node_id:
                        logger.warning(f"No package ID for resolved node '{node_type}'")
                        continue

                    normalized_id = self.normalize_package_id(node_id)

                    # PROGRESSIVE: Save user-confirmed node mapping
                    user_intervention_types = ("user_confirmed", "manual", "heuristic")
                    if selected.match_type in user_intervention_types and workflow_name:
                        self.pyproject.workflows.set_custom_node_mapping(
                            workflow_name, node_type, normalized_id
                        )
                        logger.info(f"Saved custom_node_map: {node_type} -> {normalized_id}")

                    # PROGRESSIVE: Write to workflow.nodes immediately
                    if workflow_name:
                        self._write_single_node_resolution(workflow_name, normalized_id)

                    logger.info(f"Resolved node: {node_type} -> {normalized_id}")

                except Exception as e:
                    logger.error(f"Failed to resolve {node_type}: {e}")
                    if candidates:
                        remaining_nodes_ambiguous.append(candidates)
                    else:
                        remaining_nodes_unresolved.append(WorkflowNode(id="", type=node_type))

        # ========== MODEL RESOLUTION (NEW UNIFIED FLOW) ==========

        if not model_strategy:
            # No strategy - keep everything as unresolved
            remaining_models_ambiguous = list(resolution.models_ambiguous)
            remaining_models_unresolved = list(resolution.models_unresolved)
        else:
            # Get global models table for download intent creation
            global_models_dict = {}
            try:
                all_global_models = self.pyproject.models.get_all()
                for model in all_global_models:
                    global_models_dict[model.hash] = model
            except Exception as e:
                logger.warning(f"Failed to load global models table: {e}")

            # Build context with search function and downloader
            model_context = ModelResolutionContext(
                workflow_name=workflow_name,
                global_models=global_models_dict,
                search_fn=self.search_models,
                downloader=None,  # Downloader is injected at higher level
                auto_select_ambiguous=True  # TODO: Make configurable
            )

            # Unified loop: handle both ambiguous and unresolved models
            all_unresolved_models: list[tuple[WorkflowNodeWidgetRef, list[ResolvedModel]]] = []

            # Ambiguous models (have candidates)
            for resolved_model_list in resolution.models_ambiguous:
                if resolved_model_list:
                    model_ref = resolved_model_list[0].reference
                    all_unresolved_models.append((model_ref, resolved_model_list))

            # Missing models (no candidates)
            for model_ref in resolution.models_unresolved:
                all_unresolved_models.append((model_ref, []))

            # DEDUPLICATION: Group by (widget_value, node_type)
            model_groups: dict[tuple[str, str], list[tuple[WorkflowNodeWidgetRef, list[ResolvedModel]]]] = {}

            for model_ref, candidates in all_unresolved_models:
                # Group key: (widget_value, node_type)
                # This ensures same model in same loader type gets resolved once
                key = (model_ref.widget_value, model_ref.node_type)
                if key not in model_groups:
                    model_groups[key] = []
                model_groups[key].append((model_ref, candidates))

            # Resolve each group (one prompt per unique model)
            for (widget_value, node_type), group in model_groups.items():
                # Extract all refs and candidates
                all_refs_in_group = [ref for ref, _ in group]
                primary_ref, primary_candidates = group[0]

                # Log deduplication for debugging
                if len(all_refs_in_group) > 1:
                    node_ids = ", ".join(f"#{ref.node_id}" for ref in all_refs_in_group)
                    logger.info(f"Deduplicating model '{widget_value}' found in nodes: {node_ids}")

                try:
                    # Prompt user once for this model
                    resolved = model_strategy.resolve_model(primary_ref, primary_candidates, model_context)

                    if resolved is None:
                        # User skipped - remains unresolved for ALL refs
                        for ref in all_refs_in_group:
                            remaining_models_unresolved.append(ref)
                        logger.debug(f"Skipped: {widget_value}")
                        continue

                    # PROGRESSIVE: Write with ALL refs at once
                    if workflow_name:
                        self._write_model_resolution_grouped(workflow_name, resolved, all_refs_in_group)

                    # Add to results for ALL refs (needed for update_workflow_model_paths)
                    for ref in all_refs_in_group:
                        # Create ResolvedModel for each ref pointing to same resolved model
                        ref_resolved = ResolvedModel(
                            workflow=workflow_name,
                            reference=ref,
                            resolved_model=resolved.resolved_model,
                            model_source=resolved.model_source,
                            is_optional=resolved.is_optional,
                            match_type=resolved.match_type,
                            match_confidence=resolved.match_confidence,
                            target_path=resolved.target_path,
                            needs_path_sync=resolved.needs_path_sync
                        )
                        models_to_add.append(ref_resolved)

                    # Log result
                    if resolved.is_optional:
                        logger.info(f"Marked as optional: {widget_value}")
                    elif resolved.resolved_model:
                        logger.info(f"Resolved: {widget_value} → {resolved.resolved_model.filename}")
                    else:
                        logger.info(f"Marked as optional (unresolved): {widget_value}")

                except Exception as e:
                    logger.error(f"Failed to resolve {widget_value}: {e}")
                    for ref in all_refs_in_group:
                        remaining_models_unresolved.append(ref)

        # Build updated result
        result = ResolutionResult(
            workflow_name=workflow_name,
            nodes_resolved=nodes_to_add,
            nodes_unresolved=remaining_nodes_unresolved,
            nodes_ambiguous=remaining_nodes_ambiguous,
            models_resolved=models_to_add,
            models_unresolved=remaining_models_unresolved,
            models_ambiguous=remaining_models_ambiguous,
        )

        # Batch update workflow JSON with all resolved model paths
        # This ensures all model paths are synced after interactive resolution
        # Uses consistent node IDs from same parse session (no cache mismatch issues)
        self.model_path_manager.update_workflow_model_paths(
            self._get_workflow_path(workflow_name),
            result,
            self.workflow_cache,
            self.environment_name
        )

        return result

    def _get_workflow_path(self, workflow_name: str) -> Path:
        """Get workflow path from workflow sync manager or cec path."""
        # This is a simplified version - in real implementation should use workflow_sync_manager
        from pathlib import Path
        comfyui_path = self.pyproject.path.parent.parent.parent  # Assuming standard structure
        workflows_dir = comfyui_path / "user" / "default" / "workflows"
        return workflows_dir / f"{workflow_name}.json"

    def _write_single_node_resolution(
        self,
        workflow_name: str,
        node_package_id: str
    ) -> None:
        """Write a single node resolution immediately (progressive mode).

        Updates workflow.nodes section in pyproject.toml for ONE node.
        This enables Ctrl+C safety and auto-resume.

        Args:
            workflow_name: Workflow being resolved
            node_package_id: Package ID to add to workflow.nodes
        """
        # Get existing workflow node packages from pyproject
        workflows_config = self.pyproject.workflows.get_all_with_resolutions()
        workflow_config = workflows_config.get(workflow_name, {})
        existing_nodes = set(workflow_config.get('nodes', []))

        # Add new package (set handles deduplication)
        existing_nodes.add(node_package_id)

        # Write back to pyproject
        self.pyproject.workflows.set_node_packs(workflow_name, existing_nodes)
        logger.debug(f"Added {node_package_id} to workflow '{workflow_name}' nodes")

    def _write_single_model_resolution(
        self,
        workflow_name: str,
        resolved: ResolvedModel
    ) -> None:
        """Write a single model resolution immediately (progressive mode).

        Builds ManifestWorkflowModel from resolved model and writes to both:
        1. Global models table (if resolved)
        2. Workflow models list (unified)

        Supports download intents (status=unresolved, sources=[URL], relative_path=path).

        Args:
            workflow_name: Workflow being resolved
            resolved: ResolvedModel with reference + resolved model + flags
        """
        model_ref = resolved.reference
        model = resolved.resolved_model

        # Determine category and criticality
        category = self.model_path_manager.get_category_for_node_ref(model_ref)

        # Override criticality if marked optional
        if resolved.is_optional:
            criticality = "optional"
        else:
            criticality = self.model_path_manager.get_default_criticality(category)

        # NEW: Handle download intent case
        if resolved.match_type == "download_intent":
            manifest_model = ManifestWorkflowModel(
                filename=model_ref.widget_value,
                category=category,
                criticality=criticality,
                status="unresolved",  # No hash yet
                nodes=[model_ref],
                sources=[resolved.model_source] if resolved.model_source else [],  # URL
                relative_path=resolved.target_path.as_posix() if resolved.target_path else None  # Target path
            )
            self.pyproject.workflows.add_workflow_model(workflow_name, manifest_model)

            # Invalidate cache so download intent is detected on next resolution
            self.workflow_cache.invalidate(
                env_name=self.environment_name,
                workflow_name=workflow_name
            )

            return

        # Build manifest model
        if model is None:
            # Model without hash - always unresolved (even if optional)
            # Optional means "workflow works without it", not "resolved"
            manifest_model = ManifestWorkflowModel(
                filename=model_ref.widget_value,
                category=category,
                criticality=criticality,
                status="unresolved",
                nodes=[model_ref],
                sources=[]
            )
        else:
            # Resolved model - fetch sources from repository
            sources = []
            if model.hash:
                sources_from_repo = self.model_repository.get_sources(model.hash)
                sources = [s['url'] for s in sources_from_repo]

            manifest_model = ManifestWorkflowModel(
                hash=model.hash,
                filename=model.filename,
                category=category,
                criticality=criticality,
                status="resolved",
                nodes=[model_ref],
                sources=sources
            )

            # Add to global table with sources
            global_model = ManifestModel(
                hash=model.hash,
                filename=model.filename,
                size=model.file_size,
                relative_path=model.relative_path,
                category=category,
                sources=sources
            )
            self.pyproject.models.add_model(global_model)

        # Progressive write to workflow
        self.pyproject.workflows.add_workflow_model(workflow_name, manifest_model)

        # NOTE: Workflow JSON path update moved to batch operation at end of fix_resolution()
        # Progressive JSON updates fail when cache has stale node IDs (node lookup mismatch)
        # Batch update is more efficient and ensures consistent node IDs within same parse session

    def _write_model_resolution_grouped(
        self,
        workflow_name: str,
        resolved: ResolvedModel,
        all_refs: list[WorkflowNodeWidgetRef]
    ) -> None:
        """Write model resolution for multiple node references (deduplicated).

        This is the deduplication-aware version of _write_single_model_resolution().
        When the same model appears in multiple nodes, all refs are written together
        in a single ManifestWorkflowModel entry.

        Args:
            workflow_name: Workflow being resolved
            resolved: ResolvedModel with resolution result
            all_refs: ALL node references for this model (deduplicated group)
        """
        # Use primary ref for category determination
        primary_ref = resolved.reference
        model = resolved.resolved_model

        # Determine category and criticality
        category = self.model_path_manager.get_category_for_node_ref(primary_ref)

        # Override criticality if marked optional
        if resolved.is_optional:
            criticality = "optional"
        else:
            criticality = self.model_path_manager.get_default_criticality(category)

        # Handle download intent case
        if resolved.match_type == "download_intent":
            manifest_model = ManifestWorkflowModel(
                filename=primary_ref.widget_value,
                category=category,
                criticality=criticality,
                status="unresolved",
                nodes=all_refs,  # ALL REFS!
                sources=[resolved.model_source] if resolved.model_source else [],
                relative_path=resolved.target_path.as_posix() if resolved.target_path else None
            )
            self.pyproject.workflows.add_workflow_model(workflow_name, manifest_model)

            # Invalidate cache
            self.workflow_cache.invalidate(
                env_name=self.environment_name,
                workflow_name=workflow_name
            )
            return

        # Build manifest model
        if model is None:
            # Model without hash - unresolved
            manifest_model = ManifestWorkflowModel(
                filename=primary_ref.widget_value,
                category=category,
                criticality=criticality,
                status="unresolved",
                nodes=all_refs,  # ALL REFS!
                sources=[]
            )
        else:
            # Resolved model - fetch sources from repository
            sources = []
            if model.hash:
                sources_from_repo = self.model_repository.get_sources(model.hash)
                sources = [s['url'] for s in sources_from_repo]

            manifest_model = ManifestWorkflowModel(
                hash=model.hash,
                filename=model.filename,
                category=category,
                criticality=criticality,
                status="resolved",
                nodes=all_refs,  # ALL REFS!
                sources=sources
            )

            # Add to global table with sources
            global_model = ManifestModel(
                hash=model.hash,
                filename=model.filename,
                size=model.file_size,
                relative_path=model.relative_path,
                category=category,
                sources=sources
            )
            self.pyproject.models.add_model(global_model)

        # Progressive write to workflow
        self.pyproject.workflows.add_workflow_model(workflow_name, manifest_model)

        # Log grouped write
        if len(all_refs) > 1:
            node_ids = ", ".join(f"#{ref.node_id}" for ref in all_refs)
            logger.debug(f"Wrote grouped model resolution for nodes: {node_ids}")

    def search_models(
        self,
        search_term: str,
        node_type: str | None = None,
        limit: int = 9
    ) -> list[ScoredMatch]:
        """Search for models using SQL + fuzzy matching.

        Combines fast SQL LIKE search with difflib scoring for ranked results.

        Args:
            search_term: Search term (filename, partial name, etc.)
            node_type: Optional node type to filter by category
            limit: Maximum number of results to return

        Returns:
            List of ScoredMatch objects sorted by relevance (highest first)
        """
        from ..configs.model_config import ModelConfig

        # If node_type provided, filter by category
        if node_type:
            model_config = ModelConfig.load()
            directories = model_config.get_directories_for_node(node_type)

            if directories:
                # Get models from all relevant categories
                candidates = []
                for directory in directories:
                    models = self.model_repository.get_by_category(directory)
                    candidates.extend(models)
            else:
                # Unknown node type - search all models
                candidates = self.model_repository.search(search_term)
        else:
            # No node type - search all models
            candidates = self.model_repository.search(search_term)

        if not candidates:
            return []

        # Score candidates using fuzzy matching
        scored = []
        search_lower = search_term.lower()
        search_stem = Path(search_term).stem.lower()

        for model in candidates:
            filename_lower = model.filename.lower()
            filename_stem = Path(model.filename).stem.lower()

            # Calculate scores for both full filename and stem
            full_score = SequenceMatcher(None, search_lower, filename_lower).ratio()
            stem_score = SequenceMatcher(None, search_stem, filename_stem).ratio()

            # Use best score
            score = max(full_score, stem_score)

            # Boost exact substring matches
            if search_lower in filename_lower:
                score = min(1.0, score + 0.15)

            if score > 0.3:  # Minimum 30% similarity threshold
                confidence = "high" if score > 0.8 else "good" if score > 0.6 else "possible"
                scored.append(ScoredMatch(
                    model=model,
                    score=score,
                    confidence=confidence
                ))

        # Sort by score descending
        scored.sort(key=lambda x: x.score, reverse=True)

        return scored[:limit]

    def apply_resolution(
        self,
        resolution: ResolutionResult,
        config: dict | None = None
    ) -> None:
        """Apply resolutions with smart defaults and reconciliation.

        Auto-applies sensible criticality defaults, etc.

        Args:
            resolution: Result with auto-resolved dependencies from resolve_workflow()
            config: Optional in-memory config for batched writes. If None, loads and saves immediately.
        """
        is_batch = config is not None
        if not is_batch:
            config = self.pyproject.load()

        workflow_name = resolution.workflow_name

        # Phase 1: Reconcile nodes (unchanged)
        target_node_pack_ids = set()
        target_node_types = set()

        for pkg in resolution.nodes_resolved:
            if pkg.is_optional:
                target_node_types.add(pkg.node_type)
            elif pkg.package_id is not None:
                normalized_id = self.normalize_package_id(pkg.package_id)
                target_node_pack_ids.add(normalized_id)
                target_node_types.add(pkg.node_type)

        for node in resolution.nodes_unresolved:
            target_node_types.add(node.type)
        for packages in resolution.nodes_ambiguous:
            if packages:
                target_node_types.add(packages[0].node_type)

        if target_node_pack_ids:
            self.pyproject.workflows.set_node_packs(workflow_name, target_node_pack_ids, config=config)
        else:
            self.pyproject.workflows.set_node_packs(workflow_name, None, config=config)

        # Reconcile custom_node_map
        existing_custom_map = self.pyproject.workflows.get_custom_node_map(workflow_name, config=config)
        for node_type in list(existing_custom_map.keys()):
            if node_type not in target_node_types:
                self.pyproject.workflows.remove_custom_node_mapping(workflow_name, node_type, config=config)

        # Phase 2: Build ManifestWorkflowModel entries with smart defaults
        manifest_models: list[ManifestWorkflowModel] = []

        # Group resolved models by hash
        hash_to_refs: dict[str, list[WorkflowNodeWidgetRef]] = {}
        for resolved in resolution.models_resolved:
            if resolved.resolved_model:
                model_hash = resolved.resolved_model.hash
                if model_hash not in hash_to_refs:
                    hash_to_refs[model_hash] = []
                hash_to_refs[model_hash].append(resolved.reference)
            elif resolved.match_type == "download_intent":
                # Download intent from previous session - preserve it in manifest
                category = self.model_path_manager.get_category_for_node_ref(resolved.reference)
                manifest_model = ManifestWorkflowModel(
                    filename=resolved.reference.widget_value,
                    category=category,
                    criticality="flexible",
                    status="unresolved",
                    nodes=[resolved.reference],
                    sources=[resolved.model_source] if resolved.model_source else [],
                    relative_path=resolved.target_path.as_posix() if resolved.target_path else None
                )
                manifest_models.append(manifest_model)
            elif resolved.is_optional:
                # Type C: Optional unresolved (user marked as optional, no model data)
                category = self.model_path_manager.get_category_for_node_ref(resolved.reference)
                manifest_model = ManifestWorkflowModel(
                    filename=resolved.reference.widget_value,
                    category=category,
                    criticality="optional",
                    status="unresolved",
                    nodes=[resolved.reference],
                    sources=[]
                )
                manifest_models.append(manifest_model)

        # Create manifest entries for resolved models
        for model_hash, refs in hash_to_refs.items():
            # Get model from first resolved entry
            model = next(
                (r.resolved_model for r in resolution.models_resolved if r.resolved_model and r.resolved_model.hash == model_hash),
                None
            )
            if not model:
                continue

            # Determine criticality with smart defaults
            criticality = self.model_path_manager.get_default_criticality(model.category)

            # Fetch sources from repository to enrich global table
            sources_from_repo = self.model_repository.get_sources(model.hash)
            sources = [s['url'] for s in sources_from_repo]

            # Workflow model: lightweight reference (no sources - hash is the key)
            manifest_model = ManifestWorkflowModel(
                hash=model.hash,
                filename=model.filename,
                category=model.category,
                criticality=criticality,
                status="resolved",
                nodes=refs,
                sources=[]  # Empty - sources stored in global table only
            )
            manifest_models.append(manifest_model)

            # Global table: enrich with sources from SQLite
            global_model = ManifestModel(
                hash=model.hash,
                filename=model.filename,
                size=model.file_size,
                relative_path=model.relative_path,
                category=model.category,
                sources=sources  # From SQLite - authoritative source
            )
            self.pyproject.models.add_model(global_model, config=config)

        # Load existing workflow models to preserve download intents from previous sessions
        existing_workflow_models = self.pyproject.workflows.get_workflow_models(workflow_name, config=config)
        existing_by_filename = {m.filename: m for m in existing_workflow_models}

        # Add unresolved models
        for ref in resolution.models_unresolved:
            category = self.model_path_manager.get_category_for_node_ref(ref)
            criticality = self.model_path_manager.get_default_criticality(category)

            # Check if this model already has a download intent from a previous session
            existing = existing_by_filename.get(ref.widget_value)
            sources = []
            relative_path = None
            if existing and existing.status == "unresolved" and existing.sources:
                # Preserve download intent from previous session
                sources = existing.sources
                relative_path = existing.relative_path
                logger.debug(f"Preserving download intent for '{ref.widget_value}': sources={sources}, path={relative_path}")

            manifest_model = ManifestWorkflowModel(
                filename=ref.widget_value,
                category=category,
                criticality=criticality,
                status="unresolved",
                nodes=[ref],
                sources=sources,
                relative_path=relative_path
            )
            manifest_models.append(manifest_model)

        # Write all models to workflow
        self.pyproject.workflows.set_workflow_models(workflow_name, manifest_models, config=config)

        # Clean up orphaned workflows from pyproject.toml
        # This handles workflows deleted from ComfyUI (whether committed or never-committed)
        comfyui_path = self.pyproject.path.parent.parent.parent  # Assuming standard structure
        comfyui_workflows = comfyui_path / "user" / "default" / "workflows"
        workflows_in_pyproject = set(config.get('tool', {}).get('comfygit', {}).get('workflows', {}).keys())
        workflows_in_comfyui = set()
        if comfyui_workflows.exists():
            workflows_in_comfyui = {f.stem for f in comfyui_workflows.glob("*.json")}

        orphaned_workflows = workflows_in_pyproject - workflows_in_comfyui
        if orphaned_workflows:
            removed_count = self.pyproject.workflows.remove_workflows(list(orphaned_workflows), config=config)
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} deleted workflow(s) from pyproject.toml")

        # Clean up orphaned models (must run AFTER workflow sections are removed)
        self.pyproject.models.cleanup_orphans(config=config)

        # Save if not in batch mode
        if not is_batch:
            self.pyproject.save(config)

        # Phase 3: Update workflow JSON with resolved paths
        self.model_path_manager.update_workflow_model_paths(
            self._get_workflow_path(workflow_name),
            resolution,
            self.workflow_cache,
            self.environment_name
        )