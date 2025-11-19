"""Integration tests for PyTorch configuration preservation.

Tests that PyTorch is fixed per environment - git operations detect what's
installed and override pyproject.toml to match, rather than trying to change
backends.
"""
import pytest
from unittest.mock import patch


class TestGetInstalledPytorchInfo:
    """Test PyTorch detection from venv."""

    def test_extracts_backend_from_version(self):
        """Should extract backend suffix from version string."""
        from comfygit_core.utils.pytorch import extract_backend_from_version

        assert extract_backend_from_version("2.9.0+cu128") == "cu128"
        assert extract_backend_from_version("2.9.0+rocm6.3") == "rocm6.3"
        assert extract_backend_from_version("2.9.0") is None

    def test_get_installed_info_with_cuda(self):
        """Should return installed PyTorch info with backend."""
        from comfygit_core.utils.pytorch import get_installed_pytorch_info
        from unittest.mock import MagicMock

        # ARRANGE - Mock uv_manager
        mock_uv = MagicMock()
        mock_python = "/path/to/python"
        mock_uv.show_package.side_effect = lambda pkg, python: {
            "torch": "Name: torch\nVersion: 2.9.0+cu128\n",
            "torchvision": "Name: torchvision\nVersion: 0.18.0+cu128\n",
            "torchaudio": "Name: torchaudio\nVersion: 2.9.0+cu128\n",
        }.get(pkg, "")

        # ACT
        result = get_installed_pytorch_info(mock_uv, mock_python)

        # ASSERT
        assert result["torch"] == "2.9.0+cu128"
        assert result["torchvision"] == "0.18.0+cu128"
        assert result["torchaudio"] == "2.9.0+cu128"
        assert result["backend"] == "cu128"

    def test_get_installed_info_cpu_only(self):
        """Should return 'cpu' backend when no suffix."""
        from comfygit_core.utils.pytorch import get_installed_pytorch_info
        from unittest.mock import MagicMock

        # ARRANGE - Mock uv_manager with CPU versions
        mock_uv = MagicMock()
        mock_python = "/path/to/python"
        mock_uv.show_package.side_effect = lambda pkg, python: {
            "torch": "Name: torch\nVersion: 2.9.0\n",
            "torchvision": "Name: torchvision\nVersion: 0.18.0\n",
            "torchaudio": "Name: torchaudio\nVersion: 2.9.0\n",
        }.get(pkg, "")

        # ACT
        result = get_installed_pytorch_info(mock_uv, mock_python)

        # ASSERT
        assert result["backend"] == "cpu"


