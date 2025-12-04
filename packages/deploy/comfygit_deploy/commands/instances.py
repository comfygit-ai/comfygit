"""Instance management CLI command implementations."""

import asyncio
import json
import time
import webbrowser
from argparse import Namespace

from ..config import DeployConfig
from ..providers.runpod import RunPodAPIError, RunPodClient


def _get_runpod_client() -> RunPodClient | None:
    """Get RunPod client if configured."""
    config = DeployConfig()
    api_key = config.runpod_api_key
    if api_key:
        return RunPodClient(api_key)
    return None


def handle_instances(args: Namespace) -> int:
    """Handle 'instances' command - list all instances."""
    client = _get_runpod_client()

    if not client:
        print("Error: RunPod API key not configured.")
        print("Run: cg-deploy runpod config --api-key <your-key>")
        return 1

    try:
        pods = asyncio.run(client.list_pods())
    except RunPodAPIError as e:
        print(f"Error: {e}")
        return 1

    # Filter by status if requested
    status_filter = getattr(args, "status", None)
    if status_filter:
        status_map = {"running": "RUNNING", "stopped": "EXITED"}
        target_status = status_map.get(status_filter.lower())
        if target_status:
            pods = [p for p in pods if p.get("desiredStatus") == target_status]

    # JSON output
    if getattr(args, "json", False):
        print(json.dumps(pods, indent=2))
        return 0

    if not pods:
        print("No instances found.")
        return 0

    print(f"{'ID':<15} {'Name':<30} {'Status':<10} {'GPU':<20} {'$/hr':>8}")
    print("-" * 85)

    for pod in pods:
        pod_id = pod.get("id", "?")
        name = pod.get("name", "?")[:30]
        status = pod.get("desiredStatus", "?")
        gpu = pod.get("machine", {}).get("gpuDisplayName", "?")[:20] if pod.get("machine") else "?"
        cost = pod.get("costPerHr", 0)

        print(f"{pod_id:<15} {name:<30} {status:<10} {gpu:<20} ${cost:>7.2f}")

        # Show URL for running pods
        if status == "RUNNING":
            url = RunPodClient.get_comfyui_url(pod)
            if url:
                print(f"  -> {url}")

    return 0


def handle_start(args: Namespace) -> int:
    """Handle 'start' command."""
    client = _get_runpod_client()
    if not client:
        print("Error: RunPod API key not configured.")
        return 1

    instance_id = args.instance_id
    print(f"Starting instance {instance_id}...")

    try:
        result = asyncio.run(client.start_pod(instance_id))
        print(f"Status: {result.get('desiredStatus')}")
        if result.get("costPerHr"):
            print(f"Cost: ${result['costPerHr']:.2f}/hr")
        return 0
    except RunPodAPIError as e:
        print(f"Error: {e}")
        return 1


def handle_stop(args: Namespace) -> int:
    """Handle 'stop' command."""
    client = _get_runpod_client()
    if not client:
        print("Error: RunPod API key not configured.")
        return 1

    instance_id = args.instance_id
    print(f"Stopping instance {instance_id}...")

    try:
        result = asyncio.run(client.stop_pod(instance_id))
        print(f"Status: {result.get('desiredStatus')}")
        return 0
    except RunPodAPIError as e:
        print(f"Error: {e}")
        return 1


def handle_terminate(args: Namespace) -> int:
    """Handle 'terminate' command."""
    client = _get_runpod_client()
    if not client:
        print("Error: RunPod API key not configured.")
        return 1

    instance_id = args.instance_id

    # Confirm unless --force
    if not getattr(args, "force", False):
        confirm = input(f"Terminate instance {instance_id}? This cannot be undone. [y/N]: ")
        if confirm.lower() != "y":
            print("Cancelled.")
            return 0

    print(f"Terminating instance {instance_id}...")

    try:
        asyncio.run(client.delete_pod(instance_id))
        print("Instance terminated.")
        return 0
    except RunPodAPIError as e:
        print(f"Error: {e}")
        return 1


def handle_open(args: Namespace) -> int:
    """Handle 'open' command - open ComfyUI URL in browser."""
    client = _get_runpod_client()
    if not client:
        print("Error: RunPod API key not configured.")
        return 1

    instance_id = args.instance_id

    try:
        pod = asyncio.run(client.get_pod(instance_id))
    except RunPodAPIError as e:
        print(f"Error: {e}")
        return 1

    url = RunPodClient.get_comfyui_url(pod)
    if not url:
        print(f"Instance {instance_id} is not running or URL not available.")
        return 1

    print(f"Opening: {url}")
    webbrowser.open(url)
    return 0


def handle_wait(args: Namespace) -> int:
    """Handle 'wait' command - wait for instance to be ready."""
    client = _get_runpod_client()
    if not client:
        print("Error: RunPod API key not configured.")
        return 1

    instance_id = args.instance_id
    timeout = getattr(args, "timeout", 300)
    start_time = time.time()

    print(f"Waiting for instance {instance_id} to be ready (timeout: {timeout}s)...")

    while time.time() - start_time < timeout:
        try:
            pod = asyncio.run(client.get_pod(instance_id))
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


def handle_logs(args: Namespace) -> int:
    """Handle 'logs' command."""
    # RunPod doesn't have a direct logs API - users need to use the console
    instance_id = args.instance_id
    print("Log streaming not available via API.")
    print(f"View logs in RunPod console: https://www.runpod.io/console/pods/{instance_id}")
    return 0
