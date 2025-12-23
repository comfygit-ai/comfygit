"""Integration tests for per-environment manager architecture.

These tests verify the migration from workspace-level symlinked system nodes
to per-environment tracked manager nodes. The goal is to ensure version
coherence during git rollback operations.

Implementation Plan Reference:
.claude/context/shared/plans/2025-12-22-implementation-plan-per-environment-mana.md
"""

import json
from pathlib import Path

import pytest

from comfygit_core.core.environment import Environment
from comfygit_core.factories.workspace_factory import WorkspaceFactory
from comfygit_core.models.shared import ManagerStatus
from comfygit_core.utils.symlink_utils import is_link


class TestManagerStatus:
    """Tests for Environment.get_manager_status()."""

    def test_get_manager_status_not_installed(self, test_env):
        """When manager is not installed, status should reflect that."""
        # ARRANGE - test_env has no manager installed

        # ACT
        status = test_env.get_manager_status()

        # ASSERT
        assert isinstance(status, ManagerStatus)
        assert status.current_version is None
        assert status.is_tracked is False
        assert status.is_legacy is False

    def test_get_manager_status_tracked(self, test_env):
        """When manager is tracked in pyproject.toml, status reflects that."""
        # ARRANGE - Add comfygit-manager as a tracked node
        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["nodes"]["comfygit-manager"] = {
            "name": "comfygit-manager",
            "version": "0.3.0",
            "source": "registry",
            "registry_id": "comfygit-manager",
        }
        test_env.pyproject.save(config)

        # Create the node directory
        manager_path = test_env.comfyui_path / "custom_nodes" / "comfygit-manager"
        manager_path.mkdir(parents=True)

        # ACT
        status = test_env.get_manager_status()

        # ASSERT
        assert status.current_version == "0.3.0"
        assert status.is_tracked is True
        assert status.is_legacy is False

    def test_get_manager_status_legacy_symlink(self, test_workspace, test_env):
        """When manager is a symlink to workspace system_nodes, it's legacy."""
        # ARRANGE - Create a symlinked system node (legacy architecture)
        system_nodes_path = test_workspace.paths.system_nodes
        system_nodes_path.mkdir(parents=True, exist_ok=True)

        manager_source = system_nodes_path / "comfygit-manager"
        manager_source.mkdir(parents=True)
        (manager_source / "__init__.py").write_text("# manager")
        (manager_source / "pyproject.toml").write_text(
            '[project]\nname = "comfygit-manager"\nversion = "0.2.0"\n'
        )

        # Create symlink in custom_nodes
        manager_link = test_env.comfyui_path / "custom_nodes" / "comfygit-manager"
        manager_link.symlink_to(manager_source)

        # ACT
        status = test_env.get_manager_status()

        # ASSERT
        assert status.is_legacy is True
        assert status.is_tracked is False
        assert status.current_version == "0.2.0"


class TestUpdateManager:
    """Tests for Environment.update_manager() migration logic."""

    def test_update_manager_migrates_symlink_to_tracked(self, test_workspace, test_env, monkeypatch):
        """update_manager() should convert symlink to tracked node."""
        # ARRANGE - Create a legacy symlinked manager
        system_nodes_path = test_workspace.paths.system_nodes
        system_nodes_path.mkdir(parents=True, exist_ok=True)

        manager_source = system_nodes_path / "comfygit-manager"
        manager_source.mkdir(parents=True)
        (manager_source / "__init__.py").write_text("# manager")

        manager_link = test_env.comfyui_path / "custom_nodes" / "comfygit-manager"
        manager_link.symlink_to(manager_source)

        # Verify it's a symlink before update
        assert is_link(manager_link)

        # Mock registry lookup to return fake version
        def mock_get_node(node_id):
            from comfygit_core.models.shared import NodeInfo
            return NodeInfo(
                name="comfygit-manager",
                version="0.3.0",
                source="registry",
                registry_id="comfygit-manager",
            )

        monkeypatch.setattr(test_env.node_lookup, "get_node", mock_get_node)
        monkeypatch.setattr(
            test_env.node_lookup, "download_to_cache",
            lambda info: manager_source  # Reuse source as "cache"
        )
        monkeypatch.setattr(
            test_env.node_lookup, "scan_requirements",
            lambda path: []
        )

        # ACT
        result = test_env.update_manager()

        # ASSERT
        assert result.changed is True
        assert result.was_migration is True

        # Manager should now be in pyproject.toml
        config = test_env.pyproject.load()
        assert "comfygit-manager" in config["tool"]["comfygit"]["nodes"]

        # Manager should NOT be a symlink anymore
        manager_path = test_env.comfyui_path / "custom_nodes" / "comfygit-manager"
        assert not is_link(manager_path)
        assert manager_path.is_dir()

    def test_update_manager_removes_system_nodes_dependency_group(self, test_env, monkeypatch):
        """update_manager() should cleanup dependency-groups.system-nodes."""
        # ARRANGE - Add legacy dependency group
        config = test_env.pyproject.load()
        config["dependency-groups"] = {"system-nodes": ["comfygit-core>=0.2.0"]}
        test_env.pyproject.save(config)

        # Create tracked manager
        manager_path = test_env.comfyui_path / "custom_nodes" / "comfygit-manager"
        manager_path.mkdir(parents=True)

        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["nodes"]["comfygit-manager"] = {
            "name": "comfygit-manager",
            "version": "0.2.0",
            "source": "registry",
        }
        test_env.pyproject.save(config)

        # Mock registry for update
        def mock_get_node(node_id):
            from comfygit_core.models.shared import NodeInfo
            return NodeInfo(
                name="comfygit-manager",
                version="0.3.0",
                source="registry",
                registry_id="comfygit-manager",
            )

        monkeypatch.setattr(test_env.node_lookup, "get_node", mock_get_node)
        monkeypatch.setattr(
            test_env.node_lookup, "download_to_cache",
            lambda info: manager_path
        )
        monkeypatch.setattr(
            test_env.node_lookup, "scan_requirements",
            lambda path: ["comfygit-core>=0.3.0"]
        )

        # ACT
        test_env.update_manager()

        # ASSERT - system-nodes group should be removed
        config = test_env.pyproject.load()
        assert "system-nodes" not in config.get("dependency-groups", {})


