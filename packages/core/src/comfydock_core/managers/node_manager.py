# managers/node_manager.py
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..managers.pyproject_manager import PyprojectManager
from ..managers.resolution_tester import ResolutionTester
from ..managers.uv_project_manager import UVProjectManager
from ..models.exceptions import (
    CDEnvironmentError,
    CDNodeConflictError,
    CDNodeNotFoundError,
)
from ..models.shared import NodePackage
from ..services.global_node_resolver import GlobalNodeResolver
from ..services.node_registry import NodeInfo, NodeRegistry

if TYPE_CHECKING:
    from ..services.registry_data_manager import RegistryDataManager

logger = get_logger(__name__)


class NodeManager:
    """Manages all node operations for an environment."""

    def __init__(
        self,
        pyproject: PyprojectManager,
        uv: UVProjectManager,
        node_registry: NodeRegistry,
        resolution_tester: ResolutionTester,
        custom_nodes_path: Path,
        registry_data_manager: RegistryDataManager
    ):
        self.pyproject = pyproject
        self.uv = uv
        self.node_registry = node_registry
        self.resolution_tester = resolution_tester
        self.custom_nodes_path = custom_nodes_path
        self.registry_data_manager = registry_data_manager

        # Initialize global resolver for GitHub URL → Registry ID mapping
        node_mapper_path = self.registry_data_manager.get_mappings_path()
        self.global_resolver = GlobalNodeResolver(node_mapper_path)

    def add_node_package(self, node_package: NodePackage) -> None:
        """Add a complete node package with requirements and source tracking.

        This is the low-level method for adding pre-prepared node packages.
        """
        # Check for duplicates
        existing_nodes = self.pyproject.nodes.get_existing()
        for existing_id, existing_node in existing_nodes.items():
            if existing_node.name == node_package.name:
                raise ValueError(
                    f"Node '{node_package.name}' already exists (stored as '{existing_id}'). "
                    f"To replace it, first remove the existing node then add the new one."
                )

        # Snapshot sources before processing
        existing_sources = self.pyproject.uv_config.get_source_names()

        # Generate collision-resistant group name for UV dependencies
        group_name = self.pyproject.nodes.generate_group_name(
            node_package.node_info, node_package.identifier
        )

        # Add requirements if any
        if node_package.requirements:
            self.uv.add_requirements_with_sources(
                node_package.requirements, group=group_name, no_sync=True, raw=True
            )

        # Detect new sources after processing
        current_sources = self.pyproject.uv_config.get_source_names()
        new_sources = current_sources - existing_sources

        # Update node with detected sources
        if new_sources:
            node_package.node_info.dependency_sources = sorted(new_sources)

        # Store node configuration
        self.pyproject.nodes.add(node_package.node_info, node_package.identifier)

    def add_node(self, identifier: str, is_local: bool = False, is_development: bool = False, no_test: bool = False) -> NodeInfo:
        """Add a custom node to the environment.

        Raises:
            CDNodeNotFoundError: If node not found
            CDNodeConflictError: If node has dependency conflicts
            CDEnvironmentError: If node with same name already exists
        """
        logger.info(f"Adding node: {identifier}")

        # Handle development nodes
        if is_development:
            return self._add_development_node(identifier)

        # Check for existing installation by registry ID (if GitHub URL provided)
        registry_id = None
        github_url = None

        if self._is_github_url(identifier):
            github_url = identifier
            # Try to resolve GitHub URL to registry ID
            if self.global_resolver:
                if resolved := self.global_resolver.resolve_github_url(identifier):
                    registry_id, package_data = resolved
                    logger.info(f"Resolved GitHub URL to registry ID: {registry_id}")

                    # Check if already installed by registry ID
                    if self._is_node_installed_by_registry_id(registry_id):
                        existing_info = self._get_existing_node_by_registry_id(registry_id)
                        print(f"✅ Node already installed: {existing_info.get('name', registry_id)} v{existing_info.get('version', 'unknown')}")
                        response = input("Use existing version? (y/N): ").lower().strip()
                        if response == 'y':
                            return NodeInfo(
                                name=existing_info.get('name', registry_id),
                                registry_id=registry_id,
                                version=existing_info.get('version'),
                                repository=existing_info.get('repository'),
                                source=existing_info.get('source', 'unknown')
                            )
        else:
            registry_id = identifier

        # Get complete node package from NodeRegistry
        node_package = self.node_registry.prepare_node(identifier, is_local)

        # Enhance with dual-source information if available
        if github_url and registry_id:
            node_package.node_info.registry_id = registry_id
            node_package.node_info.repository = github_url
            logger.info(f"Enhanced node info with dual sources: registry_id={registry_id}, github_url={github_url}")

        # Add to pyproject with all complexity handled internally
        try:
            self.add_node_package(node_package)
        except Exception as e:
            # Re-raise as CDEnvironmentError for consistency
            if "already exists" in str(e):
                raise CDEnvironmentError(str(e))
            raise

        # Test resolution if requested (extraction happens later after sync)
        if not no_test:
            resolution_result = self.resolution_tester.test_resolution(self.pyproject.path)
            if not resolution_result.success:
                raise CDNodeConflictError(
                    f"Node '{node_package.name}' has dependency conflicts: "
                    f"{self.resolution_tester.format_conflicts(resolution_result)}"
                )

        logger.info(f"Successfully added node '{node_package.name}'")
        return node_package.node_info

    def remove_node(self, identifier: str):
        """Remove a custom node.

        Raises:
            CDNodeNotFoundError: If node not found
        """
        # Check development nodes first
        if self.pyproject.dev_nodes.exists(identifier):
            removed = self.pyproject.dev_nodes.remove(identifier)
            if removed:
                logger.info(f"Removed development node '{identifier}' from tracking")
                print(f"ℹ️ Development node '{identifier}' removed from tracking (files preserved)")
                return

        # Get node info before removal to capture dependency sources
        existing_nodes = self.pyproject.nodes.get_existing()
        if identifier not in existing_nodes:
            raise CDNodeNotFoundError(f"Node '{identifier}' not found in environment")

        removed_node = existing_nodes[identifier]
        removed_sources = removed_node.dependency_sources or []

        # Remove the node
        removed = self.pyproject.nodes.remove(identifier)

        if not removed:
            raise CDNodeNotFoundError(f"Node '{identifier}' not found in environment")

        # Clean up orphaned sources
        self.pyproject.uv_config.cleanup_orphaned_sources(removed_sources)

        logger.info(f"Removed node '{identifier}' from environment")

    def sync_nodes_to_filesystem(self):
        """Sync custom nodes directory to match expected state from pyproject.toml."""
        # Get expected nodes from pyproject.toml
        pyproject_config = self.pyproject.load()
        expected_nodes = self.node_registry.parse_expected_nodes(pyproject_config)

        # Always sync to filesystem, even with empty dict (to remove unwanted nodes)
        self.node_registry.sync_nodes_to_filesystem(expected_nodes, self.custom_nodes_path)

    def _is_github_url(self, identifier: str) -> bool:
        """Check if identifier is a GitHub URL."""
        return identifier.startswith(('https://github.com/', 'git@github.com:', 'ssh://git@github.com/'))

    def _is_node_installed_by_registry_id(self, registry_id: str) -> bool:
        """Check if a node is already installed by registry ID."""
        existing_nodes = self.pyproject.nodes.get_existing()
        for node_info in existing_nodes.values():
            if hasattr(node_info, 'registry_id') and node_info.registry_id == registry_id:
                return True
        return False

    def _get_existing_node_by_registry_id(self, registry_id: str) -> dict:
        """Get existing node configuration by registry ID."""
        existing_nodes = self.pyproject.nodes.get_existing()
        for node_info in existing_nodes.values():
            if hasattr(node_info, 'registry_id') and node_info.registry_id == registry_id:
                return {
                    'name': node_info.name,
                    'registry_id': node_info.registry_id,
                    'version': node_info.version,
                    'repository': node_info.repository,
                    'source': node_info.source
                }
        return {}

    def _add_development_node(self, identifier: str) -> NodeInfo:
        """Add a development node by discovering it in the custom_nodes directory."""
        # Look for existing directory
        node_path = self.custom_nodes_path / identifier

        if not node_path.exists() or not node_path.is_dir():
            # Try case-insensitive search
            for item in self.custom_nodes_path.iterdir():
                if item.is_dir() and item.name.lower() == identifier.lower():
                    node_path = item
                    identifier = item.name  # Use actual directory name
                    break
            else:
                raise CDNodeNotFoundError(
                    f"Development node directory '{identifier}' not found in {self.custom_nodes_path}"
                )

        # Check if already tracked
        if self.pyproject.dev_nodes.exists(identifier):
            print(f"⚠️ Development node '{identifier}' is already tracked")
            # Return a simple NodeInfo for consistency
            dev_node = self.pyproject.dev_nodes.get_all()[identifier]
            return NodeInfo(
                name=dev_node.get('name', identifier),
                version=dev_node.get('version', 'dev'),
                source='development'
            )

        # Add to development section
        self.pyproject.dev_nodes.add(identifier, identifier)

        print(f"✓ Added development node '{identifier}' for tracking")

        # Return a simple NodeInfo
        return NodeInfo(
            name=identifier,
            version='dev',
            source='development'
        )

