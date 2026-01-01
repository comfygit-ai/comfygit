"""Common validation utilities for path and object existence checks."""

from pathlib import Path
from typing import Optional

from ..models.exceptions import CDEnvironmentError, CDEnvironmentNotFoundError


def ensure_path_exists(path: Path, description: str) -> None:
    """Ensure a path exists, raise error with description if not.

    Args:
        path: Path to check
        description: Human-readable description of what the path is

    Raises:
        CDEnvironmentError: If path doesn't exist
    """
    if not path.exists():
        raise CDEnvironmentError(f"{description} does not exist: {path}")


def ensure_directory_exists(path: Path, description: str) -> None:
    """Ensure a path exists and is a directory.

    Args:
        path: Path to check
        description: Human-readable description of what the directory is

    Raises:
        CDEnvironmentError: If path doesn't exist or isn't a directory
    """
    if not path.exists():
        raise CDEnvironmentError(f"{description} does not exist: {path}")
    if not path.is_dir():
        raise CDEnvironmentError(f"{description} is not a directory: {path}")


def ensure_file_exists(path: Path, description: str) -> None:
    """Ensure a path exists and is a file.

    Args:
        path: Path to check
        description: Human-readable description of what the file is

    Raises:
        CDEnvironmentError: If path doesn't exist or isn't a file
    """
    if not path.exists():
        raise CDEnvironmentError(f"{description} does not exist: {path}")
    if not path.is_file():
        raise CDEnvironmentError(f"{description} is not a file: {path}")


def validate_not_exists(path: Path, description: str) -> None:
    """Ensure a path does NOT exist (for creation operations).

    Args:
        path: Path to check
        description: Human-readable description of what would be created

    Raises:
        CDEnvironmentError: If path already exists
    """
    if path.exists():
        raise CDEnvironmentError(f"{description} already exists: {path}")


def validate_writable_directory(path: Path, description: str) -> None:
    """Ensure a directory exists and is writable.

    Args:
        path: Path to check
        description: Human-readable description of the directory

    Raises:
        CDEnvironmentError: If path doesn't exist, isn't a directory, or isn't writable
    """
    ensure_directory_exists(path, description)

    # Check if we can write to it by trying to create a temp file
    import tempfile
    try:
        with tempfile.TemporaryFile(dir=path) as _:
            pass
    except (OSError, IOError) as e:
        raise CDEnvironmentError(f"{description} is not writable: {path}") from e


def validate_parent_directory_exists(path: Path, description: str) -> None:
    """Ensure the parent directory of a path exists.

    Args:
        path: Path whose parent to check
        description: Human-readable description of what will be created

    Raises:
        CDEnvironmentError: If parent directory doesn't exist
    """
    parent = path.parent
    if not parent.exists():
        raise CDEnvironmentError(
            f"Parent directory for {description} does not exist: {parent}"
        )


def validate_git_repository(path: Path, description: Optional[str] = None) -> None:
    """Ensure a path is a git repository.

    Handles both normal git repos (with .git directory) and git worktrees
    (with .git file that points to the main repo).

    Args:
        path: Path to check
        description: Optional description (defaults to "Directory")

    Raises:
        CDEnvironmentError: If path is not a git repository
    """
    desc = description or "Directory"
    ensure_directory_exists(path, desc)

    git_path = path / ".git"
    # Git repos have .git as directory, worktrees have .git as file
    if not git_path.exists():
        raise CDEnvironmentError(f"{desc} is not a git repository: {path}")


def validate_environment_name(name: str) -> None:
    """Validate environment name format.

    Args:
        name: Environment name to validate

    Raises:
        CDEnvironmentError: If name is invalid
    """
    if not name:
        raise CDEnvironmentError("Environment name cannot be empty")

    if not name.replace("-", "").replace("_", "").isalnum():
        raise CDEnvironmentError(
            f"Environment name '{name}' contains invalid characters. "
            "Only letters, numbers, hyphens, and underscores are allowed."
        )

    if name.startswith("-") or name.startswith("_"):
        raise CDEnvironmentError(
            f"Environment name '{name}' cannot start with a hyphen or underscore"
        )


def validate_package_identifier(identifier: str) -> None:
    """Validate package identifier format (GitHub URL or registry ID).

    Args:
        identifier: Package identifier to validate

    Raises:
        CDEnvironmentError: If identifier is invalid
    """
    if not identifier:
        raise CDEnvironmentError("Package identifier cannot be empty")

    # Basic validation - more specific validation should be done by specialized functions
    if " " in identifier:
        raise CDEnvironmentError(f"Package identifier '{identifier}' contains spaces")