"""Instance management CLI command implementations.

Provides unified instance listing and management across RunPod and custom workers.
Instance IDs use namespacing: worker_name:instance_id for custom, plain id for RunPod.
"""

import asyncio
import json
import time
import webbrowser
from argparse import Namespace

from ..config import DeployConfig
from ..providers.custom import CustomWorkerClient, CustomWorkerError
from ..providers.runpod import RunPodAPIError, RunPodClient


def parse_instance_id(instance_id: str) -> tuple[str | None, str]:
    """Parse instance ID into (worker_name, local_id).

    Format: "worker_name:local_id" for custom workers, plain id for RunPod.

    Returns:
        (worker_name, local_id) - worker_name is None for RunPod instances
    """
    if ":" in instance_id:
        worker_name, local_id = instance_id.split(":", 1)
        return worker_name, local_id
    return None, instance_id


def _convert_runpod_to_unified(pod: dict) -> dict:
    """Convert RunPod pod to unified instance format."""
    status_map = {"RUNNING": "running", "EXITED": "stopped", "PENDING": "deploying"}
    return {
        "id": pod.get("id"),
        "provider": "runpod",
        "worker_name": None,
        "name": pod.get("name"),
        "status": status_map.get(pod.get("desiredStatus", ""), pod.get("desiredStatus")),
        "gpu": pod.get("machine", {}).get("gpuDisplayName") if pod.get("machine") else None,
        "cost_per_hour": pod.get("costPerHr", 0),
        "comfyui_url": RunPodClient.get_comfyui_url(pod),
    }


def _convert_worker_to_unified(worker_name: str, instance: dict) -> dict:
    """Convert custom worker instance to unified format with namespaced ID."""
    return {
        "id": f"{worker_name}:{instance.get('id')}",
        "provider": "custom",
        "worker_name": worker_name,
        "name": instance.get("name"),
        "status": instance.get("status"),
        "gpu": None,  # Could be fetched from worker system info if needed
        "cost_per_hour": 0,  # Self-hosted
        "comfyui_url": instance.get("comfyui_url"),
    }


async def _fetch_all_instances(
    config: DeployConfig, provider_filter: str | None
) -> list[dict]:
    """Fetch instances from all configured providers.

    Args:
        config: Deploy configuration
        provider_filter: Optional filter ('runpod' or 'custom')

    Returns:
        List of unified instance dicts
    """
    instances = []

    # Fetch RunPod instances
    if provider_filter in (None, "runpod"):
        api_key = config.runpod_api_key
        if api_key:
            try:
                client = RunPodClient(api_key)
                pods = await client.list_pods()
                instances.extend(_convert_runpod_to_unified(pod) for pod in pods)
            except RunPodAPIError as e:
                print(f"Warning: RunPod error: {e}")

    # Fetch custom worker instances
    if provider_filter in (None, "custom"):
        for worker_name, worker_config in config.workers.items():
            try:
                client = CustomWorkerClient(
                    worker_config["host"],
                    worker_config["port"],
                    worker_config["api_key"],
                )
                worker_instances = await client.list_instances()
                instances.extend(
                    _convert_worker_to_unified(worker_name, inst)
                    for inst in worker_instances
                )
            except Exception:
                # Worker offline or unreachable - skip silently
                pass

    return instances


def handle_instances(args: Namespace) -> int:
    """Handle 'instances' command - list all instances from all providers."""
    config = DeployConfig()
    provider_filter = getattr(args, "provider", None)

    # Check if we have any providers configured
    has_runpod = config.runpod_api_key is not None
    has_workers = len(config.workers) > 0

    if not has_runpod and not has_workers:
        print("No providers configured.")
        print("Run: cg-deploy runpod config --api-key <key>")
        print("  or: cg-deploy custom add <name> --host <ip> --api-key <key>")
        return 1

    # Require RunPod key only if specifically filtering for runpod
    if provider_filter == "runpod" and not has_runpod:
        print("Error: RunPod API key not configured.")
        print("Run: cg-deploy runpod config --api-key <your-key>")
        return 1

    # Fetch all instances
    instances = asyncio.run(_fetch_all_instances(config, provider_filter))

    # Filter by status if requested
    status_filter = getattr(args, "status", None)
    if status_filter:
        instances = [i for i in instances if i.get("status") == status_filter]

    # JSON output
    if getattr(args, "json", False):
        print(json.dumps(instances, indent=2))
        return 0

    if not instances:
        print("No instances found.")
        return 0

    # Table output
    print(f"{'ID':<25} {'Name':<25} {'Provider':<10} {'Status':<10} {'$/hr':>8}")
    print("-" * 80)

    for inst in instances:
        inst_id = inst.get("id", "?")[:25]
        name = (inst.get("name") or "?")[:25]
        provider = inst.get("provider", "?")
        if inst.get("worker_name"):
            provider = inst["worker_name"][:10]
        status = inst.get("status", "?")
        cost = inst.get("cost_per_hour", 0)

        print(f"{inst_id:<25} {name:<25} {provider:<10} {status:<10} ${cost:>7.2f}")

        # Show URL for running instances
        if status == "running" and inst.get("comfyui_url"):
            print(f"  -> {inst['comfyui_url']}")

    return 0