class TestEnvironmentCreation:
    """Tests for new environment creation with per-environment manager."""

    def test_create_environment_includes_manager(
        self, tmp_path, mock_comfyui_clone, mock_github_api, monkeypatch
    ):
        """New environments should have manager installed and tracked."""
        # ARRANGE
        workspace_path = tmp_path / "test_workspace"
        workspace = WorkspaceFactory.create(workspace_path)

        # Setup required workspace config
        custom_nodes_cache = workspace.paths.cache / "custom_nodes"
        custom_nodes_cache.mkdir(parents=True, exist_ok=True)
        node_mappings = custom_nodes_cache / "node_mappings.json"
        with open(node_mappings, 'w') as f:
            json.dump({"mappings": {}, "packages": {}, "stats": {}}, f)

        models_dir = workspace_path / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        workspace.set_models_directory(models_dir)

        # Mock node lookup for manager installation
        def mock_get_node(node_id):
            if node_id == "comfygit-manager":
                from comfygit_core.models.shared import NodeInfo
                return NodeInfo(
                    name="comfygit-manager",
                    version="0.3.0",
                    source="registry",
                    registry_id="comfygit-manager",
                )
            raise ValueError(f"Unknown node: {node_id}")

        # ACT
        env = workspace.create_environment(
            name="test-env",
            python_version="3.12",
            comfyui_version="master"
        )

        # ASSERT - Manager should be tracked in pyproject
        config = env.pyproject.load()
        nodes = config.get("tool", {}).get("comfygit", {}).get("nodes", {})
        assert "comfygit-manager" in nodes

        # Manager should NOT be in system_nodes directory
        system_nodes_path = workspace.paths.system_nodes
        assert not (system_nodes_path / "comfygit-manager").exists()

        # Manager should be in custom_nodes (not a symlink)
        manager_path = env.comfyui_path / "custom_nodes" / "comfygit-manager"
        assert manager_path.exists()
        assert not is_link(manager_path)

    def test_create_environment_no_system_nodes_directory(
        self, tmp_path, mock_comfyui_clone, mock_github_api
    ):
        """New workspaces should not create .metadata/system_nodes/ directory."""
        # ARRANGE
        workspace_path = tmp_path / "test_workspace"

        # ACT
        workspace = WorkspaceFactory.create(workspace_path)

        # ASSERT - system_nodes directory should NOT be created
        system_nodes_path = workspace.paths.metadata / "system_nodes"
        assert not system_nodes_path.exists()


