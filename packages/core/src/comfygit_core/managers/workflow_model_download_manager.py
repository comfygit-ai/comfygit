"""Workflow model download manager - handles model downloads and hash updates for workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..models.manifest import ManifestModel
from ..models.workflow import DownloadResult, WorkflowNodeWidgetRef
from ..services.model_downloader import DownloadRequest

if TYPE_CHECKING:
    from ..models.workflow import BatchDownloadCallbacks, ResolutionResult
    from ..repositories.model_repository import ModelRepository
    from ..services.model_downloader import ModelDownloader
    from .pyproject_manager import PyprojectManager

logger = get_logger(__name__)


class WorkflowModelDownloadManager:
    """Manages model downloads and hash updates specifically for workflows."""

    def __init__(
        self,
        model_repository: ModelRepository,
        model_downloader: ModelDownloader,
        pyproject: PyprojectManager
    ):
        self.model_repository = model_repository
        self.downloader = model_downloader
        self.pyproject = pyproject

    def update_model_hash(
        self,
        workflow_name: str,
        reference: WorkflowNodeWidgetRef,
        new_hash: str
    ) -> None:
        """Update hash for a model after download completes.

        Updates download intent (status=unresolved, sources=[URL]) to resolved state
        by atomically: 1) creating global table entry, 2) updating workflow model.

        Args:
            workflow_name: Workflow containing the model
            reference: Widget reference to identify the model
            new_hash: Hash of downloaded model

        Raises:
            ValueError: If model not found in workflow or repository
        """
        # Load workflow models
        models = self.pyproject.workflows.get_workflow_models(workflow_name)

        # Find model matching the reference
        for idx, model in enumerate(models):
            if reference in model.nodes:
                # Capture download metadata before clearing
                download_sources = model.sources if model.sources else []

                # STEP 1: Get model from repository (should always exist after download)
                resolved_model = self.model_repository.get_model(new_hash)
                if not resolved_model:
                    raise ValueError(
                        f"Model {new_hash} not found in repository after download. "
                        f"This indicates the model wasn't properly indexed."
                    )

                # STEP 2: Create global table entry FIRST (before clearing workflow model)
                manifest_model = ManifestModel(
                    hash=new_hash,
                    filename=resolved_model.filename,
                    relative_path=resolved_model.relative_path,
                    category=model.category,
                    size=resolved_model.file_size,
                    sources=download_sources
                )
                self.pyproject.models.add_model(manifest_model)

                # STEP 3: Update workflow model (clear transient fields, set hash)
                models[idx].hash = new_hash
                models[idx].status = "resolved"
                models[idx].sources = []
                models[idx].relative_path = None

                # STEP 4: Save workflow models
                self.pyproject.workflows.set_workflow_models(workflow_name, models)

                logger.info(f"Updated model '{model.filename}' with hash {new_hash}")
                return

        raise ValueError(f"Model with reference {reference} not found in workflow '{workflow_name}'")

    def execute_pending_downloads(
        self,
        result: ResolutionResult,
        callbacks: BatchDownloadCallbacks | None = None
    ) -> list[DownloadResult]:
        """Execute batch downloads for all download intents in result.

        All user-facing output is delivered via callbacks.

        Args:
            result: Resolution result containing download intents
            callbacks: Optional callbacks for progress/status (provided by CLI)

        Returns:
            List of DownloadResult objects
        """
        # Collect download intents
        intents = [r for r in result.models_resolved if r.match_type == "download_intent"]

        if not intents:
            return []

        # Notify batch start
        if callbacks and callbacks.on_batch_start:
            callbacks.on_batch_start(len(intents))

        results = []
        for idx, resolved in enumerate(intents, 1):
            filename = resolved.reference.widget_value

            # Notify file start
            if callbacks and callbacks.on_file_start:
                callbacks.on_file_start(filename, idx, len(intents))

            # Check if already downloaded (deduplication)
            if resolved.model_source:
                existing = self.model_repository.find_by_source_url(resolved.model_source)
                if existing:
                    # Reuse existing model - update pyproject with hash
                    self.update_model_hash(
                        result.workflow_name,
                        resolved.reference,
                        existing.hash
                    )
                    # Notify success (reused existing)
                    if callbacks and callbacks.on_file_complete:
                        callbacks.on_file_complete(filename, True, None)
                    results.append(DownloadResult(
                        success=True,
                        filename=filename,
                        model=existing,
                        reused=True
                    ))
                    continue

            # Validate required fields
            if not resolved.target_path or not resolved.model_source:
                error_msg = "Download intent missing target_path or model_source"
                if callbacks and callbacks.on_file_complete:
                    callbacks.on_file_complete(filename, False, error_msg)
                results.append(DownloadResult(
                    success=False,
                    filename=filename,
                    error=error_msg
                ))
                continue

            # Download new model
            target_path = self.downloader.models_dir / resolved.target_path
            request = DownloadRequest(
                url=resolved.model_source,
                target_path=target_path,
                workflow_name=result.workflow_name
            )

            # Use per-file progress callback if provided
            progress_callback = callbacks.on_file_progress if callbacks else None
            download_result = self.downloader.download(request, progress_callback=progress_callback)

            if download_result.success and download_result.model:
                # Update pyproject with actual hash
                self.update_model_hash(
                    result.workflow_name,
                    resolved.reference,
                    download_result.model.hash
                )
                # Notify success
                if callbacks and callbacks.on_file_complete:
                    callbacks.on_file_complete(filename, True, None)
            else:
                # Notify failure (model remains unresolved with source in pyproject)
                if callbacks and callbacks.on_file_complete:
                    callbacks.on_file_complete(filename, False, download_result.error)

            results.append(DownloadResult(
                success=download_result.success,
                filename=filename,
                model=download_result.model if download_result.success else None,
                error=download_result.error if not download_result.success else None
            ))

        # Notify batch complete
        if callbacks and callbacks.on_batch_complete:
            success_count = sum(1 for r in results if r.success)
            callbacks.on_batch_complete(success_count, len(results))

        return results

    def update_model_criticality(
        self,
        workflow_name: str,
        model_identifier: str,
        new_criticality: str
    ) -> bool:
        """Update criticality for a model in a workflow.

        Allows changing model criticality after initial resolution without
        re-resolving the entire workflow.

        Args:
            workflow_name: Workflow to update
            model_identifier: Filename or hash to match
            new_criticality: "required", "flexible", or "optional"

        Returns:
            True if model was found and updated, False otherwise

        Raises:
            ValueError: If new_criticality is not valid
        """
        # Validate criticality
        if new_criticality not in ("required", "flexible", "optional"):
            raise ValueError(f"Invalid criticality: {new_criticality}")

        # Load workflow models
        models = self.pyproject.workflows.get_workflow_models(workflow_name)

        if not models:
            return False

        # Find matching model(s)
        matches = []
        for i, model in enumerate(models):
            if model.hash == model_identifier or model.filename == model_identifier:
                matches.append((i, model))

        if not matches:
            return False

        # If single match, update directly
        if len(matches) == 1:
            idx, model = matches[0]
            old_criticality = model.criticality
            models[idx].criticality = new_criticality
            self.pyproject.workflows.set_workflow_models(workflow_name, models)
            logger.info(
                f"Updated '{model.filename}' criticality: "
                f"{old_criticality} → {new_criticality}"
            )
            return True

        # Multiple matches - update all and return True
        for idx, model in matches:
            models[idx].criticality = new_criticality

        self.pyproject.workflows.set_workflow_models(workflow_name, models)
        logger.info(
            f"Updated {len(matches)} model(s) with identifier '{model_identifier}' "
            f"to criticality '{new_criticality}'"
        )
        return True