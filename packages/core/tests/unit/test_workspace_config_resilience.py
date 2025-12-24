"""Tests for workspace config and environment resilience.

Issue 1: WorkspaceConfigRepository.load() silently recreates config on parse errors
Issue 2: Environment.__init__ hard-fails when models directory is null
"""
import json

import pytest
from comfygit_core.models.exceptions import ComfyDockError
from comfygit_core.repositories.workspace_config_repository import WorkspaceConfigRepository


class TestWorkspaceConfigLoadBehavior:
    """Test that config loading fails loudly instead of silently recreating."""

    def test_load_raises_on_invalid_json(self, tmp_path):
        """Should raise error on malformed JSON, not silently recreate config."""
        config_file = tmp_path / "workspace.json"
        config_file.write_text("{ invalid json }")

        repo = WorkspaceConfigRepository(config_file)

        # Current behavior: silently recreates config (BAD)
        # Expected behavior: raise ComfyDockError
        with pytest.raises(ComfyDockError, match="Failed to load workspace config"):
            _ = repo.config_file

    def test_load_raises_on_missing_required_fields(self, tmp_path):
        """Should raise error when required fields are missing."""
        config_file = tmp_path / "workspace.json"
        # Missing 'version' and other required fields
        config_file.write_text('{"active_environment": ""}')

        repo = WorkspaceConfigRepository(config_file)

        with pytest.raises(ComfyDockError, match="Failed to load workspace config"):
            _ = repo.config_file

    def test_load_does_not_overwrite_existing_on_error(self, tmp_path):
        """Should preserve existing config file even when it can't be parsed."""
        config_file = tmp_path / "workspace.json"
        original_content = "{ invalid but preserved }"
        config_file.write_text(original_content)

        repo = WorkspaceConfigRepository(config_file)

        with pytest.raises(ComfyDockError):
            _ = repo.config_file

        # File should still contain original content, not be overwritten
        assert config_file.read_text() == original_content

    def test_load_works_with_valid_config(self, tmp_path):
        """Sanity check: valid config should load successfully."""
        config_file = tmp_path / "workspace.json"
        valid_config = {
            "version": 1,
            "active_environment": "",
            "created_at": "2025-01-01T00:00:00",
            "global_model_directory": None,
            "api_credentials": None
        }
        config_file.write_text(json.dumps(valid_config))

        repo = WorkspaceConfigRepository(config_file)
        config = repo.config_file

        assert config.version == 1
        assert config.global_model_directory is None


class TestEnvironmentModelPathResilience:
    """Test that Environment handles missing models directory gracefully."""

    def test_environment_loads_when_models_directory_null(self, tmp_path):
        """Environment should load even when global_model_directory is null."""
        from comfygit_core.core.environment import Environment
        from comfygit_core.core.workspace import Workspace, WorkspacePaths

        # Create workspace with null models directory
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        metadata_path = workspace_path / ".metadata"
        metadata_path.mkdir()

        # Config with null global_model_directory
        config = {
            "version": 1,
            "active_environment": "",
            "created_at": "2025-01-01T00:00:00",
            "global_model_directory": None
        }
        (metadata_path / "workspace.json").write_text(json.dumps(config))

        # Create workspace directories
        (workspace_path / "environments").mkdir()
        (workspace_path / "comfygit_cache").mkdir()
        (workspace_path / "logs").mkdir()
        (workspace_path / "models").mkdir()  # Default models dir exists
        (workspace_path / "input").mkdir()
        (workspace_path / "output").mkdir()

        workspace = Workspace(WorkspacePaths(workspace_path))

        # Create minimal environment structure
        env_path = workspace_path / "environments" / "test-env"
        env_path.mkdir(parents=True)
        cec_path = env_path / ".cec"
        cec_path.mkdir()
        comfyui_path = env_path / "ComfyUI"
        comfyui_path.mkdir()

        # This should NOT raise - should use default workspace/models path
        env = Environment(
            name="test-env",
            path=env_path,
            workspace=workspace
        )

        # Should have fallen back to workspace default models path
        assert env.global_models_path == workspace.paths.models

    def test_list_environments_returns_envs_when_models_null(self, tmp_path):
        """Workspace.list_environments() should return environments even when models dir null."""
        from comfygit_core.core.workspace import Workspace, WorkspacePaths
        from comfygit_core.utils.environment_cleanup import mark_environment_complete

        # Create workspace with null models directory
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        metadata_path = workspace_path / ".metadata"
        metadata_path.mkdir()

        config = {
            "version": 1,
            "active_environment": "",
            "created_at": "2025-01-01T00:00:00",
            "global_model_directory": None
        }
        (metadata_path / "workspace.json").write_text(json.dumps(config))

        # Create workspace directories
        (workspace_path / "environments").mkdir()
        (workspace_path / "comfygit_cache").mkdir()
        (workspace_path / "logs").mkdir()
        (workspace_path / "models").mkdir()
        (workspace_path / "input").mkdir()
        (workspace_path / "output").mkdir()

        workspace = Workspace(WorkspacePaths(workspace_path))

        # Create an environment
        env_path = workspace_path / "environments" / "my-env"
        env_path.mkdir(parents=True)
        cec_path = env_path / ".cec"
        cec_path.mkdir()
        (env_path / "ComfyUI").mkdir()
        mark_environment_complete(cec_path)

        # Current behavior: returns empty list because Environment.__init__ throws
        # Expected behavior: returns the environment
        envs = workspace.list_environments()
        assert len(envs) == 1
        assert envs[0].name == "my-env"

    def test_get_models_directory_returns_default_when_null(self, tmp_path):
        """get_models_directory should return workspace default when config is null."""
        from comfygit_core.core.workspace import Workspace, WorkspacePaths

        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()
        metadata_path = workspace_path / ".metadata"
        metadata_path.mkdir()

        config = {
            "version": 1,
            "active_environment": "",
            "created_at": "2025-01-01T00:00:00",
            "global_model_directory": None
        }
        (metadata_path / "workspace.json").write_text(json.dumps(config))

        # Create all workspace directories
        (workspace_path / "environments").mkdir()
        (workspace_path / "comfygit_cache").mkdir()
        (workspace_path / "logs").mkdir()
        (workspace_path / "models").mkdir()
        (workspace_path / "input").mkdir()
        (workspace_path / "output").mkdir()

        workspace = Workspace(WorkspacePaths(workspace_path))

        # Current behavior: raises ComfyDockError
        # Expected behavior: returns workspace.paths.models
        models_dir = workspace.workspace_config_manager.get_models_directory()
        assert models_dir == workspace.paths.models
