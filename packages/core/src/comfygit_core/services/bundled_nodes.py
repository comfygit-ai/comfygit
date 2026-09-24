"""Portable bundled-node source and managed runtime copies (no provider policy)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from ..models.shared import NodeInfo

IGNORED_DIRECTORIES = frozenset(
    {".git", "__pycache__", ".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
)
MAX_FILES = 20000
MAX_BYTES = 256 * 1024 * 1024


def validate_node_name(name: str) -> None:
    """Require one portable path component, without excluding ordinary spaces."""
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if (
        not name
        or name.split(".")[0].upper() in reserved
        or name in {".", ".."}
        or any(c in name for c in '/\\\x00:<>"|?*')
        or name.endswith((".", " "))
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError(f"Unsafe custom-node name: {name!r}")


def validate_bundle_path(value: str | None) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Bundled node requires bundle_path")
    parts = value.split("/")
    if (
        PureWindowsPath(value).drive
        or PurePosixPath(value).is_absolute()
        or "\\" in value
        or "\x00" in value
        or len(parts) < 2
        or parts[0] != "bundled_nodes"
        or any(p in {"", ".", ".."} for p in parts)
    ):
        raise ValueError(f"Unsafe bundle_path: {value!r}")
    for part in parts:
        validate_node_name(part)
    return value


@dataclass(frozen=True)
class BundleSnapshot:
    root: Path
    files: tuple[str, ...]
    digest: str


def snapshot_directory(root: Path) -> BundleSnapshot:
    """Validate and hash a portable file set without importing custom code."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Bundled node directory is missing or a symlink: {root}")
    files: list[str] = []
    total = 0
    digest = hashlib.sha256()

    def fail_walk(error: OSError) -> None:
        raise error

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=fail_walk):
        parent = Path(directory)
        visible = [
            n
            for n in dirs + names
            if n not in IGNORED_DIRECTORIES and not n.endswith((".pyc", ".pyo"))
        ]
        if len({n.casefold() for n in visible}) != len(visible):
            raise ValueError(f"Bundled node contains case-colliding paths: {parent}")
        for name in sorted(visible):
            validate_node_name(name)
            item = parent / name
            if item.is_symlink() or not (item.is_file() or item.is_dir()):
                raise ValueError(f"Bundled node contains a link or special file: {item}")
        dirs[:] = sorted(
            d for d in dirs if d not in IGNORED_DIRECTORIES and not d.endswith((".pyc", ".pyo"))
        )
        for name in sorted(names):
            if name.endswith((".pyc", ".pyo")) or name in IGNORED_DIRECTORIES:
                continue
            item = parent / name
            total += item.stat().st_size
            if len(files) >= MAX_FILES or total > MAX_BYTES:
                raise ValueError("Bundled node exceeds portable file/size limits")
            relative = item.relative_to(root).as_posix()
            digest.update(relative.encode() + b"\x00")
            digest.update(b"x" if item.stat().st_mode & 0o111 else b"-")
            with item.open("rb") as stream:
                file_hash = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    file_hash.update(chunk)
                content = file_hash.digest()
            digest.update(content)
            files.append(relative)
    if "__init__.py" not in files:
        raise ValueError(f"Bundled node has no __init__.py: {root}")
    return BundleSnapshot(root, tuple(files), digest.hexdigest())


def resolve_bundle_path(manifest_root: Path, bundle_path: str | None) -> Path:
    relative = validate_bundle_path(bundle_path)
    root = manifest_root.resolve()
    source = root
    for part in relative.split("/"):
        source = source / part
        if source.is_symlink():
            raise ValueError(f"Bundled node source contains a symlink: {source}")
    if not source.resolve().is_relative_to(root):
        raise ValueError("Bundled node source escapes the manifest")
    return source


def source_snapshot(manifest_root: Path, node: NodeInfo) -> BundleSnapshot:
    validate_node_name(node.name)
    return snapshot_directory(resolve_bundle_path(manifest_root, node.bundle_path))


def copy_snapshot(snapshot: BundleSnapshot, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    try:
        for relative in snapshot.files:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot.root / relative, target)
        if snapshot_directory(destination).digest != snapshot.digest:
            raise ValueError("Bundled node source changed while copying")
    except BaseException:
        shutil.rmtree(destination)
        raise


