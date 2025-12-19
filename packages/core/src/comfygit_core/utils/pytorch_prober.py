"""PyTorch version prober via temporary venv.

Creates a temporary virtual environment to discover exact PyTorch versions
for a given Python version and backend combination.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from ..logging.logging_config import get_logger
from .common import run_command

logger = get_logger(__name__)


class PyTorchProbeError(Exception):
    """Error during PyTorch version probing."""

    pass


def get_exact_python_version(requested_version: str) -> str:
    """Get exact Python version that uv would use.

    Args:
        requested_version: Requested version (e.g., "3.12" or "3.12.11")

    Returns:
        Exact version (e.g., "3.12.11")

    Raises:
        PyTorchProbeError: If version cannot be determined
    """
    # Use uv python find to get the interpreter path
    result = run_command(["uv", "python", "find", requested_version])

    if result.returncode != 0:
        raise PyTorchProbeError(
            f"Could not find Python {requested_version}: {result.stderr}"
        )

    # Parse output - looks like: /path/to/cpython-3.12.11-linux.../bin/python3.12
    # We need to extract the full 3-part version from the path
    output = result.stdout.strip()

    # Match cpython-X.Y.Z or python-X.Y.Z in path
    match = re.search(r"(?:cpython|python)-(\d+\.\d+\.\d+)", output, re.IGNORECASE)
    if match:
        return match.group(1)

    # Also try pythonX.Y.Z format (some systems)
    match = re.search(r"python(\d+\.\d+\.\d+)", output, re.IGNORECASE)
    if match:
        return match.group(1)

    raise PyTorchProbeError(
        f"Could not parse Python version from uv output: {output}"
    )


def probe_pytorch_versions(
    python_version: str,
    backend: str,
    workspace_path: Path,
) -> dict[str, str]:
    """Probe PyTorch versions by creating temp venv and installing.

    Creates a temporary virtual environment, installs PyTorch packages,
    extracts their versions, and caches the results.

    Args:
        python_version: Exact Python version (e.g., "3.12.11")
        backend: PyTorch backend (e.g., "cu128", "cpu")
        workspace_path: Path to workspace (for cache storage)

    Returns:
        Dict mapping package name to version string:
        {"torch": "2.9.1+cu128", "torchvision": "0.24.1+cu128", ...}

    Raises:
        PyTorchProbeError: If probing fails
    """
    from ..caching.pytorch_version_cache import PyTorchVersionCache
    from .pytorch import get_pytorch_index_url

    temp_dir = tempfile.mkdtemp(prefix=".comfygit-pytorch-probe-")

    try:
        logger.info(f"Probing PyTorch versions for Python {python_version} + {backend}...")

        # 1. Create venv with exact Python version
        venv_result = run_command(
            ["uv", "venv", temp_dir, "--python", python_version]
        )

        if venv_result.returncode != 0:
            raise PyTorchProbeError(
                f"Failed to create probe venv: {venv_result.stderr}"
            )

        # 2. Install PyTorch packages from the backend index
        index_url = get_pytorch_index_url(backend)

        install_result = run_command(
            [
                "uv",
                "pip",
                "install",
                "--python", temp_dir,
                "--index-url", index_url,
                "torch",
                "torchvision",
                "torchaudio",
            ]
        )

        if install_result.returncode != 0:
            raise PyTorchProbeError(
                f"Failed to install PyTorch packages: {install_result.stderr}"
            )

        # 3. Get installed package versions
        list_result = run_command(
            ["uv", "pip", "list", "--python", temp_dir, "--format=json"]
        )

        if list_result.returncode != 0:
            raise PyTorchProbeError(
                f"Failed to list packages: {list_result.stderr}"
            )

        # 4. Parse JSON output and append backend suffix
        # uv pip list doesn't include local version suffix (+cuXXX), so we add it
        packages = json.loads(list_result.stdout)
        versions = {}

        for pkg in packages:
            name = pkg.get("name", "").lower()
            if name in ("torch", "torchvision", "torchaudio"):
                version = pkg.get("version", "")
                # Append backend suffix if not already present
                if version and "+" not in version:
                    version = f"{version}+{backend}"
                versions[name] = version

        if not versions:
            raise PyTorchProbeError("No PyTorch packages found after install")

        # 5. Cache the results
        cache = PyTorchVersionCache(workspace_path)
        cache.set_versions(python_version, backend, versions)

        logger.info(f"Probed PyTorch versions: torch={versions.get('torch')}")

        return versions

    finally:
        # 6. Clean up temp directory
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up temp dir {temp_dir}: {e}")
