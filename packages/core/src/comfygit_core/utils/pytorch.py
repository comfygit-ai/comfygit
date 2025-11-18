"""PyTorch-specific utilities for backend detection and index URL generation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..constants import PYTORCH_INDEX_BASE_URL


def get_pytorch_index_url(backend: str) -> str:
    """Generate PyTorch index URL for any backend.

    PyTorch uses a consistent URL pattern for all backends:
    https://download.pytorch.org/whl/{backend}

    This works for:
    - CPU: cpu
    - CUDA: cu118, cu121, cu124, cu126, cu128, cu130, etc.
    - ROCm: rocm6.2, rocm6.3, rocm6.4, etc.
    - Intel XPU: xpu

    Args:
        backend: Backend identifier (e.g., 'cu128', 'rocm6.3', 'cpu')

    Returns:
        Full index URL for the backend

    Examples:
        >>> get_pytorch_index_url("cu128")
        'https://download.pytorch.org/whl/cu128'
        >>> get_pytorch_index_url("rocm6.3")
        'https://download.pytorch.org/whl/rocm6.3'
    """
    return f"{PYTORCH_INDEX_BASE_URL}/{backend}"


def extract_backend_from_version(version: str) -> str | None:
    """Extract backend from PyTorch version string.

    PyTorch versions with specific backends use the format:
    {version}+{backend} (e.g., '2.9.0+cu128')

    CPU-only builds may omit the backend suffix on some platforms.

    Args:
        version: Version string (e.g., '2.9.0+cu128', '2.6.0')

    Returns:
        Backend string (e.g., 'cu128', 'rocm6.3') or None if no backend suffix

    Examples:
        >>> extract_backend_from_version("2.9.0+cu128")
        'cu128'
        >>> extract_backend_from_version("2.9.0")
        None
    """
    if '+' in version:
        return version.split('+')[1]
    return None


def extract_pip_show_package_version(pip_show_output: str) -> str | None:
    """Extract version from pip show output.

    Args:
        pip_show_output: Output from 'uv pip show package'

    Returns:
        Version string (e.g., '2.6.0+cu128') or None if not found
    """
    import re
    match = re.search(r'^Version:\s*(.+)$', pip_show_output, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def get_installed_pytorch_info(uv_manager: Any, python_executable: Path) -> dict:
    """Get installed PyTorch version and backend from venv.

    Args:
        uv_manager: UVProjectManager instance for pip commands
        python_executable: Path to Python executable in venv

    Returns:
        {
            "torch": "2.9.1+cu128",
            "torchvision": "0.18.1+cu128",
            "torchaudio": "2.9.1+cu128",
            "backend": "cu128"  # or "cpu" if no backend suffix
        }
    """
    from ..constants import PYTORCH_CORE_PACKAGES

    result = {"backend": "cpu"}

    for pkg in PYTORCH_CORE_PACKAGES:
        try:
            output = uv_manager.show_package(pkg, python_executable)
            version = extract_pip_show_package_version(output)
            if version:
                result[pkg] = version
                # Extract backend from first package with version suffix
                if result["backend"] == "cpu":
                    backend = extract_backend_from_version(version)
                    if backend:
                        result["backend"] = backend
        except Exception:
            # Package not installed
            pass

    return result
