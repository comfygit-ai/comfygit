"""Integration tests for export/import functionality."""
import tempfile
from pathlib import Path

import pytest

from comfydock_core.managers.export_import_manager import ExportImportManager, ExportManifest


class TestExportImportBasic:
    """Test basic export/import operations."""

    def test_export_creates_tarball(self, tmp_path):
        """Test that export creates a valid tarball."""
        # Setup test environment structure
        cec_path = tmp_path / "test_env" / ".cec"
        cec_path.mkdir(parents=True)
        comfyui_path = tmp_path / "test_env" / "ComfyUI"
        comfyui_path.mkdir(parents=True)

        # Create minimal pyproject.toml
        pyproject_path = cec_path / "pyproject.toml"
        pyproject_path.write_text("""
[project]
name = "test-env"
version = "0.1.0"

[tool.comfydock]
        """)

        # Create workflows directory
        workflows_path = cec_path / "workflows"
        workflows_path.mkdir()
        (workflows_path / "test.json").write_text('{"nodes": []}')

        # Create manifest
        manifest = ExportManifest(
            timestamp="2025-01-15T10:00:00Z",
            comfydock_version="0.5.0",
            environment_name="test_env",
            workflows=["test.json"],
            python_version="3.12",
            comfyui_version=None,
            platform="linux",
            total_models=0,
            total_nodes=0,
            dev_nodes=[]
        )

        # Export
        output_path = tmp_path / "export.tar.gz"
        manager = ExportImportManager(cec_path, comfyui_path)

        from comfydock_core.managers.pyproject_manager import PyprojectManager
        pyproject_manager = PyprojectManager(pyproject_path)

        result = manager.create_export(output_path, manifest, pyproject_manager)

        # Verify
        assert result.exists()
        assert result.stat().st_size > 0

    def test_import_extracts_tarball(self, tmp_path):
        """Test that import extracts tarball correctly."""
        # First create an export
        source_cec = tmp_path / "source" / ".cec"
        source_cec.mkdir(parents=True)
        source_comfyui = tmp_path / "source" / "ComfyUI"
        source_comfyui.mkdir(parents=True)

        # Create minimal content
        (source_cec / "pyproject.toml").write_text('[project]\nname = "test"')
        workflows = source_cec / "workflows"
        workflows.mkdir()
        (workflows / "test.json").write_text('{}')

        # Create manifest
        manifest = ExportManifest(
            timestamp="2025-01-15T10:00:00Z",
            comfydock_version="0.5.0",
            environment_name="test",
            workflows=["test.json"],
            python_version="3.12",
            comfyui_version=None,
            platform="linux",
            total_models=0,
            total_nodes=0
        )

        # Export
        tarball_path = tmp_path / "test.tar.gz"
        manager = ExportImportManager(source_cec, source_comfyui)

        from comfydock_core.managers.pyproject_manager import PyprojectManager
        pyproject_manager = PyprojectManager(source_cec / "pyproject.toml")

        manager.create_export(tarball_path, manifest, pyproject_manager)

        # Now import
        target_cec = tmp_path / "target" / ".cec"
        manager2 = ExportImportManager(target_cec, tmp_path / "target" / "ComfyUI")
        extracted_manifest = manager2.extract_import(tarball_path, target_cec)

        # Verify
        assert target_cec.exists()
        assert (target_cec / "pyproject.toml").exists()
        assert (target_cec / "workflows" / "test.json").exists()
        assert extracted_manifest.environment_name == "test"
        assert extracted_manifest.workflows == ["test.json"]


class TestPrepareImportModels:
    """Test model download intent preparation for import."""

    def test_prepare_import_converts_missing_models(self, tmp_path, test_workspace):
        """Test that prepare_import converts missing models to download intents."""
        # This would require a full environment setup
        # For MVP, we'll keep this as a placeholder for future enhancement
        pytest.skip("Requires full environment setup - future enhancement")
