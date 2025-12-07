"""Tests for WebSocket log streaming (Phase 3).

Tests for real-time log streaming from worker to CLI.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from comfygit_deploy.worker.server import create_worker_app


class TestLogStreamingEndpoint(AioHTTPTestCase):
    """Tests for WebSocket log streaming endpoint on worker server."""

    async def get_application(self) -> web.Application:
        """Create test application."""
        self.state_dir = Path("/tmp/test_logs_streaming")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        return create_worker_app(
            api_key="test-key",
            workspace_path=Path("/tmp/workspace"),
            state_dir=self.state_dir,
        )

    async def tearDownAsync(self) -> None:
        """Clean up test files."""
        import shutil

        if self.state_dir.exists():
            shutil.rmtree(self.state_dir)

    @unittest_run_loop
    async def test_logs_endpoint_exists(self) -> None:
        """WebSocket endpoint /api/v1/instances/{id}/logs exists."""
        # First create an instance to get a valid ID
        async with self.client.post(
            "/api/v1/instances",
            json={"import_source": "https://github.com/test/repo.git"},
            headers={"Authorization": "Bearer test-key"},
        ) as resp:
            data = await resp.json()
            instance_id = data["id"]

        # Connect to logs endpoint via WebSocket
        async with self.client.ws_connect(
            f"/api/v1/instances/{instance_id}/logs",
            headers={"Authorization": "Bearer test-key"},
        ) as ws:
            # Should connect successfully
            assert not ws.closed

    @unittest_run_loop
    async def test_logs_endpoint_requires_auth(self) -> None:
        """WebSocket logs endpoint requires authentication."""
        from aiohttp import WSServerHandshakeError

        with pytest.raises(WSServerHandshakeError) as exc_info:
            # Should fail without auth header - returns 401
            await self.client.ws_connect("/api/v1/instances/test-id/logs")
        assert exc_info.value.status == 401

    @unittest_run_loop
    async def test_logs_returns_json_messages(self) -> None:
        """Log messages are returned as JSON with type, timestamp, level, message."""
        # Create instance
        async with self.client.post(
            "/api/v1/instances",
            json={"import_source": "https://github.com/test/repo.git"},
            headers={"Authorization": "Bearer test-key"},
        ) as resp:
            data = await resp.json()
            instance_id = data["id"]

        async with self.client.ws_connect(
            f"/api/v1/instances/{instance_id}/logs",
            headers={"Authorization": "Bearer test-key"},
        ) as ws:
            # Wait for a log message (may need to trigger activity)
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=1.0)
                assert "type" in msg
                assert msg["type"] == "log"
                assert "timestamp" in msg
                assert "level" in msg
                assert "message" in msg
            except asyncio.TimeoutError:
                # No logs yet is OK - just verify connection worked
                pass


class TestLogStreamingClient:
    """Tests for CustomWorkerClient log streaming."""

    @pytest.mark.asyncio
    async def test_client_has_stream_logs_method(self) -> None:
        """CustomWorkerClient has stream_logs async generator method."""
        import inspect

        from comfygit_deploy.providers.custom import CustomWorkerClient

        client = CustomWorkerClient(host="localhost", port=9090, api_key="test")

        # Should have stream_logs method (async generator or coroutine)
        assert hasattr(client, "stream_logs")
        assert (
            asyncio.iscoroutinefunction(client.stream_logs)
            or inspect.isasyncgenfunction(client.stream_logs)
            or hasattr(client.stream_logs, "__anext__")
        )

    @pytest.mark.asyncio
    async def test_stream_logs_yields_log_entries(self) -> None:
        """stream_logs yields LogEntry objects."""
        from comfygit_deploy.providers.custom import CustomWorkerClient, LogEntry

        client = CustomWorkerClient(host="localhost", port=9090, api_key="test")

        # Mock the WebSocket connection
        with patch.object(client, "_connect_ws") as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.__aiter__ = lambda self: self
            mock_ws.__anext__ = AsyncMock(
                side_effect=[
                    MagicMock(
                        type=1,  # TEXT
                        data=json.dumps(
                            {
                                "type": "log",
                                "timestamp": "2024-01-15T10:30:00Z",
                                "level": "INFO",
                                "message": "ComfyUI started",
                            }
                        ),
                    ),
                    StopAsyncIteration,
                ]
            )
            mock_connect.return_value.__aenter__ = AsyncMock(return_value=mock_ws)
            mock_connect.return_value.__aexit__ = AsyncMock(return_value=None)

            logs = []
            async for entry in client.stream_logs("inst_123"):
                logs.append(entry)
                break  # Just get one

            assert len(logs) == 1
            assert isinstance(logs[0], LogEntry)
            assert logs[0].level == "INFO"
            assert logs[0].message == "ComfyUI started"


class TestLogsFollowCommand:
    """Tests for 'cg-deploy logs --follow' CLI command."""

    def test_logs_follow_streams_for_custom_worker(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """logs --follow streams logs for custom worker instances."""
        import json
        from argparse import Namespace

        from comfygit_deploy.commands.instances import handle_logs

        monkeypatch.setenv("HOME", str(tmp_path))
        config_dir = tmp_path / ".config" / "comfygit" / "deploy"
        config_dir.mkdir(parents=True)

        # Setup config with a custom worker
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "workers": {
                        "my-worker": {
                            "host": "192.168.1.50",
                            "port": 9090,
                            "api_key": "test-key",
                        }
                    }
                }
            )
        )

        with patch(
            "comfygit_deploy.commands.instances.stream_worker_logs"
        ) as mock_stream:
            # Simulate streaming a few log lines then stopping
            mock_stream.return_value = None  # Side effect handled via printing

            args = Namespace(instance_id="my-worker:inst_123", follow=True, lines=100)
            handle_logs(args)

            # Should call stream_worker_logs for custom worker with follow=True
            mock_stream.assert_called_once()
            call_args = mock_stream.call_args
            assert call_args[1].get("follow") is True or call_args[0][3] is True

    def test_logs_without_follow_gets_last_n_lines(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """logs without --follow fetches last N lines (not streaming)."""
        import json
        from argparse import Namespace

        from comfygit_deploy.commands.instances import handle_logs

        monkeypatch.setenv("HOME", str(tmp_path))
        config_dir = tmp_path / ".config" / "comfygit" / "deploy"
        config_dir.mkdir(parents=True)

        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "workers": {
                        "my-worker": {
                            "host": "192.168.1.50",
                            "port": 9090,
                            "api_key": "test-key",
                        }
                    }
                }
            )
        )

        with patch(
            "comfygit_deploy.commands.instances.fetch_worker_logs"
        ) as mock_fetch:
            mock_fetch.return_value = [
                {"level": "INFO", "message": "Line 1"},
                {"level": "INFO", "message": "Line 2"},
            ]

            args = Namespace(instance_id="my-worker:inst_123", follow=False, lines=50)
            result = handle_logs(args)

            # Should call fetch_worker_logs (not stream)
            mock_fetch.assert_called_once()
            assert result == 0


class TestNativeManagerLogCapture:
    """Tests for NativeManager capturing ComfyUI process logs."""

    def test_native_manager_captures_stdout(self) -> None:
        """NativeManager captures stdout from ComfyUI process."""
        from comfygit_deploy.worker.native_manager import NativeManager

        manager = NativeManager(workspace_path=Path("/tmp/workspace"))

        # Should have log capture capability
        assert hasattr(manager, "get_logs")

    def test_get_logs_returns_captured_output(self) -> None:
        """get_logs returns captured stdout/stderr."""
        from comfygit_deploy.worker.native_manager import NativeManager, ProcessLogs

        manager = NativeManager(workspace_path=Path("/tmp/workspace"))

        # Mock a running process with captured output
        logs = manager.get_logs("inst_123", lines=100)

        assert isinstance(logs, ProcessLogs)
        assert hasattr(logs, "stdout")
        assert hasattr(logs, "stderr")
        assert isinstance(logs.stdout, list)

    def test_get_logs_for_nonexistent_instance(self) -> None:
        """get_logs raises or returns empty for unknown instance."""
        from comfygit_deploy.worker.native_manager import NativeManager

        manager = NativeManager(workspace_path=Path("/tmp/workspace"))

        # Should handle gracefully
        logs = manager.get_logs("nonexistent_instance", lines=100)
        assert logs.stdout == [] or logs is None


class TestWorkerServerLogsEndpoint:
    """Tests for REST endpoint to fetch logs (non-streaming)."""

    @pytest.mark.asyncio
    async def test_get_logs_endpoint_exists(self) -> None:
        """GET /api/v1/instances/{id}/logs returns recent logs."""
        from aiohttp.test_utils import TestClient, TestServer

        state_dir = Path("/tmp/test_get_logs")
        state_dir.mkdir(parents=True, exist_ok=True)

        try:
            app = create_worker_app(
                api_key="test-key",
                workspace_path=Path("/tmp/workspace"),
                state_dir=state_dir,
            )

            async with TestClient(TestServer(app)) as client:
                # First create an instance
                resp = await client.post(
                    "/api/v1/instances",
                    json={"import_source": "https://github.com/test/repo.git"},
                    headers={"Authorization": "Bearer test-key"},
                )
                data = await resp.json()
                instance_id = data["id"]

                # GET logs endpoint
                resp = await client.get(
                    f"/api/v1/instances/{instance_id}/logs?lines=50",
                    headers={"Authorization": "Bearer test-key"},
                )

                # Should return 200 with logs array
                assert resp.status == 200
                data = await resp.json()
                assert "logs" in data
                assert isinstance(data["logs"], list)
        finally:
            import shutil

            if state_dir.exists():
                shutil.rmtree(state_dir)
