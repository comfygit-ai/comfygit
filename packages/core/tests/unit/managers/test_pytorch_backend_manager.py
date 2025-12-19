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

    def test_get_backend_raises_when_file_missing(self, temp_cec):
        """Should raise ValueError when file doesn't exist."""
        manager = PyTorchBackendManager(temp_cec)

        with pytest.raises(ValueError, match=".pytorch-backend"):
            manager.get_backend()

    def test_has_backend_false_when_missing(self, temp_cec):
        """Should return False when .pytorch-backend file doesn't exist."""
        manager = PyTorchBackendManager(temp_cec)
        assert not manager.has_backend()

    def test_has_backend_true_when_exists(self, temp_cec):
        """Should return True when .pytorch-backend file exists."""
        backend_file = temp_cec / ".pytorch-backend"
        backend_file.write_text("cu128")

        manager = PyTorchBackendManager(temp_cec)
        assert manager.has_backend()

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


class TestGitignoreUpdate:
    """Tests for .gitignore migration support."""

    @pytest.fixture
    def temp_cec(self):
        """Create a temporary .cec directory for testing."""
        with TemporaryDirectory() as tmpdir:
            cec_path = Path(tmpdir) / ".cec"
            cec_path.mkdir()
            yield cec_path

    def test_set_backend_adds_gitignore_entry_when_missing(self, temp_cec):
        """set_backend should add .pytorch-backend to .gitignore if missing."""
        # Create .gitignore without .pytorch-backend entry
        gitignore = temp_cec / ".gitignore"
        gitignore.write_text("# Existing entries\nstaging/\n__pycache__/\n")

        manager = PyTorchBackendManager(temp_cec)
        manager.set_backend("cu128")

        # Should have added .pytorch-backend
        content = gitignore.read_text()
        assert ".pytorch-backend" in content

    def test_set_backend_does_not_duplicate_gitignore_entry(self, temp_cec):
        """set_backend should not duplicate .pytorch-backend if already present."""
        # Create .gitignore WITH .pytorch-backend entry
        gitignore = temp_cec / ".gitignore"
        original_content = "# Existing entries\nstaging/\n.pytorch-backend\n__pycache__/\n"
        gitignore.write_text(original_content)

        manager = PyTorchBackendManager(temp_cec)
        manager.set_backend("cu128")

        # Should not have added duplicate
        content = gitignore.read_text()
        assert content.count(".pytorch-backend") == 1

    def test_set_backend_creates_gitignore_if_missing(self, temp_cec):
        """set_backend should create .gitignore if it doesn't exist."""
        gitignore = temp_cec / ".gitignore"
        assert not gitignore.exists()

        manager = PyTorchBackendManager(temp_cec)
        manager.set_backend("cu128")

        # Should have created .gitignore with the entry
        assert gitignore.exists()
        content = gitignore.read_text()
        assert ".pytorch-backend" in content

    def test_set_backend_handles_gitignore_with_comment(self, temp_cec):
        """set_backend should recognize entry even with trailing comment."""
        gitignore = temp_cec / ".gitignore"
        gitignore.write_text(".pytorch-backend # machine-specific\n")

        manager = PyTorchBackendManager(temp_cec)
        manager.set_backend("cu128")

        # Should not have added duplicate
        content = gitignore.read_text()
        assert content.count(".pytorch-backend") == 1
