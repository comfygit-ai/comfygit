"""Test for is_legacy_manager method."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from comfygit_core.core.environment import Environment
from comfygit_core.constants import MANAGER_NODE_ID


def test_is_legacy_manager_with_tracked_node():
    """Test that is_legacy_manager returns False when manager is tracked in pyproject."""
    env = MagicMock(spec=Environment)
    env.pyproject = MagicMock()
    env.pyproject.nodes.get_existing.return_value = {
        MANAGER_NODE_ID: {"url": "https://example.com", "version": "1.0.0"}
    }

    # Use real method bound to mock
    result = Environment.is_legacy_manager(env)

    assert result is False
    env.pyproject.nodes.get_existing.assert_called_once()


def test_is_legacy_manager_with_symlink():
    """Test that is_legacy_manager returns True when manager is symlinked."""
    env = MagicMock(spec=Environment)
    env.pyproject = MagicMock()
    env.pyproject.nodes.get_existing.return_value = {}  # No tracked nodes
    env.custom_nodes_path = Path("/fake/custom_nodes")

    with patch("comfygit_core.core.environment.is_link", return_value=True):
        # Use real method bound to mock
        result = Environment.is_legacy_manager(env)

    assert result is True


def test_is_legacy_manager_with_no_manager():
    """Test that is_legacy_manager returns False when no manager exists."""
    env = MagicMock(spec=Environment)
    env.pyproject = MagicMock()
    env.pyproject.nodes.get_existing.return_value = {}  # No tracked nodes
    env.custom_nodes_path = Path("/fake/custom_nodes")

    with patch("comfygit_core.core.environment.is_link", return_value=False):
        # Use real method bound to mock
        result = Environment.is_legacy_manager(env)

    assert result is False