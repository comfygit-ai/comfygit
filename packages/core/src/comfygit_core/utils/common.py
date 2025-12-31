"""Common utilities for ComfyUI Environment Capture."""

import re
import subprocess
from pathlib import Path

from ..logging.logging_config import get_logger
from ..models.exceptions import CDProcessError

logger = get_logger(__name__)


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int | None = 30,
    capture_output: bool = True,
    text: bool = True,
    check: bool = False,
    env: dict | None = None
) -> subprocess.CompletedProcess:
    """Run a subprocess command with proper error handling.

    Args:
        cmd: Command and arguments as a list
        cwd: Working directory for the command
        timeout: Command timeout in seconds
        capture_output: Whether to capture stdout/stderr
        text: Whether to decode output as text
        check: Whether to raise exception on non-zero exit code
        env: Environment variables to pass to subprocess

    Returns:
        CompletedProcess instance

    Raises:
        CDProcessError: If command fails and check=True
        subprocess.TimeoutExpired: If command times out
    """
    try:
        logger.debug(f"Running command: {' '.join(cmd)}")
        if cwd:
            logger.debug(f"Working directory: {cwd}")

        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            check=check,
            timeout=timeout,
            capture_output=capture_output,
            text=text,
            env=env
        )

        return result

    except subprocess.CalledProcessError as e:
        # Transform CalledProcessError into our custom exception
        error_msg = f"Command failed with exit code {e.returncode}: {' '.join(cmd)}"
        if e.stderr:
            error_msg += f"\nStderr: {e.stderr}"
        logger.error(error_msg)
        raise CDProcessError(
            message=error_msg,
            command=cmd,
            stderr=e.stderr,
            stdout=e.stdout,
            returncode=e.returncode
        )
    except subprocess.TimeoutExpired:
        error_msg = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        logger.error(error_msg)
        # Let TimeoutExpired propagate - it's specific and useful
        raise
    except Exception as e:
        error_msg = f"Error running command {' '.join(cmd)}: {e}"
        logger.error(error_msg)
        raise

def format_size(size_bytes: int) -> str:
    """Format a size in bytes as human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 MB")
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)

    # Calculate the appropriate unit index
    size_index = 0
    while size >= 1024.0 and size_index < len(size_names) - 1:
        size /= 1024.0
        size_index += 1

    # Format with no decimal places for bytes, 1 decimal place for larger units
    format_str = f"{int(size)}" if size_index == 0 else f"{size:.1f}"
    return f"{format_str} {size_names[size_index]}"


def _log_file_content(
    file_path: Path,
    file_type: str,
    context: str = "",
    max_lines: int | None = None,
    preview_lines: tuple[int, int] = (30, 5),
    count_non_empty: bool = False,
) -> None:
    """Generic function to log file content with formatting.

    Args:
        file_path: Path to the file
        file_type: Description of the file type (e.g., "pyproject.toml", "requirements")
        context: Optional context string for the log message
        max_lines: Maximum lines to show (None means show all)
        preview_lines: Tuple of (head_lines, tail_lines) for preview mode
        count_non_empty: If True, count non-comment, non-empty lines
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        # Count meaningful lines if requested
        package_count_msg = ""
        if count_non_empty:
            package_lines = [l for l in lines if l.strip() and not l.strip().startswith('#')]
            package_count_msg = f" ({len(package_lines)} packages)"

        # Create the header
        separator = '=' * 60 if count_non_empty else '-' * 60
        if context:
            header = f"{context}{package_count_msg}:"
        else:
            header = f"{file_type} content{package_count_msg}:"

        msg_lines = [header, separator]

        # Handle line limiting
        if max_lines and len(lines) > max_lines:
            head_count, tail_count = preview_lines
            msg_lines.extend(lines[:head_count])
            msg_lines.append(f"... ({len(lines) - head_count - tail_count} more lines) ...")
            msg_lines.extend(lines[-tail_count:])
        else:
            msg_lines.extend(lines)

        msg_lines.append(separator)
        logger.info('\n'.join(msg_lines))
    except Exception as e:
        logger.debug(f"Could not log {file_type}: {e}")


def log_pyproject_content(pyproject_path: Path, context: str = "") -> None:
    """Log pyproject.toml content in a nicely formatted way.

    Args:
        pyproject_path: Path to pyproject.toml file
        context: Optional context string for the log message
    """
    _log_file_content(pyproject_path, "pyproject.toml", context)

def log_requirements_content(requirements_file: Path, show_all: bool = True) -> None:
    """Log the compiled requirements file content.

    Args:
        requirements_file: Path to the compiled requirements file
        show_all: If True, show all lines, otherwise show a summary
    """
    _log_file_content(
        requirements_file,
        file_type="requirements",
        context="Compiled requirements file",
        max_lines=50 if not show_all else None,
        preview_lines=(30, 5),
        count_non_empty=True
    )
