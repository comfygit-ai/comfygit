"""Dev CLI command handlers.

Commands for setting up development mode with local package paths.
"""

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEV_CONFIG_PATH = Path.home() / ".config" / "comfygit" / "deploy" / "dev.json"


@dataclass
class DevNode:
    """A development node configuration."""

    name: str
    path: str


def load_dev_config() -> dict:
    """Load dev config from disk."""
    if not DEV_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(DEV_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def get_dev_nodes() -> list[DevNode]:
    """Get list of configured dev nodes."""
    config = load_dev_config()
    return [DevNode(name=n["name"], path=n["path"]) for n in config.get("dev_nodes", [])]


def save_dev_config(config: dict) -> None:
    """Save dev config to disk."""
    DEV_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEV_CONFIG_PATH.write_text(json.dumps(config, indent=2))


def get_workspace_path() -> Path | None:
    """Get workspace path from env or default."""
    env_home = os.environ.get("COMFYGIT_HOME")
    if env_home:
        return Path(env_home)
    default = Path.home() / "comfygit"
    if default.exists():
        return default
    return None


def handle_setup(args: argparse.Namespace) -> int:
    """Handle 'dev setup' command."""
    config = load_dev_config()

    # Show current config
    if args.show:
        if not config:
            print("No dev config set.")
        else:
            print("Dev config:")
            if config.get("core_path"):
                print(f"  Core: {config['core_path']}")
            if config.get("manager_path"):
                print(f"  Manager: {config['manager_path']}")
            dev_nodes = config.get("dev_nodes", [])
            if dev_nodes:
                print(f"  Dev nodes ({len(dev_nodes)}):")
                for node in dev_nodes:
                    print(f"    - {node['name']}: {node['path']}")
        return 0

    # Clear config
    if args.clear:
        # Also restore manager symlink to original
        workspace = get_workspace_path()
        if workspace and config.get("manager_path"):
            manager_link = workspace / ".metadata" / "system_nodes" / "comfygit-manager"
            if manager_link.is_symlink():
                manager_link.unlink()
                print(f"Removed dev manager symlink: {manager_link}")
                print("Run 'cg init' or manually clone the manager to restore.")

        if DEV_CONFIG_PATH.exists():
            DEV_CONFIG_PATH.unlink()
        print("Dev config cleared.")
        return 0

    # Validate and set paths
    if args.core:
        core_path = Path(args.core).resolve()
        if not (core_path / "pyproject.toml").exists():
            print(f"Error: Not a valid package path: {core_path}")
            print("  Expected pyproject.toml in the directory.")
            return 1
        config["core_path"] = str(core_path)
        print(f"Core path: {core_path}")

    if args.manager:
        manager_path = Path(args.manager).resolve()
        if not (manager_path / "__init__.py").exists() and not (manager_path / "server").exists():
            print(f"Error: Not a valid manager path: {manager_path}")
            return 1
        config["manager_path"] = str(manager_path)
        print(f"Manager path: {manager_path}")

        # Symlink manager to system_nodes
        workspace = get_workspace_path()
        if workspace:
            system_nodes = workspace / ".metadata" / "system_nodes"
            system_nodes.mkdir(parents=True, exist_ok=True)
            manager_link = system_nodes / "comfygit-manager"

            # Remove existing (whether symlink or directory)
            if manager_link.is_symlink():
                manager_link.unlink()
            elif manager_link.is_dir():
                import shutil
                shutil.rmtree(manager_link)

            manager_link.symlink_to(manager_path)
            print(f"Symlinked: {manager_link} -> {manager_path}")

    if not args.core and not args.manager:
        print("Usage: cg-deploy dev setup --core PATH --manager PATH")
        print("       cg-deploy dev setup --show")
        print("       cg-deploy dev setup --clear")
        return 0

    save_dev_config(config)
    print()
    print("Dev mode configured!")
    print()
    print("Start worker with dev paths:")
    if config.get("core_path"):
        print(f"  cg-deploy worker up --dev-core {config['core_path']}")
    print()
    print("Or set environment variable:")
    if config.get("core_path"):
        print(f"  export COMFYGIT_DEV_CORE_PATH={config['core_path']}")

    return 0


def handle_patch(args: argparse.Namespace) -> int:
    """Handle 'dev patch' command - patch existing environments with dev config."""
    config = load_dev_config()
    core_path = config.get("core_path")
    dev_nodes = config.get("dev_nodes", [])

    if not core_path and not dev_nodes:
        print("No dev config found.")
        print("Run: cg-deploy dev setup --core PATH")
        print("     cg-deploy dev add-node NAME PATH")
        return 1

    workspace = get_workspace_path()
    if not workspace:
        print("No workspace found. Set COMFYGIT_HOME or run 'cg init'.")
        return 1

    envs_dir = workspace / "environments"
    if not envs_dir.exists():
        print("No environments found.")
        return 0

    # Find environments to patch
    if args.env:
        envs = [envs_dir / args.env]
        if not envs[0].exists():
            print(f"Environment not found: {args.env}")
            return 1
    else:
        envs = [e for e in envs_dir.iterdir() if e.is_dir() and (e / ".venv").exists()]

    if not envs:
        print("No environments with .venv found.")
        return 0

    print(f"Patching {len(envs)} environment(s):")
    if core_path:
        print(f"  - dev core: {core_path}")
    for node in dev_nodes:
        print(f"  - dev node: {node['name']} -> {node['path']}")
    print()

    for env_path in envs:
        env_name = env_path.name
        venv_python = env_path / ".venv" / "bin" / "python"

        if not venv_python.exists():
            print(f"  {env_name}: skipped (no .venv)")
            continue

        success = True

        # Patch core if configured
        if core_path:
            cmd = ["uv", "pip", "install", "-e", core_path, "--python", str(venv_python)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  {env_name}: core failed - {result.stderr.strip()[:60]}")
                success = False

        # Apply dev nodes
        for node in dev_nodes:
            node_result = _apply_dev_node_to_env(env_path, node["name"], node["path"], workspace)
            if not node_result:
                print(f"  {env_name}: node {node['name']} failed")
                success = False

        if success:
            print(f"  {env_name}: patched")

    print()
    print("Done. Restart any running ComfyUI instances to apply changes.")

    return 0


def _apply_dev_node_to_env(env_path: Path, node_name: str, node_path: str, workspace: Path) -> bool:
    """Apply a dev node to an environment (symlink + track).

    Args:
        env_path: Path to the environment
        node_name: Name of the node
        node_path: Path to the dev node source
        workspace: Workspace path

    Returns:
        True if successful
    """
    import shutil

    custom_nodes = env_path / "ComfyUI" / "custom_nodes"
    if not custom_nodes.exists():
        return False

    target = custom_nodes / node_name
    source = Path(node_path)

    # Create/update symlink
    if target.is_symlink():
        if target.resolve() == source.resolve():
            # Already correct
            pass
        else:
            target.unlink()
            target.symlink_to(source)
    elif target.exists():
        # Regular directory exists - replace with symlink
        shutil.rmtree(target)
        target.symlink_to(source)
    else:
        target.symlink_to(source)

    # Track with cg node add --dev
    env = os.environ.copy()
    env["COMFYGIT_HOME"] = str(workspace)

    cmd = ["cg", "-e", env_path.name, "node", "add", node_name, "--dev"]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    # Success if tracked or already tracked
    return result.returncode == 0 or "already tracked" in result.stderr.lower()


def handle_add_node(args: argparse.Namespace) -> int:
    """Handle 'dev add-node' command."""
    config = load_dev_config()

    node_name = args.name
    node_path = Path(args.path).resolve()

    # Validate path
    if not node_path.is_dir():
        print(f"Error: Path does not exist: {node_path}")
        return 1

    # Check for __init__.py or common node indicators
    has_init = (node_path / "__init__.py").exists()
    has_nodes = (node_path / "nodes.py").exists() or (node_path / "nodes").exists()
    if not has_init and not has_nodes:
        print(f"Warning: {node_path} doesn't look like a ComfyUI node (no __init__.py or nodes.py)")

    # Add to dev_nodes list
    dev_nodes = config.get("dev_nodes", [])

    # Check if already exists
    existing = next((n for n in dev_nodes if n["name"] == node_name), None)
    if existing:
        existing["path"] = str(node_path)
        print(f"Updated dev node: {node_name} -> {node_path}")
    else:
        dev_nodes.append({"name": node_name, "path": str(node_path)})
        print(f"Added dev node: {node_name} -> {node_path}")

    config["dev_nodes"] = dev_nodes
    save_dev_config(config)

    print()
    print("To apply to existing environments:")
    print("  cg-deploy dev patch")
    print()
    print("New instances created with --dev will include this node.")

    return 0


def handle_remove_node(args: argparse.Namespace) -> int:
    """Handle 'dev remove-node' command."""
    config = load_dev_config()
    node_name = args.name

    dev_nodes = config.get("dev_nodes", [])
    original_len = len(dev_nodes)

    dev_nodes = [n for n in dev_nodes if n["name"] != node_name]

    if len(dev_nodes) == original_len:
        print(f"Dev node not found: {node_name}")
        return 1

    config["dev_nodes"] = dev_nodes
    save_dev_config(config)

    print(f"Removed dev node: {node_name}")
    print("Note: Existing symlinks in environments are not removed.")

    return 0


def handle_list_nodes(args: argparse.Namespace) -> int:
    """Handle 'dev list-nodes' command."""
    config = load_dev_config()
    dev_nodes = config.get("dev_nodes", [])

    if not dev_nodes:
        print("No dev nodes configured.")
        print()
        print("Add a dev node:")
        print("  cg-deploy dev add-node NAME PATH")
        return 0

    print(f"Dev nodes ({len(dev_nodes)}):")
    for node in dev_nodes:
        path = Path(node["path"])
        exists = "✓" if path.exists() else "✗"
        print(f"  {exists} {node['name']}: {node['path']}")

    return 0