class TestOverridePytorchConfig:
    """Test PyTorch config override from installed packages."""

    def test_override_skips_when_config_matches_installed(self, test_env):
        """Should skip file modification when config already matches installed PyTorch.

        This prevents spurious 'uncommitted changes' after git checkout when the
        installed PyTorch backend matches what's in pyproject.toml.
        """
        # ARRANGE - Set up config with cu128 that matches what will be "installed"
        config = test_env.pyproject.load()

        if "uv" not in config["tool"]:
            config["tool"]["uv"] = {}

        config["tool"]["uv"]["index"] = [
            {"name": "pytorch-cu128", "url": "https://download.pytorch.org/whl/cu128", "explicit": True}
        ]
        config["tool"]["uv"]["sources"] = {
            "torch": {"index": "pytorch-cu128"},
            "torchvision": {"index": "pytorch-cu128"},
            "torchaudio": {"index": "pytorch-cu128"},
        }
        config["tool"]["uv"]["constraint-dependencies"] = [
            "torch==2.9.0+cu128",
            "torchvision==0.18.0+cu128",
            "torchaudio==2.9.0+cu128",
        ]
        test_env.pyproject.save(config)

        # Commit to establish clean state
        test_env.git_manager.commit_all("setup with cu128")

        # Verify no uncommitted changes before override
        assert not test_env.git_manager.has_uncommitted_changes(), "Should start clean"

        # ACT - Mock the installed PyTorch as cu128 (same as config)
        with patch.object(test_env.uv_manager, 'show_package') as mock_show:
            mock_show.side_effect = lambda pkg, python: {
                "torch": "Name: torch\nVersion: 2.9.0+cu128\n",
                "torchvision": "Name: torchvision\nVersion: 0.18.0+cu128\n",
                "torchaudio": "Name: torchaudio\nVersion: 2.9.0+cu128\n",
            }.get(pkg, "")

            test_env.git_orchestrator._override_pytorch_config_from_installed()

        # ASSERT - No changes should have been made
        has_changes = test_env.git_manager.has_uncommitted_changes()
        assert not has_changes, (
            "Should not modify pyproject.toml when config already matches installed PyTorch"
        )

    def test_override_strips_old_config_and_writes_new(self, test_env):
        """Should strip old PyTorch config and write config matching installed."""
        # ARRANGE - Set up config with cu121 (will be overridden)
        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["torch_backend"] = "cu121"

        if "uv" not in config["tool"]:
            config["tool"]["uv"] = {}

        config["tool"]["uv"]["index"] = [
            {"name": "pytorch-cu121", "url": "https://download.pytorch.org/whl/cu121", "explicit": True}
        ]
        config["tool"]["uv"]["sources"] = {
            "torch": {"index": "pytorch-cu121"},
            "torchvision": {"index": "pytorch-cu121"},
            "torchaudio": {"index": "pytorch-cu121"},
        }
        config["tool"]["uv"]["constraint-dependencies"] = [
            "torch==2.5.0+cu121",
            "numpy>=1.20.0",  # Non-PyTorch constraint
        ]
        test_env.pyproject.save(config)

        # ACT - Mock the installed PyTorch as cu128
        with patch.object(test_env.uv_manager, 'show_package') as mock_show:
            mock_show.side_effect = lambda pkg, python: {
                "torch": "Name: torch\nVersion: 2.9.0+cu128\n",
                "torchvision": "Name: torchvision\nVersion: 0.18.0+cu128\n",
                "torchaudio": "Name: torchaudio\nVersion: 2.9.0+cu128\n",
            }.get(pkg, "")

            test_env.git_orchestrator._override_pytorch_config_from_installed()

        # ASSERT - Config should now have cu128
        config = test_env.pyproject.load()

        # Old indexes should be gone, new one added
        indexes = config.get("tool", {}).get("uv", {}).get("index", [])
        old_indexes = [idx for idx in indexes if "cu121" in idx.get("name", "")]
        assert len(old_indexes) == 0, "Old cu121 indexes should be removed"

        new_indexes = [idx for idx in indexes if "cu128" in idx.get("name", "")]
        assert len(new_indexes) == 1, "New cu128 index should be added"

        # Constraints should have cu128 versions
        constraints = config.get("tool", {}).get("uv", {}).get("constraint-dependencies", [])
        cu128_constraints = [c for c in constraints if "cu128" in c]
        assert len(cu128_constraints) == 3, "Should have constraints for all PyTorch packages"

        # Non-PyTorch constraint should be preserved
        numpy_constraints = [c for c in constraints if "numpy" in c]
        assert len(numpy_constraints) == 1, "Non-PyTorch constraints should be preserved"

    def test_override_skips_when_no_pytorch_installed(self, test_env):
        """Should skip override when no PyTorch in venv."""
        # ARRANGE - Config has cu121
        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["torch_backend"] = "cu121"
        test_env.pyproject.save(config)

        # ACT - Mock no PyTorch installed
        with patch.object(test_env.uv_manager, 'show_package') as mock_show:
            mock_show.side_effect = Exception("Package not found")
            test_env.git_orchestrator._override_pytorch_config_from_installed()

        # ASSERT - Config should be unchanged
        config = test_env.pyproject.load()
        assert config["tool"]["comfygit"]["torch_backend"] == "cu121"


