"""Core data models for ComfyUI migration manifest schema v1.0.

This module provides type-safe dataclasses for representing ComfyUI environment
detection results and migration manifests. All models include validation,
serialization helpers, and proper type hints for IDE support.

This module also consolidates all dataclasses used throughout the detector
to provide a single source of truth for data structures.
"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .exceptions import ComfyDockError


@dataclass
class RegistryNodeVersion:
    """Version information for a node."""
    changelog: str
    dependencies: list[str]
    deprecated: bool
    id: str
    version: str
    download_url: str

    @classmethod
    def from_api_data(cls, api_data: dict) -> "RegistryNodeVersion | None":
        if not api_data:
            return None
        return cls(
            changelog=api_data.get("changelog", ""),
            dependencies=api_data.get("dependencies", []),
            deprecated=api_data.get("deprecated", False),
            id=api_data.get("id", ""),
            version=api_data.get("version", ""),
            download_url=api_data.get("downloadUrl", ""),
        )

@dataclass
class RegistryNodeInfo:
    """Information about a custom node."""
    id: str
    name: str
    description: str
    author: str | None = None
    license: str | None = None
    icon: str | None = None
    repository: str | None = None
    tags: list[str] = field(default_factory=list)
    latest_version: RegistryNodeVersion | None = None

    @classmethod
    def from_api_data(cls, api_data: dict) -> "RegistryNodeInfo | None":
        # Ensure dict has id, name and description keys:
        id = api_data.get("id")
        name = api_data.get("name")
        description = api_data.get("description")
        if not id or not name or not description:
            return None
        return cls(
            id=id,
            name=name,
            description=description,
            author=api_data.get("author"),
            license=api_data.get("license"),
            icon=api_data.get("icon"),
            repository=api_data.get("repository"),
            tags=api_data.get("tags", []),
            latest_version=RegistryNodeVersion.from_api_data(api_data.get("latest_version", {})),
        )

@dataclass
class NodeInfo:
    """Information about a custom node."""
    name: str
    repository: str | None = None
    download_url: str | None = None
    registry_id: str | None = None
    version: str | None = None
    source: str = "unknown"  # registry, git, or local
    dependency_sources: list[str] | None = None

    @classmethod
    def from_registry_node(cls, registry_node_info: RegistryNodeInfo):
        return cls(
            name=registry_node_info.name,
            registry_id=registry_node_info.id,
            version=registry_node_info.latest_version.version if registry_node_info.latest_version else None,
            download_url=registry_node_info.latest_version.download_url if registry_node_info.latest_version else None,
            source="registry"
        )

    @classmethod
    def from_pyproject_config(cls, pyproject_config: dict, node_identifier: str) -> "NodeInfo | None":
        if not pyproject_config:
            return None
        node_config = pyproject_config.get(node_identifier)
        if not node_config:
            return None
        name = node_config.get("name")
        if not name:
            return None
        return cls(
            name=name,
            version=node_config.get("version"),
            source=node_config.get("source", "unknown"),
            download_url=node_config.get("download_url"),
            registry_id=node_config.get("registry_id"),
            repository=node_config.get("repository"),
            dependency_sources=node_config.get("dependency_sources"),
        )

@dataclass
class NodePackage:
    """Complete package for a node including info and requirements."""
    node_info: NodeInfo
    requirements: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.node_info.name

    @property
    def identifier(self) -> str:
        """Get the best identifier for this node."""
        return self.node_info.registry_id or self.node_info.name

@dataclass
class Package:
    """Represents an installed Python package."""

    name: str
    version: str
    is_editable: bool = False

    def validate(self) -> None:
        """Validate package information."""
        if not self.name:
            raise ComfyDockError("Package name cannot be empty")
        if not self.version:
            raise ComfyDockError("Package version cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Package':
        """Create instance from dictionary."""
        return cls(**data)

@dataclass
class SystemRequirements:
    """System requirements for the environment."""

    python_version: str
    cuda_version: str | None = None
    platform: str = "linux"
    architecture: str | None = None
    comfyui_version: str = ""

    def validate(self) -> None:
        """Validate system info fields."""
        if not self._is_valid_version(self.python_version):
            raise ComfyDockError(f"Invalid Python version format: {self.python_version}")

        if self.cuda_version and not self._is_valid_cuda_version(self.cuda_version):
            raise ComfyDockError(f"Invalid CUDA version format: {self.cuda_version}")

        # Platform validation
        valid_platforms = {'linux', 'darwin', 'win32'}
        if self.platform not in valid_platforms:
            raise ComfyDockError(f"Invalid platform: {self.platform}. Must be one of: {', '.join(valid_platforms)}")

        # ComfyUI version validation (required)
        if not self.comfyui_version:
            raise ComfyDockError("ComfyUI version is required")

    @staticmethod
    def _is_valid_version(version: str) -> bool:
        """Check if version follows M.m.p format."""
        pattern = r'^\d+\.\d+\.\d+$'
        return bool(re.match(pattern, version))

    @staticmethod
    def _is_valid_cuda_version(version: str) -> bool:
        """Check if CUDA version is valid (M.m format)."""
        pattern = r'^\d+\.\d+$'
        return bool(re.match(pattern, version))


    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'python_version': self.python_version,
            'cuda_version': self.cuda_version,
            'platform': self.platform,
            'comfyui_version': self.comfyui_version
        }
        if self.architecture:
            result['architecture'] = self.architecture
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'SystemRequirements':
        """Create instance from dictionary."""
        return cls(**data)

@dataclass
class PyTorchSpec:
    """PyTorch packages configuration with index URL."""

    index_url: str
    packages: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate PyTorch specification."""
        if not self._is_valid_url(self.index_url):
            raise ComfyDockError(f"Invalid PyTorch index URL: {self.index_url}")

        if not self.packages:
            raise ComfyDockError("PyTorch packages cannot be empty")

        for package, version in self.packages.items():
            if not self._is_valid_package_name(package):
                raise ComfyDockError(f"Invalid package name: {package}")
            if not self._is_valid_version(version):
                raise ComfyDockError(f"Invalid version for {package}: {version}")

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Check if URL is absolute with scheme."""
        try:
            result = urlparse(url)
            return bool(result.scheme and result.netloc)
        except Exception:
            return False

    @staticmethod
    def _is_valid_package_name(name: str) -> bool:
        """Check if package name follows PEP 508."""
        # Basic validation: alphanumeric with dash, underscore, dot
        pattern = r'^[a-zA-Z0-9\-_\.]+$'
        return bool(re.match(pattern, name))

    @staticmethod
    def _is_valid_version(version: str) -> bool:
        """Check if version is valid (basic semver with optional suffix like +cu126)."""
        pattern = r'^\d+\.\d+(\.\d+)?(\+[a-zA-Z0-9]+)?$'
        return bool(re.match(pattern, version))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'PyTorchSpec':
        """Create instance from dictionary."""
        return cls(**data)

def create_system_requirements_from_detection(
    python_version: str,
    cuda_version: str | None = None,
    platform: str = "linux",
    architecture: str | None = None,
    comfyui_version: str = ""
) -> SystemRequirements:
    """Create SystemRequirements from detection results."""
    info = SystemRequirements(
        python_version=python_version,
        cuda_version=cuda_version,
        platform=platform,
        architecture=architecture,
        comfyui_version=comfyui_version
    )
    info.validate()
    return info


@dataclass
class SystemInfo:
    """System information detected from a ComfyUI installation.
    
    This dataclass represents all system-level information needed
    to recreate a ComfyUI environment.
    """

    # Python information
    python_version: str
    python_executable: Path | None = None
    python_major_minor: str | None = None

    # CUDA/GPU information
    cuda_version: str | None = None
    cuda_torch_version: str | None = None  # CUDA version PyTorch was built with

    # PyTorch information
    torch_version: str | None = None
    pytorch_info: dict | None = None  # Full PyTorch detection results

    # Platform information
    platform: str = ""
    architecture: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for compatibility with existing code."""
        result = {
            'python_version': self.python_version,
            'cuda_version': self.cuda_version,
            'torch_version': self.torch_version,
            'cuda_torch_version': self.cuda_torch_version,
            'platform': self.platform,
            'architecture': self.architecture,
            'pytorch_info': self.pytorch_info
        }

        # Include optional fields if present
        if self.python_executable:
            result['python_executable'] = str(self.python_executable)
        if self.python_major_minor:
            result['python_major_minor'] = self.python_major_minor

        return result

