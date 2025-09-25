"""ModelResolver - Resolve model requirements for environment import/export."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from ..managers.model_index_manager import ModelIndexManager

logger = get_logger(__name__)


@dataclass
class ResolutionResult:
    """Result of model resolution process."""

    resolved: dict[str, ModelIndex] = field(default_factory=dict)
    """Models successfully resolved by hash"""

    downloadable: dict[str, dict] = field(default_factory=dict)
    """Models that can be downloaded from known sources"""

    needs_confirmation: dict[str, list[ModelIndex]] = field(default_factory=dict)
    """Models with multiple potential matches requiring user confirmation"""

    missing: dict[str, dict] = field(default_factory=dict)
    """Models that could not be resolved or downloaded"""

    @property
    def total_models(self) -> int:
        """Total number of models in resolution request."""
        return (len(self.resolved) + len(self.downloadable) +
                len(self.needs_confirmation) + len(self.missing))

    @property
    def success_rate(self) -> float:
        """Percentage of models successfully resolved."""
        if self.total_models == 0:
            return 100.0
        return (len(self.resolved) / self.total_models) * 100.0


class ModelResolver:
    """Resolve model requirements for environments using multiple strategies."""

    def __init__(self, index_manager: ModelIndexManager, download_manager=None):
        """Initialize ModelResolver.
        
        Args:
            index_manager: ModelIndexManager for lookups
            download_manager: Optional ModelDownloadManager for downloading
        """
        self.index_manager = index_manager
        self.download_manager = download_manager

    def resolve_models(self, manifest: dict) -> ResolutionResult:
        """Resolve all models in environment manifest.
        
        Tries multiple resolution strategies:
        1. Short hash (exact match)
        2. Full BLAKE3 hash
        3. SHA256 hash  
        4. Filename matching with user confirmation
        
        Args:
            manifest: Model manifest with 'required' and 'optional' sections
            
        Returns:
            ResolutionResult with categorized outcomes
        """
        result = ResolutionResult()

        # Combine all models from required and optional sections
        all_models = {}
        all_models.update(manifest.get('required', {}))
        all_models.update(manifest.get('optional', {}))

        logger.info(f"Resolving {len(all_models)} models")

        for short_hash, model_spec in all_models.items():
            logger.debug(f"Resolving model: {model_spec.get('filename', 'unknown')} [{short_hash[:8]}...]")

            # Strategy 1: Try short hash first
            matches = self.index_manager.find_model_by_hash(short_hash)
            if matches:
                result.resolved[short_hash] = matches[0]
                logger.debug(f"✓ Resolved by short hash: {short_hash[:8]}...")
                continue

            # Strategy 2: Try full BLAKE3 hash
            if blake3_hash := model_spec.get('blake3'):
                matches = self.index_manager.find_model_by_hash(blake3_hash)
                if matches:
                    result.resolved[short_hash] = matches[0]
                    logger.debug(f"✓ Resolved by BLAKE3: {short_hash[:8]}...")
                    continue

            # Strategy 3: Try SHA256 hash
            if sha256_hash := model_spec.get('sha256'):
                matches = self.index_manager.find_model_by_hash(sha256_hash)
                if matches:
                    result.resolved[short_hash] = matches[0]
                    logger.debug(f"✓ Resolved by SHA256: {short_hash[:8]}...")
                    continue

            # Strategy 4: Check if downloadable from sources
            if sources := model_spec.get('sources'):
                result.downloadable[short_hash] = model_spec
                logger.debug(f"→ Downloadable: {short_hash[:8]}...")
                continue

            # Strategy 5: Try filename matching as last resort
            filename = model_spec.get('filename', '')
            if filename:
                matches = self.index_manager.find_by_filename(filename)
                if matches:
                    if len(matches) == 1:
                        # Single match - auto-resolve but flag for confirmation
                        result.needs_confirmation[short_hash] = matches
                        logger.debug(f"? Filename match (needs confirmation): {short_hash[:8]}...")
                    else:
                        # Multiple matches - require user selection
                        result.needs_confirmation[short_hash] = matches
                        logger.debug(f"? Multiple filename matches: {short_hash[:8]}...")
                    continue

            # No resolution possible
            result.missing[short_hash] = model_spec
            logger.debug(f"✗ Could not resolve: {short_hash[:8]}...")

        logger.info(f"Resolution complete: {len(result.resolved)}/{len(all_models)} resolved")
        return result

    def resolve_with_downloads(self, manifest: dict, auto_download: bool = False) -> ResolutionResult:
        """Resolve models with automatic downloading of missing models.
        
        Args:
            manifest: Model manifest to resolve
            auto_download: Automatically download missing models
            
        Returns:
            ResolutionResult with download attempts included
        """
        if not self.download_manager:
            logger.warning("No download manager available - skipping downloads")
            return self.resolve_models(manifest)

        # First pass: standard resolution
        result = self.resolve_models(manifest)

        if not result.downloadable:
            return result

        logger.info(f"Found {len(result.downloadable)} downloadable models")

        # Download missing models
        for short_hash, model_spec in result.downloadable.copy().items():
            sources = model_spec.get('sources', [])
            if not sources:
                continue

            if auto_download:
                success = self._attempt_download(short_hash, sources, result)
                if success:
                    # Move from downloadable to resolved
                    del result.downloadable[short_hash]
            else:
                logger.info(f"Model {short_hash[:8]}... available for download from {sources[0]['type']}")

        return result

    def _attempt_download(self, short_hash: str, sources: list[dict], result: ResolutionResult) -> bool:
        """Attempt to download model from available sources.
        
        Args:
            short_hash: Model short hash
            sources: List of source dictionaries
            result: ResolutionResult to update
            
        Returns:
            True if download successful
        """
        for source in sources:
            try:
                url = source.get('url')
                if not url:
                    continue

                logger.info(f"Downloading {short_hash[:8]}... from {source.get('type', 'unknown')}")
                model = self.download_manager.download_from_url(url)

                # Add to resolved models
                result.resolved[short_hash] = model
                logger.info(f"✓ Downloaded and resolved: {short_hash[:8]}...")
                return True

            except Exception as e:
                logger.warning(f"Download failed for {short_hash[:8]}... from {url}: {e}")
                continue

        return False


    def generate_export_manifest(self, model_hashes: list[str]) -> dict:
        """Generate export manifest with full metadata for models.
        
        Args:
            model_hashes: List of model hashes to include
            
        Returns:
            Export manifest with complete model metadata
        """
        export_manifest = {
            'required': {},
            'optional': {}
        }

        for model_hash in model_hashes:
            models = self.index_manager.find_model_by_hash(model_hash)
            if not models:
                logger.warning(f"Model not found for export: {model_hash[:8]}...")
                continue

            model = models[0]

            # Get all known sources
            sources = self.index_manager.get_sources(model_hash)

            # Compute additional hashes if needed
            model_path = Path(model.path)
            blake3_hash = None
            sha256_hash = None

            if model_path.exists():
                # Only compute if we don't already have them
                existing_models = self.index_manager.find_model_by_hash(model_hash)
                if existing_models:
                    # Check if we need to compute additional hashes
                    try:
                        sha256_hash = self.index_manager.compute_sha256(model_path)
                        self.index_manager.update_sha256(model_hash, sha256_hash)
                    except Exception as e:
                        logger.warning(f"Failed to compute SHA256 for {model_hash[:8]}...: {e}")

            # Build manifest entry
            manifest_entry = {
                'filename': model.filename,
                'type': model.model_type,
                'size': model.file_size,
            }

            # Add hashes if available
            if blake3_hash:
                manifest_entry['blake3'] = blake3_hash
            if sha256_hash:
                manifest_entry['sha256'] = sha256_hash

            # Add sources if available
            if sources:
                manifest_entry['sources'] = []
                for source in sources:
                    source_entry = {
                        'type': source['type'],
                        'url': source['url']
                    }
                    if 'data' in source:
                        source_entry.update(source['data'])
                    manifest_entry['sources'].append(source_entry)

            # For now, put everything in required - could be made configurable
            export_manifest['required'][model_hash] = manifest_entry

        return export_manifest

    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human readable form."""
        size = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

