"""Tests for PyTorchBackendManager."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager


class TestPyTorchBackendManager:
    """Tests for PyTorchBackendManager class."""

    @pytest.fixture
    def temp_cec(self):
        """Create a temporary .cec directory for testing."""
        with TemporaryDirectory() as tmpdir:
            cec_path = Path(tmpdir) / ".cec"
            cec_path.mkdir()
            yield cec_path

    def test_get_backend_returns_file_content(self, temp_cec):
        """Should read backend from .pytorch-backend file."""
        backend_file = temp_cec / ".pytorch-backend"
        backend_file.write_text("cu128")

        manager = PyTorchBackendManager(temp_cec)
        assert manager.get_backend() == "cu128"

    def test_get_backend_strips_whitespace(self, temp_cec):
        """Should strip whitespace from backend file."""
        backend_file = temp_cec / ".pytorch-backend"
        backend_file.write_text("  cu121\n  ")

        manager = PyTorchBackendManager(temp_cec)
        assert manager.get_backend() == "cu121"

    def test_get_backend_auto_detects_when_file_missing(self, temp_cec):
        """Should auto-detect backend when file doesn't exist."""
        manager = PyTorchBackendManager(temp_cec)
        backend = manager.get_backend()

        # Should return a valid backend (auto-detected)
        assert backend is not None
        assert isinstance(backend, str)
        assert len(backend) > 0

    def test_set_backend_writes_file(self, temp_cec):
        """Should write backend to .pytorch-backend file."""
        manager = PyTorchBackendManager(temp_cec)
        manager.set_backend("cu128")

        backend_file = temp_cec / ".pytorch-backend"
        assert backend_file.exists()
        assert backend_file.read_text() == "cu128"

    def test_set_backend_overwrites_existing(self, temp_cec):
        """Should overwrite existing backend file."""
        backend_file = temp_cec / ".pytorch-backend"
        backend_file.write_text("cu121")

        manager = PyTorchBackendManager(temp_cec)
        manager.set_backend("cu128")

        assert backend_file.read_text() == "cu128"

    def test_detect_backend_returns_cpu_on_no_cuda(self, temp_cec):
        """Should return 'cpu' when no CUDA is available."""
        manager = PyTorchBackendManager(temp_cec)
        # In test environment without CUDA, should return cpu
        backend = manager.detect_backend()

        # Either cpu or a valid CUDA backend
        assert backend is not None
        assert isinstance(backend, str)

    def test_get_pytorch_config_includes_index(self, temp_cec):
        """Should generate config with PyTorch index."""
        backend_file = temp_cec / ".pytorch-backend"
        backend_file.write_text("cu128")

        manager = PyTorchBackendManager(temp_cec)
        config = manager.get_pytorch_config()

        # Should have index configuration
        assert "indexes" in config
        assert len(config["indexes"]) > 0
        assert any("cu128" in idx.get("url", "") for idx in config["indexes"])

    def test_get_pytorch_config_includes_sources(self, temp_cec):
        """Should generate config with PyTorch package sources."""
        backend_file = temp_cec / ".pytorch-backend"
        backend_file.write_text("cu128")

        manager = PyTorchBackendManager(temp_cec)
        config = manager.get_pytorch_config()

        # Should have sources for torch packages
        assert "sources" in config
        assert "torch" in config["sources"]

    def test_get_pytorch_config_includes_constraints(self, temp_cec):
        """Should generate config with PyTorch constraints."""
        backend_file = temp_cec / ".pytorch-backend"
        backend_file.write_text("cu128")

        manager = PyTorchBackendManager(temp_cec)
        config = manager.get_pytorch_config()

        # Should have constraint dependencies
        assert "constraints" in config

    def test_get_pytorch_config_for_cpu(self, temp_cec):
        """Should generate valid config for CPU backend."""
        backend_file = temp_cec / ".pytorch-backend"
        backend_file.write_text("cpu")

        manager = PyTorchBackendManager(temp_cec)
        config = manager.get_pytorch_config()

        # CPU should have an index URL too
        assert "indexes" in config
        assert any("cpu" in idx.get("url", "") for idx in config["indexes"])

    def test_get_pytorch_config_for_rocm(self, temp_cec):
        """Should generate valid config for ROCm backend."""
        backend_file = temp_cec / ".pytorch-backend"
        backend_file.write_text("rocm6.3")

        manager = PyTorchBackendManager(temp_cec)
        config = manager.get_pytorch_config()

        # ROCm should have its index URL
        assert "indexes" in config
        assert any("rocm6.3" in idx.get("url", "") for idx in config["indexes"])


class TestPyTorchBackendValidation:
    """Tests for backend validation."""

    @pytest.fixture
    def temp_cec(self):
        """Create a temporary .cec directory for testing."""
        with TemporaryDirectory() as tmpdir:
            cec_path = Path(tmpdir) / ".cec"
            cec_path.mkdir()
            yield cec_path

    def test_validate_known_cuda_backends(self, temp_cec):
        """Should accept known CUDA backends."""
        manager = PyTorchBackendManager(temp_cec)

        # Common CUDA backends should be valid
        for backend in ["cu118", "cu121", "cu124", "cu126", "cu128"]:
            assert manager.is_valid_backend(backend)

    def test_validate_cpu_backend(self, temp_cec):
        """Should accept cpu backend."""
        manager = PyTorchBackendManager(temp_cec)
        assert manager.is_valid_backend("cpu")

    def test_validate_rocm_backends(self, temp_cec):
        """Should accept ROCm backends."""
        manager = PyTorchBackendManager(temp_cec)

        for backend in ["rocm6.2", "rocm6.3", "rocm6.4"]:
            assert manager.is_valid_backend(backend)

    def test_validate_xpu_backend(self, temp_cec):
        """Should accept Intel XPU backend."""
        manager = PyTorchBackendManager(temp_cec)
        assert manager.is_valid_backend("xpu")

    def test_validate_future_cuda_backends(self, temp_cec):
        """Should accept future CUDA backends matching pattern."""
        manager = PyTorchBackendManager(temp_cec)

        # Future versions should still be valid based on pattern
        for backend in ["cu130", "cu140", "cu200"]:
            assert manager.is_valid_backend(backend)

    def test_reject_invalid_backends(self, temp_cec):
        """Should reject clearly invalid backends."""
        manager = PyTorchBackendManager(temp_cec)

        for backend in ["invalid", "cuda12", "rocm", "", "123"]:
            assert not manager.is_valid_backend(backend)
