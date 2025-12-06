"""Dev CLI command handlers.

Commands for setting up development mode with local package paths.
"""

import argparse
import json
import os
import subprocess
from pathlib import Path

DEV_CONFIG_PATH = Path.home() / ".config" / "comfygit" / "deploy" / "dev.json"


def load_dev_config() -> dict:
    """Load dev config from disk."""
    if not DEV_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(DEV_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


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
    """Handle 'dev patch' command - patch existing environments with dev core."""
    config = load_dev_config()
    core_path = config.get("core_path")

    if not core_path:
        print("No dev core path configured.")
        print("Run: cg-deploy dev setup --core PATH")
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

    print(f"Patching {len(envs)} environment(s) with dev core: {core_path}")
    print()

    for env_path in envs:
        env_name = env_path.name
        venv_python = env_path / ".venv" / "bin" / "python"

        if not venv_python.exists():
            print(f"  {env_name}: skipped (no .venv)")
            continue

        # Install editable
        cmd = ["uv", "pip", "install", "-e", core_path, "--python", str(venv_python)]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"  {env_name}: patched")
        else:
            print(f"  {env_name}: failed - {result.stderr.strip()[:60]}")

    print()
    print("Done. Restart any running ComfyUI instances to use dev core.")

    return 0
