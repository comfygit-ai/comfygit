"""Test fixtures for comfygit-deploy."""

from pathlib import Path

import pytest


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory for testing."""
    config_dir = tmp_path / ".config" / "comfygit" / "deploy"
    config_dir.mkdir(parents=True)
    return config_dir
