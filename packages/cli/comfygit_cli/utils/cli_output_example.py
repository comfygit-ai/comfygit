"""Example of refactored code using cli_output utilities.

This file demonstrates how to refactor existing print statements
to use the new centralized output utilities.
"""

import sys
from .cli_output import print_success, print_error, print_warning, print_info


# BEFORE: Direct print statements scattered throughout code
def old_probe_backend(backend: str) -> None:
    """Example of old style with direct print statements."""
    print("⚠️  No PyTorch backend configured. Auto-detecting...")
    print(f"✓ Backend detected and saved: {backend}")
    print("   To change: cg env-config torch-backend set <backend>")


# AFTER: Using centralized output utilities
def new_probe_backend(backend: str) -> None:
    """Example of new style using cli_output utilities."""
    print_warning("No PyTorch backend configured. Auto-detecting...")
    print_success(f"Backend detected and saved: {backend}")
    print_info("To change: cg env-config torch-backend set <backend>")


# BEFORE: Error handling with direct prints
def old_error_handling():
    """Example of old error handling pattern."""
    try:
        # Some operation
        pass
    except Exception as e:
        print(f"✗ Error probing PyTorch backend: {e}")
        print("   Try setting it explicitly: cg env-config torch-backend set <backend>")
        sys.exit(1)


# AFTER: Using centralized error utilities
def new_error_handling():
    """Example of new error handling pattern."""
    try:
        # Some operation
        pass
    except Exception as e:
        print_error(f"Error probing PyTorch backend: {e}")
        print_info("Try setting it explicitly: cg env-config torch-backend set <backend>")
        sys.exit(1)