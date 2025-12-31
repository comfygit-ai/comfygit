"""Example of refactored code using validation utilities.

This file demonstrates how to refactor existing validation patterns
to use the new centralized validation utilities.
"""

from pathlib import Path
from ..models.exceptions import CDEnvironmentError
from .validation import ensure_directory_exists, ensure_path_exists


# BEFORE: Verbose validation with repeated patterns
def old_create_symlinks_verbose(env_name: str, input_target: Path, output_target: Path):
    """Example of old style with verbose validation."""
    # Check input directory
    if not input_target.exists():
        raise CDEnvironmentError(
            f"Workspace input directory for '{env_name}' does not exist: {input_target}\n"
            f"Call create_directories() first"
        )

    # Check output directory
    if not output_target.exists():
        raise CDEnvironmentError(
            f"Workspace output directory for '{env_name}' does not exist: {output_target}\n"
            f"Call create_directories() first"
        )

    # ... rest of implementation


# AFTER: Using centralized validation utilities
def new_create_symlinks_clean(env_name: str, input_target: Path, output_target: Path):
    """Example of new style using validation utilities."""
    # Validate directories exist
    ensure_directory_exists(input_target, f"Workspace input directory for '{env_name}'")
    ensure_directory_exists(output_target, f"Workspace output directory for '{env_name}'")

    # ... rest of implementation


# BEFORE: Multiple checks for directory validation
def old_validate_comfyui_path(comfyui_path: Path):
    """Example of old style directory validation."""
    if not comfyui_path.exists() or not comfyui_path.is_dir():
        raise ValueError(f"ComfyUI path does not exist or is not a directory: {comfyui_path}")

    # Check for required subdirectories
    for dir_name in ["models", "custom_nodes", "web"]:
        if not (comfyui_path / dir_name).is_dir():
            raise ValueError(f"Invalid ComfyUI directory: missing {dir_name}/ subdirectory")


# AFTER: Using validation utilities for cleaner code
def new_validate_comfyui_path(comfyui_path: Path):
    """Example of new style using validation utilities."""
    ensure_directory_exists(comfyui_path, "ComfyUI path")

    # Check for required subdirectories
    for dir_name in ["models", "custom_nodes", "web"]:
        ensure_directory_exists(
            comfyui_path / dir_name,
            f"ComfyUI {dir_name} subdirectory"
        )