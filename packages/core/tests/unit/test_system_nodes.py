"""Unit tests for system nodes infrastructure.

System nodes (like comfygit-manager) are infrastructure nodes that:
- Live at workspace level (.metadata/system_nodes/)
- Are symlinked into each environment's custom_nodes/
- Are never tracked in pyproject.toml
- Are never exported in tarballs
"""
from pathlib import Path

import pytest


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


class TestSystemNodeSymlinkManager:
    """Tests for SystemNodeSymlinkManager creating symlinks on environment creation."""

    def test_system_node_manager_exists_on_environment(self, test_env):
        """Environment should have system_node_manager property."""
        assert hasattr(test_env, 'system_node_manager')
        # Should return a SystemNodeSymlinkManager instance
        from comfygit_core.managers.system_node_symlink_manager import SystemNodeSymlinkManager
        assert isinstance(test_env.system_node_manager, SystemNodeSymlinkManager)

    def test_create_symlinks_creates_links_for_system_nodes(self, test_workspace):
        """create_symlinks should create symlinks for all nodes in system_nodes directory."""
        from comfygit_core.managers.system_node_symlink_manager import SystemNodeSymlinkManager
        from comfygit_core.utils.symlink_utils import is_link

        # Create a system node in workspace system_nodes directory
        system_nodes_dir = test_workspace.paths.system_nodes
        system_nodes_dir.mkdir(parents=True, exist_ok=True)
        manager_node = system_nodes_dir / "comfygit-manager"
        manager_node.mkdir()
        (manager_node / "__init__.py").write_text("# comfygit-manager")

        # Create test comfyui path
        comfyui_path = test_workspace.paths.environments / "test-env" / "ComfyUI"
        comfyui_path.mkdir(parents=True)
        custom_nodes = comfyui_path / "custom_nodes"
        custom_nodes.mkdir()

        # Create manager and call create_symlinks
        symlink_manager = SystemNodeSymlinkManager(comfyui_path, system_nodes_dir)
        linked = symlink_manager.create_symlinks()

        # Should have linked comfygit-manager
        assert "comfygit-manager" in linked
        link_path = custom_nodes / "comfygit-manager"
        assert link_path.exists()
        assert is_link(link_path)
        assert link_path.resolve() == manager_node.resolve()

    def test_create_symlinks_handles_empty_system_nodes_dir(self, test_workspace):
        """create_symlinks should handle empty system_nodes directory gracefully."""
        from comfygit_core.managers.system_node_symlink_manager import SystemNodeSymlinkManager

        # Create empty system nodes directory
        system_nodes_dir = test_workspace.paths.system_nodes
        system_nodes_dir.mkdir(parents=True, exist_ok=True)

        # Create test comfyui path
        comfyui_path = test_workspace.paths.environments / "test-env" / "ComfyUI"
        comfyui_path.mkdir(parents=True)

        # Should return empty list without error
        symlink_manager = SystemNodeSymlinkManager(comfyui_path, system_nodes_dir)
        linked = symlink_manager.create_symlinks()
        assert linked == []

    def test_create_symlinks_skips_existing_real_directory(self, test_workspace):
        """create_symlinks should not overwrite real directories."""
        from comfygit_core.managers.system_node_symlink_manager import SystemNodeSymlinkManager

        # Create system node
        system_nodes_dir = test_workspace.paths.system_nodes
        system_nodes_dir.mkdir(parents=True, exist_ok=True)
        manager_node = system_nodes_dir / "comfygit-manager"
        manager_node.mkdir()
        (manager_node / "__init__.py").write_text("# source")

        # Create real directory in custom_nodes (not a symlink)
        comfyui_path = test_workspace.paths.environments / "test-env" / "ComfyUI"
        comfyui_path.mkdir(parents=True)
        custom_nodes = comfyui_path / "custom_nodes"
        custom_nodes.mkdir()
        existing_dir = custom_nodes / "comfygit-manager"
        existing_dir.mkdir()
        (existing_dir / "__init__.py").write_text("# existing user content")

        # Should NOT overwrite the existing directory
        symlink_manager = SystemNodeSymlinkManager(comfyui_path, system_nodes_dir)
        linked = symlink_manager.create_symlinks()

        # Should not have linked (real directory exists)
        assert "comfygit-manager" not in linked
        # Original content should be preserved
        assert (existing_dir / "__init__.py").read_text() == "# existing user content"

    def test_validate_symlinks_returns_status(self, test_workspace):
        """validate_symlinks should return dict of node validity."""
        from comfygit_core.managers.system_node_symlink_manager import SystemNodeSymlinkManager

        # Create system node
        system_nodes_dir = test_workspace.paths.system_nodes
        system_nodes_dir.mkdir(parents=True, exist_ok=True)
        manager_node = system_nodes_dir / "comfygit-manager"
        manager_node.mkdir()

        # Create comfyui structure without symlinks
        comfyui_path = test_workspace.paths.environments / "test-env" / "ComfyUI"
        comfyui_path.mkdir(parents=True)
        custom_nodes = comfyui_path / "custom_nodes"
        custom_nodes.mkdir()

        symlink_manager = SystemNodeSymlinkManager(comfyui_path, system_nodes_dir)

        # Before creating symlinks - should show invalid
        status = symlink_manager.validate_symlinks()
        assert status.get("comfygit-manager") is False

        # After creating symlinks - should show valid
        symlink_manager.create_symlinks()
        status = symlink_manager.validate_symlinks()
        assert status.get("comfygit-manager") is True