def _get_custom_client(config: DeployConfig, worker_name: str) -> CustomWorkerClient | None:
    """Get CustomWorkerClient for a registered worker."""
    worker = config.get_worker(worker_name)
    if not worker:
        print(f"Error: Worker '{worker_name}' not found.")
        print("Run: cg-deploy custom list")
        return None
    return CustomWorkerClient(worker["host"], worker["port"], worker["api_key"])


def handle_start(args: Namespace) -> int:
    """Handle 'start' command - start a stopped instance."""
    config = DeployConfig()
    worker_name, local_id = parse_instance_id(args.instance_id)

    if worker_name:
        # Custom worker instance
        client = _get_custom_client(config, worker_name)
        if not client:
            return 1

        print(f"Starting instance {local_id} on {worker_name}...")
        try:
            result = asyncio.run(client.start_instance(local_id))
            print(f"Status: {result.get('status')}")
            if result.get("comfyui_url"):
                print(f"URL: {result['comfyui_url']}")
            return 0
        except CustomWorkerError as e:
            print(f"Error: {e}")
            return 1
    else:
        # RunPod instance
        api_key = config.runpod_api_key
        if not api_key:
            print("Error: RunPod API key not configured.")
            return 1

        client = RunPodClient(api_key)
        print(f"Starting instance {local_id}...")

        try:
            result = asyncio.run(client.start_pod(local_id))
            print(f"Status: {result.get('desiredStatus')}")
            if result.get("costPerHr"):
                print(f"Cost: ${result['costPerHr']:.2f}/hr")
            return 0
        except RunPodAPIError as e:
            print(f"Error: {e}")
            return 1


def handle_stop(args: Namespace) -> int:
    """Handle 'stop' command - stop a running instance."""
    config = DeployConfig()
    worker_name, local_id = parse_instance_id(args.instance_id)

    if worker_name:
        # Custom worker instance
        client = _get_custom_client(config, worker_name)
        if not client:
            return 1

        print(f"Stopping instance {local_id} on {worker_name}...")
        try:
            result = asyncio.run(client.stop_instance(local_id))
            print(f"Status: {result.get('status')}")
            return 0
        except CustomWorkerError as e:
            print(f"Error: {e}")
            return 1
    else:
        # RunPod instance
        api_key = config.runpod_api_key
        if not api_key:
            print("Error: RunPod API key not configured.")
            return 1

        client = RunPodClient(api_key)
        print(f"Stopping instance {local_id}...")

        try:
            result = asyncio.run(client.stop_pod(local_id))
            print(f"Status: {result.get('desiredStatus')}")
            return 0
        except RunPodAPIError as e:
            print(f"Error: {e}")
            return 1


def handle_terminate(args: Namespace) -> int:
    """Handle 'terminate' command - terminate and remove an instance."""
    config = DeployConfig()
    worker_name, local_id = parse_instance_id(args.instance_id)
    keep_env = getattr(args, "keep_env", False)

    # Confirm unless --force
    if not getattr(args, "force", False):
        confirm = input(f"Terminate instance {args.instance_id}? This cannot be undone. [y/N]: ")
        if confirm.lower() != "y":
            print("Cancelled.")
            return 0

    if worker_name:
        # Custom worker instance
        client = _get_custom_client(config, worker_name)
        if not client:
            return 1

        print(f"Terminating instance {local_id} on {worker_name}...")
        try:
            result = asyncio.run(client.terminate_instance(local_id, keep_env=keep_env))
            print(result.get("message", "Instance terminated."))
            return 0
        except CustomWorkerError as e:
            print(f"Error: {e}")
            return 1
    else:
        # RunPod instance
        api_key = config.runpod_api_key
        if not api_key:
            print("Error: RunPod API key not configured.")
            return 1

        client = RunPodClient(api_key)
        print(f"Terminating instance {local_id}...")

        try:
            asyncio.run(client.delete_pod(local_id))
            print("Instance terminated.")
            return 0
        except RunPodAPIError as e:
            print(f"Error: {e}")
            return 1


def handle_open(args: Namespace) -> int:
    """Handle 'open' command - open ComfyUI URL in browser."""
    config = DeployConfig()
    worker_name, local_id = parse_instance_id(args.instance_id)

    if worker_name:
        # Custom worker instance
        client = _get_custom_client(config, worker_name)
        if not client:
            return 1

        try:
            instance = asyncio.run(client.get_instance(local_id))
            url = instance.get("comfyui_url")
            if not url:
                print(f"Instance {local_id} is not running or URL not available.")
                return 1
            print(f"Opening: {url}")
            webbrowser.open(url)
            return 0
        except CustomWorkerError as e:
            print(f"Error: {e}")
            return 1
    else:
        # RunPod instance
        api_key = config.runpod_api_key
        if not api_key:
            print("Error: RunPod API key not configured.")
            return 1

        client = RunPodClient(api_key)
        try:
            pod = asyncio.run(client.get_pod(local_id))
        except RunPodAPIError as e:
            print(f"Error: {e}")
            return 1

        url = RunPodClient.get_comfyui_url(pod)
        if not url:
            print(f"Instance {local_id} is not running or URL not available.")
            return 1

        print(f"Opening: {url}")
        webbrowser.open(url)
        return 0


