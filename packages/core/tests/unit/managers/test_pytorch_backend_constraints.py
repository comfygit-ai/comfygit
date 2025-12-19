"""Tests for PyTorchBackendManager.get_pytorch_config() with version constraints."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

import pytest


class TestPyTorchBackendConstraints:
    """Tests for PyTorch version constraint injection."""

    @pytest.fixture
    def temp_env(self):
        """Create a temporary environment with .cec and workspace dirs."""
        with TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            cec_path = workspace_path / ".cec"
            cec_path.mkdir()
            comfygit_dir = workspace_path / ".comfygit"
            comfygit_dir.mkdir()

            # Create .pytorch-backend file
            backend_file = cec_path / ".pytorch-backend"
            backend_file.write_text("cu128")

            yield {
                "workspace_path": workspace_path,
                "cec_path": cec_path,
                "backend_file": backend_file,
            }

    def test_get_pytorch_config_includes_constraints_from_cache(self, temp_env):
        """Should include constraint-dependencies from cached versions."""
        from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        # Pre-populate cache
        cache = PyTorchVersionCache(temp_env["workspace_path"])
        cache.set_versions("3.12.11", "cu128", {
            "torch": "2.9.1+cu128",
            "torchvision": "0.24.1+cu128",
            "torchaudio": "2.9.1+cu128",
        })

        # Mock get_exact_python_version to return the exact version
        with patch("comfygit_core.utils.pytorch_prober.get_exact_python_version", return_value="3.12.11"):
            manager = PyTorchBackendManager(temp_env["cec_path"], temp_env["workspace_path"])
            config = manager.get_pytorch_config(python_version="3.12.11")

        # Should have constraints
        assert "constraints" in config
        constraints = config["constraints"]
        assert len(constraints) == 3
        assert "torch==2.9.1+cu128" in constraints
        assert "torchvision==0.24.1+cu128" in constraints
        assert "torchaudio==2.9.1+cu128" in constraints

    def test_get_pytorch_config_empty_constraints_on_cache_miss(self, temp_env):
        """Should return empty constraints when cache miss (no probing in get_pytorch_config)."""
        from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager

        # Mock get_exact_python_version
        with patch("comfygit_core.utils.pytorch_prober.get_exact_python_version", return_value="3.12.11"):
            manager = PyTorchBackendManager(temp_env["cec_path"], temp_env["workspace_path"])
            # No cache entry exists
            config = manager.get_pytorch_config(python_version="3.12.11")

        # Should have empty constraints (cache miss, no probing here)
        assert config["constraints"] == []
        # But should still have indexes and sources
        assert len(config["indexes"]) > 0
        assert "torch" in config["sources"]

    def test_get_pytorch_config_still_works_without_python_version(self, temp_env):
        """Should still work without python_version (no constraints)."""
        from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager

        manager = PyTorchBackendManager(temp_env["cec_path"], temp_env["workspace_path"])
        config = manager.get_pytorch_config()

        # Should have indexes and sources, constraints empty
        assert "indexes" in config
        assert "sources" in config
        assert config["constraints"] == []

    def test_get_pytorch_config_uses_exact_python_version_for_cache(self, temp_env):
        """Should use exact Python version (not requested) for cache lookup."""
        from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        # Cache uses exact version 3.12.11
        cache = PyTorchVersionCache(temp_env["workspace_path"])
        cache.set_versions("3.12.11", "cu128", {"torch": "2.9.1+cu128"})

        # Mock get_exact_python_version to resolve "3.12" to "3.12.11"
        with patch("comfygit_core.utils.pytorch_prober.get_exact_python_version", return_value="3.12.11"):
            manager = PyTorchBackendManager(temp_env["cec_path"], temp_env["workspace_path"])
            # Pass "3.12" (not exact), should still find cache
            config = manager.get_pytorch_config(python_version="3.12")

        assert "torch==2.9.1+cu128" in config["constraints"]


class TestProbeAndSetBackend:
    """Tests for probe_and_set_backend method."""

    @pytest.fixture
    def temp_env(self):
        """Create a temporary environment with .cec and workspace dirs."""
        with TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            cec_path = workspace_path / ".cec"
            cec_path.mkdir()
            comfygit_dir = workspace_path / ".comfygit"
            comfygit_dir.mkdir()

            yield {
                "workspace_path": workspace_path,
                "cec_path": cec_path,
            }

    def test_probe_and_set_backend_writes_file(self, temp_env):
        """Should write resolved backend to .pytorch-backend file."""
        from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager

        def mock_run_command(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            if "python find" in cmd_str:
                result.stdout = "/path/to/cpython-3.12.11/bin/python"
            elif "venv" in cmd_str:
                result.stdout = "Created venv"
            elif "pip install" in cmd_str and "--dry-run" in cmd_str:
                result.stdout = """ + torch==2.9.1+cu128
 + torchvision==0.24.1+cu128
 + torchaudio==2.9.1+cu128
"""
            else:
                result.stdout = ""
            return result

        with patch("comfygit_core.utils.pytorch_prober.run_command", side_effect=mock_run_command):
            with patch("shutil.rmtree"):
                manager = PyTorchBackendManager(temp_env["cec_path"], temp_env["workspace_path"])
                backend = manager.probe_and_set_backend("3.12", "auto")

        assert backend == "cu128"
        assert manager.has_backend()
        assert manager.get_backend() == "cu128"

    def test_probe_and_set_backend_caches_versions(self, temp_env):
        """Should cache probed versions for later use."""
        from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        def mock_run_command(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            if "python find" in cmd_str:
                result.stdout = "/path/to/cpython-3.12.11/bin/python"
            elif "venv" in cmd_str:
                result.stdout = "Created venv"
            elif "pip install" in cmd_str and "--dry-run" in cmd_str:
                result.stdout = """ + torch==2.9.1+cu128
 + torchvision==0.24.1+cu128
 + torchaudio==2.9.1+cu128
"""
            else:
                result.stdout = ""
            return result

        with patch("comfygit_core.utils.pytorch_prober.run_command", side_effect=mock_run_command):
            with patch("shutil.rmtree"):
                manager = PyTorchBackendManager(temp_env["cec_path"], temp_env["workspace_path"])
                manager.probe_and_set_backend("3.12", "cu128")

        # Check cache was populated
        cache = PyTorchVersionCache(temp_env["workspace_path"])
        versions = cache.get_versions("3.12.11", "cu128")
        assert versions is not None
        assert versions["torch"] == "2.9.1+cu128"

    def test_probe_and_set_backend_raises_without_workspace(self, temp_env):
        """Should raise ValueError if workspace_path not set."""
        from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager

        manager = PyTorchBackendManager(temp_env["cec_path"])  # No workspace_path

        with pytest.raises(ValueError, match="workspace_path required"):
            manager.probe_and_set_backend("3.12", "auto")
