"""RunPod CLI command implementations."""

import asyncio
import sys
from argparse import Namespace

from ..config import DeployConfig
from ..providers.runpod import RunPodAPIError, RunPodClient
from ..startup.scripts import generate_deployment_id, generate_startup_script


def _get_client() -> RunPodClient:
    """Get RunPod client with configured API key."""
    config = DeployConfig()
    api_key = config.runpod_api_key
    if not api_key:
        print("Error: RunPod API key not configured.")
        print("Run: cg-deploy runpod config --api-key <your-key>")
        sys.exit(1)
    return RunPodClient(api_key)


def handle_config(args: Namespace) -> int:
    """Handle 'runpod config' command."""
    config = DeployConfig()

    if args.api_key:
        config.runpod_api_key = args.api_key
        config.save()
        # Test the connection
        client = RunPodClient(args.api_key)
        result = asyncio.run(client.test_connection())
        if result["success"]:
            print(f"API key saved. Credit balance: ${result['credit_balance']:.2f}")
        else:
            print(f"Warning: API key saved but connection test failed: {result['error']}")
        return 0

    if args.clear:
        config.runpod_api_key = None
        config.save()
        print("API key cleared.")
        return 0

    if args.show or (not args.api_key and not args.clear):
        api_key = config.runpod_api_key
        if api_key:
            # Mask the key for display
            masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
            print(f"API Key: {masked}")
            # Test connection
            client = RunPodClient(api_key)
            result = asyncio.run(client.test_connection())
            if result["success"]:
                print("Status: Connected")
                print(f"Credit Balance: ${result['credit_balance']:.2f}")
            else:
                print(f"Status: Error - {result['error']}")
        else:
            print("No API key configured.")
            print("Run: cg-deploy runpod config --api-key <your-key>")
        return 0

    return 0


def handle_gpus(args: Namespace) -> int:
    """Handle 'runpod gpus' command."""
    client = _get_client()
    region = getattr(args, "region", None)

    try:
        gpus = asyncio.run(client.get_gpu_types_with_pricing(region))
    except RunPodAPIError as e:
        print(f"Error: {e}")
        return 1

    # Sort by price (cheapest first)
    gpus = sorted(gpus, key=lambda g: g.get("securePrice") or 999)

    print(f"{'GPU Type':<35} {'VRAM':>6} {'Secure':>8} {'Spot':>8} {'Stock':>10}")
    print("-" * 75)

    for gpu in gpus:
        name = gpu.get("displayName", gpu.get("id", "Unknown"))[:35]
        vram = gpu.get("memoryInGb", "?")
        secure_price = gpu.get("securePrice")
        spot_price = gpu.get("secureSpotPrice")
        stock = gpu.get("lowestPrice", {}).get("stockStatus", "?")

        secure_str = f"${secure_price:.2f}/hr" if secure_price else "N/A"
        spot_str = f"${spot_price:.2f}/hr" if spot_price else "N/A"

        print(f"{name:<35} {vram:>4}GB {secure_str:>8} {spot_str:>8} {stock:>10}")

    return 0


def handle_volumes(args: Namespace) -> int:
    """Handle 'runpod volumes' command."""
    client = _get_client()

    try:
        volumes = asyncio.run(client.list_network_volumes())
    except RunPodAPIError as e:
        print(f"Error: {e}")
        return 1

    if not volumes:
        print("No network volumes found.")
        return 0

    print(f"{'ID':<15} {'Name':<25} {'Size':>8} {'Region':<15}")
    print("-" * 65)

    for vol in volumes:
        vol_id = vol.get("id", "?")
        name = vol.get("name", "?")[:25]
        size = vol.get("size", "?")
        region = vol.get("dataCenterId", vol.get("dataCenter", "?"))

        print(f"{vol_id:<15} {name:<25} {size:>6}GB {region:<15}")

    return 0


def handle_regions(args: Namespace) -> int:
    """Handle 'runpod regions' command."""
    client = _get_client()

    try:
        regions = asyncio.run(client.get_data_centers())
    except RunPodAPIError as e:
        print(f"Error: {e}")
        return 1

    print(f"{'ID':<15} {'Name':<35} {'Available':>10}")
    print("-" * 62)

    for dc in regions:
        dc_id = dc.get("id", "?")
        name = dc.get("name", "?")[:35]
        available = "Yes" if dc.get("available", True) else "No"

        print(f"{dc_id:<15} {name:<35} {available:>10}")

    return 0


def handle_deploy(args: Namespace) -> int:
    """Handle 'runpod deploy' command."""
    client = _get_client()

    # Generate deployment ID
    name = getattr(args, "name", None) or args.import_source.split("/")[-1].replace(".git", "")
    deployment_id = generate_deployment_id(name)

    # Generate startup script
    startup_script = generate_startup_script(
        deployment_id=deployment_id,
        import_source=args.import_source,
        branch=getattr(args, "branch", None),
    )

    # Create pod
    print(f"Creating deployment: {deployment_id}")
    print(f"GPU: {args.gpu}")
    print(f"Source: {args.import_source}")

    try:
        # Use spot pricing if requested
        pricing_type = getattr(args, "pricing_type", "ON_DEMAND")
        cloud_type = getattr(args, "cloud_type", "SECURE")
        volume_id = getattr(args, "volume", None)

        pod = asyncio.run(
            client.create_pod(
                name=deployment_id,
                image_name="runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
                gpu_type_id=args.gpu,
                cloud_type=cloud_type,
                ports=["8188/http", "22/tcp"],
                docker_start_cmd=["/bin/bash", "-c", startup_script],
                network_volume_id=volume_id,
                interruptible=(pricing_type == "SPOT"),
            )
        )
    except RunPodAPIError as e:
        print(f"Error creating pod: {e}")
        return 1

    pod_id = pod.get("id")
    print(f"\nPod created: {pod_id}")
    print(f"Status: {pod.get('desiredStatus')}")

    url = RunPodClient.get_comfyui_url(pod)
    if url:
        print(f"ComfyUI URL: {url}")

    print(f"\nConsole: https://www.runpod.io/console/pods/{pod_id}")
    print("\nUse 'cg-deploy wait {pod_id}' to wait for deployment to complete.")

    return 0
