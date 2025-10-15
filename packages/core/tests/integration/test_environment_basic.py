"""Final working integration tests with subprocess-level mocking."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from comfydock_core.factories.workspace_factory import WorkspaceFactory
from comfydock_core.models.exceptions import CDEnvironmentNotFoundError


def test_workspace_operations(tmp_path):
    """Test basic workspace operations - this works."""
    workspace_path = tmp_path / "test_workspace"

    # Initialize workspace
    workspace = WorkspaceFactory.create(workspace_path)

    # Verify workspace structure created
    assert workspace.path.exists()
    assert (workspace.path / ".metadata").exists()
    assert (workspace.path / "environments").exists()
    assert (workspace.path / "comfydock_cache").exists()

    # List environments (should be empty)
    environments = workspace.list_environments()
    assert len(environments) == 0


def test_environment_lifecycle_with_subprocess_mock(tmp_path):
    """Test environment lifecycle by mocking subprocess.run directly."""
    import json

    # Create workspace
    workspace_path = tmp_path / "test_workspace"
    workspace = WorkspaceFactory.create(workspace_path)

    # Create empty node mappings file to avoid network fetch
    custom_nodes_cache = workspace.paths.cache / "custom_nodes"
    custom_nodes_cache.mkdir(parents=True, exist_ok=True)
    node_mappings = custom_nodes_cache / "node_mappings.json"
    with open(node_mappings, 'w') as f:
        json.dump({"mappings": {}, "packages": {}, "stats": {}}, f)

    # Set models directory (required for environment creation)
    models_dir = workspace_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    workspace.set_models_directory(models_dir)

    # Mock subprocess.run to prevent any real external calls
    with patch('subprocess.run') as mock_subprocess_run:

        # Setup mock to return success for all commands
        def subprocess_side_effect(cmd, *args, **kwargs):
            # Create a successful result
            result = subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="Success",
                stderr=""
            )

            # Handle specific commands
            if isinstance(cmd, list):
                if cmd[0] == "git":
                    if "clone" in cmd:
                        # Extract target path from git clone command
                        if "--" in cmd:
                            target_idx = cmd.index("--") + 1
                            if target_idx < len(cmd):
                                target_path = Path(cmd[target_idx])
                                target_path.mkdir(parents=True, exist_ok=True)
                                # Create ComfyUI marker files
                                (target_path / "main.py").touch()
                                (target_path / "nodes.py").touch()
                                (target_path / "folder_paths.py").touch()
                                (target_path / "comfy").mkdir(exist_ok=True)
                                (target_path / "models").mkdir(exist_ok=True)
                                (target_path / "custom_nodes").mkdir(exist_ok=True)
                    elif "describe" in cmd:
                        result.stdout = "v1.0.0"
                    elif "init" in cmd:
                        # Git init - create .git directory
                        cwd = kwargs.get('cwd', Path.cwd())
                        if isinstance(cwd, str):
                            cwd = Path(cwd)
                        (cwd / ".git").mkdir(exist_ok=True)
                elif cmd[0] == "uv":
                    # UV commands - just return success
                    if "version" in cmd:
                        result.stdout = "0.4.0"
                    elif "init" in cmd:
                        # Create pyproject.toml
                        cwd = kwargs.get('cwd', Path.cwd())
                        if isinstance(cwd, str):
                            cwd = Path(cwd)
                        (cwd / "pyproject.toml").touch()
                    elif "sync" in cmd:
                        # Create .venv marker
                        cwd = kwargs.get('cwd', Path.cwd())
                        if isinstance(cwd, str):
                            cwd = Path(cwd)
                        venv_path = cwd.parent / ".venv"
                        venv_path.mkdir(exist_ok=True)
                        (venv_path / "bin").mkdir(exist_ok=True)
                        (venv_path / "bin" / "python").touch()

            return result

        mock_subprocess_run.side_effect = subprocess_side_effect

        # Create environment
        env = workspace.create_environment(
            name="test-env",
            python_version="3.11",
            comfyui_version="master"
        )

        # Verify environment created
        assert env.name == "test-env"
        assert env.path.exists()

        # List environments
        environments = workspace.list_environments()
        assert len(environments) == 1
        assert environments[0].name == "test-env"

        # Set as active
        workspace.set_active_environment("test-env")
        active = workspace.get_active_environment()
        assert active.name == "test-env"

        # Delete environment
        workspace.delete_environment("test-env")

        # Verify deleted
        assert not env.path.exists()
        environments = workspace.list_environments()
        assert len(environments) == 0


def test_environment_errors(tmp_path):
    """Test error handling without environment creation."""

    workspace_path = tmp_path / "test_workspace"
    workspace = WorkspaceFactory.create(workspace_path)

    # Test that we can't delete non-existent environment
    with pytest.raises(CDEnvironmentNotFoundError):
        workspace.delete_environment("non-existent")

    # Test that we can't set non-existent environment as active
    with pytest.raises(CDEnvironmentNotFoundError):
        workspace.set_active_environment("non-existent")

    # Test getting non-existent environment raises error
    with pytest.raises(CDEnvironmentNotFoundError):
        workspace.get_environment("non-existent")
