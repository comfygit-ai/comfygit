"""Shared utilities for cross-platform symlink operations."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..models.exceptions import CDEnvironmentError


def is_link(path: Path) -> bool:
    """Detect both symlinks and junctions (Windows).

    Args:
        path: Path to check

    Returns:
        True if path is a symlink or junction, False otherwise
    """
    if path.is_symlink():
        return True
    # Python 3.12+: Direct junction check
    if hasattr(os.path, 'isjunction') and os.path.isjunction(path):
        return True
    # Fallback: Check if path resolution differs (works for junctions and symlinks)
    try:
        return path.exists() and path.absolute() != path.resolve()
    except (OSError, RuntimeError):
        return False


def create_platform_link(link_path: Path, target_path: Path, name: str) -> None:
    """Create symlink (Unix) or junction (Windows).

    Args:
        link_path: Path where symlink should be created
        target_path: Path that symlink should point to
        name: Directory name for error messages (e.g., "models", "input")

    Raises:
        CDEnvironmentError: If link creation fails
    """
    try:
        if os.name == "nt":  # Windows
            create_windows_junction(link_path, target_path, name)
        else:  # Linux/macOS
            os.symlink(target_path, link_path)
    except CDEnvironmentError:
        # Re-raise CDEnvironmentError as-is
        raise
    except Exception as e:
        raise CDEnvironmentError(f"Failed to create {name} symlink: {e}") from e


def create_windows_junction(link_path: Path, target_path: Path, name: str) -> None:
    """Create junction on Windows using mklink command.

    Args:
        link_path: Path where junction should be created
        target_path: Path that junction should point to
        name: Directory name for error messages

    Raises:
        CDEnvironmentError: If junction creation fails
    """
    # Use mklink /J for directory junction (no admin required)
    result = subprocess.run(
        [
            "mklink",
            "/J",
            str(link_path),
            str(target_path),
        ],
        shell=True,  # Required for mklink
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise CDEnvironmentError(
            f"Failed to create {name} junction:\n"
            f"  Command: mklink /J {link_path} {target_path}\n"
            f"  Error: {result.stderr}\n"
            f"  Note: On Windows, you may need Administrator privileges or Developer Mode enabled"
        )


def is_safe_to_delete(path: Path, safe_files: set[str]) -> bool:
    """Check if directory is safe to delete.

    Safe to delete if:
    - Completely empty
    - Only contains empty subdirectories
    - Only contains placeholder files from safe_files set

    Args:
        path: Directory path to check
        safe_files: Set of filenames that are safe to delete (e.g., {".gitkeep", ".gitignore"})

    Returns:
        True if safe to delete, False if contains actual content
    """
    if not path.exists():
        return True  # Nonexistent is safe

    # Get all files recursively
    all_items = list(path.rglob("*"))
    files = [f for f in all_items if f.is_file()]

    if len(files) == 0:
        return True  # Completely empty (or only empty dirs)

    # Check if files are only placeholders
    for file in files:
        if file.name not in safe_files:
            # Has actual content
            return False

    return True  # Only placeholder files
