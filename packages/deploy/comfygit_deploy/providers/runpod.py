"""RunPod REST and GraphQL API client for pod and resource management.

REST API v1: https://rest.runpod.io/v1
GraphQL API: https://api.runpod.io/graphql
"""

from dataclasses import dataclass
from typing import Any

import aiohttp

# RunPod data centers (static list - no REST endpoint available)
DATA_CENTERS = [
    {"id": "US-GA-1", "name": "United States (Georgia)", "available": True},
    {"id": "US-GA-2", "name": "United States (Georgia 2)", "available": True},
    {"id": "US-IL-1", "name": "United States (Illinois)", "available": True},
    {"id": "US-KS-2", "name": "United States (Kansas)", "available": True},
    {"id": "US-KS-3", "name": "United States (Kansas 2)", "available": True},
    {"id": "US-TX-1", "name": "United States (Texas)", "available": True},
    {"id": "US-TX-3", "name": "United States (Texas 2)", "available": True},
    {"id": "US-TX-4", "name": "United States (Texas 3)", "available": True},
    {"id": "US-WA-1", "name": "United States (Washington)", "available": True},
    {"id": "US-CA-2", "name": "United States (California)", "available": True},
    {"id": "US-NC-1", "name": "United States (North Carolina)", "available": True},
    {"id": "US-DE-1", "name": "United States (Delaware)", "available": True},
    {"id": "CA-MTL-1", "name": "Canada (Montreal)", "available": True},
    {"id": "CA-MTL-2", "name": "Canada (Montreal 2)", "available": True},
    {"id": "CA-MTL-3", "name": "Canada (Montreal 3)", "available": True},
    {"id": "EU-CZ-1", "name": "Europe (Czech Republic)", "available": True},
    {"id": "EU-FR-1", "name": "Europe (France)", "available": True},
    {"id": "EU-NL-1", "name": "Europe (Netherlands)", "available": True},
    {"id": "EU-RO-1", "name": "Europe (Romania)", "available": True},
    {"id": "EU-SE-1", "name": "Europe (Sweden)", "available": True},
    {"id": "EUR-IS-1", "name": "Europe (Iceland)", "available": True},
    {"id": "EUR-IS-2", "name": "Europe (Iceland 2)", "available": True},
    {"id": "EUR-IS-3", "name": "Europe (Iceland 3)", "available": True},
    {"id": "EUR-NO-1", "name": "Europe (Norway)", "available": True},
    {"id": "AP-JP-1", "name": "Asia-Pacific (Japan)", "available": True},
    {"id": "OC-AU-1", "name": "Oceania (Australia)", "available": True},
]

# Common GPU types available on RunPod
GPU_TYPES = [
    "NVIDIA GeForce RTX 4090",
    "NVIDIA GeForce RTX 3090",
    "NVIDIA GeForce RTX 3090 Ti",
    "NVIDIA GeForce RTX 3080 Ti",
    "NVIDIA GeForce RTX 3080",
    "NVIDIA GeForce RTX 3070",
    "NVIDIA GeForce RTX 4080",
    "NVIDIA GeForce RTX 4080 SUPER",
    "NVIDIA GeForce RTX 4070 Ti",
    "NVIDIA GeForce RTX 5090",
    "NVIDIA GeForce RTX 5080",
    "NVIDIA A40",
    "NVIDIA A100 80GB PCIe",
    "NVIDIA A100-SXM4-80GB",
    "NVIDIA A30",
    "NVIDIA H100 80GB HBM3",
    "NVIDIA H100 PCIe",
    "NVIDIA H100 NVL",
    "NVIDIA H200",
    "NVIDIA B200",
    "NVIDIA L40S",
    "NVIDIA L40",
    "NVIDIA L4",
    "NVIDIA RTX A6000",
    "NVIDIA RTX A5000",
    "NVIDIA RTX A4500",
    "NVIDIA RTX A4000",
    "NVIDIA RTX A2000",
    "NVIDIA RTX 6000 Ada Generation",
    "NVIDIA RTX 5000 Ada Generation",
    "NVIDIA RTX 4000 Ada Generation",
    "NVIDIA RTX 4000 SFF Ada Generation",
    "NVIDIA RTX 2000 Ada Generation",
    "Tesla V100-PCIE-16GB",
    "Tesla V100-FHHL-16GB",
    "Tesla V100-SXM2-16GB",
    "Tesla V100-SXM2-32GB",
    "AMD Instinct MI300X OAM",
]