def handle_wait(args: Namespace) -> int:
    """Handle 'wait' command - wait for instance to be ready."""
    config = DeployConfig()
    worker_name, local_id = parse_instance_id(args.instance_id)
    timeout = getattr(args, "timeout", 300)
    start_time = time.time()

    print(f"Waiting for instance {args.instance_id} to be ready (timeout: {timeout}s)...")

    if worker_name:
        # Custom worker instance
        client = _get_custom_client(config, worker_name)
        if not client:
            return 1

        while time.time() - start_time < timeout:
            try:
                instance = asyncio.run(client.get_instance(local_id))
                status = instance.get("status")

                if status == "running":
                    url = instance.get("comfyui_url")
                    if url:
                        print("\nInstance ready!")
                        print(f"ComfyUI URL: {url}")
                        return 0

                elapsed = int(time.time() - start_time)
                print(f"\r  Status: {status} ({elapsed}s)", end="", flush=True)

            except CustomWorkerError as e:
                print(f"\nWarning: {e}")

            time.sleep(5)
    else:
        # RunPod instance
        api_key = config.runpod_api_key
        if not api_key:
            print("Error: RunPod API key not configured.")
            return 1

        client = RunPodClient(api_key)
        while time.time() - start_time < timeout:
            try:
                pod = asyncio.run(client.get_pod(local_id))
                status = pod.get("desiredStatus")

                if status == "RUNNING":
                    url = RunPodClient.get_comfyui_url(pod)
                    if url:
                        print("\nInstance ready!")
                        print(f"ComfyUI URL: {url}")
                        return 0

                elapsed = int(time.time() - start_time)
                print(f"\r  Status: {status} ({elapsed}s)", end="", flush=True)

            except RunPodAPIError as e:
                print(f"\nWarning: {e}")

            time.sleep(5)

    print(f"\nTimeout: Instance not ready after {timeout}s")
    return 1


def stream_worker_logs(
    host: str, port: int, api_key: str, instance_id: str, follow: bool
) -> None:
    """Stream logs from a custom worker instance.

    Args:
        host: Worker host
        port: Worker port
        api_key: API key
        instance_id: Instance ID (local, not namespaced)
        follow: If True, stream continuously; if False, just print and exit
    """
    from ..providers.custom import CustomWorkerClient

    async def _stream():
        client = CustomWorkerClient(host=host, port=port, api_key=api_key)
        try:
            async for entry in client.stream_logs(instance_id):
                print(f"[{entry.level}] {entry.message}")
        except KeyboardInterrupt:
            pass

    asyncio.run(_stream())


def fetch_worker_logs(
    host: str, port: int, api_key: str, instance_id: str, lines: int
) -> list[dict]:
    """Fetch recent logs from a custom worker instance.

    Args:
        host: Worker host
        port: Worker port
        api_key: API key
        instance_id: Instance ID (local, not namespaced)
        lines: Number of lines to fetch

    Returns:
        List of log entries
    """
    from ..providers.custom import CustomWorkerClient

    async def _fetch():
        client = CustomWorkerClient(host=host, port=port, api_key=api_key)
        return await client.get_logs(instance_id, lines=lines)

    return asyncio.run(_fetch())


def handle_logs(args: Namespace) -> int:
    """Handle 'logs' command."""
    config = DeployConfig()
    worker_name, local_id = parse_instance_id(args.instance_id)
    follow = getattr(args, "follow", False)
    lines = getattr(args, "lines", 100)

    if worker_name:
        # Custom worker logs
        worker = config.get_worker(worker_name)
        if not worker:
            print(f"Error: Worker '{worker_name}' not found.")
            return 1

        if follow:
            # Stream logs via WebSocket
            stream_worker_logs(
                host=worker["host"],
                port=worker["port"],
                api_key=worker["api_key"],
                instance_id=local_id,
                follow=True,
            )
        else:
            # Fetch recent logs
            logs = fetch_worker_logs(
                host=worker["host"],
                port=worker["port"],
                api_key=worker["api_key"],
                instance_id=local_id,
                lines=lines,
            )
            for entry in logs:
                level = entry.get("level", "INFO")
                message = entry.get("message", "")
                print(f"[{level}] {message}")
    else:
        # RunPod doesn't have a direct logs API - users need to use the console
        print("Log streaming not available via API.")
        print(f"View logs in RunPod console: https://www.runpod.io/console/pods/{local_id}")

    return 0
