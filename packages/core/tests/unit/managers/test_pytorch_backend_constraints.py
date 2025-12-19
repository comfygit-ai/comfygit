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

    def test_get_pytorch_config_probes_on_cache_miss(self, temp_env):
        """Should probe for versions when cache is empty."""
        from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager

        def mock_run_command(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0

            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "python find" in cmd_str:
                # uv python find returns a path like this
                result.stdout = "/home/user/.local/share/uv/python/cpython-3.12.11-linux-x86_64-gnu/bin/python3.12"
            elif "venv" in cmd_str:
                result.stdout = "Using CPython 3.12.11"
            elif "pip" in cmd_str and "install" in cmd_str:
                result.stdout = "Installed"
            elif "pip" in cmd_str and "list" in cmd_str:
                # Real uv pip list output - NO backend suffix!
                result.stdout = '[{"name": "torch", "version": "2.9.1"}, {"name": "torchvision", "version": "0.24.1"}, {"name": "torchaudio", "version": "2.9.1"}]'
            return result

        with patch("comfygit_core.utils.pytorch_prober.run_command", side_effect=mock_run_command):
            with patch("shutil.rmtree"):
                manager = PyTorchBackendManager(temp_env["cec_path"], temp_env["workspace_path"])
                config = manager.get_pytorch_config(python_version="3.12.11")

        # Prober should append backend suffix to versions
        assert "constraints" in config
        assert "torch==2.9.1+cu128" in config["constraints"]

    def test_get_pytorch_config_empty_constraints_on_probe_failure(self, temp_env):
        """Should return empty constraints if probe fails."""
        from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager

        def mock_run_command(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 1  # Fail
            result.stderr = "Error"
            return result

        with patch("comfygit_core.utils.pytorch_prober.run_command", side_effect=mock_run_command):
            manager = PyTorchBackendManager(temp_env["cec_path"], temp_env["workspace_path"])
            config = manager.get_pytorch_config(python_version="3.12.11")

        # Should still work but with empty constraints
        assert config["constraints"] == []

    def test_get_pytorch_config_still_works_without_python_version(self, temp_env):
        """Should still work without python_version (backwards compat for legacy code)."""
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