# Progress and Utility Models

@dataclass
class ProgressContext:
    """Context for nested progress tracking."""
    task: str
    start_time: float
    total_items: int | None = None
    current_item: int = 0


# Model Management Models

@dataclass
class TrackedDirectory:
    """Tracked model directory configuration."""
    id: str
    path: str
    added_at: str
    last_sync: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'TrackedDirectory':
        """Create instance from dictionary."""
        return cls(**data)

@dataclass
class ModelInfo:
    """Core model identity (unique by hash)."""
    file_size: int
    blake3_hash: str | None = None
    sha256_hash: str | None = None
    short_hash: str = ""

    def validate(self) -> None:
        """Validate model information."""
        if self.file_size <= 0:
            raise ComfyDockError("File size must be positive")
        # blake3_hash can be empty initially - will be filled when needed

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ModelInfo':
        """Create instance from dictionary."""
        return cls(**data)


@dataclass
class ModelLocation:
    """A location where a model exists in the filesystem."""
    model_hash: str
    relative_path: str
    filename: str
    mtime: float
    last_seen: int

    def validate(self) -> None:
        """Validate model location."""
        if not self.model_hash:
            raise ComfyDockError("Model hash cannot be empty")
        if not self.filename:
            raise ComfyDockError("Filename cannot be empty")
        if not self.relative_path:
            raise ComfyDockError("Relative path cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ModelLocation':
        """Create instance from dictionary."""
        return cls(**data)


@dataclass
class ModelWithLocation:
    """Combined model and location information for convenience."""
    hash: str
    file_size: int
    relative_path: str
    filename: str
    mtime: float
    last_seen: int
    blake3_hash: str | None = None
    sha256_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate model with location entry."""
        if not self.hash:
            raise ComfyDockError("Hash cannot be empty")
        if not self.filename:
            raise ComfyDockError("Filename cannot be empty")
        if self.file_size <= 0:
            raise ComfyDockError("File size must be positive")
        if not self.relative_path:
            raise ComfyDockError("Relative path cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ModelWithLocation':
        """Create instance from dictionary."""
        return cls(**data)


# Cache Models

@dataclass
class CachedNodeInfo:
    """Information about a cached custom node."""
    cache_key: str
    name: str
    install_method: str
    url: str
    ref: str | None = None
    cached_at: str = ""
    last_accessed: str = ""
    access_count: int = 0
    size_bytes: int = 0
    content_hash: str | None = None
    source_info: dict | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'CachedNodeInfo':
        """Create from dictionary."""
        return cls(**data)