class TestSystemNodeRequirements:
    """Tests for SystemNodeSymlinkManager.get_all_requirements()."""

    def test_get_all_requirements_parses_pyproject_toml(self, test_workspace):
        """get_all_requirements should parse dependencies from pyproject.toml."""
        from comfygit_core.managers.system_node_symlink_manager import SystemNodeSymlinkManager

        # Create system node with pyproject.toml
        system_nodes_dir = test_workspace.paths.system_nodes
        system_nodes_dir.mkdir(parents=True, exist_ok=True)
        manager_node = system_nodes_dir / "comfygit-manager"
        manager_node.mkdir()
        (manager_node / "__init__.py").write_text("# comfygit-manager")

        # Create pyproject.toml with dependencies
        pyproject_content = """
[project]
name = "comfygit-manager"
version = "0.1.0"
dependencies = [
    "comfygit-core",
    "watchdog>=6.0.0",
]
"""
        (manager_node / "pyproject.toml").write_text(pyproject_content)

        # Create test comfyui path
        comfyui_path = test_workspace.paths.environments / "test-env" / "ComfyUI"
        comfyui_path.mkdir(parents=True)

        symlink_manager = SystemNodeSymlinkManager(comfyui_path, system_nodes_dir)
        requirements = symlink_manager.get_all_requirements()

        assert "comfygit-core" in requirements
        assert "watchdog>=6.0.0" in requirements

    def test_get_all_requirements_parses_requirements_txt_fallback(self, test_workspace):
        """get_all_requirements should fall back to requirements.txt if no pyproject.toml."""
        from comfygit_core.managers.system_node_symlink_manager import SystemNodeSymlinkManager

        # Create system node with requirements.txt only
        system_nodes_dir = test_workspace.paths.system_nodes
        system_nodes_dir.mkdir(parents=True, exist_ok=True)
        node_dir = system_nodes_dir / "test-node"
        node_dir.mkdir()
        (node_dir / "__init__.py").write_text("# test-node")

        # Create requirements.txt
        (node_dir / "requirements.txt").write_text("requests>=2.0.0\naiohttp")

        comfyui_path = test_workspace.paths.environments / "test-env" / "ComfyUI"
        comfyui_path.mkdir(parents=True)

        symlink_manager = SystemNodeSymlinkManager(comfyui_path, system_nodes_dir)
        requirements = symlink_manager.get_all_requirements()

        assert "requests>=2.0.0" in requirements
        assert "aiohttp" in requirements

    def test_get_all_requirements_handles_empty_system_nodes(self, test_workspace):
        """get_all_requirements should return empty list for empty system_nodes dir."""
        from comfygit_core.managers.system_node_symlink_manager import SystemNodeSymlinkManager

        # Create empty system nodes directory
        system_nodes_dir = test_workspace.paths.system_nodes
        system_nodes_dir.mkdir(parents=True, exist_ok=True)

        comfyui_path = test_workspace.paths.environments / "test-env" / "ComfyUI"
        comfyui_path.mkdir(parents=True)

        symlink_manager = SystemNodeSymlinkManager(comfyui_path, system_nodes_dir)
        requirements = symlink_manager.get_all_requirements()

        assert requirements == []

    def test_get_all_requirements_deduplicates(self, test_workspace):
        """get_all_requirements should deduplicate requirements across nodes."""
        from comfygit_core.managers.system_node_symlink_manager import SystemNodeSymlinkManager

        system_nodes_dir = test_workspace.paths.system_nodes
        system_nodes_dir.mkdir(parents=True, exist_ok=True)

        # Create two nodes with overlapping requirements
        for node_name in ["node-a", "node-b"]:
            node_dir = system_nodes_dir / node_name
            node_dir.mkdir()
            (node_dir / "__init__.py").write_text(f"# {node_name}")
            (node_dir / "requirements.txt").write_text("requests>=2.0.0\ncommon-dep")

        comfyui_path = test_workspace.paths.environments / "test-env" / "ComfyUI"
        comfyui_path.mkdir(parents=True)

        symlink_manager = SystemNodeSymlinkManager(comfyui_path, system_nodes_dir)
        requirements = symlink_manager.get_all_requirements()

        # Should not have duplicates
        assert requirements.count("requests>=2.0.0") == 1
        assert requirements.count("common-dep") == 1


