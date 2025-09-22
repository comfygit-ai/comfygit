"""ModelPathManager - Manages extra_model_paths.yaml for ComfyUI environments."""
from __future__ import annotations
import json
from pathlib import Path

import yaml

from ..configs.model_config import ModelConfig
from ..logging.logging_config import get_logger

logger = get_logger(__name__)


class ModelPathManager:
    """Manages extra_model_paths.yaml for ComfyUI model path configuration."""

    def __init__(self, comfyui_path: Path, global_models_path: Path):
        """Initialize ModelPathManager.

        Args:
            comfyui_path: Path to ComfyUI directory
            global_models_path: Path to global models directory
        """
        self.comfyui_path = comfyui_path
        self.global_models_path = global_models_path
        self.yaml_path = comfyui_path / "extra_model_paths.yaml"

    def sync_model_paths(self) -> dict:
        """Create or update extra_model_paths.yaml with global models directory.

        Returns:
            Dictionary with sync statistics including changes
        """
        # Get current configuration
        existing_config = self._load_existing_config()

        # Discover directories once
        standard_dirs = self._get_standard_directories()
        discovered_dirs = self._discover_additional_directories(standard_dirs)
        all_dirs = standard_dirs + discovered_dirs

        # Check if update is needed
        needs_update, changes = self._check_if_update_needed(existing_config, all_dirs)

        stats = {
            "status": "unchanged",
            "global_models_path": str(self.global_models_path),
            "config_file": str(self.yaml_path),
            "total_directories": len(all_dirs),
            "standard_count": len(standard_dirs),
            "discovered_count": len(discovered_dirs),
            "changes": changes
        }

        if not needs_update:
            logger.debug(f"Model paths already configured for {self.comfyui_path.name} - no changes needed")
            return stats

        # Build and write new configuration
        config = self._build_config_with_dirs(all_dirs)
        self._write_yaml(config)

        stats["status"] = "updated"

        # Log changes
        if changes.get("added"):
            logger.info(f"Added model directories for {self.comfyui_path.name}: {', '.join(changes['added'])}")
        if changes.get("removed"):
            logger.info(f"Removed model directories for {self.comfyui_path.name}: {', '.join(changes['removed'])}")
        if not changes.get("added") and not changes.get("removed"):
            logger.info(f"Model paths updated for {self.comfyui_path.name}: {len(all_dirs)} directories mapped")

        return stats

    def clean_model_paths(self) -> bool:
        """Remove extra_model_paths.yaml configuration.

        Returns:
            True if file was removed, False if it didn't exist
        """
        if self.yaml_path.exists():
            self.yaml_path.unlink()
            logger.info(f"Removed model path configuration: {self.yaml_path}")
            return True
        return False

    def get_config_status(self) -> dict:
        """Get current configuration status.

        Returns:
            Dictionary with configuration status
        """
        if not self.yaml_path.exists():
            return {
                "configured": False,
                "global_models_path": None,
                "config_file": str(self.yaml_path)
            }

        try:
            with open(self.yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            comfydock_config = config.get('comfydock', {})
            current_path = comfydock_config.get('base_path')

            return {
                "configured": True,
                "global_models_path": current_path,
                "config_file": str(self.yaml_path),
                "is_current": current_path == str(self.global_models_path)
            }
        except Exception as e:
            logger.warning(f"Failed to read existing config: {e}")
            return {
                "configured": False,
                "global_models_path": None,
                "config_file": str(self.yaml_path),
                "error": str(e)
            }

    def _load_existing_config(self) -> dict | None:
        """Load existing YAML configuration if present.

        Returns:
            Existing configuration dictionary or None
        """
        if not self.yaml_path.exists():
            return None

        try:
            with open(self.yaml_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.debug(f"Could not load existing config: {e}")
            return None

    def _check_if_update_needed(self, existing_config: dict | None, all_dirs: list[str]) -> tuple[bool, dict]:
        """Check if configuration needs updating.

        Args:
            existing_config: Existing YAML configuration or None
            all_dirs: List of all directories that should be configured

        Returns:
            Tuple of (needs_update, changes_dict)
        """
        changes = {"added": [], "removed": []}

        # If no existing config, all directories are new
        if not existing_config:
            changes["added"] = all_dirs
            return True, changes

        # Get existing directories (excluding base_path and is_default)
        existing_dirs = set()
        comfyui_config = existing_config.get("comfyui", {})
        for key, value in comfyui_config.items():
            if key not in ["base_path", "is_default"] and value.endswith("/"):
                existing_dirs.add(key)

        current_dirs = set(all_dirs)

        # Check if base path changed
        if comfyui_config.get("base_path") != str(self.global_models_path):
            return True, changes

        # Find differences
        changes["added"] = sorted(current_dirs - existing_dirs)
        changes["removed"] = sorted(existing_dirs - current_dirs)

        needs_update = bool(changes["added"] or changes["removed"])
        return needs_update, changes

    def _build_config_with_dirs(self, all_directories: list[str]) -> dict:
        """Build the YAML configuration with given directories.

        Args:
            all_directories: List of all directories to include

        Returns:
            Dictionary representing the YAML configuration
        """
        config = {
            "comfyui": {
                "base_path": str(self.global_models_path),
                "is_default": True,
                **{name: f"{name}/" for name in all_directories}
            }
        }
        return config

    def _get_standard_directories(self) -> list[str]:
        """Get standard ComfyUI model directory names.

        Returns:
            List of standard directory names
        """
        return ModelConfig.load().standard_directories

    def _discover_additional_directories(self, standard_directories: list[str]) -> list[str]:
        """Discover additional model directories in the base path.

        Args:
            standard_directories: List of standard directories to exclude

        Returns:
            List of additional directory names found in base path
        """
        if not self.global_models_path.exists():
            return []

        try:
            additional_dirs = []
            standard_set = set(standard_directories)

            # Scan for directories in the base path
            for item in self.global_models_path.iterdir():
                if item.is_dir() and item.name not in standard_set:
                    # Skip hidden directories and common non-model directories
                    if not item.name.startswith('.') and item.name not in {'__pycache__', 'temp', 'tmp'}:
                        additional_dirs.append(item.name)

            # Sort for consistent ordering
            additional_dirs.sort()

            if additional_dirs:
                logger.debug(f"Discovered additional model directories: {additional_dirs}")

            return additional_dirs

        except Exception as e:
            logger.warning(f"Failed to discover additional directories in {self.global_models_path}: {e}")
            return []


    def _write_yaml(self, config: dict) -> None:
        """Write configuration to YAML file.

        Args:
            config: Configuration dictionary to write
        """
        try:
            # Ensure ComfyUI directory exists
            self.comfyui_path.mkdir(parents=True, exist_ok=True)

            with open(self.yaml_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.debug(f"Written model path configuration to {self.yaml_path}")

        except Exception as e:
            logger.error(f"Failed to write model path configuration: {e}")
            raise