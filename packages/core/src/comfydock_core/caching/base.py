"""Base classes for caching infrastructure.

Provides platform-aware cache path resolution and content caching infrastructure
that can be extended for specific cache types (ComfyUI, custom nodes, models, etc).
"""

import hashlib
import json
import os
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..logging.logging_config import get_logger

logger = get_logger(__name__)


class CacheBase:
    """Minimal base providing platform-aware cache path resolution.

    Provides common cache directory resolution with support for:
    - Platform-specific defaults (Linux, macOS, Windows)
    - Environment variable override (COMFYDOCK_CACHE)
    - Explicit path override
    """

    def __init__(self, cache_name: str = "comfydock",
                 cache_base_path: Path | None = None):
        """Initialize cache base.

        Args:
            cache_name: Name of the cache subdirectory
            cache_base_path: Override cache base path (for testing)
        """
        self.cache_name = cache_name
        self.cache_base = cache_base_path or self._get_default_cache_path()

    def _get_default_cache_path(self) -> Path:
        """Get platform-aware cache path with env var override.

        Priority:
        1. COMFYDOCK_CACHE environment variable
        2. Platform-specific default:
           - Linux: ~/.cache/comfydock or $XDG_CACHE_HOME/comfydock
           - macOS: ~/Library/Caches/comfydock
           - Windows: %LOCALAPPDATA%/comfydock

        Returns:
            Path to cache directory
        """
        # Priority 1: Environment variable
        env_cache = os.environ.get('COMFYDOCK_CACHE')
        if env_cache:
            return Path(env_cache)

        # Priority 2: Platform-specific default
        system = platform.system()

        if system == "Windows":
            base = os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')
            return Path(base) / self.cache_name
        elif system == "Darwin":
            return Path.home() / 'Library' / 'Caches' / self.cache_name
        else:
            # Linux and others
            xdg_cache = os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')
            return Path(xdg_cache) / self.cache_name

    def _ensure_cache_dirs(self, *subdirs: str):
        """Ensure cache subdirectories exist.

        Args:
            *subdirs: Subdirectory paths to create under cache_base
        """
        for subdir in subdirs:
            (self.cache_base / subdir).mkdir(parents=True, exist_ok=True)


class ContentCacheBase(CacheBase):
    """Base for content-based caching (files, directories, large data).

    Provides infrastructure for caching content with:
    - Directory-based storage (cache_key/content/)
    - Metadata tracking (size, hash, timestamps)
    - Index file for fast lookup
    - Content hashing for integrity
    """

    def __init__(self, content_type: str, cache_base_path: Path | None = None):
        """Initialize content cache.

        Args:
            content_type: Type of content being cached (e.g., "comfyui", "custom_nodes")
            cache_base_path: Override cache base path (for testing)
        """
        super().__init__("comfydock", cache_base_path)
        self.content_type = content_type
        self.cache_dir = self.cache_base / content_type
        self.store_dir = self.cache_dir / "store"
        self.index_file = self.cache_dir / "index.json"

        # Ensure directories exist
        self._ensure_cache_dirs(content_type, f"{content_type}/store")

        # Load index
        self.index = self._load_index()

    def _load_index(self) -> dict:
        """Load cache index from disk.

        Returns:
            Index dictionary mapping cache keys to metadata
        """
        if not self.index_file.exists():
            return {}

        try:
            with open(self.index_file, encoding='utf-8') as f:
                data = json.load(f)
            return data.get("items", {})
        except Exception as e:
            logger.error(f"Failed to load cache index: {e}")
            return {}

    def _save_index(self):
        """Save cache index to disk atomically."""
        try:
            data = {
                "version": "1.0",
                "content_type": self.content_type,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "items": self.index
            }

            # Atomic write: temp file then replace
            temp_file = self.index_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self.index_file)

        except Exception as e:
            logger.error(f"Failed to save cache index: {e}")

    def _calculate_content_hash(self, content_dir: Path) -> str:
        """Calculate SHA256 hash of directory content for integrity checking.

        Args:
            content_dir: Directory to hash

        Returns:
            SHA256 hexdigest of all files in directory
        """
        hasher = hashlib.sha256()

        # Sort files for deterministic hashing
        for file_path in sorted(content_dir.rglob("*")):
            if file_path.is_file():
                # Include relative path in hash
                rel_path = file_path.relative_to(content_dir)
                hasher.update(str(rel_path).encode())

                # Include file content
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        hasher.update(chunk)

        return hasher.hexdigest()

    def cache_content(self, cache_key: str, source_path: Path,
                     metadata: dict | None = None) -> Path:
        """Cache content from source directory.

        Args:
            cache_key: Unique cache key
            source_path: Path to source content directory
            metadata: Optional additional metadata to store

        Returns:
            Path to cached content directory
        """
        cache_dir = self.store_dir / cache_key
        content_dir = cache_dir / "content"

        # Clean up existing cache entry
        if cache_dir.exists():
            shutil.rmtree(cache_dir)

        cache_dir.mkdir(parents=True)

        # Copy content
        shutil.copytree(source_path, content_dir)

        # Calculate metadata
        size_bytes = sum(
            f.stat().st_size for f in content_dir.rglob("*") if f.is_file()
        )
        content_hash = self._calculate_content_hash(content_dir)

        # Store metadata
        full_metadata = {
            "cache_key": cache_key,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "size_bytes": size_bytes,
            "content_hash": content_hash,
            **(metadata or {})
        }

        with open(cache_dir / "metadata.json", "w", encoding='utf-8') as f:
            json.dump(full_metadata, f, indent=2)

        # Update index
        self.index[cache_key] = full_metadata
        self._save_index()

        logger.debug(f"Cached {self.content_type} with key: {cache_key}")
        return content_dir

    def get_cached_path(self, cache_key: str) -> Path | None:
        """Get path to cached content if it exists.

        Args:
            cache_key: Cache key to look up

        Returns:
            Path to content directory, or None if not cached
        """
        content_path = self.store_dir / cache_key / "content"
        return content_path if content_path.exists() else None
