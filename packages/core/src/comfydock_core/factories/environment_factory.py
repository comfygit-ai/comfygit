"""Factory for creating new environments."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from comfydock_core.core.environment import Environment

from ..logging.logging_config import get_logger
from ..managers.git_manager import GitManager
from ..models.exceptions import (
    CDEnvironmentExistsError,
)
from ..utils.comfyui_ops import clone_comfyui

if TYPE_CHECKING:
    from comfydock_core.core.workspace import WorkspacePaths
    from comfydock_core.repositories.model_repository import ModelRepository
    from comfydock_core.repositories.node_mappings_repository import NodeMappingsRepository
    from comfydock_core.repositories.workspace_config_repository import WorkspaceConfigRepository
    from comfydock_core.services.model_downloader import ModelDownloader
    from comfydock_core.models.protocols import ImportCallbacks

logger = get_logger(__name__)

class EnvironmentFactory:

    @staticmethod
    def create(
        name: str,
        env_path: Path,
        workspace_paths: WorkspacePaths,
        model_repository: ModelRepository,
        node_mapping_repository: NodeMappingsRepository,
        workspace_config_manager: WorkspaceConfigRepository,
        model_downloader: ModelDownloader,
        python_version: str = "3.12",
        comfyui_version: str | None = None,
    ) -> Environment:
        """Create a new environment."""
        if env_path.exists():
            raise CDEnvironmentExistsError(f"Environment path already exists: {env_path}")

        # Create structure
        env_path.mkdir(parents=True)
        cec_path = env_path / ".cec"
        cec_path.mkdir()

        # Pin Python version for uv
        python_version_file = cec_path / ".python-version"
        python_version_file.write_text(python_version + "\n")
        logger.debug(f"Created .python-version: {python_version}")

        # Initialize environment
        env = Environment(
            name=name,
            path=env_path,
            workspace_paths=workspace_paths,
            model_repository=model_repository,
            node_mapping_repository=node_mapping_repository,
            workspace_config_manager=workspace_config_manager,
            model_downloader=model_downloader,
        )

        # Clone ComfyUI
        logger.info("Cloning ComfyUI (this may take a moment)...")
        try:
            comfyui_version = clone_comfyui(env.comfyui_path, comfyui_version)
            if comfyui_version:
                logger.info(f"Successfully cloned ComfyUI version: {comfyui_version}")
            else:
                logger.warning("ComfyUI clone failed")
                raise RuntimeError("ComfyUI clone failed")
        except Exception as e:
            logger.warning(f"ComfyUI clone failed: {e}")
            raise e

        # Remove ComfyUI's default models directory (will be replaced with symlink)
        models_dir = env.comfyui_path / "models"
        if models_dir.exists() and not models_dir.is_symlink():
            shutil.rmtree(models_dir)
            logger.debug("Removed ComfyUI's default models directory")

        # Create initial pyproject.toml
        config = EnvironmentFactory._create_initial_pyproject(name, python_version, comfyui_version)
        env.pyproject.save(config)

        # Get requirements from ComfyUI and add them
        comfyui_reqs = env.comfyui_path / "requirements.txt"
        if comfyui_reqs.exists():
            logger.info("Adding ComfyUI requirements...")
            env.uv_manager.add_requirements_with_sources(comfyui_reqs, frozen=True)

        # Initial UV sync to create venv (verbose to show progress)
        logger.info("Creating virtual environment...")
        env.uv_manager.sync_project(verbose=True)

        # Use GitManager for repository initialization
        git_mgr = GitManager(cec_path)
        git_mgr.initialize_environment_repo("Initial environment setup")

        # Create model symlink (should succeed now that models/ is removed)
        try:
            env.model_symlink_manager.create_symlink()
            logger.info("Model directory linked successfully")
        except Exception as e:
            logger.error(f"Failed to create model symlink: {e}")
            raise  # FATAL - environment won't work without models

        logger.info(f"Environment '{name}' created successfully")
        return env

    @staticmethod
    def import_from_bundle(
        tarball_path: Path,
        name: str,
        env_path: Path,
        workspace_paths: "WorkspacePaths",
        model_repository: "ModelRepository",
        node_mapping_repository: "NodeMappingsRepository",
        workspace_config_manager: "WorkspaceConfigRepository",
        model_downloader: "ModelDownloader",
        model_strategy: str = "all",
        callbacks: "ImportCallbacks | None" = None
    ) -> Environment:
        """Import environment from tarball bundle.

        Args:
            tarball_path: Path to .tar.gz bundle
            name: Name for imported environment
            env_path: Path where environment will be created
            workspace_paths: Workspace paths
            model_repository: Model repository
            node_mapping_repository: Node mapping repository
            workspace_config_manager: Workspace config manager
            model_downloader: Model downloader
            model_strategy: "all", "required", or "skip"
            callbacks: Optional callbacks for progress updates

        Returns:
            Environment

        Raises:
            CDEnvironmentExistsError: If environment path exists
            ValueError: If tarball is invalid
        """
        if env_path.exists():
            raise CDEnvironmentExistsError(f"Environment path already exists: {env_path}")

        # Create environment directory and extract bundle
        env_path.mkdir(parents=True)
        cec_path = env_path / ".cec"

        from ..managers.export_import_manager import ExportImportManager
        manager = ExportImportManager(cec_path, env_path / "ComfyUI")
        manager.extract_import(tarball_path, cec_path)

        logger.info(f"Extracted bundle to {cec_path}")

        # Create Environment object
        env = Environment(
            name=name,
            path=env_path,
            workspace_paths=workspace_paths,
            model_repository=model_repository,
            node_mapping_repository=node_mapping_repository,
            workspace_config_manager=workspace_config_manager,
            model_downloader=model_downloader,
        )

        # Run import orchestration
        manager.import_bundle(
            env=env,
            tarball_path=tarball_path,
            model_strategy=model_strategy,
            callbacks=callbacks
        )

        logger.info(f"Environment '{name}' imported successfully")
        return env

    @staticmethod
    def _create_initial_pyproject(name: str, python_version: str, comfyui_version: str) -> dict:
        """Create the initial pyproject.toml."""
        config = {
            "project": {
                "name": f"comfydock-env-{name}",
                "version": "0.1.0",
                "requires-python": f">={python_version}",
                "dependencies": []
            },
            "tool": {
                "comfydock": {
                    "comfyui_version": comfyui_version,
                    "python_version": python_version,
                    "nodes": {}
                }
            }
        }
        return config
