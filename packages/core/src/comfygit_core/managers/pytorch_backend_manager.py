"""Manages .pytorch-backend file and PyTorch configuration injection."""
from __future__ import annotations

import re
from pathlib import Path

from ..constants import PYTORCH_CORE_PACKAGES
from ..logging.logging_config import get_logger
from ..utils.pytorch import get_pytorch_index_url

logger = get_logger(__name__)


class PyTorchBackendManager:
    """Manages .pytorch-backend file and PyTorch configuration injection.

    The .pytorch-backend file stores the user's PyTorch backend choice (e.g., cu128, cpu).
    This file is gitignored, allowing different machines to use different backends
    while sharing the same environment configuration.
    """

    # Valid backend patterns
    BACKEND_PATTERNS = [
        r'^cu\d{2,3}$',  # CUDA: cu118, cu121, cu128, cu130, etc.
        r'^cpu$',  # CPU
        r'^rocm\d+\.\d+$',  # ROCm: rocm6.2, rocm6.3, etc.
        r'^xpu$',  # Intel XPU
    ]

    def __init__(self, cec_path: Path):
        """Initialize manager.

        Args:
            cec_path: Path to the .cec directory
        """
        self.cec_path = cec_path
        self.backend_file = cec_path / ".pytorch-backend"

    def get_backend(self) -> str:
        """Read backend from file, or auto-detect if missing.

        Returns:
            Backend string (e.g., 'cu128', 'cpu')
        """
        if self.backend_file.exists():
            backend = self.backend_file.read_text().strip()
            if backend:
                logger.debug(f"Read PyTorch backend from file: {backend}")
                return backend

        # Auto-detect if file doesn't exist or is empty
        backend = self.detect_backend()
        logger.info(f"Auto-detected PyTorch backend: {backend}")
        return backend

    def set_backend(self, backend: str) -> None:
        """Write backend to file.

        Also ensures .pytorch-backend is in .gitignore (for migration from
        older environments that don't have this entry).

        Args:
            backend: Backend string (e.g., 'cu128', 'cpu')
        """
        self.backend_file.write_text(backend)
        logger.info(f"Set PyTorch backend: {backend}")

        # Ensure .gitignore has this entry (migration support)
        self._ensure_gitignore_entry()

    def _ensure_gitignore_entry(self) -> None:
        """Ensure .pytorch-backend is in .gitignore.

        This supports migration from older environments that were created
        before .pytorch-backend was added to the default .gitignore template.
        """
        gitignore_path = self.cec_path / ".gitignore"
        entry = ".pytorch-backend"

        if not gitignore_path.exists():
            # No .gitignore - unusual, but create with just this entry
            gitignore_path.write_text(f"# PyTorch backend configuration (machine-specific)\n{entry}\n")
            logger.debug(f"Created .gitignore with entry: {entry}")
            return

        current_content = gitignore_path.read_text()

        # Check if entry already exists
        for line in current_content.split('\n'):
            stripped = line.split('#')[0].strip()
            if stripped == entry:
                return  # Already present

        # Add entry at the end
        if not current_content.endswith('\n'):
            current_content += '\n'
        current_content += f"\n# PyTorch backend configuration (machine-specific)\n{entry}\n"
        gitignore_path.write_text(current_content)
        logger.info(f"Added {entry} to .gitignore (migration)")

    def detect_backend(self) -> str:
        """Auto-detect appropriate backend for current system.

        Uses nvidia-smi to detect CUDA version and maps to appropriate backend.

        Returns:
            Backend string (e.g., 'cu128', 'cpu')
        """
        from ..utils.common import run_command

        try:
            result = run_command(['nvidia-smi'])
            if result.returncode == 0:
                # Parse CUDA version from nvidia-smi output
                match = re.search(r'CUDA Version:\s*(\d+)\.(\d+)', result.stdout)
                if match:
                    major = int(match.group(1))
                    minor = int(match.group(2))
                    backend = f"cu{major}{minor}"
                    logger.info(f"Detected CUDA {major}.{minor}, using backend: {backend}")
                    return backend
        except Exception as e:
            logger.debug(f"Could not detect CUDA: {e}")

        logger.info("No CUDA detected, using CPU backend")
        return "cpu"

    def is_valid_backend(self, backend: str) -> bool:
        """Check if backend string matches valid patterns.

        Args:
            backend: Backend string to validate

        Returns:
            True if valid, False otherwise
        """
        if not backend:
            return False

        for pattern in self.BACKEND_PATTERNS:
            if re.match(pattern, backend):
                return True

        return False

    def get_pytorch_config(self) -> dict:
        """Generate PyTorch uv config for current backend.

        Returns dict with:
            - indexes: List of index configs (name, url, explicit)
            - sources: Dict mapping package names to index names
            - constraints: List of constraint strings (empty for now, can be extended)

        Returns:
            Configuration dict for PyTorch packages
        """
        backend = self.get_backend()
        index_url = get_pytorch_index_url(backend)
        index_name = f"pytorch-{backend}"

        config = {
            "indexes": [
                {
                    "name": index_name,
                    "url": index_url,
                    "explicit": True,
                }
            ],
            "sources": {},
            "constraints": [],
        }

        # Map all PyTorch core packages to the index
        for package in PYTORCH_CORE_PACKAGES:
            config["sources"][package] = {"index": index_name}

        logger.debug(f"Generated PyTorch config for backend {backend}: {config}")
        return config
