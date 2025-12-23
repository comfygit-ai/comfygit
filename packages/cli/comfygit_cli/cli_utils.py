"""Utility functions for ComfyGit CLI."""

import sys
from typing import TYPE_CHECKING

from comfygit_core.factories.workspace_factory import WorkspaceFactory
from comfygit_core.models.exceptions import CDWorkspaceNotFoundError
from .logging.environment_logger import WorkspaceLogger

if TYPE_CHECKING:
    from comfygit_core.core.workspace import Workspace

# Track if we've already shown the legacy notice this session
_legacy_notice_shown = False

def get_workspace_or_exit() -> "Workspace":
    """Get workspace or exit with error message."""
    global _legacy_notice_shown

    try:
        workspace = WorkspaceFactory.find()
        # Initialize workspace logging
        WorkspaceLogger.set_workspace_path(workspace.path)

        # Show legacy workspace notice once per session
        if not _legacy_notice_shown and workspace.is_legacy_schema():
            _legacy_notice_shown = True
            print("Legacy workspace detected. Run 'cg -e <ENV> manager update' to migrate.")
            print("")

        return workspace
    except CDWorkspaceNotFoundError:
        print("✗ No workspace initialized. Run 'cg init' first.")
        sys.exit(1)

def get_workspace_optional() -> "Workspace | None":
    """Get workspace if it exists."""
    try:
        workspace = WorkspaceFactory.find()
        # Initialize workspace logging
        WorkspaceLogger.set_workspace_path(workspace.path)
        return workspace
    except CDWorkspaceNotFoundError:
        return None
