"""Tests for PyTorchVersionCache."""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import tomlkit


class TestPyTorchVersionCache:
    """Tests for PyTorchVersionCache class."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        with TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            yield workspace_path

    def test_get_versions_returns_none_when_cache_empty(self, temp_workspace):
        """Should return None when no versions are cached."""
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        cache = PyTorchVersionCache(temp_workspace)
        result = cache.get_versions("3.12.11", "cu128")
        assert result is None

    def test_set_and_get_versions(self, temp_workspace):
        """Should store and retrieve PyTorch versions."""
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        cache = PyTorchVersionCache(temp_workspace)
        versions = {
            "torch": "2.9.1+cu128",
            "torchvision": "0.24.1+cu128",
            "torchaudio": "2.9.1+cu128",
        }

        cache.set_versions("3.12.11", "cu128", versions)

        result = cache.get_versions("3.12.11", "cu128")
        assert result is not None
        assert result["torch"] == "2.9.1+cu128"
        assert result["torchvision"] == "0.24.1+cu128"
        assert result["torchaudio"] == "2.9.1+cu128"

    def test_get_versions_different_python_versions(self, temp_workspace):
        """Should distinguish between different Python versions."""
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        cache = PyTorchVersionCache(temp_workspace)

        # Cache for Python 3.11
        cache.set_versions("3.11.0", "cu128", {"torch": "2.9.0+cu128"})

        # Cache for Python 3.12
        cache.set_versions("3.12.11", "cu128", {"torch": "2.9.1+cu128"})

        # Should retrieve the correct version for each Python
        assert cache.get_versions("3.11.0", "cu128")["torch"] == "2.9.0+cu128"
        assert cache.get_versions("3.12.11", "cu128")["torch"] == "2.9.1+cu128"

    def test_get_versions_different_backends(self, temp_workspace):
        """Should distinguish between different backends."""
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        cache = PyTorchVersionCache(temp_workspace)

        cache.set_versions("3.12.11", "cu128", {"torch": "2.9.1+cu128"})
        cache.set_versions("3.12.11", "cu126", {"torch": "2.9.1+cu126"})

        assert cache.get_versions("3.12.11", "cu128")["torch"] == "2.9.1+cu128"
        assert cache.get_versions("3.12.11", "cu126")["torch"] == "2.9.1+cu126"

    def test_clear_all(self, temp_workspace):
        """Should clear all cached versions."""
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        cache = PyTorchVersionCache(temp_workspace)

        cache.set_versions("3.12.11", "cu128", {"torch": "2.9.1+cu128"})
        cache.set_versions("3.12.11", "cu126", {"torch": "2.9.1+cu126"})

        cache.clear_all()

        assert cache.get_versions("3.12.11", "cu128") is None
        assert cache.get_versions("3.12.11", "cu126") is None

    def test_clear_backend(self, temp_workspace):
        """Should clear versions for a specific backend only."""
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        cache = PyTorchVersionCache(temp_workspace)

        cache.set_versions("3.12.11", "cu128", {"torch": "2.9.1+cu128"})
        cache.set_versions("3.12.11", "cu126", {"torch": "2.9.1+cu126"})

        cache.clear_backend("cu128")

        assert cache.get_versions("3.12.11", "cu128") is None
        assert cache.get_versions("3.12.11", "cu126") is not None

    def test_cache_persists_to_file(self, temp_workspace):
        """Cache should persist to disk and survive recreation."""
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        # Create cache and add versions
        cache1 = PyTorchVersionCache(temp_workspace)
        cache1.set_versions("3.12.11", "cu128", {"torch": "2.9.1+cu128"})

        # Create new cache instance
        cache2 = PyTorchVersionCache(temp_workspace)
        result = cache2.get_versions("3.12.11", "cu128")

        assert result is not None
        assert result["torch"] == "2.9.1+cu128"

    def test_cache_file_location(self, temp_workspace):
        """Cache file should be at workspace/comfygit_cache/pytorch-cache.toml."""
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        cache = PyTorchVersionCache(temp_workspace)
        cache.set_versions("3.12.11", "cu128", {"torch": "2.9.1+cu128"})

        cache_file = temp_workspace / "comfygit_cache" / "pytorch-cache.toml"
        assert cache_file.exists()

    def test_get_all_cached_entries(self, temp_workspace):
        """Should return all cached entries for display."""
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        cache = PyTorchVersionCache(temp_workspace)

        cache.set_versions("3.12.11", "cu128", {"torch": "2.9.1+cu128"})
        cache.set_versions("3.12.11", "cu126", {"torch": "2.9.1+cu126"})
        cache.set_versions("3.11.0", "cu128", {"torch": "2.9.0+cu128"})

        entries = cache.get_all_entries()

        assert len(entries) == 3
