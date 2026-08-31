import re
from pathlib import Path
from urllib.parse import urlparse

from ..constants import DEFAULT_COMFYUI_REPOSITORY
from ..logging.logging_config import get_logger
from .common import run_command
from .git import (
    git_clone,
    git_remote_get_url,
    git_rev_parse,
    is_git_url,
    normalize_github_url,
)

logger = get_logger(__name__)

FULL_GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def normalize_comfyui_repository(repository: str | None) -> str:
    """Validate and normalize a portable ComfyUI Git repository URL."""
    value = str(repository or DEFAULT_COMFYUI_REPOSITORY).strip()
    if not value or not is_git_url(value):
        raise ValueError(
            "ComfyUI repository must be an HTTP(S) or SSH Git URL."
        )
    if "#" in value:
        raise ValueError("ComfyUI repository URLs cannot contain fragments.")
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and (
        parsed.username is not None or parsed.password is not None
    ):
        raise ValueError(
            "ComfyUI repository credentials must not be embedded in the URL."
        )
    return value


def comfyui_repository_identity(repository: str) -> str:
    """Return a credential-free canonical identity for cache/comparison use."""
    normalized = normalize_github_url(repository).rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.lower()


def normalize_comfyui_commit_sha(commit_sha: str | None) -> str | None:
    """Validate the immutable ComfyUI revision stored in a manifest."""
    if commit_sha is None:
        return None
    value = str(commit_sha).strip()
    if not FULL_GIT_SHA_RE.fullmatch(value):
        raise ValueError(
            "comfyui_commit_sha must be a full 40-character hexadecimal Git SHA."
        )
    return value.lower()


def verify_comfyui_checkout(
    checkout_path: Path,
    *,
    repository: str,
    commit_sha: str | None = None,
) -> str:
    """Verify that a checkout has the declared origin and immutable HEAD."""
    expected_repository = normalize_comfyui_repository(repository)
    actual_repository = git_remote_get_url(checkout_path, "origin")
    if not actual_repository:
        raise ValueError(
            f"Materialized ComfyUI checkout has no origin remote: {checkout_path}"
        )
    if comfyui_repository_identity(actual_repository) != comfyui_repository_identity(
        expected_repository
    ):
        raise ValueError(
            "Materialized ComfyUI origin mismatch: expected "
            f"{expected_repository}, found {actual_repository}."
        )
    actual_commit = git_rev_parse(checkout_path, "HEAD")
    if not actual_commit:
        raise ValueError(
            f"Materialized ComfyUI checkout has no readable HEAD: {checkout_path}"
        )
    if commit_sha and actual_commit.lower() != str(commit_sha).lower():
        raise ValueError(
            "Materialized ComfyUI commit mismatch: expected "
            f"{commit_sha}, found {actual_commit}."
        )
    return actual_commit


def validate_comfyui_installation(comfyui_path: Path) -> bool:
    """Check if a directory contains a valid ComfyUI installation.

    Args:
        comfyui_path: Path to check

    Returns:
        True if valid ComfyUI installation, False otherwise
    """
    # Check for essential ComfyUI files
    required_files = ["main.py", "nodes.py", "folder_paths.py"]

    for file in required_files:
        if not (comfyui_path / file).exists():
            return False

    # Check for essential directories
    required_dirs = ["comfy", "models"]

    for dir_name in required_dirs:
        if not (comfyui_path / dir_name).is_dir():
            return False

    return True


def get_comfyui_version(comfyui_path: Path) -> str:
    """Detect ComfyUI version from git tags."""
    comfyui_version = "unknown"
    try:
        git_dir = comfyui_path / ".git"
        if git_dir.exists():
            result = run_command(
                ["git", "describe", "--tags", "--always"], cwd=comfyui_path
            )
            if result.returncode == 0:
                comfyui_version = result.stdout.strip()
    except Exception as e:
        logger.debug(f"Could not detect ComfyUI version from {comfyui_path}: {e}")

    return comfyui_version


def resolve_comfyui_version(
    version_spec: str | None,
    github_client,
    repository: str | None = None,
) -> tuple[str, str, str | None]:
    """Resolve version specification to concrete version.

    Args:
        version_spec: User input ("latest", "v0.3.20", "abc123", "main", None)
        github_client: GitHub client for API calls

    Returns:
        Tuple of (version_to_clone, version_type, commit_sha)
        - version_to_clone: What to pass to git clone
        - version_type: "release" | "commit" | "branch"
        - commit_sha: Actual commit SHA (None if not yet cloned)

    Examples:
        None → ("v0.3.20", "release", None)  # Latest release
        "latest" → ("v0.3.20", "release", None)
        "v0.3.15" → ("v0.3.15", "release", None)
        "abc123" → ("abc123", "commit", None)
        "master" → ("master", "branch", None)
    """
    comfyui_repo = normalize_comfyui_repository(repository)

    # Handle None or "latest" - fetch latest release
    if version_spec is None or version_spec == "latest":
        repo_info = github_client.get_repository_info(comfyui_repo)
        if repo_info and repo_info.latest_release:
            return (repo_info.latest_release, "release", None)
        else:
            logger.warning("No releases found, falling back to master branch")
            return ("master", "branch", None)

    # Handle release tags (starts with 'v')
    if version_spec.startswith('v'):
        # Validate release exists
        if github_client.validate_version_exists(comfyui_repo, version_spec):
            return (version_spec, "release", None)
        else:
            logger.warning(f"Release {version_spec} not found on GitHub")
            raise ValueError(f"ComfyUI release {version_spec} does not exist")

    # Handle branch alias (ComfyUI only has master branch)
    if version_spec == "master":
        return (version_spec, "branch", None)

    # Assume commit hash
    return (version_spec, "commit", None)


def clone_comfyui(
    target_path: Path,
    version: str | None = None,
    *,
    repository: str | None = None,
    token: str | None = None,
) -> str | None:
    """Clone ComfyUI repository to a target path.

    Args:
        target_path: Where to clone ComfyUI
        version: Optional specific version/tag/commit to checkout

    Returns:
        ComfyUI version string (commit hash or tag)

    Raises:
        RuntimeError: If cloning fails
    """
    # Clone the repository with shallow clone for speed
    repository = normalize_comfyui_repository(repository)
    git_clone(
        repository,
        target_path,
        depth=1,
        ref=version,
        timeout=5 * 60,
        token=token,
    )
    return get_comfyui_version(target_path)
