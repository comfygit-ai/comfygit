"""Auto workflow tracking - all workflows in ComfyUI are automatically managed."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..models.protocols import ModelResolutionStrategy, NodeResolutionStrategy
from ..models.workflow import (
    DetailedWorkflowStatus,
    ResolutionResult,
    WorkflowAnalysisStatus,
    WorkflowDependencies,
    WorkflowSyncStatus,
)
from ..resolvers.model_resolver import ModelResolver
from ..services.model_downloader import BatchDownloadCallbacks
from .model_path_manager import ModelPathManager
from .workflow_analyzer import WorkflowAnalyzer
from .workflow_model_download_manager import WorkflowModelDownloadManager
from .workflow_resolver import WorkflowResolver
from .workflow_sync_manager import WorkflowSyncManager

if TYPE_CHECKING:
    from ..caching.workflow_cache import WorkflowCacheRepository
    from ..repositories.model_repository import ModelRepository
    from ..repositories.node_mappings_repository import NodeMappingsRepository
    from ..services.model_downloader import ModelDownloader
    from .pyproject_manager import PyprojectManager

logger = get_logger(__name__)


class WorkflowManager:
    """Manages all workflows automatically by orchestrating specialized sub-managers.

    This is the main entry point for workflow operations. It delegates to:
    - WorkflowSyncManager: Sync between ComfyUI and .cec directories
    - WorkflowAnalyzer: Analyze workflow dependencies and status
    - WorkflowResolver: Resolve nodes and models for workflows
    - ModelPathManager: Manage model paths and directory stripping
    - WorkflowModelDownloadManager: Handle model downloads and updates
    """

    def __init__(
        self,
        comfyui_path: Path,
        cec_path: Path,
        pyproject: PyprojectManager,
        model_repository: ModelRepository,
        node_mapping_repository: NodeMappingsRepository,
        model_downloader: ModelDownloader,
        workflow_cache: WorkflowCacheRepository,
        environment_name: str
    ):
        self.comfyui_path = comfyui_path
        self.cec_path = cec_path
        self.pyproject = pyproject
        self.environment_name = environment_name

        # Initialize specialized managers
        self.sync_manager = WorkflowSyncManager(
            comfyui_path=comfyui_path,
            cec_path=cec_path,
            workflow_cache=workflow_cache,
            environment_name=environment_name
        )

        self.path_manager = ModelPathManager(
            model_repository=model_repository,
            model_resolver=ModelResolver(model_repository=model_repository)
        )

        self.analyzer = WorkflowAnalyzer(
            cec_path=cec_path,
            pyproject=pyproject,
            workflow_cache=workflow_cache,
            workflow_sync_manager=self.sync_manager,
            environment_name=environment_name
        )

        self.resolver = WorkflowResolver(
            pyproject=pyproject,
            model_repository=model_repository,
            node_mapping_repository=node_mapping_repository,
            workflow_cache=workflow_cache,
            model_path_manager=self.path_manager,
            environment_name=environment_name
        )

        self.download_manager = WorkflowModelDownloadManager(
            model_repository=model_repository,
            model_downloader=model_downloader,
            pyproject=pyproject
        )

    # ========== Workflow sync methods - delegate to sync_manager ==========

    def get_workflow_path(self, name: str) -> Path:
        """Check if workflow exists in ComfyUI directory and return path."""
        return self.sync_manager.get_workflow_path(name)

    def get_workflow_sync_status(self) -> WorkflowSyncStatus:
        """Get file-level sync status between ComfyUI and .cec."""
        return self.sync_manager.get_workflow_sync_status()

    def copy_all_workflows(self) -> dict[str, Path | None]:
        """Copy ALL workflows from ComfyUI to .cec for commit."""
        return self.sync_manager.copy_all_workflows()

    def restore_from_cec(self, name: str) -> bool:
        """Restore a workflow from .cec to ComfyUI directory."""
        return self.sync_manager.restore_from_cec(name)

    def restore_all_from_cec(self, preserve_uncommitted: bool = False) -> dict[str, str]:
        """Restore all workflows from .cec to ComfyUI."""
        return self.sync_manager.restore_all_from_cec(preserve_uncommitted)

    # ========== Workflow analysis methods - delegate to analyzer ==========

    def analyze_workflow(self, name: str) -> WorkflowDependencies:
        """Analyze a single workflow for dependencies - with caching."""
        return self.analyzer.analyze_workflow(name)

    def analyze_and_resolve_workflow(self, name: str) -> tuple[WorkflowDependencies, ResolutionResult]:
        """Analyze and resolve workflow with full caching."""
        return self.analyzer.analyze_and_resolve_workflow(name, self.resolver.resolve_workflow)

    def analyze_single_workflow_status(
        self,
        name: str,
        sync_state: str,
        installed_nodes: set[str] | None = None
    ) -> WorkflowAnalysisStatus:
        """Analyze a single workflow for dependencies and resolution status."""
        return self.analyzer.analyze_single_workflow_status(
            name, sync_state, installed_nodes, self.resolver.resolve_workflow
        )

    def get_workflow_status(self) -> DetailedWorkflowStatus:
        """Get detailed workflow status with full dependency analysis."""
        return self.analyzer.get_workflow_status(self.resolver.resolve_workflow)

    # ========== Workflow resolution methods - delegate to resolver ==========

    def resolve_workflow(self, analysis: WorkflowDependencies) -> ResolutionResult:
        """Attempt automatic resolution of workflow dependencies."""
        return self.resolver.resolve_workflow(analysis)

    def fix_resolution(
        self,
        resolution: ResolutionResult,
        node_strategy: NodeResolutionStrategy | None = None,
        model_strategy: ModelResolutionStrategy | None = None
    ) -> ResolutionResult:
        """Fix remaining issues using strategies with progressive writes."""
        return self.resolver.fix_resolution(resolution, node_strategy, model_strategy)

    def apply_resolution(
        self,
        resolution: ResolutionResult,
        config: dict | None = None
    ) -> None:
        """Apply resolutions with smart defaults and reconciliation."""
        self.resolver.apply_resolution(resolution, config)

    def search_models(
        self,
        search_term: str,
        node_type: str | None = None,
        limit: int = 9
    ) -> list:
        """Search for models using SQL + fuzzy matching."""
        return self.resolver.search_models(search_term, node_type, limit)

    # ========== Model download methods - delegate to download_manager ==========

    def update_model_criticality(
        self,
        workflow_name: str,
        model_identifier: str,
        new_criticality: str
    ) -> bool:
        """Update criticality for a model in a workflow."""
        return self.download_manager.update_model_criticality(
            workflow_name, model_identifier, new_criticality
        )

    def execute_pending_downloads(
        self,
        result: ResolutionResult,
        callbacks: BatchDownloadCallbacks | None = None
    ) -> list:
        """Execute batch downloads for all download intents in result."""
        return self.download_manager.execute_pending_downloads(result, callbacks)

    # ========== Model path methods - delegate to path_manager ==========

    def update_workflow_model_paths(
        self,
        resolution: ResolutionResult
    ) -> None:
        """Update workflow JSON files with resolved and stripped model paths."""
        workflow_path = self.sync_manager.get_workflow_path(resolution.workflow_name)
        self.path_manager.update_workflow_model_paths(
            workflow_path,
            resolution,
            self.analyzer.workflow_cache,
            self.environment_name
        )