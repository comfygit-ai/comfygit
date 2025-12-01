"""Tests for NodeLookupService version fallback behavior.

TDD tests for the scenario where:
1. Package exists in local cache
2. BUT the specific requested version is NOT in the cached data
3. System should fall back to live API to get download_url for that version

Also tests git clone fallback when version is not a valid git ref.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from comfygit_core.models.node_mapping import GlobalNodePackage, GlobalNodePackageVersion
from comfygit_core.models.registry import RegistryNodeInfo, RegistryNodeVersion
from comfygit_core.models.shared import NodeInfo
from comfygit_core.repositories.node_mappings_repository import NodeMappingsRepository
from comfygit_core.services.node_lookup_service import NodeLookupService


class TestNodeLookupVersionNotInCache:
    """Test fallback to API when specific version is not in cached data."""

    @pytest.fixture
    def mock_mappings_data_old_version(self):
        """Create mock mappings with only version 1.10.0 (stale cache)."""
        return {
            "version": "2025.01.01",
            "generated_at": "2025-01-01T00:00:00",
            "stats": {
                "packages": 1,
                "signatures": 1,
                "total_nodes": 1,
                "augmented": True,
                "augmentation_date": "2025-01-01T00:00:00",
                "nodes_from_manager": 0,
                "manager_packages": 0
            },
            "mappings": {},
            "packages": {
                "comfyui-akatz-nodes": {
                    "id": "comfyui-akatz-nodes",
                    "display_name": "ComfyUI-AKatz-Nodes",
                    "author": "akatz-ai",
                    "description": "AKatz custom nodes",
                    "repository": "https://github.com/akatz-ai/comfyui-akatz-nodes",
                    "downloads": 1000,
                    "github_stars": 100,
                    "rating": None,
                    "license": "MIT",
                    "category": "nodes",
                    "icon": None,
                    "tags": [],
                    "status": "active",
                    "created_at": "2024-01-01T00:00:00",
                    "source": None,
                    "versions": {
                        "1.10.0": {
                            "version": "1.10.0",
                            "changelog": "Old release",
                            "release_date": "2024-11-01T00:00:00",
                            "dependencies": [],
                            "deprecated": False,
                            "download_url": "https://cdn.comfy.org/comfyui-akatz-nodes/1.10.0/node.zip",
                            "status": "active",
                            "supported_accelerators": None,
                            "supported_comfyui_version": None,
                            "supported_os": None
                        }
                        # NOTE: 1.11.1 is NOT in cache - simulates stale 24hr cache
                    }
                }
            }
        }

    @pytest.fixture
    def cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mappings_repo_stale(self, mock_mappings_data_old_version):
        """Create a NodeMappingsRepository with stale cache data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text(json.dumps(mock_mappings_data_old_version))

            mock_data_manager = Mock()
            mock_data_manager.get_mappings_path.return_value = mappings_path

            repo = NodeMappingsRepository(data_manager=mock_data_manager)
            yield repo

    def test_find_node_falls_back_to_api_when_version_not_in_cache(self, mappings_repo_stale, cache_dir):
        """SHOULD fall back to API when requested version is not in cached mappings.

        Scenario: User requests comfyui-akatz-nodes@1.11.1 but cache only has 1.10.0
        Expected: System should query live API to get download_url for 1.11.1
        """
        # ARRANGE
        mock_registry_client = MagicMock()

        # Mock get_node to return the package info
        mock_registry_node = RegistryNodeInfo(
            id="comfyui-akatz-nodes",
            name="ComfyUI-AKatz-Nodes",
            description="AKatz custom nodes",
            repository="https://github.com/akatz-ai/comfyui-akatz-nodes",
            latest_version=RegistryNodeVersion(
                changelog="New release",
                dependencies=[],
                deprecated=False,
                id="comfyui-akatz-nodes-v1.11.1",
                version="1.11.1",
                download_url=""  # get_node() often returns empty download_url
            )
        )
        mock_registry_client.get_node.return_value = mock_registry_node

        # Mock install_node to return complete version data with download_url
        mock_complete_version = RegistryNodeVersion(
            changelog="New release",
            dependencies=[],
            deprecated=False,
            id="comfyui-akatz-nodes-v1.11.1",
            version="1.11.1",
            download_url="https://cdn.comfy.org/comfyui-akatz-nodes/1.11.1/node.zip"
        )
        mock_registry_client.install_node.return_value = mock_complete_version

        mock_workspace_config_repo = Mock()
        mock_workspace_config_repo.get_prefer_registry_cache.return_value = True

        service = NodeLookupService(
            cache_path=cache_dir,
            node_mappings_repository=mappings_repo_stale,
            workspace_config_repository=mock_workspace_config_repo
        )
        service.registry_client = mock_registry_client

        # ACT
        result = service.find_node("comfyui-akatz-nodes@1.11.1")

        # ASSERT
        assert result is not None
        assert result.name == "ComfyUI-AKatz-Nodes"
        assert result.registry_id == "comfyui-akatz-nodes"
        assert result.version == "1.11.1"
        # Key assertion: should have download_url from API, not None
        assert result.download_url == "https://cdn.comfy.org/comfyui-akatz-nodes/1.11.1/node.zip"

        # Should have called API since version not in cache
        mock_registry_client.get_node.assert_called_once_with("comfyui-akatz-nodes")
        mock_registry_client.install_node.assert_called_once_with("comfyui-akatz-nodes", "1.11.1")

    def test_find_node_returns_cached_version_when_available(self, mappings_repo_stale, cache_dir):
        """SHOULD return cached data when requested version IS in cache.

        Scenario: User requests comfyui-akatz-nodes@1.10.0 which is in cache
        Expected: System should return cached data without hitting API
        """
        # ARRANGE
        mock_registry_client = MagicMock()

        mock_workspace_config_repo = Mock()
        mock_workspace_config_repo.get_prefer_registry_cache.return_value = True

        service = NodeLookupService(
            cache_path=cache_dir,
            node_mappings_repository=mappings_repo_stale,
            workspace_config_repository=mock_workspace_config_repo
        )
        service.registry_client = mock_registry_client

        # ACT
        result = service.find_node("comfyui-akatz-nodes@1.10.0")

        # ASSERT
        assert result is not None
        assert result.version == "1.10.0"
        assert result.download_url == "https://cdn.comfy.org/comfyui-akatz-nodes/1.10.0/node.zip"

        # Should NOT have called API
        mock_registry_client.get_node.assert_not_called()
        mock_registry_client.install_node.assert_not_called()

    def test_find_node_handles_missing_download_url_from_cache(self, mappings_repo_stale, cache_dir):
        """SHOULD fall back to API when cached version has no download_url.

        Edge case: Version exists in cache but download_url is None/empty
        """
        # Modify cache to have version with no download_url
        mappings_repo_stale.global_mappings.packages["comfyui-akatz-nodes"].versions["1.10.0"].download_url = None

        # ARRANGE
        mock_registry_client = MagicMock()

        mock_complete_version = RegistryNodeVersion(
            changelog="",
            dependencies=[],
            deprecated=False,
            id="comfyui-akatz-nodes-v1.10.0",
            version="1.10.0",
            download_url="https://cdn.comfy.org/comfyui-akatz-nodes/1.10.0/node.zip"
        )
        mock_registry_client.install_node.return_value = mock_complete_version

        mock_registry_node = RegistryNodeInfo(
            id="comfyui-akatz-nodes",
            name="ComfyUI-AKatz-Nodes",
            description="AKatz custom nodes",
            repository="https://github.com/akatz-ai/comfyui-akatz-nodes",
            latest_version=mock_complete_version
        )
        mock_registry_client.get_node.return_value = mock_registry_node

        mock_workspace_config_repo = Mock()
        mock_workspace_config_repo.get_prefer_registry_cache.return_value = True

        service = NodeLookupService(
            cache_path=cache_dir,
            node_mappings_repository=mappings_repo_stale,
            workspace_config_repository=mock_workspace_config_repo
        )
        service.registry_client = mock_registry_client

        # ACT
        result = service.find_node("comfyui-akatz-nodes@1.10.0")

        # ASSERT - should have fallen back to API
        assert result is not None
        assert result.download_url == "https://cdn.comfy.org/comfyui-akatz-nodes/1.10.0/node.zip"
        mock_registry_client.get_node.assert_called_once()


