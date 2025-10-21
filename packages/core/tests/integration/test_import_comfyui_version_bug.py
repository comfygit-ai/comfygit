"""Integration test for ComfyUI version reproducibility on import.

BUG: export_import_manager.py:228 always passes None to clone_comfyui(),
     ignoring the comfyui_version from manifest and pyproject.toml.

This test verifies that when importing an environment, the EXACT ComfyUI
version specified in the export is cloned, not the latest HEAD.
"""

import json
import shutil
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comfydock_core.factories.environment_factory import EnvironmentFactory


class TestImportComfyUIVersionBug:
    """Test that import reproduces exact ComfyUI version."""

    def test_import_uses_comfyui_version_from_manifest(self, test_workspace):
        """BUG: SHOULD clone specific comfyui_version from manifest, not HEAD."""
        # ARRANGE - Create a fake export with v0.3.15 in manifest
        export_tarball = test_workspace.paths.root / "test_export.tar.gz"

        # Create export structure
        export_content = test_workspace.paths.root / "export_content"
        export_content.mkdir()

        # Create manifest with specific version
        manifest = {
            "timestamp": "2025-01-15T12:00:00",
            "comfydock_version": "1.0.0",
            "environment_name": "test-env",
            "workflows": [],
            "python_version": "3.12",
            "comfyui_version": "v0.3.15",  # ← Specific version!
            "platform": "linux",
            "total_models": 0,
            "total_nodes": 0
        }

        manifest_json = json.dumps(manifest, indent=2)
        (export_content / "manifest.json").write_text(manifest_json)

        # Create pyproject.toml with version metadata
        pyproject_content = """
[project]
name = "comfydock-env-test"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[tool.comfydock]
comfyui_version = "v0.3.15"
python_version = "3.12"
nodes = {}
"""
        (export_content / "pyproject.toml").write_text(pyproject_content)

        # Create tarball
        with tarfile.open(export_tarball, "w:gz") as tar:
            for item in export_content.iterdir():
                tar.add(item, arcname=item.name)

        # Mock clone_comfyui to track what version is requested
        cloned_version = None

        def mock_clone_comfyui(target_path, version):
            nonlocal cloned_version
            cloned_version = version
            # Create minimal ComfyUI structure
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "main.py").write_text("# ComfyUI")
            (target_path / "nodes.py").write_text("# nodes")
            (target_path / "folder_paths.py").write_text("# paths")
            (target_path / "comfy").mkdir()
            (target_path / "models").mkdir()
            # Return version
            return version

        # ACT - Import the environment
        with patch('comfydock_core.utils.comfyui_ops.clone_comfyui', side_effect=mock_clone_comfyui), \
             patch('comfydock_core.utils.git.git_rev_parse', return_value="abc123def456"):
            env = test_workspace.import_environment(
                tarball_path=export_tarball,
                name="imported-env"
            )

        # ASSERT - Should have cloned v0.3.15, not None
        assert cloned_version is not None, \
            "BUG CONFIRMED: clone_comfyui called with None instead of v0.3.15"
        assert cloned_version == "v0.3.15", \
            f"Expected version 'v0.3.15' but got '{cloned_version}'"

    def test_import_uses_version_not_commit_sha(self, test_workspace):
        """SHOULD use comfyui_version (tag/branch), NOT commit_sha (can't shallow clone)."""
        # ARRANGE
        export_tarball = test_workspace.paths.root / "test_export.tar.gz"
        export_content = test_workspace.paths.root / "export_content"
        export_content.mkdir()

        # Create manifest
        manifest = {
            "timestamp": "2025-01-15T12:00:00",
            "comfydock_version": "1.0.0",
            "environment_name": "test-env",
            "workflows": [],
            "python_version": "3.12",
            "comfyui_version": "v0.3.15",
            "platform": "linux",
            "total_models": 0,
            "total_nodes": 0
        }
        (export_content / "manifest.json").write_text(json.dumps(manifest))

        # Create pyproject with both version and commit_sha
        pyproject_content = """
[project]
name = "comfydock-env-test"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[tool.comfydock]
comfyui_version = "v0.3.15"
comfyui_commit_sha = "abc123def456"
python_version = "3.12"
nodes = {}
"""
        (export_content / "pyproject.toml").write_text(pyproject_content)

        # Create tarball
        with tarfile.open(export_tarball, "w:gz") as tar:
            for item in export_content.iterdir():
                tar.add(item, arcname=item.name)

        # Mock clone
        cloned_version = None

        def mock_clone_comfyui(target_path, version):
            nonlocal cloned_version
            cloned_version = version
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "main.py").write_text("# ComfyUI")
            (target_path / "nodes.py").write_text("# nodes")
            (target_path / "folder_paths.py").write_text("# paths")
            (target_path / "comfy").mkdir()
            (target_path / "models").mkdir()
            return version

        # ACT
        with patch('comfydock_core.utils.comfyui_ops.clone_comfyui', side_effect=mock_clone_comfyui), \
             patch('comfydock_core.utils.git.git_rev_parse', return_value="abc123def456"):
            env = test_workspace.import_environment(
                tarball_path=export_tarball,
                name="imported-env2"
            )

        # ASSERT - Should use version tag (can shallow clone), not commit SHA (can't shallow clone)
        assert cloned_version == "v0.3.15", \
            f"Expected version tag 'v0.3.15' but got '{cloned_version}'. Commit SHA can't be shallow cloned!"