@dataclass
class RunPodAPIError(Exception):
    """Error from RunPod API."""

    message: str
    status_code: int

    def __str__(self) -> str:
        return f"RunPod API Error ({self.status_code}): {self.message}"


class RunPodClient:
    """Async client for RunPod REST and GraphQL APIs."""

    base_url = "https://rest.runpod.io/v1"
    graphql_url = "https://api.runpod.io/graphql"

    def __init__(self, api_key: str):
        """Initialize client with API key.

        Args:
            api_key: RunPod API key (starts with rpa_ or rps_)

        Raises:
            ValueError: If api_key is empty
        """
        if not api_key:
            raise ValueError("API key required")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        """Get request headers with authorization."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _get(
        self, path: str, params: dict | None = None, operation: str = "get"
    ) -> Any:
        """Make GET request and return JSON response."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self._headers(),
            ) as response:
                if response.status >= 400:
                    await self._handle_error(response)
                return await response.json()

    async def _post(
        self, path: str, data: dict | None = None, operation: str = "post"
    ) -> Any:
        """Make POST request and return JSON response."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}{path}",
                json=data,
                headers=self._headers(),
            ) as response:
                if response.status >= 400:
                    await self._handle_error(response)
                if response.status == 204:
                    return None
                try:
                    return await response.json()
                except Exception:
                    return None

    async def _delete(self, path: str, operation: str = "delete") -> None:
        """Make DELETE request."""
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self.base_url}{path}",
                headers=self._headers(),
            ) as response:
                if response.status >= 400:
                    await self._handle_error(response)

    async def _patch(
        self, path: str, data: dict | None = None, operation: str = "patch"
    ) -> Any:
        """Make PATCH request and return JSON response."""
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                f"{self.base_url}{path}",
                json=data,
                headers=self._headers(),
            ) as response:
                if response.status >= 400:
                    await self._handle_error(response)
                return await response.json()

    async def _handle_error(self, response: aiohttp.ClientResponse) -> None:
        """Handle error response."""
        try:
            error_body = await response.json()
            message = error_body.get(
                "message", error_body.get("error", str(error_body))
            )
        except Exception:
            message = await response.text() or f"HTTP {response.status}"
        raise RunPodAPIError(message, response.status)

    async def _graphql_query(
        self, query: str, variables: dict | None = None, operation: str = "graphql"
    ) -> dict:
        """Execute a GraphQL query against RunPod API.

        Note: RunPod GraphQL uses API key as URL parameter, not Bearer token.
        """
        url = f"{self.graphql_url}?api_key={self.api_key}"
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                return await response.json()

    def _handle_graphql_errors(
        self, result: dict, operation: str = "graphql"
    ) -> None:
        """Raise exception if GraphQL response contains errors."""
        if "errors" in result:
            error_msg = result["errors"][0].get("message", "GraphQL error")
            raise RunPodAPIError(error_msg, 400)

    # =========================================================================
    # User Info / Connection Test
    # =========================================================================

    async def get_user_info(self) -> dict[str, Any]:
        """Get user account info including credit balance."""
        query = """
        query {
            myself {
                id
                clientBalance
                currentSpendPerHr
                spendLimit
            }
        }
        """
        result = await self._graphql_query(query, operation="get_user_info")
        self._handle_graphql_errors(result, "get_user_info")

        if not result.get("data") or not result["data"].get("myself"):
            raise RunPodAPIError("Invalid API key or unauthorized", 401)

        return result["data"]["myself"]

    async def test_connection(self) -> dict[str, Any]:
        """Test API key validity and return account info.

        Returns:
            {"success": True, "credit_balance": float} on success
            {"success": False, "error": "message"} on failure
        """
        try:
            user_info = await self.get_user_info()
            return {
                "success": True,
                "credit_balance": user_info.get("clientBalance", 0),
            }
        except RunPodAPIError as e:
            return {"success": False, "error": e.message}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Pod Operations
    # =========================================================================

    async def list_pods(
        self,
        desired_status: str | None = None,
        gpu_type_id: str | None = None,
        include_machine: bool = False,
    ) -> list[dict]:
        """List all pods."""
        params = {}
        if desired_status:
            params["desiredStatus"] = desired_status
        if gpu_type_id:
            params["gpuTypeId"] = gpu_type_id
        if include_machine:
            params["includeMachine"] = "true"

        return await self._get("/pods", params=params or None, operation="list_pods")

    async def get_pod(self, pod_id: str, include_machine: bool = False) -> dict:
        """Get pod by ID."""
        params = {}
        if include_machine:
            params["includeMachine"] = "true"
        return await self._get(
            f"/pods/{pod_id}", params=params or None, operation="get_pod"
        )

    async def create_pod(
        self,
        name: str,
        image_name: str,
        gpu_type_id: str,
        gpu_count: int = 1,
        volume_in_gb: int = 20,
        container_disk_in_gb: int = 50,
        cloud_type: str = "SECURE",
        ports: list[str] | None = None,
        env: dict[str, str] | None = None,
        docker_start_cmd: list[str] | None = None,
        network_volume_id: str | None = None,
        data_center_ids: list[str] | None = None,
        interruptible: bool = False,
    ) -> dict:
        """Create a new pod."""
        data = {
            "name": name,
            "imageName": image_name,
            "gpuTypeIds": [gpu_type_id],
            "gpuCount": gpu_count,
            "volumeInGb": volume_in_gb,
            "containerDiskInGb": container_disk_in_gb,
            "cloudType": cloud_type,
            "interruptible": interruptible,
        }

        if ports:
            data["ports"] = ports
        if env:
            data["env"] = env
        if docker_start_cmd:
            data["dockerStartCmd"] = docker_start_cmd
        if network_volume_id:
            data["networkVolumeId"] = network_volume_id
        if data_center_ids:
            data["dataCenterIds"] = data_center_ids

        return await self._post("/pods", data=data, operation="create_pod")

    async def delete_pod(self, pod_id: str) -> bool:
        """Delete a pod."""
        await self._delete(f"/pods/{pod_id}", operation="delete_pod")
        return True

    async def start_pod(self, pod_id: str) -> dict:
        """Start a stopped pod using GraphQL podResume mutation."""
        query = f"""
        mutation {{
            podResume(input: {{ podId: "{pod_id}" }}) {{
                id
                desiredStatus
                costPerHr
            }}
        }}
        """
        result = await self._graphql_query(query, operation="start_pod")
        self._handle_graphql_errors(result, "start_pod")
        return result["data"]["podResume"]

    async def stop_pod(self, pod_id: str) -> dict:
        """Stop a running pod using GraphQL podStop mutation."""
        query = f"""
        mutation {{
            podStop(input: {{ podId: "{pod_id}" }}) {{
                id
                desiredStatus
            }}
        }}
        """
        result = await self._graphql_query(query, operation="stop_pod")
        self._handle_graphql_errors(result, "stop_pod")
        return result["data"]["podStop"]

    async def restart_pod(self, pod_id: str) -> bool:
        """Restart a pod."""
        await self._post(f"/pods/{pod_id}/restart", operation="restart_pod")
        return True

    # =========================================================================
    # Network Volume Operations
    # =========================================================================

    async def list_network_volumes(self) -> list[dict]:
        """List network volumes."""
        return await self._get("/networkvolumes", operation="list_network_volumes")

    async def get_network_volume(self, volume_id: str) -> dict:
        """Get network volume by ID."""
        return await self._get(
            f"/networkvolumes/{volume_id}", operation="get_network_volume"
        )

    async def create_network_volume(
        self, name: str, size_gb: int, data_center_id: str
    ) -> dict:
        """Create a network volume."""
        data = {
            "name": name,
            "size": size_gb,
            "dataCenterId": data_center_id,
        }
        return await self._post(
            "/networkvolumes", data=data, operation="create_network_volume"
        )

    async def delete_network_volume(self, volume_id: str) -> bool:
        """Delete a network volume."""
        await self._delete(
            f"/networkvolumes/{volume_id}", operation="delete_network_volume"
        )
        return True

    # =========================================================================
    # GPU Types and Data Centers
    # =========================================================================

    async def get_gpu_types_with_pricing(
        self, data_center_id: str | None = None
    ) -> list[dict]:
        """Get GPU types with pricing and availability."""
        if data_center_id:
            lowest_price_input = (
                f'input: {{ gpuCount: 1, dataCenterId: "{data_center_id}" }}'
            )
        else:
            lowest_price_input = "input: { gpuCount: 1 }"

        query = f"""
        query {{
            gpuTypes {{
                id
                displayName
                memoryInGb
                secureCloud
                communityCloud
                securePrice
                communityPrice
                secureSpotPrice
                communitySpotPrice
                lowestPrice({lowest_price_input}) {{
                    minimumBidPrice
                    uninterruptablePrice
                    stockStatus
                }}
            }}
        }}
        """
        result = await self._graphql_query(
            query, operation="get_gpu_types_with_pricing"
        )
        self._handle_graphql_errors(result, "get_gpu_types_with_pricing")
        return result["data"]["gpuTypes"]

    async def get_data_centers(self) -> list[dict]:
        """Get available data centers (uses static fallback if API fails)."""
        try:
            query = """
            query {
                myself {
                    datacenters {
                        id
                        name
                        location
                        storageSupport
                        listed
                        region
                    }
                }
            }
            """
            result = await self._graphql_query(query, operation="get_data_centers")
            self._handle_graphql_errors(result, "get_data_centers")
            raw_dcs = result["data"]["myself"]["datacenters"]
            return [
                {
                    "id": dc.get("id"),
                    "name": dc.get("name") or dc.get("location", dc.get("id")),
                    "location": dc.get("location"),
                    "region": dc.get("region"),
                    "available": dc.get("listed", True)
                    and dc.get("storageSupport", True),
                }
                for dc in raw_dcs
                if dc.get("listed", True)
            ]
        except Exception:
            return DATA_CENTERS.copy()

    # =========================================================================
    # Static Helper Methods
    # =========================================================================

    @staticmethod
    def get_comfyui_url(pod: dict, port: int = 8188) -> str | None:
        """Get ComfyUI proxy URL for a running pod."""
        if pod.get("desiredStatus") != "RUNNING":
            return None

        pod_id = pod.get("id")
        if not pod_id:
            return None

        return f"https://{pod_id}-{port}.proxy.runpod.net"

    @staticmethod
    def get_ssh_command(pod: dict) -> str | None:
        """Get SSH command for connecting to a pod."""
        public_ip = pod.get("publicIp")
        port_mappings = pod.get("portMappings", {})

        if not public_ip or not port_mappings:
            return None

        ssh_port = port_mappings.get("22")
        if not ssh_port:
            return None

        return f"ssh root@{public_ip} -p {ssh_port}"

    @staticmethod
    def _estimate_gpu_memory(gpu_id: str) -> int:
        """Estimate GPU memory based on model name."""
        memory_map = {
            "RTX 4090": 24,
            "RTX 5090": 32,
            "RTX 5080": 16,
            "RTX 4080": 16,
            "RTX 3090": 24,
            "RTX 3080": 10,
            "RTX 3070": 8,
            "RTX 4070": 12,
            "A100 80GB": 80,
            "A100-SXM4-80GB": 80,
            "H100 80GB": 80,
            "H100 PCIe": 80,
            "H100 NVL": 94,
            "H200": 141,
            "B200": 192,
            "A40": 48,
            "A30": 24,
            "L40S": 48,
            "L40": 48,
            "L4": 24,
            "RTX A6000": 48,
            "RTX A5000": 24,
            "RTX A4500": 20,
            "RTX A4000": 16,
            "RTX 6000 Ada": 48,
            "RTX 5000 Ada": 32,
            "RTX 4000 Ada": 20,
            "V100": 16,
            "V100-SXM2-32GB": 32,
            "MI300X": 192,
        }
        for key, mem in memory_map.items():
            if key in gpu_id:
                return mem
        return 24  # Default