class TestEnvironmentFactorySystemNodeDeps:
    """Tests for EnvironmentFactory including system node deps in pyproject.toml."""

    def test_create_environment_includes_system_node_deps_in_dependency_group(
        self, test_workspace, mock_comfyui_clone, mock_github_api
    ):
        """Created environment should have system-nodes dependency group."""
        # Create system node with dependencies
        system_nodes_dir = test_workspace.paths.system_nodes
        system_nodes_dir.mkdir(parents=True, exist_ok=True)
        manager_node = system_nodes_dir / "comfygit-manager"
        manager_node.mkdir()
        (manager_node / "__init__.py").write_text("# comfygit-manager")
        pyproject_content = """
[project]
name = "comfygit-manager"
version = "0.1.0"
dependencies = [
    "comfygit-core",
    "watchdog>=6.0.0",
]
"""
        (manager_node / "pyproject.toml").write_text(pyproject_content)

        # Create environment
        from comfygit_core.factories.environment_factory import EnvironmentFactory

        env = EnvironmentFactory.create(
            name="test-env",
            env_path=test_workspace.paths.environments / "test-env",
            workspace=test_workspace,
            python_version="3.12",
            comfyui_version="v0.3.20",
        )

        # Check pyproject.toml has system-nodes dependency group
        config = env.pyproject.load()
        assert "dependency-groups" in config
        assert "system-nodes" in config["dependency-groups"]
        system_deps = config["dependency-groups"]["system-nodes"]
        assert "comfygit-core" in system_deps
        assert "watchdog>=6.0.0" in system_deps

    def test_create_environment_includes_schema_version(
        self, test_workspace, mock_comfyui_clone, mock_github_api
    ):
        """Created environment should have schema_version in tool.comfygit."""
        from comfygit_core.constants import PYPROJECT_SCHEMA_VERSION
        from comfygit_core.factories.environment_factory import EnvironmentFactory

        env = EnvironmentFactory.create(
            name="test-env",
            env_path=test_workspace.paths.environments / "test-env",
            workspace=test_workspace,
            python_version="3.12",
            comfyui_version="v0.3.20",
        )

        config = env.pyproject.load()
        assert config["tool"]["comfygit"]["schema_version"] == PYPROJECT_SCHEMA_VERSION


class TestFinalizeImportSystemNodeDeps:
    """Tests for finalize_import reconciling system node deps."""

    def test_finalize_import_updates_system_nodes_dependency_group(
        self, test_workspace, mock_comfyui_clone, mock_github_api
    ):
        """finalize_import should update system-nodes group from local workspace."""

        # Create system node with dependencies in workspace
        system_nodes_dir = test_workspace.paths.system_nodes
        system_nodes_dir.mkdir(parents=True, exist_ok=True)
        manager_node = system_nodes_dir / "comfygit-manager"
        manager_node.mkdir()
        (manager_node / "__init__.py").write_text("# comfygit-manager")
        pyproject_content = """
[project]
name = "comfygit-manager"
version = "0.2.0"
dependencies = [
    "comfygit-core>=0.2.0",
    "watchdog>=7.0.0",
    "new-local-dep",
]
"""
        (manager_node / "pyproject.toml").write_text(pyproject_content)

        # Create environment structure (simulating import_from_bundle)
        env_path = test_workspace.paths.environments / "imported-env"
        env_path.mkdir(parents=True)
        cec_path = env_path / ".cec"
        cec_path.mkdir()

        # Create pyproject.toml as if it was imported (with old system-nodes deps)
        import tomlkit
        imported_config = {
            "project": {
                "name": "comfygit-env-imported-env",
                "version": "0.1.0",
                "requires-python": ">=3.12",
                "dependencies": []
            },
            "tool": {
                "comfygit": {
                    "schema_version": 1,
                    "comfyui_version": "v0.3.20",
                    "comfyui_version_type": "release",
                    "python_version": "3.12",
                    "torch_backend": "auto",
                    "nodes": {}
                }
            },
            "dependency-groups": {
                "system-nodes": [
                    "comfygit-core>=0.1.0",  # Old version from export source
                    "watchdog>=6.0.0",        # Old version
                ]
            }
        }
        with open(cec_path / "pyproject.toml", "w") as f:
            tomlkit.dump(imported_config, f)

        # Create .python-version file
        (cec_path / ".python-version").write_text("3.12")

        # Create environment instance and finalize import
        from comfygit_core.core.environment import Environment
        env = Environment(
            name="imported-env",
            path=env_path,
            workspace=test_workspace,
            torch_backend="auto",
        )
        env.finalize_import()

        # Check that system-nodes dep group was updated from LOCAL workspace
        config = env.pyproject.load()
        assert "dependency-groups" in config
        assert "system-nodes" in config["dependency-groups"]
        system_deps = config["dependency-groups"]["system-nodes"]

        # Should have the NEW local workspace deps, not the imported ones
        assert "comfygit-core>=0.2.0" in system_deps
        assert "watchdog>=7.0.0" in system_deps
        assert "new-local-dep" in system_deps
        # Old versions should NOT be present
        assert "comfygit-core>=0.1.0" not in system_deps
        assert "watchdog>=6.0.0" not in system_deps
