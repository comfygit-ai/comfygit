"""Utilities for handling and formatting UV command errors."""

import logging
from typing import Optional

from ..models.exceptions import UVCommandError


def extract_uv_error_hint(stderr: str) -> Optional[str]:
    """Extract the most useful error hint from UV stderr output.

    UV typically formats errors with:
    - Lines starting with "error:"
    - Lines containing "conflict"
    - Multi-line dependency resolution explanations
    - The final/last non-empty line often contains the key message

    Args:
        stderr: The stderr output from UV command

    Returns:
        Most relevant error line, or None if stderr is empty
    """
    if not stderr or not stderr.strip():
        return None

    lines = [line.strip() for line in stderr.strip().split('\n') if line.strip()]

    if not lines:
        return None

    # Search for lines with error keywords (in reverse - most recent first)
    error_keywords = ['error:', 'conflict', 'unsatisfiable', 'incompatible', 'failed', '× ']

    for line in reversed(lines):
        lower_line = line.lower()
        if any(keyword in lower_line for keyword in error_keywords):
            return line

    # No keyword found - return last non-empty line
    return lines[-1]


def log_uv_error(logger: logging.Logger, error: UVCommandError, context: str) -> None:
    """Log complete UV error details for debugging.

    Logs all available error information:
    - Context (node name, operation, etc.)
    - Command that was executed
    - Return code
    - Full stderr output
    - Full stdout output (if present)

    Args:
        logger: Logger instance to use
        error: The UVCommandError exception
        context: Context string (e.g., node name, operation)
    """
    logger.error(f"UV command failed for '{context}'")

    if error.command:
        logger.error(f"  Command: {' '.join(error.command)}")

    if error.returncode is not None:
        logger.error(f"  Return code: {error.returncode}")

    if error.stderr:
        logger.error(f"  STDERR:\n{error.stderr}")

    if error.stdout:
        logger.error(f"  STDOUT:\n{error.stdout}")


def format_uv_error_for_user(error: UVCommandError, max_hint_length: int = 300) -> str:
    """Format UV error for user-facing display.

    Provides a concise, helpful error message with:
    - Clear error type
    - Truncated error hint from stderr
    - Reference to logs for full details

    Args:
        error: The UVCommandError exception
        max_hint_length: Maximum length for error hint display

    Returns:
        User-friendly error message
    """
    base_msg = "UV dependency resolution failed"

    # Try to extract helpful hint
    if error.stderr:
        hint = extract_uv_error_hint(error.stderr)
        if hint:
            # Truncate if too long
            if len(hint) > max_hint_length:
                hint = hint[:max_hint_length] + "..."
            return f"{base_msg} - {hint}"

    return base_msg


def handle_uv_error(
    error: UVCommandError,
    context: str,
    logger: logging.Logger,
    max_hint_length: int = 300
) -> tuple[str, bool]:
    """Complete UV error handling: log details + return user message.

    This is the main entry point for handling UV errors in the CLI.
    It performs both logging and user message formatting in one call.

    Args:
        error: The UVCommandError exception
        context: Context string (e.g., node name, operation)
        logger: Logger instance to use for detailed logging
        max_hint_length: Maximum length for error hint in user message

    Returns:
        Tuple of (user_message, logs_written)
        - user_message: Brief message to show to user
        - logs_written: True if detailed logs were written
    """
    # Log complete error details
    log_uv_error(logger, error, context)

    # Format user-friendly message
    user_msg = format_uv_error_for_user(error, max_hint_length)

    return user_msg, True
