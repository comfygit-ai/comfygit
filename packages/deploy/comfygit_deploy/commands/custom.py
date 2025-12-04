"""Custom worker CLI command handlers.

Commands for managing connections to self-hosted workers.
"""

import argparse
import asyncio
from typing import Any

from ..config import DeployConfig
from ..providers.custom import CustomWorkerClient


def test_worker_connection(host: str, port: int, api_key: str) -> dict[str, Any]:
    """Test connection to a worker (sync wrapper)."""
    async def _test():
        client = CustomWorkerClient(host=host, port=port, api_key=api_key)
        return await client.test_connection()

    return asyncio.run(_test())


def deploy_to_worker(
    host: str,
    port: int,
    api_key: str,
    import_source: str,
    name: str | None = None,
    branch: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Deploy to a worker (sync wrapper)."""
    async def _deploy():
        client = CustomWorkerClient(host=host, port=port, api_key=api_key)
        return await client.create_instance(
            import_source=import_source,
            name=name,
            branch=branch,
            mode=mode,
        )

    return asyncio.run(_deploy())


def handle_add(args: argparse.Namespace) -> int:
    """Handle 'custom add' command."""
    if not args.host and not args.discovered:
        print("Error: --host is required (or use --discovered)")
        return 1

    if args.discovered:
        # TODO: Load from last scan results
        print("Error: --discovered not yet implemented")
        return 1

    if not args.api_key:
        print("Error: --api-key is required")
        return 1

    config = DeployConfig()
    config.add_worker(args.name, args.host, args.port, args.api_key)
    config.save()

    print(f"Added worker '{args.name}'")
    print(f"  Host: {args.host}:{args.port}")

    return 0


def handle_remove(args: argparse.Namespace) -> int:
    """Handle 'custom remove' command."""
    config = DeployConfig()

    if not config.remove_worker(args.name):
        print(f"Error: Worker '{args.name}' not found")
        return 1

    config.save()
    print(f"Removed worker '{args.name}'")
    return 0


def handle_list(args: argparse.Namespace) -> int:
    """Handle 'custom list' command."""
    config = DeployConfig()
    workers = config.workers

    if not workers:
        print("No workers registered.")
        print("Use 'cg-deploy custom add' to register a worker.")
        return 0

    print("Registered workers:")
    for name, info in workers.items():
        host = info.get("host", "?")
        port = info.get("port", "?")
        mode = info.get("mode", "docker")
        print(f"  {name}: {host}:{port} ({mode})")

    return 0


def handle_test(args: argparse.Namespace) -> int:
    """Handle 'custom test' command."""
    config = DeployConfig()
    worker = config.get_worker(args.name)

    if not worker:
        print(f"Error: Worker '{args.name}' not found")
        return 1

    print(f"Testing connection to '{args.name}'...")

    result = test_worker_connection(
        host=worker["host"],
        port=worker["port"],
        api_key=worker["api_key"],
    )

    if result.get("success"):
        print(f"  Status: OK")
        print(f"  Version: {result.get('worker_version', 'unknown')}")
        return 0
    else:
        print(f"  Status: FAILED")
        print(f"  Error: {result.get('error', 'Unknown error')}")
        return 1


def handle_deploy(args: argparse.Namespace) -> int:
    """Handle 'custom deploy' command."""
    config = DeployConfig()
    worker = config.get_worker(args.worker_name)

    if not worker:
        print(f"Error: Worker '{args.worker_name}' not found")
        return 1

    print(f"Deploying to '{args.worker_name}'...")
    print(f"  Source: {args.import_source}")
    if args.branch:
        print(f"  Branch: {args.branch}")
    print(f"  Mode: {args.mode}")

    try:
        result = deploy_to_worker(
            host=worker["host"],
            port=worker["port"],
            api_key=worker["api_key"],
            import_source=args.import_source,
            name=args.name,
            branch=args.branch,
            mode=args.mode,
        )

        print()
        print("Deployment started!")
        print(f"  Instance ID: {result.get('id')}")
        print(f"  Name: {result.get('name')}")
        print(f"  Port: {result.get('assigned_port')}")
        print(f"  Status: {result.get('status')}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def handle_scan(args: argparse.Namespace) -> int:
    """Handle 'custom scan' command (mDNS discovery)."""
    print(f"Scanning for workers (timeout: {args.timeout}s)...")
    print()
    print("mDNS discovery is planned for Phase 3.")
    print("Use 'cg-deploy custom add' to manually add workers.")
    return 0
