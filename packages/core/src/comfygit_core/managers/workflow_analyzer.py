"""Workflow analysis manager - analyzes workflow dependencies and resolution status."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..analyzers.workflow_dependency_parser import WorkflowDependencyParser
from ..logging.logging_config import get_logger
from ..models.workflow import (
    DetailedWorkflowStatus,
    ResolutionResult,
    WorkflowAnalysisStatus,
    WorkflowDependencies,
)

if TYPE_CHECKING:
    from ..caching.workflow_cache import WorkflowCacheRepository
    from .pyproject_manager import PyprojectManager
    from .workflow_sync_manager import WorkflowSyncManager

logger = get_logger(__name__)


class WorkflowAnalyzer:
    """Analyzes workflow dependencies and resolution status."""

    def __init__(
        self,
        cec_path: Path,
        pyproject: PyprojectManager,
        workflow_cache: WorkflowCacheRepository,
        workflow_sync_manager: WorkflowSyncManager,
        environment_name: str
    ):
        self.cec_path = cec_path
        self.pyproject = pyproject
        self.workflow_cache = workflow_cache
        self.workflow_sync_manager = workflow_sync_manager
        self.environment_name = environment_name

    def analyze_workflow(self, name: str) -> WorkflowDependencies:
        """Analyze a single workflow for dependencies - with caching.

        NOTE: For best performance, use analyze_and_resolve_workflow() which
        caches BOTH analysis and resolution.

        Args:
            name: Workflow name

        Returns:
            WorkflowDependencies

        Raises:
            FileNotFoundError if workflow not found
        """
        workflow_path = self.workflow_sync_manager.get_workflow_path(name)

        # Check cache first
        cached = self.workflow_cache.get(
            env_name=self.environment_name,
            workflow_name=name,
            workflow_path=workflow_path,
            pyproject_path=self.pyproject.path
        )

        if cached is not None:
            logger.debug(f"Cache HIT for workflow '{name}'")
            return cached.dependencies

        logger.debug(f"Cache MISS for workflow '{name}' - running full analysis")

        # Cache miss - run full analysis
        parser = WorkflowDependencyParser(workflow_path, cec_path=self.cec_path)
        deps = parser.analyze_dependencies()

        # Store in cache (no resolution yet)
        self.workflow_cache.set(
            env_name=self.environment_name,
            workflow_name=name,
            workflow_path=workflow_path,
            dependencies=deps,
            resolution=None,
            pyproject_path=self.pyproject.path
        )

        return deps

    def analyze_and_resolve_workflow(
        self,
        name: str,
        resolver_func
    ) -> tuple[WorkflowDependencies, ResolutionResult]:
        """Analyze and resolve workflow with full caching.

        This is the preferred method for performance - caches BOTH analysis and resolution.

        Args:
            name: Workflow name
            resolver_func: Function to resolve workflow dependencies

        Returns:
            Tuple of (dependencies, resolution)

        Raises:
            FileNotFoundError if workflow not found
        """
        workflow_path = self.workflow_sync_manager.get_workflow_path(name)

        # Check cache
        cached = self.workflow_cache.get(
            env_name=self.environment_name,
            workflow_name=name,
            workflow_path=workflow_path,
            pyproject_path=self.pyproject.path
        )

        if cached and not cached.needs_reresolution and cached.resolution:
            # Full cache hit - both analysis and resolution valid
            logger.debug(f"Cache HIT (full) for workflow '{name}'")
            return (cached.dependencies, cached.resolution)

        if cached and cached.needs_reresolution:
            # Partial hit - workflow content valid but resolution stale
            logger.debug(f"Cache PARTIAL HIT for workflow '{name}' - re-resolving")
            dependencies = cached.dependencies
        else:
            # Full miss - analyze workflow
            logger.debug(f"Cache MISS for workflow '{name}' - full analysis + resolution")
            parser = WorkflowDependencyParser(workflow_path, cec_path=self.cec_path)
            dependencies = parser.analyze_dependencies()

        # Resolve (either from cache miss or stale resolution)
        resolution = resolver_func(dependencies)

        # Cache both analysis and resolution
        self.workflow_cache.set(
            env_name=self.environment_name,
            workflow_name=name,
            workflow_path=workflow_path,
            dependencies=dependencies,
            resolution=resolution,
            pyproject_path=self.pyproject.path
        )

        return (dependencies, resolution)

    def analyze_single_workflow_status(
        self,
        name: str,
        sync_state: str,
        installed_nodes: set[str] | None = None,
        resolver_func = None
    ) -> WorkflowAnalysisStatus:
        """Analyze a single workflow for dependencies and resolution status.

        This is read-only - no side effects, no copying, just analysis.

        Args:
            name: Workflow name
            sync_state: Sync state ("new", "modified", "deleted", "synced")
            installed_nodes: Pre-loaded set of installed node IDs (avoids re-reading pyproject)
            resolver_func: Function to resolve workflow dependencies

        Returns:
            WorkflowAnalysisStatus with complete dependency and resolution info
        """
        # Analyze and resolve workflow (cached)
        dependencies, resolution = self.analyze_and_resolve_workflow(name, resolver_func)

        # Calculate uninstalled nodes from current resolution
        if installed_nodes is None:
            installed_nodes = set(self.pyproject.nodes.get_existing().keys())

        resolved_packages = set(r.package_id for r in resolution.nodes_resolved if r.package_id)
        uninstalled_nodes = list(resolved_packages - installed_nodes)

        return WorkflowAnalysisStatus(
            name=name,
            sync_state=sync_state,
            dependencies=dependencies,
            resolution=resolution,
            uninstalled_nodes=uninstalled_nodes
        )

    def get_workflow_status(self, resolver_func) -> DetailedWorkflowStatus:
        """Get detailed workflow status with full dependency analysis.

        Analyzes ALL workflows in ComfyUI directory, checking dependencies
        and resolution status. This is read-only - no copying to .cec.

        Args:
            resolver_func: Function to resolve workflow dependencies

        Returns:
            DetailedWorkflowStatus with sync status and analysis for each workflow
        """
        sync_status = self.workflow_sync_manager.get_workflow_sync_status()
        installed_nodes = set(self.pyproject.nodes.get_existing().keys())

        all_workflow_names = sync_status.new + sync_status.modified + sync_status.synced
        analyzed: list[WorkflowAnalysisStatus] = []

        for name in all_workflow_names:
            if name in sync_status.new:
                state = "new"
            elif name in sync_status.modified:
                state = "modified"
            else:
                state = "synced"

            try:
                analysis = self.analyze_single_workflow_status(
                    name, state, installed_nodes, resolver_func
                )
                analyzed.append(analysis)
            except Exception as e:
                logger.error(f"Failed to analyze workflow {name}: {e}")

        return DetailedWorkflowStatus(
            sync_status=sync_status,
            analyzed_workflows=analyzed
        )