class TestStatusScanner:
    """Tests for status scanner treating manager as normal node."""

    def test_status_includes_manager_in_nodes(self, test_env):
        """Manager should appear in status as a regular node, not filtered."""
        # ARRANGE - Add manager as tracked node
        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["nodes"]["comfygit-manager"] = {
            "name": "comfygit-manager",
            "version": "0.3.0",
            "source": "registry",
        }
        test_env.pyproject.save(config)

        # Create manager directory
        manager_path = test_env.comfyui_path / "custom_nodes" / "comfygit-manager"
        manager_path.mkdir(parents=True)

        # ACT
        status = test_env.status()

        # ASSERT - Manager should NOT be in system nodes filter
        # (it should be visible as a normal tracked node)
        node_names = [n.name for n in status.node.tracked_nodes]
        assert "comfygit-manager" in node_names


class TestNodeManagerAllowsManager:
    """Tests for NodeManager accepting comfygit-manager."""

    def test_add_node_allows_comfygit_manager(self, test_env, monkeypatch):
        """NodeManager.add_node() should accept comfygit-manager."""
        # ARRANGE
        manager_path = test_env.comfyui_path / "custom_nodes" / "comfygit-manager"

        def mock_get_node(identifier):
            from comfygit_core.models.shared import NodeInfo
            return NodeInfo(
                name="comfygit-manager",
                version="0.3.0",
                source="registry",
                registry_id="comfygit-manager",
            )

        monkeypatch.setattr(test_env.node_lookup, "get_node", mock_get_node)
        monkeypatch.setattr(
            test_env.node_lookup, "download_to_cache",
            lambda info: manager_path
        )
        monkeypatch.setattr(
            test_env.node_lookup, "scan_requirements",
            lambda path: []
        )

        # Create dummy cache source
        cache_source = test_env.workspace.paths.cache / "node_cache" / "comfygit-manager"
        cache_source.mkdir(parents=True)
        (cache_source / "__init__.py").write_text("# manager")

        monkeypatch.setattr(
            test_env.node_lookup, "download_to_cache",
            lambda info: cache_source
        )

        # ACT - Should NOT raise ValueError for system node
        result = test_env.node_manager.add_node("comfygit-manager")

        # ASSERT
        assert result.name == "comfygit-manager"

        # Verify it's tracked in pyproject
        config = test_env.pyproject.load()
        assert "comfygit-manager" in config["tool"]["comfygit"]["nodes"]


class TestExportIncludesManager:
    """Tests for export including manager git info."""

    def test_export_includes_manager_git_info(self, test_env, monkeypatch):
        """Export should include manager's git info since it's per-environment."""
        # ARRANGE - Add manager as tracked node with git info
        config = test_env.pyproject.load()
        config["tool"]["comfygit"]["nodes"]["comfygit-manager"] = {
            "name": "comfygit-manager",
            "version": "0.3.0",
            "source": "registry",
            "registry_id": "comfygit-manager",
            "pinned_commit": "abc123",
            "branch": "main",
        }
        test_env.pyproject.save(config)

        # Create manager directory with git
        manager_path = test_env.comfyui_path / "custom_nodes" / "comfygit-manager"
        manager_path.mkdir(parents=True)

        # Initialize git in manager
        import subprocess
        subprocess.run(["git", "init"], cwd=manager_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=manager_path, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=manager_path, capture_output=True
        )
        (manager_path / "__init__.py").write_text("# manager")
        subprocess.run(["git", "add", "-A"], cwd=manager_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=manager_path, capture_output=True
        )

        # ACT - Call the method that populates git info for export
        # This is _auto_populate_dev_node_git_info in environment.py
        test_env._auto_populate_dev_node_git_info()

        # ASSERT - Manager's git info should be populated
        config = test_env.pyproject.load()
        manager_node = config["tool"]["comfygit"]["nodes"]["comfygit-manager"]
        # The manager should have its git commit updated
        assert "pinned_commit" in manager_node


class TestWorkspaceSchemaVersion:
    """Tests for workspace schema version management."""

    def test_new_workspace_has_schema_v2(self, tmp_path):
        """New workspaces should have schema version 2."""
        # ACT
        workspace = WorkspaceFactory.create(tmp_path / "test")

        # ASSERT
        version_file = workspace.paths.metadata / "version"
        assert version_file.exists()
        assert version_file.read_text().strip() == "2"

    def test_legacy_workspace_detected(self, tmp_path):
        """Workspace without version file is schema v1 (legacy)."""
        # ARRANGE - Create workspace structure manually (legacy)
        workspace_path = tmp_path / "legacy_workspace"
        workspace_path.mkdir()
        metadata = workspace_path / ".metadata"
        metadata.mkdir()
        (metadata / "workspace.json").write_text("{}")

        # ACT
        from comfygit_core.core.workspace import WorkspacePaths, Workspace
        paths = WorkspacePaths(workspace_path)
        workspace = Workspace(paths)

        # ASSERT
        assert workspace.is_legacy_schema() is True
