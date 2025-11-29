"""Unit tests for system nodes infrastructure.

System nodes (like comfygit-manager) are infrastructure nodes that:
- Live at workspace level (.metadata/system_nodes/)
- Are symlinked into each environment's custom_nodes/
- Are never tracked in pyproject.toml
- Are never exported in tarballs
"""
import pytest
from pathlib import Path


class TestSystemCustomNodesConstant:
    """Tests for SYSTEM_CUSTOM_NODES constant."""

    def test_system_custom_nodes_constant_exists(self):
        """SYSTEM_CUSTOM_NODES constant should exist in constants module."""
        from comfygit_core.constants import SYSTEM_CUSTOM_NODES
        assert SYSTEM_CUSTOM_NODES is not None

    def test_comfygit_manager_in_system_nodes(self):
        """comfygit-manager should be in SYSTEM_CUSTOM_NODES."""
        from comfygit_core.constants import SYSTEM_CUSTOM_NODES
        assert 'comfygit-manager' in SYSTEM_CUSTOM_NODES

    def test_system_custom_nodes_is_set(self):
        """SYSTEM_CUSTOM_NODES should be a set for efficient lookup."""
        from comfygit_core.constants import SYSTEM_CUSTOM_NODES
        assert isinstance(SYSTEM_CUSTOM_NODES, set)


class TestWorkspacePathsSystemNodes:
    """Tests for WorkspacePaths.system_nodes property."""

    def test_workspace_paths_has_system_nodes_property(self):
        """WorkspacePaths should have system_nodes property."""
        from comfygit_core.core.workspace import WorkspacePaths
        paths = WorkspacePaths(Path("/tmp/test"))
        # Property should exist and be accessible
        assert hasattr(paths, 'system_nodes')

    def test_system_nodes_path_is_under_metadata(self):
        """system_nodes path should be under .metadata directory."""
        from comfygit_core.core.workspace import WorkspacePaths
        paths = WorkspacePaths(Path("/tmp/test"))
        assert paths.system_nodes == Path("/tmp/test/.metadata/system_nodes")

    def test_ensure_directories_creates_system_nodes(self, tmp_path):
        """ensure_directories should create system_nodes directory."""
        from comfygit_core.core.workspace import WorkspacePaths
        paths = WorkspacePaths(tmp_path)
        paths.ensure_directories()
        assert paths.system_nodes.exists()


class TestNodeManagerRejectsSystemNodes:
    """Tests for NodeManager rejecting system nodes."""

    def test_add_node_rejects_comfygit_manager(self, test_env):
        """add_node should reject comfygit-manager with clear error."""
        with pytest.raises(ValueError, match="system node"):
            test_env.add_node("comfygit-manager")

    def test_add_node_rejects_system_node_as_dev(self, test_env):
        """add_node should reject system nodes even as development nodes."""
        with pytest.raises(ValueError, match="system node"):
            test_env.add_node("comfygit-manager", is_development=True)


class TestStatusScannerSkipsSystemNodes:
    """Tests for status scanner skipping system nodes."""

    def test_status_scanner_skips_comfygit_manager(self, test_env):
        """Status scanner should not report comfygit-manager as untracked."""
        # Create comfygit-manager directory in custom_nodes
        custom_nodes = test_env.comfyui_path / "custom_nodes"
        manager_dir = custom_nodes / "comfygit-manager"
        manager_dir.mkdir(parents=True, exist_ok=True)
        (manager_dir / "__init__.py").write_text("# comfygit-manager")

        # Get status - comfygit-manager should NOT appear in extra_nodes
        status = test_env.status()
        assert "comfygit-manager" not in status.comparison.extra_nodes
        # Also should not appear in dev_nodes_untracked
        assert "comfygit-manager" not in status.comparison.dev_nodes_untracked


class TestExportSkipsSystemNodes:
    """Tests for export skipping system nodes."""

    def test_auto_populate_skips_comfygit_manager(self, test_env):
        """_auto_populate_dev_node_git_info should skip comfygit-manager."""
        import subprocess

        # Create comfygit-manager as a dev node with git info
        custom_nodes = test_env.comfyui_path / "custom_nodes"
        manager_dir = custom_nodes / "comfygit-manager"
        manager_dir.mkdir(parents=True, exist_ok=True)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=manager_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=manager_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=manager_dir, capture_output=True)
        (manager_dir / "__init__.py").write_text("# comfygit-manager")
        subprocess.run(["git", "add", "."], cwd=manager_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=manager_dir, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/comfygit-manager.git"],
            cwd=manager_dir, capture_output=True
        )

        # Add as tracked dev node in pyproject.toml (simulating current broken behavior)
        config = test_env.pyproject.load()
        config.setdefault('tool', {}).setdefault('comfygit', {}).setdefault('nodes', {})['comfygit-manager'] = {
            'name': 'comfygit-manager',
            'source': 'development',
            'version': 'dev'
        }
        test_env.pyproject.save(config)

        # Call _auto_populate_dev_node_git_info
        test_env._auto_populate_dev_node_git_info(callbacks=None)

        # Verify comfygit-manager was NOT updated with git info
        config = test_env.pyproject.load()
        node_data = config['tool']['comfygit']['nodes'].get('comfygit-manager', {})

        # Should NOT have repository/branch captured (that's the bug we're fixing)
        assert 'repository' not in node_data or node_data.get('repository') is None
        assert 'branch' not in node_data or node_data.get('branch') is None


class TestSyncNodesSkipsSystemNodes:
    """Tests for sync_nodes_to_filesystem skipping system nodes."""

    def test_sync_does_not_remove_comfygit_manager(self, test_env):
        """sync_nodes_to_filesystem should not remove comfygit-manager."""
        # Create comfygit-manager directory
        custom_nodes = test_env.comfyui_path / "custom_nodes"
        manager_dir = custom_nodes / "comfygit-manager"
        manager_dir.mkdir(parents=True, exist_ok=True)
        (manager_dir / "__init__.py").write_text("# comfygit-manager")

        # Sync with remove_extra=True (repair mode)
        test_env.node_manager.sync_nodes_to_filesystem(remove_extra=True)

        # comfygit-manager should still exist
        assert manager_dir.exists()

    def test_sync_dev_nodes_skips_comfygit_manager(self, test_env):
        """_sync_dev_nodes_from_git should skip comfygit-manager."""
        # Add comfygit-manager as dev node with repo in pyproject
        config = test_env.pyproject.load()
        config.setdefault('tool', {}).setdefault('comfygit', {}).setdefault('nodes', {})['comfygit-manager'] = {
            'name': 'comfygit-manager',
            'source': 'development',
            'version': 'dev',
            'repository': 'https://github.com/test/comfygit-manager.git',
            'branch': 'feature/local-only'  # This branch doesn't exist on remote
        }
        test_env.pyproject.save(config)

        # Sync should NOT try to clone comfygit-manager (it would fail with bad branch)
        # If it tries to clone, it will raise an error due to missing branch
        test_env.node_manager.sync_nodes_to_filesystem(remove_extra=False)

        # If we get here without error, the sync skipped comfygit-manager
        # (which is the correct behavior - it's a system node)
