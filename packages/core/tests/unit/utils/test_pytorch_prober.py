"""Tests for PyTorch version prober utilities."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest


class TestGetExactPythonVersion:
    """Tests for get_exact_python_version function."""

    def test_parses_uv_python_find_output(self):
        """Should parse exact Python version from uv python find output."""
        from comfygit_core.utils.pytorch_prober import get_exact_python_version

        mock_result = MagicMock()
        mock_result.returncode = 0
        # Real uv python find output looks like this path
        mock_result.stdout = "/home/user/.local/share/uv/python/cpython-3.12.11-linux-x86_64-gnu/bin/python3.12"

        with patch("comfygit_core.utils.pytorch_prober.run_command", return_value=mock_result):
            version = get_exact_python_version("3.12")
            assert version == "3.12.11"

    def test_handles_3_part_version_request(self):
        """Should work when given exact 3-part version."""
        from comfygit_core.utils.pytorch_prober import get_exact_python_version

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/home/user/.local/share/uv/python/cpython-3.11.9-linux-x86_64-gnu/bin/python3.11"

        with patch("comfygit_core.utils.pytorch_prober.run_command", return_value=mock_result):
            version = get_exact_python_version("3.11.9")
            assert version == "3.11.9"

    def test_raises_on_invalid_output(self):
        """Should raise error when can't parse version."""
        from comfygit_core.utils.pytorch_prober import get_exact_python_version, PyTorchProbeError

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/usr/bin/python3"  # No version in path

        with patch("comfygit_core.utils.pytorch_prober.run_command", return_value=mock_result):
            with pytest.raises(PyTorchProbeError):
                get_exact_python_version("3.12")


class TestProbePyTorchVersions:
    """Tests for probe_pytorch_versions function."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        with TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            yield workspace_path

    def test_probe_returns_version_dict_with_backend_suffix(self, temp_workspace):
        """Should return dict with torch versions including backend suffix.

        uv pip list returns versions WITHOUT local suffix (e.g., "2.9.1"),
        so the prober must append the backend suffix (e.g., "+cu128").
        """
        from comfygit_core.utils.pytorch_prober import probe_pytorch_versions

        # Mock all subprocess calls - uv pip list returns versions WITHOUT suffix
        def mock_run_command(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            if "venv" in cmd_str:
                result.stdout = "Using CPython 3.12.11\nCreated venv"
            elif "pip install" in cmd_str:
                result.stdout = "Installed packages"
            elif "pip list" in cmd_str:
                # Real uv pip list output - NO backend suffix!
                result.stdout = '[{"name": "torch", "version": "2.9.1"}, {"name": "torchvision", "version": "0.24.1"}, {"name": "torchaudio", "version": "2.9.1"}]'
            return result

        with patch("comfygit_core.utils.pytorch_prober.run_command", side_effect=mock_run_command):
            with patch("shutil.rmtree"):  # Don't actually delete
                versions = probe_pytorch_versions("3.12.11", "cu128", temp_workspace)

        assert "torch" in versions
        assert "torchvision" in versions
        assert "torchaudio" in versions
        # Prober should append the backend suffix
        assert versions["torch"] == "2.9.1+cu128"
        assert versions["torchvision"] == "0.24.1+cu128"
        assert versions["torchaudio"] == "2.9.1+cu128"

    def test_probe_updates_cache(self, temp_workspace):
        """Probe should update the workspace cache with suffixed versions."""
        from comfygit_core.utils.pytorch_prober import probe_pytorch_versions
        from comfygit_core.caching.pytorch_version_cache import PyTorchVersionCache

        def mock_run_command(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            if "venv" in cmd_str:
                result.stdout = "Using CPython 3.12.11"
            elif "pip install" in cmd_str:
                result.stdout = "Installed"
            elif "pip list" in cmd_str:
                # Real output - no suffix
                result.stdout = '[{"name": "torch", "version": "2.9.1"}, {"name": "torchvision", "version": "0.24.1"}, {"name": "torchaudio", "version": "2.9.1"}]'
            return result

        with patch("comfygit_core.utils.pytorch_prober.run_command", side_effect=mock_run_command):
            with patch("shutil.rmtree"):
                probe_pytorch_versions("3.12.11", "cu128", temp_workspace)

        # Cache should now have the versions WITH backend suffix appended
        cache = PyTorchVersionCache(temp_workspace)
        cached = cache.get_versions("3.12.11", "cu128")
        assert cached is not None
        assert cached["torch"] == "2.9.1+cu128"

    def test_probe_cleans_up_temp_dir(self, temp_workspace):
        """Probe should clean up temporary venv directory."""
        from comfygit_core.utils.pytorch_prober import probe_pytorch_versions

        cleanup_called = []

        def mock_run_command(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            if "venv" in cmd_str:
                result.stdout = "Using CPython 3.12.11"
            elif "pip install" in cmd_str:
                result.stdout = "Installed"
            elif "pip list" in cmd_str:
                # Real output - no suffix
                result.stdout = '[{"name": "torch", "version": "2.9.1"}]'
            return result

        def mock_rmtree(path, *args, **kwargs):
            cleanup_called.append(path)

        with patch("comfygit_core.utils.pytorch_prober.run_command", side_effect=mock_run_command):
            with patch("shutil.rmtree", side_effect=mock_rmtree):
                probe_pytorch_versions("3.12.11", "cu128", temp_workspace)

        assert len(cleanup_called) > 0
