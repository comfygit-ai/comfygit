"""Manages .pytorch-backend file and PyTorch configuration injection."""
from __future__ import annotations

import re
from pathlib import Path

from ..constants import PYTORCH_CORE_PACKAGES
from ..logging.logging_config import get_logger
from ..utils.pytorch import get_pytorch_index_url

logger = get_logger(__name__)


class PyTorchBackendManager:
    """Manages .pytorch-backend file and PyTorch configuration injection.

    The .pytorch-backend file stores the user's PyTorch backend choice (e.g., cu128, cpu).
    This file is gitignored, allowing different machines to use different backends
    while sharing the same environment configuration.
    """

    # Valid backend patterns
    BACKEND_PATTERNS = [
        r'^cu\d{2,3}$',  # CUDA: cu118, cu121, cu128, cu130, etc.
        r'^cpu$',  # CPU
        r'^rocm\d+\.\d+$',  # ROCm: rocm6.2, rocm6.3, etc.
        r'^xpu$',  # Intel XPU
    ]

    def __init__(self, cec_path: Path, workspace_path: Path | None = None):
        """Initialize manager.

        Args:
            cec_path: Path to the .cec directory
            workspace_path: Path to workspace root (needed for version cache)
        """
        self.cec_path = cec_path
        self.workspace_path = workspace_path
        self.backend_file = cec_path / ".pytorch-backend"

    def get_backend(self) -> str:
        """Read backend from file.

        Returns:
            Backend string (e.g., 'cu128', 'cpu')

        Raises:
            ValueError: If .pytorch-backend file doesn't exist or is empty
        """
        if self.backend_file.exists():
            backend = self.backend_file.read_text().strip()
            if backend:
                logger.debug(f"Read PyTorch backend from file: {backend}")
                return backend

        raise ValueError(
            ".pytorch-backend file not found or empty. "
            "Run probe_and_set_backend() first."
        )

    def set_backend(self, backend: str) -> None:
        """Write backend to file.

        Also ensures .pytorch-backend is in .gitignore (for migration from
        older environments that don't have this entry).

        Args:
            backend: Backend string (e.g., 'cu128', 'cpu')
        """
        self.backend_file.write_text(backend)
        logger.info(f"Set PyTorch backend: {backend}")

        # Ensure .gitignore has this entry (migration support)
        self._ensure_gitignore_entry()

    def probe_and_set_backend(
        self,
        python_version: str,
        backend: str = "auto",
    ) -> str:
        """Probe PyTorch versions and set backend.

        Uses uv's dry-run probing to detect the appropriate backend
        and cache version information.

        Args:
            python_version: Python version (e.g., "3.12")
            backend: Backend to probe ("auto" for auto-detection, or specific like "cu128")

        Returns:
            Resolved backend string (e.g., "cu128", "cpu")

        Raises:
            PyTorchProbeError: If probing fails
        """
        from ..utils.pytorch_prober import probe_pytorch_versions

        if not self.workspace_path:
            raise ValueError("workspace_path required for probing")

        # Probe versions (also caches them)
        _, resolved_backend = probe_pytorch_versions(
            python_version, backend, self.workspace_path
        )

        # Write resolved backend to file
        self.set_backend(resolved_backend)

        return resolved_backend

    def has_backend(self) -> bool:
        """Check if .pytorch-backend file exists and is non-empty."""
        if not self.backend_file.exists():
            return False
        return bool(self.backend_file.read_text().strip())

    def _ensure_gitignore_entry(self) -> None:
        """Ensure .pytorch-backend is in .gitignore."""
        gitignore_path = self.cec_path / ".gitignore"
        entry = ".pytorch-backend"

        if not gitignore_path.exists():
            gitignore_path.write_text(f"# PyTorch backend configuration (machine-specific)\n{entry}\n")
            logger.debug(f"Created .gitignore with entry: {entry}")
            return

        current_content = gitignore_path.read_text()

        # Check if entry already exists
        for line in current_content.split('\n'):
            stripped = line.split('#')[0].strip()
            if stripped == entry:
                return  # Already present

        # Add entry at the end
        if not current_content.endswith('\n'):
            current_content += '\n'
        current_content += f"\n# PyTorch backend configuration (machine-specific)\n{entry}\n"
        gitignore_path.write_text(current_content)
        logger.info(f"Added {entry} to .gitignore (migration)")

    def is_valid_backend(self, backend: str) -> bool:
        """Check if backend string matches valid patterns.

        Args:
            backend: Backend string to validate

        Returns:
            True if valid, False otherwise
        """
        if not backend:
            return False

        for pattern in self.BACKEND_PATTERNS:
            if re.match(pattern, backend):
                return True

        return False

    def get_pytorch_config(
        self,
        python_version: str | None = None,
        backend_override: str | None = None,
    ) -> dict:
        """Generate PyTorch uv config for current backend.

        When python_version is provided and workspace_path is set, includes
        constraint-dependencies with exact PyTorch versions from cache.

        Args:
            python_version: Python version for constraint lookup (e.g., "3.12")
            backend_override: Override backend instead of reading from file (e.g., "cu128")

        Returns dict with:
            - indexes: List of index configs (name, url, explicit)
            - sources: Dict mapping package names to index names
            - constraints: List of constraint strings (e.g., ["torch==2.9.1+cu128"])

        Returns:
            Configuration dict for PyTorch packages
        """
        backend = backend_override if backend_override else self.get_backend()
        index_url = get_pytorch_index_url(backend)
        index_name = f"pytorch-{backend}"

        sources: dict[str, dict[str, str]] = {}
        constraints: list[str] = []

        # Map all PyTorch core packages to the index
        for package in PYTORCH_CORE_PACKAGES:
            sources[package] = {"index": index_name}

        # Add constraints from cache (probing should have happened earlier)
        if python_version and self.workspace_path:
            versions = self._get_cached_versions(python_version, backend)
            if versions:
                constraints = [
                    f"{pkg}=={version}"
                    for pkg, version in versions.items()
                    if pkg in PYTORCH_CORE_PACKAGES
                ]

        config = {
            "indexes": [
                {
                    "name": index_name,
                    "url": index_url,
                    "explicit": True,
                }
            ],
            "sources": sources,
            "constraints": constraints,
        }

        logger.debug(f"Generated PyTorch config for backend {backend}: {config}")
        return config

    def _get_cached_versions(
        self, python_version: str, backend: str
    ) -> dict[str, str] | None:
        """Get PyTorch versions from cache only.

        Args:
            python_version: Python version (may be "3.12" or "3.12.11")
            backend: PyTorch backend (e.g., "cu128")

        Returns:
            Dict of package versions, or None if not cached
        """
        from ..caching.pytorch_version_cache import PyTorchVersionCache
        from ..utils.pytorch_prober import PyTorchProbeError, get_exact_python_version

        if not self.workspace_path:
            return None

        # Get exact Python version for cache key
        try:
            exact_py = get_exact_python_version(python_version)
        except PyTorchProbeError as e:
            logger.warning(f"Could not determine exact Python version: {e}")
            exact_py = python_version

        # Check cache only - no probing here
        cache = PyTorchVersionCache(self.workspace_path)
        versions = cache.get_versions(exact_py, backend)

        if versions:
            logger.debug(f"Using cached PyTorch versions for {exact_py}+{backend}")
        else:
            logger.debug(f"No cached PyTorch versions for {exact_py}+{backend}")

        return versions
