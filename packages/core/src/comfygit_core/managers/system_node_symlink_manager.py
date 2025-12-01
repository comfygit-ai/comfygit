"""SystemNodeSymlinkManager - Creates symlinks from custom_nodes to workspace system_nodes."""
from __future__ import annotations

from pathlib import Path

import tomlkit

from ..logging.logging_config import get_logger
from ..utils.symlink_utils import create_platform_link, is_link

logger = get_logger(__name__)


class SystemNodeSymlinkManager:
    """Manages symlinks from ComfyUI/custom_nodes to workspace system_nodes.

    System nodes are infrastructure custom nodes (like comfygit-manager) that:
    - Live at workspace level (.metadata/system_nodes/)
    - Are symlinked into every environment
    - Are never tracked in pyproject.toml
    - Are never exported/imported

    This follows the same pattern as ModelSymlinkManager and UserContentSymlinkManager.
    """

    def __init__(self, comfyui_path: Path, workspace_system_nodes: Path):
        """Initialize SystemNodeSymlinkManager.

        Args:
            comfyui_path: Path to ComfyUI directory
            workspace_system_nodes: Path to workspace .metadata/system_nodes/
        """
        self.comfyui_path = comfyui_path
        self.custom_nodes_path = comfyui_path / "custom_nodes"
        self.system_nodes_path = workspace_system_nodes

    def create_symlinks(self) -> list[str]:
        """Create symlinks for all available system nodes.

        Iterates through workspace system_nodes/ directory and creates
        symlinks in custom_nodes/ for each one found.

        Returns:
            List of node names that were linked
        """
        if not self.system_nodes_path.exists():
            logger.debug("System nodes directory does not exist, skipping")
            return []

        # Ensure custom_nodes directory exists
        self.custom_nodes_path.mkdir(parents=True, exist_ok=True)

        linked = []
        for node_dir in self.system_nodes_path.iterdir():
            if not node_dir.is_dir():
                continue

            node_name = node_dir.name
            link_path = self.custom_nodes_path / node_name

            if link_path.exists():
                if is_link(link_path):
                    # Already a link - check if pointing to correct target
                    if link_path.resolve() == node_dir.resolve():
                        logger.debug(f"System node '{node_name}' already linked correctly")
                        continue
                    else:
                        # Wrong target - recreate
                        logger.info(f"Updating system node link for '{node_name}'")
                        link_path.unlink()
                else:
                    # Real directory exists - don't overwrite
                    logger.warning(
                        f"Cannot create system node link for '{node_name}': "
                        f"directory already exists at {link_path}"
                    )
                    continue

            # Create symlink
            create_platform_link(link_path, node_dir, node_name)
            linked.append(node_name)
            logger.info(f"Linked system node: {node_name}")

        return linked

    def validate_symlinks(self) -> dict[str, bool]:
        """Check if all system node symlinks exist and point to correct targets.

        Returns:
            Dict mapping node name to validity (True if valid)
        """
        results = {}

        if not self.system_nodes_path.exists():
            return results

        for node_dir in self.system_nodes_path.iterdir():
            if not node_dir.is_dir():
                continue

            node_name = node_dir.name
            link_path = self.custom_nodes_path / node_name

            if not link_path.exists():
                results[node_name] = False
            elif not is_link(link_path):
                results[node_name] = False
            elif link_path.resolve() != node_dir.resolve():
                results[node_name] = False
            else:
                results[node_name] = True

        return results

    def get_all_requirements(self) -> list[str]:
        """Scan all system nodes and collect their requirements.

        Reads pyproject.toml (preferred) or requirements.txt from each
        system node and returns a combined list of requirements.

        Returns:
            List of requirement strings (e.g., ["comfygit-core", "watchdog>=6.0.0"])
        """
        if not self.system_nodes_path.exists():
            return []

        all_requirements: set[str] = set()

        for node_dir in self.system_nodes_path.iterdir():
            if not node_dir.is_dir():
                continue

            requirements = self._parse_node_requirements(node_dir)
            all_requirements.update(requirements)

        return list(all_requirements)

    def _parse_node_requirements(self, node_dir: Path) -> list[str]:
        """Parse requirements from a single system node.

        Tries pyproject.toml first, then falls back to requirements.txt.
        """
        # Try pyproject.toml first
        pyproject_path = node_dir / "pyproject.toml"
        if pyproject_path.exists():
            try:
                with open(pyproject_path, encoding="utf-8") as f:
                    config = tomlkit.load(f)
                dependencies = config.get("project", {}).get("dependencies", [])
                if dependencies:
                    logger.debug(f"Found {len(dependencies)} deps in {node_dir.name}/pyproject.toml")
                    return list(dependencies)
            except Exception as e:
                logger.warning(f"Failed to parse {pyproject_path}: {e}")

        # Fall back to requirements.txt
        requirements_path = node_dir / "requirements.txt"
        if requirements_path.exists():
            try:
                content = requirements_path.read_text(encoding="utf-8")
                requirements = [
                    line.strip()
                    for line in content.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                if requirements:
                    logger.debug(f"Found {len(requirements)} deps in {node_dir.name}/requirements.txt")
                    return requirements
            except Exception as e:
                logger.warning(f"Failed to parse {requirements_path}: {e}")

        return []
