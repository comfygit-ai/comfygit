"""Common CLI output utilities for consistent messaging."""

import sys
from typing import Optional


def print_success(message: str) -> None:
    """Print a success message with checkmark.

    Args:
        message: Success message to display
    """
    print(f"✓ {message}")


def print_error(message: str, file=sys.stderr) -> None:
    """Print an error message with X mark.

    Args:
        message: Error message to display
        file: Output file (defaults to stderr)
    """
    print(f"✗ {message}", file=file)


def print_warning(message: str) -> None:
    """Print a warning message with warning symbol.

    Args:
        message: Warning message to display
    """
    print(f"⚠ {message}")


def print_info(message: str) -> None:
    """Print an info message with info symbol.

    Args:
        message: Info message to display
    """
    print(f"ℹ {message}")


def print_progress(message: str, current: Optional[int] = None, total: Optional[int] = None) -> None:
    """Print a progress message.

    Args:
        message: Progress message to display
        current: Current item number
        total: Total number of items
    """
    if current is not None and total is not None:
        print(f"⟳ [{current}/{total}] {message}")
    else:
        print(f"⟳ {message}")


def print_list_item(item: str, indent: int = 2) -> None:
    """Print a list item with bullet point.

    Args:
        item: Item text to display
        indent: Number of spaces to indent
    """
    print(f"{' ' * indent}• {item}")


def print_section_header(title: str) -> None:
    """Print a section header.

    Args:
        title: Section title
    """
    print(f"\n{title}")
    print("=" * len(title))


def print_subsection_header(title: str) -> None:
    """Print a subsection header.

    Args:
        title: Subsection title
    """
    print(f"\n{title}")
    print("-" * len(title))


def print_key_value(key: str, value: str, indent: int = 0) -> None:
    """Print a key-value pair.

    Args:
        key: The key/label
        value: The value
        indent: Number of spaces to indent
    """
    print(f"{' ' * indent}{key}: {value}")


def print_separator(char: str = "─", length: int = 60) -> None:
    """Print a visual separator line.

    Args:
        char: Character to use for separator
        length: Length of separator line
    """
    print(char * length)