"""NodeLookupService - Pure stateless service for finding nodes and analyzing requirements."""

from pathlib import Path

from comfydock_core.models.exceptions import CDNodeNotFoundError, CDRegistryError
from comfydock_core.models.shared import NodeInfo

from ..caching import APICacheManager, CustomNodeCacheManager
from ..logging.logging_config import get_logger
from ..analyzers.custom_node_scanner import CustomNodeScanner
from ..clients import ComfyRegistryClient, GitHubClient

logger = get_logger(__name__)


class NodeLookupService:
    """Pure stateless service for finding nodes and analyzing their requirements.

    Responsibilities:
    - Registry API calls (finding nodes by ID/URL)
    - GitHub API calls (validating repos, getting commit info)
    - Requirement scanning (analyzing node directories)
    - Cache management (API responses, downloaded node archives)
    """

    def __init__(self, workspace_path: Path | None = None, cache_path: Path | None = None):
        """Initialize the node lookup service."""
        self.scanner = CustomNodeScanner()
        cache_path = cache_path or (workspace_path / "cache" if workspace_path else None)
        self.api_cache = APICacheManager(cache_base_path=cache_path)
        self.custom_node_cache = CustomNodeCacheManager(cache_base_path=cache_path)
        self.registry_client = ComfyRegistryClient(cache_manager=self.api_cache)
        self.github_client = GitHubClient(cache_manager=self.api_cache)

    def find_node(self, identifier: str) -> NodeInfo | None:
        """Find node info from registry or git URL.

        Args:
            identifier: Registry ID (optionally with @version), node name, or git URL

        Returns:
            NodeInfo with metadata, or None if not found
        """
        # Parse version from identifier if present (e.g., "package-id@1.2.3")
        requested_version = None
        if '@' in identifier and not identifier.startswith(('https://', 'git@', 'ssh://')):
            parts = identifier.split('@', 1)
            identifier = parts[0]
            requested_version = parts[1]

        # Check if it's a git URL
        if identifier.startswith(('https://', 'git@', 'ssh://')):
            try:
                if repo_info := self.github_client.get_repository_info(identifier):
                    return NodeInfo(
                        name=repo_info.name,
                        repository=repo_info.clone_url,
                        source="git",
                        version=repo_info.latest_commit
                    )
            except Exception as e:
                logger.warning(f"Invalid git URL: {e}")
                return None

        # Check registry
        try:
            registry_node = self.registry_client.get_node(identifier)
            if registry_node:
                logger.info(f"Found node '{registry_node.name}' in registry: {str(registry_node)}")
                if requested_version:
                    version = requested_version
                    logger.info(f"Using requested version: {version}")
                else:
                    version = registry_node.latest_version.version if registry_node.latest_version else None
                node_version = self.registry_client.install_node(registry_node.id, version)
                if node_version:
                    registry_node.latest_version = node_version
                return NodeInfo.from_registry_node(registry_node)
        except CDRegistryError as e:
            logger.warning(f"Cannot reach registry: {e}")

        logger.debug(f"Node '{identifier}' not found")
        return None

    def get_node(self, identifier: str) -> NodeInfo:
        """Get a node - raises if not found.

        Args:
            identifier: Registry ID, node name, or git URL

        Returns:
            NodeInfo with metadata

        Raises:
            CDNodeNotFoundError: If node not found in any source
        """
        node = self.find_node(identifier)
        if not node:
            msg = f"Node '{identifier}' not found"
            if identifier.startswith(('http://', 'https://')) and not identifier.endswith('.git'):
                msg += ". Did you mean to provide a git URL? (should end with .git)"
            elif '/' not in identifier:
                msg += " in registry. Try: 1) Full registry ID, 2) Git URL, or 3) Local path"
            raise CDNodeNotFoundError(msg)
        return node

    def scan_requirements(self, node_path: Path) -> list[str]:
        """Scan a node directory for Python requirements.

        Args:
            node_path: Path to node directory

        Returns:
            List of requirement strings (empty if none found)
        """
        deps = self.scanner.scan_node(node_path)
        if deps and deps.requirements:
            logger.info(f"Found {len(deps.requirements)} requirements in {node_path.name}")
            return deps.requirements
        logger.info(f"No requirements found in {node_path.name}")
        return []

    def download_to_cache(self, node_info: NodeInfo) -> Path | None:
        """Download a node to cache and return the cached path.

        Args:
            node_info: Node information

        Returns:
            Path to cached node directory, or None if download failed
        """
        from ..utils.download import download_and_extract_archive
        from ..utils.git import git_clone
        import tempfile

        # Check if already cached
        if cache_path := self.custom_node_cache.get_cached_path(node_info):
            logger.debug(f"Node '{node_info.name}' already in cache")
            return cache_path

        # Download to temp location
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / node_info.name

            try:
                if node_info.source == "registry":
                    if not node_info.download_url:
                        # Fallback: Clone from repository if download URL missing
                        if node_info.repository:
                            logger.info(
                                f"No CDN package for '{node_info.name}', "
                                f"falling back to git clone from {node_info.repository}"
                            )
                            # Update source to git for this installation
                            node_info.source = "git"
                            ref = node_info.version if node_info.version else None
                            git_clone(node_info.repository, temp_path, depth=1, ref=ref, timeout=30)
                        else:
                            logger.error(
                                f"Cannot download '{node_info.name}': "
                                f"no CDN package and no repository URL"
                            )
                            return None
                    else:
                        download_and_extract_archive(node_info.download_url, temp_path)
                elif node_info.source == "git":
                    if not node_info.repository:
                        logger.error(f"No repository URL for git node '{node_info.name}'")
                        return None
                    ref = node_info.version if node_info.version else None
                    git_clone(node_info.repository, temp_path, depth=1, ref=ref, timeout=30)
                else:
                    logger.error(f"Unsupported source: '{node_info.source}'")
                    return None

                # Cache it
                logger.info(f"Caching node '{node_info.name}'")
                return self.custom_node_cache.cache_node(node_info, temp_path)

            except Exception as e:
                logger.error(f"Failed to download node '{node_info.name}': {e}")
                return None

    def search_nodes(self, query: str, limit: int = 10) -> list[NodeInfo] | None:
        """Search for nodes in the registry.

        Args:
            query: Search term
            limit: Maximum results

        Returns:
            List of matching NodeInfo objects or None
        """
        try:
            nodes = self.registry_client.search_nodes(query)
            if nodes:
                return [NodeInfo.from_registry_node(node) for node in nodes[:limit]]
        except CDRegistryError as e:
            logger.warning(f"Failed to search registry: {e}")
        return None
