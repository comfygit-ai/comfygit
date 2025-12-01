"""Tests for system node installation during workspace init."""
import argparse
from unittest.mock import MagicMock, patch

import pytest


class TestInitSystemNodes:
    """Tests for system node installation in init command."""

    def test_default_system_nodes_constant_exists(self):
        """DEFAULT_SYSTEM_NODES constant should exist and include comfygit-manager."""
        from comfygit_cli.global_commands import DEFAULT_SYSTEM_NODES

        assert DEFAULT_SYSTEM_NODES is not None
        assert "comfygit-manager" in DEFAULT_SYSTEM_NODES
        assert "url" in DEFAULT_SYSTEM_NODES["comfygit-manager"]

    def test_install_system_nodes_clones_comfygit_manager(self, tmp_path):
        """_install_system_nodes should clone comfygit-manager to system_nodes."""
        from comfygit_cli.global_commands import GlobalCommands

        # Create mock workspace
        mock_workspace = MagicMock()
        mock_workspace.paths.system_nodes = tmp_path / "system_nodes"
        mock_workspace.paths.system_nodes.mkdir(parents=True)

        global_cmds = GlobalCommands()

        # Patch at the source module where git_clone is defined
        with patch("comfygit_core.utils.git.git_clone") as mock_clone:
            global_cmds._install_system_nodes(mock_workspace)

            # Verify git_clone was called
            mock_clone.assert_called_once()
            call_args = mock_clone.call_args

            # Check URL
            assert "comfygit-manager" in call_args.kwargs["url"]
            # Check target path
            assert str(call_args.kwargs["target_path"]).endswith("comfygit-manager")
            # Check shallow clone
            assert call_args.kwargs["depth"] == 1

    def test_install_system_nodes_skips_existing(self, tmp_path):
        """_install_system_nodes should skip if node already exists."""
        from comfygit_cli.global_commands import GlobalCommands

        # Create mock workspace with existing comfygit-manager
        mock_workspace = MagicMock()
        mock_workspace.paths.system_nodes = tmp_path / "system_nodes"
        mock_workspace.paths.system_nodes.mkdir(parents=True)
        (mock_workspace.paths.system_nodes / "comfygit-manager").mkdir()

        global_cmds = GlobalCommands()

        # Patch at the source module where git_clone is defined
        with patch("comfygit_core.utils.git.git_clone") as mock_clone:
            global_cmds._install_system_nodes(mock_workspace)

            # git_clone should NOT be called since directory exists
            mock_clone.assert_not_called()

    def test_bare_flag_skips_system_nodes(self, tmp_path, monkeypatch):
        """init with --bare flag should skip system node installation."""
        from comfygit_cli.global_commands import GlobalCommands

        global_cmds = GlobalCommands()

        # Mock workspace factory and creation
        mock_workspace = MagicMock()
        mock_workspace.paths.root = tmp_path
        mock_workspace.paths.system_nodes = tmp_path / "system_nodes"
        mock_workspace.path = tmp_path
        mock_workspace.update_registry_data.return_value = True
        mock_workspace.get_models_directory.return_value = tmp_path / "models"

        with patch("comfygit_cli.global_commands.WorkspaceFactory") as mock_factory:
            mock_factory.get_paths.return_value = mock_workspace.paths
            mock_factory.create.return_value = mock_workspace

            with patch.object(global_cmds, "_install_system_nodes") as mock_install:
                with patch.object(global_cmds, "_setup_models_directory"):
                    args = argparse.Namespace(
                        path=None,
                        models_dir=None,
                        yes=True,
                        bare=True
                    )

                    global_cmds.init(args)

                    # _install_system_nodes should NOT be called
                    mock_install.assert_not_called()

    def test_init_calls_install_system_nodes_by_default(self, tmp_path, monkeypatch):
        """init without --bare should call _install_system_nodes."""
        from comfygit_cli.global_commands import GlobalCommands

        global_cmds = GlobalCommands()

        # Mock workspace factory and creation
        mock_workspace = MagicMock()
        mock_workspace.paths.root = tmp_path
        mock_workspace.paths.system_nodes = tmp_path / "system_nodes"
        mock_workspace.path = tmp_path
        mock_workspace.update_registry_data.return_value = True
        mock_workspace.get_models_directory.return_value = tmp_path / "models"

        with patch("comfygit_cli.global_commands.WorkspaceFactory") as mock_factory:
            mock_factory.get_paths.return_value = mock_workspace.paths
            mock_factory.create.return_value = mock_workspace

            with patch.object(global_cmds, "_install_system_nodes") as mock_install:
                with patch.object(global_cmds, "_setup_models_directory"):
                    args = argparse.Namespace(
                        path=None,
                        models_dir=None,
                        yes=True,
                        bare=False
                    )

                    global_cmds.init(args)

                    # _install_system_nodes SHOULD be called
                    mock_install.assert_called_once_with(mock_workspace)
