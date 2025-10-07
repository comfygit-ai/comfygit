"""Tests for UV error handling and logging."""

import logging
from unittest.mock import Mock, MagicMock
import pytest

from comfydock_core.models.exceptions import UVCommandError


class TestUVErrorHandling:
    """Test UV error extraction and logging."""

    def test_extract_error_hint_from_stderr_simple(self):
        """Test extracting error hint from simple UV stderr."""
        # Arrange
        stderr = """
Resolved 5 packages in 123ms
error: Package 'foo' conflicts with package 'bar'
        """

        # Act
        from comfydock_core.utils.uv_error_handler import extract_uv_error_hint
        hint = extract_uv_error_hint(stderr)

        # Assert
        assert hint == "error: Package 'foo' conflicts with package 'bar'"

    def test_extract_error_hint_from_stderr_multiline(self):
        """Test extracting error hint from multi-line UV stderr with conflict keyword."""
        # Arrange
        stderr = """
Resolved 10 packages in 456ms
  × No solution found when resolving dependencies:
  ╰─▶ Because torch==2.0.0 depends on numpy>=1.20 and you require torch==2.0.0,
      numpy>=1.20 is required.
      And because opencv-python==4.8.0 depends on numpy<1.20 and you require opencv-python==4.8.0,
      we can conclude that your requirements are unsatisfiable.

  hint: Pre-releases are available for numpy in the requested range
        """

        # Act
        from comfydock_core.utils.uv_error_handler import extract_uv_error_hint
        hint = extract_uv_error_hint(stderr)

        # Assert - Should find the dependency conflict line
        assert "numpy" in hint.lower() or "opencv" in hint.lower() or "unsatisfiable" in hint.lower()

    def test_extract_error_hint_no_keywords(self):
        """Test extracting error hint when no error/conflict keywords found."""
        # Arrange
        stderr = """
Some output line 1
Some output line 2
Final important line
        """

        # Act
        from comfydock_core.utils.uv_error_handler import extract_uv_error_hint
        hint = extract_uv_error_hint(stderr)

        # Assert - Should return last non-empty line
        assert hint == "Final important line"

    def test_extract_error_hint_empty_stderr(self):
        """Test extracting error hint from empty stderr."""
        # Arrange
        stderr = ""

        # Act
        from comfydock_core.utils.uv_error_handler import extract_uv_error_hint
        hint = extract_uv_error_hint(stderr)

        # Assert
        assert hint is None

    def test_log_uv_error_details(self, caplog):
        """Test that UV error details are logged completely."""
        # Arrange
        caplog.set_level(logging.ERROR)

        error = UVCommandError(
            message="UV command failed with code 1",
            command=["uv", "sync", "--all-groups"],
            stderr="error: Package conflict detected\ndetailed error info here",
            stdout="Some stdout output",
            returncode=1
        )

        # Act
        from comfydock_core.utils.uv_error_handler import log_uv_error
        logger = logging.getLogger("test_logger")
        log_uv_error(logger, error, "test-node")

        # Assert - Check that all details are logged
        logged_output = caplog.text
        assert "test-node" in logged_output
        assert "uv sync --all-groups" in logged_output
        assert "Return code: 1" in logged_output
        assert "Package conflict detected" in logged_output
        assert "Some stdout output" in logged_output

    def test_format_uv_error_for_user(self):
        """Test formatting UV error for user display."""
        # Arrange
        error = UVCommandError(
            message="UV command failed with code 1",
            command=["uv", "sync"],
            stderr="error: Package 'foo' conflicts with 'bar'\nAdditional context here",
            stdout="",
            returncode=1
        )

        # Act
        from comfydock_core.utils.uv_error_handler import format_uv_error_for_user
        user_message = format_uv_error_for_user(error)

        # Assert
        assert "UV dependency resolution failed" in user_message or "dependency" in user_message.lower()
        # Should include hint but truncated
        assert "foo" in user_message or "conflict" in user_message.lower()

    def test_handle_uv_error_integration(self, caplog):
        """Test complete UV error handling flow."""
        # Arrange
        caplog.set_level(logging.ERROR)
        logger = logging.getLogger("test_integration")

        error = UVCommandError(
            message="UV command failed with code 1",
            command=["uv", "add", "conflicting-package"],
            stderr="""
Resolved 15 packages in 789ms
error: Because package-a==1.0 depends on dep>=2.0 and package-b==1.0 depends on dep<2.0,
       we can conclude that package-a==1.0 and package-b==1.0 are incompatible.
            """,
            stdout="",
            returncode=1
        )

        # Act
        from comfydock_core.utils.uv_error_handler import handle_uv_error
        user_msg, log_complete = handle_uv_error(error, "test-package", logger)

        # Assert
        # User message should be helpful but concise
        assert isinstance(user_msg, str)
        assert len(user_msg) < 200  # Should be brief
        assert "dependency" in user_msg.lower() or "conflict" in user_msg.lower()

        # Should indicate logs have more info
        assert log_complete is True

        # Logger should have captured full details
        logged = caplog.text
        assert "test-package" in logged
        assert "uv add conflicting-package" in logged
        assert "package-a" in logged or "package-b" in logged