def _state_path(custom_nodes: Path) -> Path:
    return custom_nodes.parent.parent / ".bundled-node-state.json"


def read_state(custom_nodes: Path) -> dict[str, dict[str, str]]:
    path = _state_path(custom_nodes)
    if path.is_symlink():
        raise ValueError("Bundled-node state may not be a symlink")
    if not path.exists():
        return {}
    state = json.loads(path.read_text())
    if not isinstance(state, dict) or any(not isinstance(v, dict) for v in state.values()):
        raise ValueError("Invalid bundled-node runtime state")
    return state


def write_state(custom_nodes: Path, state: dict[str, dict[str, str]]) -> None:
    path = _state_path(custom_nodes)
    if path.is_symlink():
        raise ValueError("Bundled-node state may not be a symlink")
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(state, stream)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def install_bundle(manifest_root: Path, custom_nodes: Path, node: NodeInfo) -> bool:
    """Install/update a managed copy; preserve conflicting runtime edits."""
    snapshot = source_snapshot(manifest_root, node)
    if custom_nodes.is_symlink():
        raise ValueError("custom_nodes may not be a symlink for bundle installation")
    custom_nodes.mkdir(parents=True, exist_ok=True)
    target = custom_nodes / node.name
    disabled = custom_nodes / f"{node.name}.disabled"
    if not target.exists() and not target.is_symlink() and disabled.exists():
        if disabled.is_symlink():
            raise ValueError("Disabled bundled node may not be a symlink")
        disabled.rename(target)
    state = read_state(custom_nodes)
    previous = state.get(node.name, {})
    if target.exists() or target.is_symlink():
        current = snapshot_directory(target).digest
        if current == snapshot.digest:
            state[node.name] = {**previous, "installed_digest": current}
            write_state(custom_nodes, state)
            return False
        if current != previous.get("installed_digest"):
            raise ValueError(
                f"Bundled node {node.name!r} has conflicting runtime edits; edit its authored bundle instead"
            )
    with tempfile.TemporaryDirectory(prefix=".cg-bundle-", dir=custom_nodes.parent) as tmp:
        staged, backup = Path(tmp) / "new", Path(tmp) / "old"
        copy_snapshot(snapshot, staged)
        if target.exists():
            target.rename(backup)
        try:
            staged.rename(target)
            state[node.name] = {**previous, "installed_digest": snapshot.digest}
            write_state(custom_nodes, state)
        except BaseException:
            if target.exists():
                shutil.rmtree(target)
            if backup.exists():
                backup.rename(target)
            raise
    return True


def copy_declared_bundles(
    manifest_root: Path, destination: Path, nodes: dict[str, NodeInfo]
) -> None:
    validate_node_destinations(nodes.values())
    copied: set[str] = set()
    for node in nodes.values():
        if node.source != "bundled":
            continue
        try:
            snapshot = source_snapshot(manifest_root, node)
        except ValueError:
            if node.criticality == "optional":
                continue
            raise
        relative = validate_bundle_path(node.bundle_path)
        if relative not in copied:
            copy_snapshot(snapshot, resolve_bundle_path(destination, relative))
            copied.add(relative)


def validate_node_destinations(nodes: Iterable[NodeInfo]) -> None:
    """Reject ambiguous runtime targets before any reconciliation writes."""
    destinations: set[str] = set()
    for node in nodes:
        validate_node_name(node.name)
        key = node.name.casefold()
        if key in destinations:
            raise ValueError(f"Conflicting custom-node destination: {node.name}")
        destinations.add(key)


def assert_clean_runtime_copy(custom_nodes: Path, name: str) -> None:
    """Preserve edits when a previously managed bundle is removed by reconciliation."""
    previous = read_state(custom_nodes).get(name)
    if previous and snapshot_directory(custom_nodes / name).digest != previous.get(
        "installed_digest"
    ):
        raise ValueError(
            f"Bundled node {name!r} has conflicting runtime edits; preserve them before removal"
        )


def forget_runtime_copy(custom_nodes: Path, name: str) -> None:
    state = read_state(custom_nodes)
    if name in state:
        del state[name]
        write_state(custom_nodes, state)
