"""Global node resolver using prebuilt mappings."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, List
from urllib.parse import urlparse

from ..models.node_mapping import (
    GlobalNodeMapping,
    GlobalNodeMappings,
    GlobalNodeMappingsStats,
    GlobalNodePackage,
    GlobalNodePackageVersion
)


from comfydock_core.models.workflow import (
    WorkflowNode,
    ResolvedNodePackage,
    NodeResolutionResult,
    NodeResolutionContext,
    ScoredPackageMatch,
)

from ..logging.logging_config import get_logger
from ..utils.input_signature import create_node_key, normalize_workflow_inputs

logger = get_logger(__name__)


class GlobalNodeResolver:
    """Resolves unknown nodes using global mappings file."""

    def __init__(self, mappings_path: Path):
        self.mappings_path = mappings_path
        self.global_mappings, self.github_to_registry = self._load_mappings()

    def _load_mappings(self) -> tuple[GlobalNodeMappings, dict[str, GlobalNodePackage]]:
        """Load global mappings from file."""
        if not self.mappings_path.exists():
            logger.warning(f"Global mappings file not found: {self.mappings_path}")
            raise FileNotFoundError

        try:
            with open(self.mappings_path) as f:
                data = json.load(f)

            # Load into GlobalNodeMappings dataclass
            stats_data = data.get("stats", {})
            stats = GlobalNodeMappingsStats(
                packages=stats_data.get("packages"),
                signatures=stats_data.get("signatures"),
                total_nodes=stats_data.get("total_nodes"),
                augmented=stats_data.get("augmented"),
                augmentation_date=stats_data.get("augmentation_date"),
                nodes_from_manager=stats_data.get("nodes_from_manager"),
                synthetic_packages=stats_data.get("synthetic_packages"),
            )

            # Convert mappings dict to GlobalNodeMapping objects
            mappings = {}
            for key, mapping_data in data.get("mappings", {}).items():
                mappings[key] = GlobalNodeMapping(
                    id=key,
                    package_id=mapping_data.get("package_id", ""),
                    versions=mapping_data.get("versions", []),
                    source=mapping_data.get("source"),
                )

            # Convert packages dict to GlobalNodePackage objects
            packages = {}
            for pkg_id, pkg_data in data.get("packages", {}).items():
                # Loop over versions and create global node package version objects
                versions: dict[str, GlobalNodePackageVersion] = {}
                pkg_versions = pkg_data.get("versions", {})
                for version_id, version_data in pkg_versions.items():
                    version = GlobalNodePackageVersion(
                        version=version_id,
                        changelog=version_data.get("changelog"),
                        release_date=version_data.get("release_date"),
                        dependencies=version_data.get("dependencies"),
                        deprecated=version_data.get("deprecated"),
                        download_url=version_data.get("download_url"),
                        status=version_data.get("status"),
                        supported_accelerators=version_data.get("supported_accelerators"),
                        supported_comfyui_version=version_data.get("supported_comfyui_version"),
                        supported_os=version_data.get("supported_os"),
                    )
                    versions[version_id] = version

                packages[pkg_id] = GlobalNodePackage(
                    id=pkg_id,
                    display_name=pkg_data.get("display_name"),
                    author=pkg_data.get("author"),
                    description=pkg_data.get("description"),
                    repository=pkg_data.get("repository"),
                    downloads=pkg_data.get("downloads"),
                    github_stars=pkg_data.get("github_stars"),
                    rating=pkg_data.get("rating"),
                    license=pkg_data.get("license"),
                    category=pkg_data.get("category"),
                    tags=pkg_data.get("tags"),
                    status=pkg_data.get("status"),
                    created_at=pkg_data.get("created_at"),
                    versions=versions,
                    synthetic=pkg_data.get("synthetic", False),
                    source=pkg_data.get("source"),
                )

            global_mappings = GlobalNodeMappings(
                version=data.get("version", "unknown"),
                generated_at=data.get("generated_at", ""),
                stats=stats,
                mappings=mappings,
                packages=packages,
            )

            github_to_registry = self._build_github_to_registry_map(global_mappings)

            if stats:
                logger.info(
                    f"Loaded global mappings: {stats.signatures} signatures "
                    f"from {stats.packages} packages, "
                    f"{len(github_to_registry)} GitHub URLs"
                )

            return global_mappings, github_to_registry

        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load global mappings: {e}")
            raise e

    def _normalize_github_url(self, url: str) -> str:
        """Normalize GitHub URL to canonical form."""
        if not url:
            return ""

        # Remove .git suffix
        url = re.sub(r"\.git$", "", url)

        # Parse URL
        parsed = urlparse(url)

        # Handle different GitHub URL formats
        if parsed.hostname in ("github.com", "www.github.com"):
            # Extract owner/repo from path
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) >= 2:
                owner, repo = path_parts[0], path_parts[1]
                return f"https://github.com/{owner}/{repo}"

        # For SSH URLs like git@github.com:owner/repo
        if url.startswith("git@github.com:"):
            repo_path = url.replace("git@github.com:", "")
            repo_path = re.sub(r"\.git$", "", repo_path)
            return f"https://github.com/{repo_path}"

        # For SSH URLs like ssh://git@github.com/owner/repo
        if url.startswith("ssh://git@github.com/"):
            repo_path = url.replace("ssh://git@github.com/", "")
            repo_path = re.sub(r"\.git$", "", repo_path)
            return f"https://github.com/{repo_path}"

        return url

    def _build_github_to_registry_map(self, global_mappings: GlobalNodeMappings) -> dict[str, GlobalNodePackage]:
        """Build reverse mapping from GitHub URLs to registry IDs."""
        github_to_registry = {}

        for _, package in global_mappings.packages.items():
            if package.repository:
                normalized_url = self._normalize_github_url(package.repository)
                if normalized_url:
                    github_to_registry[normalized_url] = package

        return github_to_registry

    def resolve_github_url(self, github_url: str) -> GlobalNodePackage | None:
        """Resolve GitHub URL to registry ID and package data."""
        normalized_url = self._normalize_github_url(github_url)
        if mapping := self.github_to_registry.get(normalized_url):
            return mapping
        return None

    def get_github_url_for_package(self, package_id: str) -> str | None:
        """Get GitHub URL for a package ID."""
        if self.global_mappings and package_id in self.global_mappings.packages:
            return self.global_mappings.packages[package_id].repository
        return None

    def resolve_workflow_nodes(
        self, custom_nodes: list[WorkflowNode]
    ) -> NodeResolutionResult:
        """Resolve unknown/custom nodes from workflow.

        Args:
            custom_nodes: List of WorkflowNode that are not builtin nodes.

        Returns:
            Resolution result with matches and suggestions
        """
        result = NodeResolutionResult()

        for node in custom_nodes:
            node_type = node.type

            matches = self.resolve_single_node(node)

            if matches:
                if len(matches) > 1:
                    result.ambiguous[node_type] = matches
                else:
                    result.resolved[node_type] = matches[0]
            else:
                result.unresolved.append(node_type)

        return result

    def resolve_single_node(self, node: WorkflowNode) -> List[ResolvedNodePackage] | None:
        """Resolve a single node type."""
        mappings = self.global_mappings.mappings
        packages = self.global_mappings.packages

        node_type = node.type
        inputs = node.inputs

        # Strategy 1: Try exact match with input signature
        if inputs:
            input_signature = normalize_workflow_inputs(inputs)
            logger.debug(f"Input signature for {node_type}: {input_signature}")
            if input_signature:
                exact_key = create_node_key(node_type, input_signature)
                logger.debug(f"Exact key for {node_type}: {exact_key}")
                if exact_key in mappings:
                    mapping = mappings[exact_key]
                    logger.debug(
                        f"Exact match for {node_type}: {mapping.package_id}"
                    )
                    return [
                        ResolvedNodePackage(
                            package_id=mapping.package_id,
                            package_data=packages[mapping.package_id],
                            node_type=node_type,
                            versions=mapping.versions,
                            match_type="exact",
                            match_confidence=1.0,
                        )
                    ]

        # Strategy 2: Try type-only match
        type_only_key = create_node_key(node_type, "_")
        if type_only_key in mappings:
            mapping = mappings[type_only_key]
            logger.debug(f"Type-only match for {node_type}: {mapping.package_id}")
            return [
                ResolvedNodePackage(
                    package_id=mapping.package_id,
                    package_data=packages[mapping.package_id],
                    node_type=node_type,
                    versions=mapping.versions,
                    match_type="type_only",
                    match_confidence=0.9,
                )
            ]

        # Strategy 3: Fuzzy search (simple substring matching)
        matches: list[ResolvedNodePackage] = []
        node_type_lower = node_type.lower()

        for key, mapping in mappings.items():
            mapped_node_type = key.split("::")[0]

            # Simple substring matching
            if (
                node_type_lower in mapped_node_type.lower()
                or mapped_node_type.lower() in node_type_lower
            ):
                matches.append(
                    ResolvedNodePackage(
                        package_id=mapping.package_id,
                        package_data=packages[mapping.package_id],
                        node_type=node_type,
                        versions=mapping.versions,
                        match_type="fuzzy",
                        match_confidence=0.8,
                    )
                )
        if matches:
            logger.debug(f"Fuzzy matches for {node_type}: {matches}")
            return matches

        logger.debug(f"No match found for {node_type}")
        return None

    def resolve_single_node_with_context(
        self,
        node: WorkflowNode,
        context: NodeResolutionContext | None = None
    ) -> List[ResolvedNodePackage] | None:
        """Enhanced resolution with context awareness.

        Resolution priority:
        1. Session-resolved mappings (deduplication)
        2. Custom mappings from pyproject
        3. Properties field (cnr_id from workflow)
        4. Global mapping table (existing logic)
        5. Heuristic matching against installed packages
        6. None (trigger interactive resolution)

        Args:
            node: WorkflowNode to resolve
            context: Optional resolution context for caching and custom mappings

        Returns:
            List of resolved packages, empty list for skip, or None for unresolved
        """
        node_type = node.type

        if not context:
            # No context - fall back to original method
            return self.resolve_single_node(node)

        # Priority 1: Session cache (deduplication)
        if node_type in context.session_resolved:
            pkg_id = context.session_resolved[node_type]
            logger.debug(f"Session cache hit for {node_type}: {pkg_id}")
            return [self._create_resolved_package_from_id(pkg_id, node_type, "session_cache")]

        # Priority 2: Custom mappings
        if node_type in context.custom_mappings:
            mapping = context.custom_mappings[node_type]
            if mapping == "skip":
                logger.debug(f"Skipping {node_type} (user-configured)")
                return []  # Empty list = skip
            logger.debug(f"Custom mapping for {node_type}: {mapping}")
            result = [self._create_resolved_package_from_id(mapping, node_type, "custom_mapping")]
            context.session_resolved[node_type] = mapping
            return result

        # Priority 3: Properties field (cnr_id from ComfyUI)
        if node.properties:
            cnr_id = node.properties.get('cnr_id')
            ver = node.properties.get('ver')  # Git commit hash

            if cnr_id:
                logger.debug(f"Found cnr_id in properties: {cnr_id} @ {ver}")

                # Validate package exists in global mappings
                if cnr_id in self.global_mappings.packages:
                    pkg_data = self.global_mappings.packages[cnr_id]

                    result = [ResolvedNodePackage(
                        package_id=cnr_id,
                        package_data=pkg_data,
                        node_type=node_type,
                        versions=[ver] if ver else [],
                        match_type="properties",
                        match_confidence=1.0
                    )]

                    context.session_resolved[node_type] = cnr_id
                    return result
                else:
                    logger.warning(f"cnr_id {cnr_id} from properties not in registry")

        # Priority 4: Global table (existing logic)
        result = self.resolve_single_node(node)
        if result:
            # Cache in session
            context.session_resolved[node_type] = result[0].package_id
            return result

        # Priority 5: No match - return None to trigger interactive strategy with unified search
        logger.debug(f"No resolution found for {node_type} - will use interactive strategy")
        return None

    def _create_resolved_package_from_id(
        self,
        pkg_id: str,
        node_type: str,
        match_type: str
    ) -> ResolvedNodePackage:
        """Create ResolvedNodePackage from package ID.

        Args:
            pkg_id: Package ID to create package for
            node_type: Node type being resolved
            match_type: Type of match (session_cache, custom_mapping, properties, etc.)

        Returns:
            ResolvedNodePackage instance
        """
        pkg_data = self.global_mappings.packages.get(pkg_id)

        return ResolvedNodePackage(
            package_id=pkg_id,
            package_data=pkg_data,
            node_type=node_type,
            versions=[],
            match_type=match_type,
            match_confidence=1.0
        )

    def search_packages(
        self,
        node_type: str,
        installed_packages: dict = None,
        include_registry: bool = True,
        limit: int = 10
    ) -> List[ScoredPackageMatch]:
        """Unified search with heuristic boosting.

        Combines fuzzy matching with hint pattern detection to rank packages.
        Installed packages receive priority boosting.

        Args:
            node_type: Node type to search for
            installed_packages: Already installed packages (prioritized)
            include_registry: Also search full registry
            limit: Maximum results

        Returns:
            Scored matches sorted by relevance (highest first)
        """
        from difflib import SequenceMatcher

        if not node_type:
            return []

        scored = []
        node_type_lower = node_type.lower()
        installed_packages = installed_packages or {}

        # Build candidate pool
        candidates = {}

        # Phase 1: Installed packages (always checked first)
        for pkg_id in installed_packages.keys():
            pkg_data = self.global_mappings.packages.get(pkg_id)
            if pkg_data:
                candidates[pkg_id] = (pkg_data, True)  # True = installed

        # Phase 2: Registry packages
        if include_registry:
            for pkg_id, pkg_data in self.global_mappings.packages.items():
                if pkg_id not in candidates:
                    candidates[pkg_id] = (pkg_data, False)  # False = not installed

        # Score each candidate
        for pkg_id, (pkg_data, is_installed) in candidates.items():
            score = self._calculate_match_score(
                node_type=node_type,
                node_type_lower=node_type_lower,
                pkg_id=pkg_id,
                pkg_data=pkg_data,
                is_installed=is_installed
            )

            if score > 0.3:  # Minimum threshold
                confidence = self._score_to_confidence(score)
                scored.append(ScoredPackageMatch(
                    package_id=pkg_id,
                    package_data=pkg_data,
                    score=score,
                    confidence=confidence
                ))

        # Sort by score descending
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:limit]

    def _calculate_match_score(
        self,
        node_type: str,
        node_type_lower: str,
        pkg_id: str,
        pkg_data,
        is_installed: bool
    ) -> float:
        """Calculate comprehensive match score with bonuses.

        Scoring pipeline:
        1. Base fuzzy score (SequenceMatcher)
        2. Keyword overlap bonus
        3. Hint pattern bonuses (heuristics!)
        4. Installed package bonus
        """
        from difflib import SequenceMatcher

        pkg_id_lower = pkg_id.lower()

        # 1. Base fuzzy score
        base_score = SequenceMatcher(None, node_type_lower, pkg_id_lower).ratio()

        # Also check display name
        if pkg_data.display_name:
            name_score = SequenceMatcher(
                None, node_type_lower, pkg_data.display_name.lower()
            ).ratio()
            base_score = max(base_score, name_score)

        # 2. Keyword overlap bonus
        node_keywords = set(re.findall(r'\w+', node_type_lower))
        pkg_keywords = set(re.findall(r'\w+', pkg_id_lower))
        if pkg_data.display_name:
            pkg_keywords.update(re.findall(r'\w+', pkg_data.display_name.lower()))

        keyword_overlap = len(node_keywords & pkg_keywords) / max(len(node_keywords), 1)
        keyword_bonus = keyword_overlap * 0.20

        # 3. Hint pattern bonuses (THE HEURISTICS!)
        hint_bonus = self._detect_hint_patterns(node_type, node_type_lower, pkg_id_lower)

        # 4. Installed package bonus
        installed_bonus = 0.10 if is_installed else 0.0

        # Combine and cap at 1.0
        final_score = base_score + keyword_bonus + hint_bonus + installed_bonus
        return min(1.0, final_score)

    def _detect_hint_patterns(
        self,
        node_type: str,
        node_type_lower: str,
        pkg_id_lower: str
    ) -> float:
        """Detect hint patterns and return bonus score.

        This is where heuristics live - as score boosters!
        """
        max_bonus = 0.0

        # Pattern 1: Parenthetical hint
        # "Node Name (package)" → "package"
        if "(" in node_type and ")" in node_type:
            hint = node_type.split("(")[-1].rstrip(")").strip().lower()
            if len(hint) >= 3:  # Minimum length to avoid false positives
                if hint == pkg_id_lower:
                    max_bonus = max(max_bonus, 0.70)  # Exact match
                elif hint in pkg_id_lower:
                    max_bonus = max(max_bonus, 0.60)  # Substring match

        # Pattern 2: Pipe separator
        # "Node Name | PackageName" → "PackageName"
        if "|" in node_type:
            parts = node_type.split("|")
            if len(parts) == 2:
                hint = parts[1].strip().lower()
                if hint in pkg_id_lower:
                    max_bonus = max(max_bonus, 0.55)

        # Pattern 3: Dash/Colon separator
        # "Node Name - Package" or "Node: Package"
        for sep in [" - ", ": "]:
            if sep in node_type:
                parts = node_type.split(sep)
                if len(parts) >= 2:
                    hint = parts[-1].strip().lower()
                    if len(hint) >= 3 and hint in pkg_id_lower:
                        max_bonus = max(max_bonus, 0.50)
                        break

        # Pattern 4: Fragment match (weakest)
        # "DepthAnythingV2" → "depthanythingv2" in package
        pkg_parts = re.split(r'[-_]', pkg_id_lower)
        for part in pkg_parts:
            if len(part) > 4 and part in node_type_lower:
                max_bonus = max(max_bonus, 0.40)
                break

        return max_bonus

    def _score_to_confidence(self, score: float) -> str:
        """Convert numeric score to confidence label."""
        if score >= 0.85:
            return "high"
        elif score >= 0.65:
            return "good"
        elif score >= 0.45:
            return "possible"
        else:
            return "low"
