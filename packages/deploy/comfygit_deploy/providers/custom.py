"""Custom worker HTTP client for connecting to self-hosted workers.

Provides async interface for worker server REST API.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass
class CustomWorkerError(Exception):
    """Error from custom worker API."""

    message: str
    status_code: int

    def __str__(self) -> str:
        return f"Worker Error ({self.status_code}): {self.message}"


@dataclass
class LogEntry:
    """A single log entry from streaming."""

    timestamp: str
    level: str
    message: str


class CustomWorkerClient:
    """Async client for custom worker REST API."""

    def __init__(self, host: str, port: int, api_key: str):
        """Initialize client.

        Args:
            host: Worker host/IP
            port: Worker API port
            api_key: Worker API key
        """
        self.host = host
        self.port = port
        self.api_key = api_key
        self.base_url = f"http://{host}:{port}"

    def _headers(self) -> dict[str, str]:
        """Get request headers with authorization."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str) -> Any:
        """Make GET request and return JSON response."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
            ) as response:
                if response.status >= 400:
                    await self._handle_error(response)
                return await response.json()

    async def _post(self, path: str, data: dict | None = None) -> Any:
        """Make POST request and return JSON response."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}{path}",
                json=data,
                headers=self._headers(),
            ) as response:
                if response.status >= 400:
                    await self._handle_error(response)
                return await response.json()

    async def _delete(self, path: str) -> Any:
        """Make DELETE request and return JSON response."""
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self.base_url}{path}",
                headers=self._headers(),
            ) as response:
                if response.status >= 400:
                    await self._handle_error(response)
                return await response.json()

    async def _handle_error(self, response: aiohttp.ClientResponse) -> None:
        """Handle error response."""
        try:
            error_body = await response.json()
            message = error_body.get("error", str(error_body))
        except Exception:
            message = await response.text() or f"HTTP {response.status}"
        raise CustomWorkerError(message, response.status)

    async def test_connection(self) -> dict[str, Any]:
        """Test connection to worker.

        Returns:
            {"success": True, "worker_version": "..."} on success
            {"success": False, "error": "..."} on failure
        """
        try:
            health = await self._get("/api/v1/health")
            return {
                "success": True,
                "worker_version": health.get("worker_version"),
            }
        except CustomWorkerError as e:
            return {"success": False, "error": e.message}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_system_info(self) -> dict[str, Any]:
        """Get worker system information."""
        return await self._get("/api/v1/system/info")

    async def list_instances(self) -> list[dict]:
        """List all instances on worker."""
        result = await self._get("/api/v1/instances")
        return result.get("instances", [])

    async def create_instance(
        self,
        import_source: str,
        name: str | None = None,
        branch: str | None = None,
        mode: str | None = None,
    ) -> dict:
        """Create new instance.

        Args:
            import_source: Git URL or local path
            name: Optional instance name
            branch: Optional git branch
            mode: docker or native

        Returns:
            Instance data
        """
        data = {"import_source": import_source}
        if name:
            data["name"] = name
        if branch:
            data["branch"] = branch
        if mode:
            data["mode"] = mode

        return await self._post("/api/v1/instances", data)

    async def get_instance(self, instance_id: str) -> dict:
        """Get instance details."""
        return await self._get(f"/api/v1/instances/{instance_id}")

    async def stop_instance(self, instance_id: str) -> dict:
        """Stop a running instance."""
        return await self._post(f"/api/v1/instances/{instance_id}/stop")

    async def start_instance(self, instance_id: str) -> dict:
        """Start a stopped instance."""
        return await self._post(f"/api/v1/instances/{instance_id}/start")

    async def terminate_instance(self, instance_id: str, keep_env: bool = False) -> dict:
        """Terminate and remove instance."""
        path = f"/api/v1/instances/{instance_id}"
        if keep_env:
            path += "?keep_env=true"
        return await self._delete(path)

    async def get_logs(self, instance_id: str, lines: int = 100) -> list[dict]:
        """Get recent logs for an instance.

        Args:
            instance_id: Instance ID
            lines: Number of lines to fetch

        Returns:
            List of log entries
        """
        result = await self._get(f"/api/v1/instances/{instance_id}/logs?lines={lines}")
        return result.get("logs", [])

    def _connect_ws(self, url: str):
        """Create a WebSocket connection context manager.

        Returns an async context manager that yields the WebSocket connection.
        """
        return _WSConnectionManager(url, self.api_key)

    async def stream_logs(self, instance_id: str) -> AsyncIterator[LogEntry]:
        """Stream logs from an instance via WebSocket.

        Args:
            instance_id: Instance ID

        Yields:
            LogEntry objects as they arrive
        """
        url = f"ws://{self.host}:{self.port}/api/v1/instances/{instance_id}/logs"
        async with self._connect_ws(url) as ws:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("type") == "log":
                        yield LogEntry(
                            timestamp=data.get("timestamp", ""),
                            level=data.get("level", "INFO"),
                            message=data.get("message", ""),
                        )
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break


class _WSConnectionManager:
    """Async context manager for WebSocket connections."""

    def __init__(self, url: str, api_key: str):
        self.url = url
        self.api_key = api_key
        self._session: aiohttp.ClientSession | None = None
        self._ws = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(
            self.url, headers={"Authorization": f"Bearer {self.api_key}"}
        )
        return self._ws

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
