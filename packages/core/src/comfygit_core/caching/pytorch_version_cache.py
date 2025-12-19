"""PyTorch version cache for workspace-level version storage.

Caches exact PyTorch package versions discovered via probing, keyed by
Python version + backend combination.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import tomlkit

from ..logging.logging_config import get_logger

logger = get_logger(__name__)


class PyTorchVersionCache:
    """Workspace-level cache for PyTorch package versions.

    Stores versions discovered via probing to avoid repeated installations.
    Cache is keyed by exact Python version + backend (e.g., py3.12.11_cu128).

    Cache file location: <workspace>/comfygit_cache/pytorch-cache.toml
    """

    def __init__(self, workspace_path: Path):
        """Initialize the cache.

        Args:
            workspace_path: Path to the workspace root
        """
        self.workspace_path = workspace_path
        self.cache_dir = workspace_path / "comfygit_cache"
        self.cache_file = self.cache_dir / "pytorch-cache.toml"
        self._cache: dict | None = None

    def _load_cache(self) -> dict:
        """Load cache from disk."""
        if self._cache is not None:
            return self._cache

        if not self.cache_file.exists():
            self._cache = {}
            return self._cache

        try:
            with open(self.cache_file, encoding="utf-8") as f:
                self._cache = tomlkit.load(f)
        except Exception as e:
            logger.warning(f"Failed to load pytorch cache: {e}")
            self._cache = {}

        return self._cache

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if self._cache is None:
            return

        # Ensure directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                # Add header comment
                f.write("# PyTorch version cache - auto-generated, do not edit\n")
                f.write("# Clear with: cg pytorch-cache clear\n\n")
                tomlkit.dump(self._cache, f)
        except Exception as e:
            logger.error(f"Failed to save pytorch cache: {e}")

    def _make_key(self, python_version: str, backend: str) -> tuple[str, str]:
        """Create cache key components from Python version and backend.

        Returns (section_key, backend_key) for nested TOML structure.
        E.g., ("py3_12_11", "cu128")
        """
        # Normalize Python version: 3.12.11 -> py3_12_11
        section_key = "py" + python_version.replace(".", "_")
        return section_key, backend

    def get_versions(self, python_version: str, backend: str) -> dict[str, str] | None:
        """Get cached PyTorch versions for a Python+backend combo.

        Args:
            python_version: Exact Python version (e.g., "3.12.11")
            backend: PyTorch backend (e.g., "cu128", "cpu")

        Returns:
            Dict with torch/torchvision/torchaudio versions, or None if not cached
        """
        cache = self._load_cache()
        section_key, backend_key = self._make_key(python_version, backend)

        section = cache.get(section_key, {})
        backend_data = section.get(backend_key)

        if backend_data is None:
            return None

        # Extract just the version fields (not discovered timestamp)
        versions = {}
        for key, value in backend_data.items():
            if key != "discovered":
                versions[key] = value

        return versions if versions else None

    def set_versions(
        self, python_version: str, backend: str, versions: dict[str, str]
    ) -> None:
        """Store PyTorch versions in the cache.

        Args:
            python_version: Exact Python version (e.g., "3.12.11")
            backend: PyTorch backend (e.g., "cu128", "cpu")
            versions: Dict mapping package name to version string
        """
        cache = self._load_cache()
        section_key, backend_key = self._make_key(python_version, backend)

        # Ensure section exists
        if section_key not in cache:
            cache[section_key] = tomlkit.table()

        # Create entry with versions and timestamp
        entry = tomlkit.table()
        for pkg, version in versions.items():
            entry[pkg] = version
        entry["discovered"] = datetime.now(timezone.utc).isoformat()

        cache[section_key][backend_key] = entry

        self._save_cache()
        logger.debug(f"Cached PyTorch versions for {python_version}+{backend}")

    def clear_all(self) -> None:
        """Clear all cached PyTorch versions."""
        self._cache = {}
        self._save_cache()
        logger.info("Cleared all cached PyTorch versions")

    def clear_backend(self, backend: str) -> None:
        """Clear cached versions for a specific backend.

        Args:
            backend: Backend to clear (e.g., "cu128", "cpu")
        """
        cache = self._load_cache()
        cleared = False

        # Remove backend from all Python version sections
        for section_key in list(cache.keys()):
            section = cache[section_key]
            if isinstance(section, dict) and backend in section:
                del section[backend]
                cleared = True
                # Remove empty sections
                if not section:
                    del cache[section_key]

        if cleared:
            self._save_cache()
            logger.info(f"Cleared cached PyTorch versions for backend: {backend}")

    def get_all_entries(self) -> list[dict]:
        """Get all cached entries for display purposes.

        Returns:
            List of dicts with python_version, backend, and versions
        """
        cache = self._load_cache()
        entries = []

        for section_key, section_data in cache.items():
            if not isinstance(section_data, dict):
                continue

            # Parse Python version from section key: py3_12_11 -> 3.12.11
            if section_key.startswith("py"):
                py_version = section_key[2:].replace("_", ".")
            else:
                continue

            for backend, backend_data in section_data.items():
                if not isinstance(backend_data, dict):
                    continue

                entry = {
                    "python_version": py_version,
                    "backend": backend,
                    "versions": {
                        k: v for k, v in backend_data.items() if k != "discovered"
                    },
                    "discovered": backend_data.get("discovered"),
                }
                entries.append(entry)

        return entries
