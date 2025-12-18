"""Tests for PyTorch injection context manager."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import tomlkit

from comfygit_core.managers.pytorch_backend_manager import PyTorchBackendManager
from comfygit_core.managers.pyproject_manager import PyprojectManager


class TestPyTorchInjectionContext:
    """Tests for PyTorch injection context manager."""

    @pytest.fixture
    def temp_env(self):
        """Create a temporary environment with pyproject.toml and .cec dir."""
        with TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir)
            cec_path = env_path / ".cec"
            cec_path.mkdir()

            # Create pyproject.toml
            pyproject_path = cec_path / "pyproject.toml"
            initial_config = {
                "project": {
                    "name": "test-env",
                    "version": "0.1.0",
                    "requires-python": ">=3.11",
                    "dependencies": ["numpy>=1.0"],
                },
                "tool": {
                    "comfygit": {
                        "comfyui_version": "v0.3.60",
                        "python_version": "3.11",
                    }
                }
            }
            with open(pyproject_path, 'w') as f:
                tomlkit.dump(initial_config, f)

            # Create .pytorch-backend file
            backend_file = cec_path / ".pytorch-backend"
            backend_file.write_text("cu128")

            yield {
                "env_path": env_path,
                "cec_path": cec_path,
                "pyproject_path": pyproject_path,
                "backend_file": backend_file,
            }

    def test_injection_adds_pytorch_config(self, temp_env):
        """Should inject PyTorch config before yielding."""
        pyproject = PyprojectManager(temp_env["pyproject_path"])
        pytorch_manager = PyTorchBackendManager(temp_env["cec_path"])

        # Read original content
        original_content = temp_env["pyproject_path"].read_text()
        assert "pytorch" not in original_content.lower()

        # Use injection context
        with pyproject.pytorch_injection_context(pytorch_manager):
            # Inside context, should have PyTorch config
            injected_content = temp_env["pyproject_path"].read_text()
            assert "pytorch-cu128" in injected_content
            assert "download.pytorch.org" in injected_content

    def test_injection_restores_on_success(self, temp_env):
        """Should restore original config after successful exit."""
        pyproject = PyprojectManager(temp_env["pyproject_path"])
        pytorch_manager = PyTorchBackendManager(temp_env["cec_path"])

        original_content = temp_env["pyproject_path"].read_text()

        with pyproject.pytorch_injection_context(pytorch_manager):
            # Inside context, config is injected
            pass

        # After context, should be restored to original
        restored_content = temp_env["pyproject_path"].read_text()
        assert restored_content == original_content

    def test_injection_restores_on_error(self, temp_env):
        """Should restore original config even when an error occurs."""
        pyproject = PyprojectManager(temp_env["pyproject_path"])
        pytorch_manager = PyTorchBackendManager(temp_env["cec_path"])

        original_content = temp_env["pyproject_path"].read_text()

        with pytest.raises(ValueError):
            with pyproject.pytorch_injection_context(pytorch_manager):
                # Simulate an error during sync
                raise ValueError("Simulated sync failure")

        # After error, should still be restored
        restored_content = temp_env["pyproject_path"].read_text()
        assert restored_content == original_content

    def test_injection_includes_index(self, temp_env):
        """Should inject PyTorch index configuration."""
        pyproject = PyprojectManager(temp_env["pyproject_path"])
        pytorch_manager = PyTorchBackendManager(temp_env["cec_path"])

        with pyproject.pytorch_injection_context(pytorch_manager):
            config = pyproject.load(force_reload=True)

            # Should have tool.uv.index
            uv_config = config.get("tool", {}).get("uv", {})
            indexes = uv_config.get("index", [])

            assert len(indexes) > 0
            pytorch_index = next(
                (idx for idx in indexes if "pytorch" in idx.get("name", "")),
                None
            )
            assert pytorch_index is not None
            assert "cu128" in pytorch_index.get("url", "")

    def test_injection_includes_sources(self, temp_env):
        """Should inject PyTorch package sources."""
        pyproject = PyprojectManager(temp_env["pyproject_path"])
        pytorch_manager = PyTorchBackendManager(temp_env["cec_path"])

        with pyproject.pytorch_injection_context(pytorch_manager):
            config = pyproject.load(force_reload=True)

            # Should have tool.uv.sources.torch
            uv_config = config.get("tool", {}).get("uv", {})
            sources = uv_config.get("sources", {})

            assert "torch" in sources

    def test_injection_preserves_existing_config(self, temp_env):
        """Should preserve existing non-PyTorch config during injection."""
        pyproject = PyprojectManager(temp_env["pyproject_path"])
        pytorch_manager = PyTorchBackendManager(temp_env["cec_path"])

        with pyproject.pytorch_injection_context(pytorch_manager):
            config = pyproject.load(force_reload=True)

            # Original config should still be there
            assert config["project"]["name"] == "test-env"
            assert "numpy>=1.0" in config["project"]["dependencies"]
            assert config["tool"]["comfygit"]["comfyui_version"] == "v0.3.60"

    def test_injection_with_different_backend(self, temp_env):
        """Should inject correct config based on backend file content."""
        # Change backend to cpu
        temp_env["backend_file"].write_text("cpu")

        pyproject = PyprojectManager(temp_env["pyproject_path"])
        pytorch_manager = PyTorchBackendManager(temp_env["cec_path"])

        with pyproject.pytorch_injection_context(pytorch_manager):
            content = temp_env["pyproject_path"].read_text()
            assert "pytorch-cpu" in content
            assert "/cpu" in content  # Should have cpu in URL path


class TestPyTorchInjectionEdgeCases:
    """Tests for edge cases in PyTorch injection."""

    @pytest.fixture
    def temp_env(self):
        """Create a temporary environment."""
        with TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir)
            cec_path = env_path / ".cec"
            cec_path.mkdir()

            pyproject_path = cec_path / "pyproject.toml"
            initial_config = {
                "project": {
                    "name": "test-env",
                    "version": "0.1.0",
                    "requires-python": ">=3.11",
                    "dependencies": [],
                }
            }
            with open(pyproject_path, 'w') as f:
                tomlkit.dump(initial_config, f)

            backend_file = cec_path / ".pytorch-backend"
            backend_file.write_text("cu128")

            yield {
                "cec_path": cec_path,
                "pyproject_path": pyproject_path,
                "backend_file": backend_file,
            }

    def test_injection_with_existing_uv_config(self, temp_env):
        """Should merge with existing tool.uv config, not overwrite."""
        # Add existing uv config
        pyproject = PyprojectManager(temp_env["pyproject_path"])
        config = pyproject.load()
        config["tool"] = config.get("tool", {})
        config["tool"]["uv"] = {
            "index": [
                {"name": "pypi", "url": "https://pypi.org/simple", "explicit": False}
            ]
        }
        pyproject.save(config)

        pytorch_manager = PyTorchBackendManager(temp_env["cec_path"])

        with pyproject.pytorch_injection_context(pytorch_manager):
            injected_config = pyproject.load(force_reload=True)
            indexes = injected_config["tool"]["uv"]["index"]

            # Should have both original and PyTorch indexes
            index_names = [idx.get("name") for idx in indexes]
            assert "pypi" in index_names
            assert "pytorch-cu128" in index_names

    def test_injection_without_backend_file_auto_detects(self, temp_env):
        """Should auto-detect backend when .pytorch-backend file is missing."""
        # Remove backend file
        temp_env["backend_file"].unlink()

        pyproject = PyprojectManager(temp_env["pyproject_path"])
        pytorch_manager = PyTorchBackendManager(temp_env["cec_path"])

        with pyproject.pytorch_injection_context(pytorch_manager):
            content = temp_env["pyproject_path"].read_text()
            # Should have some pytorch config (likely cpu since no CUDA in test env)
            assert "pytorch" in content.lower()