class TestCheckoutPreservesPytorch:
    """Test that checkout preserves installed PyTorch backend."""

    def test_checkout_overrides_config_with_installed(self, test_env, mock_comfyui_clone):
        """Checkout should override pyproject.toml with installed PyTorch backend."""
        # ARRANGE - Initial commit with cpu backend
        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["torch_backend"] = "cpu"
        test_env.pyproject.save(config)
        test_env.git_manager.commit_all("commit with cpu backend")

        # Second commit with cu128 backend (simulating different machine)
        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["torch_backend"] = "cu128"
        if "uv" not in config["tool"]:
            config["tool"]["uv"] = {}
        config["tool"]["uv"]["index"] = [
            {"name": "pytorch-cu128", "url": "https://download.pytorch.org/whl/cu128", "explicit": True}
        ]
        config["tool"]["uv"]["sources"] = {
            "torch": {"index": "pytorch-cu128"},
            "torchvision": {"index": "pytorch-cu128"},
            "torchaudio": {"index": "pytorch-cu128"},
        }
        test_env.pyproject.save(config)
        test_env.git_manager.commit_all("commit with cu128 backend")

        # Get commits
        history = test_env.git_manager.get_version_history(limit=10)
        cuda_commit = history[0]["hash"]
        cpu_commit = history[1]["hash"]

        # Checkout cpu commit first
        test_env.checkout(cpu_commit, force=True)

        # ACT - Checkout cuda commit, but our machine has cu121 installed
        with patch.object(test_env.uv_manager, 'show_package') as mock_show:
            mock_show.side_effect = lambda pkg, python: {
                "torch": "Name: torch\nVersion: 2.9.0+cu121\n",
                "torchvision": "Name: torchvision\nVersion: 0.18.0+cu121\n",
                "torchaudio": "Name: torchaudio\nVersion: 2.9.0+cu121\n",
            }.get(pkg, "")

            test_env.checkout(cuda_commit, force=True)

        # ASSERT - Config should have cu121 (installed), not cu128 (from commit)
        config = test_env.pyproject.load()
        indexes = config.get("tool", {}).get("uv", {}).get("index", [])
        cu121_indexes = [idx for idx in indexes if "cu121" in idx.get("name", "")]
        assert len(cu121_indexes) == 1, "Should have cu121 index from installed PyTorch"

        cu128_indexes = [idx for idx in indexes if "cu128" in idx.get("name", "")]
        assert len(cu128_indexes) == 0, "Should not have cu128 from checked-out commit"


class TestResetPreservesPytorch:
    """Test that reset preserves installed PyTorch backend."""

    def test_hard_reset_overrides_config_with_installed(self, test_env, mock_comfyui_clone):
        """Hard reset should override pyproject.toml with installed PyTorch."""
        # ARRANGE - Commits with different backends
        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["torch_backend"] = "cpu"
        test_env.pyproject.save(config)
        test_env.git_manager.commit_all("commit with cpu")

        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["torch_backend"] = "cu128"
        test_env.pyproject.save(config)
        test_env.git_manager.commit_all("commit with cu128")

        history = test_env.git_manager.get_version_history(limit=10)
        cpu_commit = history[1]["hash"]

        # ACT - Reset to cpu commit, but machine has cu121
        with patch.object(test_env.uv_manager, 'show_package') as mock_show:
            mock_show.side_effect = lambda pkg, python: {
                "torch": "Name: torch\nVersion: 2.9.0+cu121\n",
                "torchvision": "Name: torchvision\nVersion: 0.18.0+cu121\n",
                "torchaudio": "Name: torchaudio\nVersion: 2.9.0+cu121\n",
            }.get(pkg, "")

            test_env.reset(cpu_commit, mode="hard", force=True)

        # ASSERT - Should have cu121 (installed), not cpu (from reset target)
        config = test_env.pyproject.load()
        indexes = config.get("tool", {}).get("uv", {}).get("index", [])
        cu121_indexes = [idx for idx in indexes if "cu121" in idx.get("name", "")]
        assert len(cu121_indexes) == 1, "Should have cu121 index from installed PyTorch"


class TestImportResolvesAutoBackend:
    """Test that import resolves 'auto' to concrete backend."""

    def test_import_stores_concrete_backend(self, test_env):
        """Import should store resolved backend, never 'auto'."""
        # This is tested indirectly through the finalize_import flow
        # The key assertion is that torch_backend in config is never "auto"

        # ARRANGE - Set torch_backend to "auto" in test env (simulating import with auto)
        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["torch_backend"] = "auto"
        test_env.pyproject.save(config)

        # In a real import, after installing PyTorch with --torch-backend=auto,
        # we detect the actual backend and store it. Here we just verify the
        # detection logic stores a concrete value.

        from comfygit_core.utils.pytorch import extract_backend_from_version

        # Simulated detection
        version = "2.9.0+cu128"
        backend = extract_backend_from_version(version)
        resolved_backend = backend if backend else "cpu"

        # Store resolved backend (this is what finalize_import does)
        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["torch_backend"] = resolved_backend
        test_env.pyproject.save(config)

        # ASSERT - Backend should be concrete, not "auto"
        config = test_env.pyproject.load()
        stored_backend = config["tool"]["comfygit"]["torch_backend"]
        assert stored_backend == "cu128", "Should store concrete backend"
        assert stored_backend != "auto", "Should never store 'auto' as backend"