class TestDownloadToCacheGitFallback:
    """Test git clone fallback behavior in download_to_cache."""

    @pytest.fixture
    def cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_git_clone_omits_ref_when_version_is_semver(self, cache_dir):
        """SHOULD clone without --branch when version looks like semver (not a git ref).

        Scenario: Node has source=registry but no download_url
        Git clone fallback should NOT use semver "1.11.1" as --branch
        """
        # ARRANGE
        node_info = NodeInfo(
            name="ComfyUI-AKatz-Nodes",
            registry_id="comfyui-akatz-nodes",
            repository="https://github.com/akatz-ai/comfyui-akatz-nodes",
            version="1.11.1",  # Semver, not a git tag
            download_url=None,  # No download URL - triggers git fallback
            source="registry"
        )

        service = NodeLookupService(cache_path=cache_dir)

        # Mock at the utils.git module level where it's imported from
        with patch('comfygit_core.utils.git.git_clone') as mock_git_clone:
            # ACT
            service.download_to_cache(node_info)

            # ASSERT
            mock_git_clone.assert_called_once()
            call_kwargs = mock_git_clone.call_args
            # Should NOT pass the semver as ref - ref should be None
            assert call_kwargs.kwargs.get('ref') is None, \
                f"Git clone should not use semver '1.11.1' as ref, got: {call_kwargs}"

    def test_git_clone_uses_ref_when_version_is_git_tag(self, cache_dir):
        """SHOULD use ref when version looks like a valid git tag (v1.11.1).

        Git-style versions prefixed with 'v' should be used as refs.
        """
        # ARRANGE
        node_info = NodeInfo(
            name="Some-Node",
            repository="https://github.com/example/some-node",
            version="v1.11.1",  # Git-style tag
            download_url=None,
            source="git"
        )

        service = NodeLookupService(cache_path=cache_dir)

        with patch('comfygit_core.utils.git.git_clone') as mock_git_clone:
            # ACT
            service.download_to_cache(node_info)

            # ASSERT
            mock_git_clone.assert_called_once()
            call_kwargs = mock_git_clone.call_args
            # Should use git tag as ref
            assert call_kwargs.kwargs.get('ref') == "v1.11.1"

    def test_git_clone_uses_ref_when_version_is_commit_hash(self, cache_dir):
        """SHOULD use ref when version is a commit hash."""
        # ARRANGE
        node_info = NodeInfo(
            name="Some-Node",
            repository="https://github.com/example/some-node",
            version="abc123def456789012345678901234567890abcd",  # 40-char commit hash
            download_url=None,
            source="git"
        )

        service = NodeLookupService(cache_path=cache_dir)

        with patch('comfygit_core.utils.git.git_clone') as mock_git_clone:
            # ACT
            service.download_to_cache(node_info)

            # ASSERT
            mock_git_clone.assert_called_once()
            call_kwargs = mock_git_clone.call_args
            # Should use commit hash as ref
            assert call_kwargs.kwargs.get('ref') == "abc123def456789012345678901234567890abcd"
