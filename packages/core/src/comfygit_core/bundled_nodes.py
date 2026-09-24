"""Public portable-source inventory validation for provider build planners.

Providers supply metadata from a complete, immutable source tree. Core owns
path, file-kind and size rules; installation still validates the actual bytes.
"""

from dataclasses import dataclass

from .services.bundled_nodes import (
    IGNORED_DIRECTORIES,
    MAX_BYTES,
    MAX_FILES,
    validate_bundle_path,
    validate_node_name,
)


@dataclass(frozen=True)
class BundleEntry:
    path: str
    kind: str  # file, directory, symlink, or unsupported
    size_bytes: int = 0


@dataclass(frozen=True)
class BundleInventory:
    revision: str
    entries: tuple[BundleEntry, ...]
    complete: bool = True


def validate_bundle_inventory(bundle_path: str, inventory: BundleInventory) -> int:
    """Return portable file count, or reject incomplete/unsafe/missing source."""
    relative = validate_bundle_path(bundle_path)
    if not inventory.complete or not inventory.revision:
        raise ValueError("Bundled source inventory must be complete and revision-bound")
    files = set()
    paths = set()
    size = 0
    ancestors = {"/".join(relative.split("/")[:i]) for i in range(1, len(relative.split("/")) + 1)}
    for entry in inventory.entries:
        if entry.path in ancestors and entry.kind != "directory":
            raise ValueError("Bundled source has a non-directory ancestor")
        if not entry.path.startswith(relative + "/"):
            continue
        local = entry.path[len(relative) + 1 :]
        parts = local.split("/")
        if any(
            part in IGNORED_DIRECTORIES or part.endswith((".pyc", ".pyo")) for part in parts
        ) or local.endswith((".pyc", ".pyo")):
            continue
        for part in parts:
            validate_node_name(part)
        key = local.casefold()
        if key in paths:
            raise ValueError("Bundled source contains duplicate or case-colliding paths")
        paths.add(key)
        if entry.kind == "directory":
            continue
        if entry.kind != "file" or entry.size_bytes < 0:
            raise ValueError("Bundled source contains a link or unsupported file")
        files.add(local)
        size += entry.size_bytes
        if len(files) > MAX_FILES or size > MAX_BYTES:
            raise ValueError("Bundled source exceeds portable file/size limits")
    if "__init__.py" not in files:
        raise ValueError("Bundled source is missing __init__.py at the selected revision")
    return len(files)


__all__ = ["BundleEntry", "BundleInventory", "validate_bundle_inventory"]
