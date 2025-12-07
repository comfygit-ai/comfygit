"""Tests for custom worker HTTP client.

TDD: Tests written first - should FAIL until implementation exists.
"""

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from comfygit_deploy.providers.custom import CustomWorkerClient


class TestCustomWorkerClient(AioHTTPTestCase):
    """Test CustomWorkerClient against mock server."""

    async def get_application(self) -> web.Application:
        """Create mock worker server for testing."""
        app = web.Application()

        # Store state for testing
        app["api_key"] = "cg_wk_test123"
        app["instances"] = {}

        async def auth_middleware(app: web.Application, handler):
            async def middleware(request: web.Request) -> web.Response:
                auth = request.headers.get("Authorization", "")
                if not auth.startswith("Bearer ") or auth[7:] != app["api_key"]:
                    return web.json_response({"error": "Unauthorized"}, status=401)
                return await handler(request)

            return middleware

        app.middlewares.append(auth_middleware)

        async def health(request: web.Request) -> web.Response:
            return web.json_response({"status": "ok", "worker_version": "0.1.0"})

        async def system_info(request: web.Request) -> web.Response:
            return web.json_response(
                {
                    "worker_version": "0.1.0",
                    "workspace_path": "/workspace/comfygit",
                    "default_mode": "docker",
                    "gpu": {"name": "RTX 4090", "memory_total_mb": 24576},
                    "ports": {"range_start": 8200, "range_end": 8210, "available": 10},
                }
            )

        async def list_instances(request: web.Request) -> web.Response:
            return web.json_response({"instances": list(app["instances"].values())})

        async def create_instance(request: web.Request) -> web.Response:
            data = await request.json()
            inst_id = "inst_test123"
            instance = {
                "id": inst_id,
                "name": f"deploy-{data.get('name', 'unnamed')}",
                "status": "deploying",
                "assigned_port": 8188,
                "mode": data.get("mode", "docker"),
            }
            app["instances"][inst_id] = instance
            return web.json_response(instance, status=201)

        async def get_instance(request: web.Request) -> web.Response:
            inst_id = request.match_info["id"]
            if inst_id not in app["instances"]:
                return web.json_response({"error": "Not found"}, status=404)
            return web.json_response(app["instances"][inst_id])

        async def stop_instance(request: web.Request) -> web.Response:
            inst_id = request.match_info["id"]
            if inst_id not in app["instances"]:
                return web.json_response({"error": "Not found"}, status=404)
            app["instances"][inst_id]["status"] = "stopped"
            return web.json_response(app["instances"][inst_id])

        async def start_instance(request: web.Request) -> web.Response:
            inst_id = request.match_info["id"]
            if inst_id not in app["instances"]:
                return web.json_response({"error": "Not found"}, status=404)
            app["instances"][inst_id]["status"] = "running"
            return web.json_response(app["instances"][inst_id])

        async def terminate_instance(request: web.Request) -> web.Response:
            inst_id = request.match_info["id"]
            if inst_id not in app["instances"]:
                return web.json_response({"error": "Not found"}, status=404)
            del app["instances"][inst_id]
            return web.json_response({"id": inst_id, "status": "terminated"})

        app.router.add_get("/api/v1/health", health)
        app.router.add_get("/api/v1/system/info", system_info)
        app.router.add_get("/api/v1/instances", list_instances)
        app.router.add_post("/api/v1/instances", create_instance)
        app.router.add_get("/api/v1/instances/{id}", get_instance)
        app.router.add_post("/api/v1/instances/{id}/stop", stop_instance)
        app.router.add_post("/api/v1/instances/{id}/start", start_instance)
        app.router.add_delete("/api/v1/instances/{id}", terminate_instance)

        return app

    def make_worker_client(self) -> CustomWorkerClient:
        """Create CustomWorkerClient pointing to test server."""
        # The test server runs on a random port - get it from self.server
        port = self.server.port
        return CustomWorkerClient(
            host="127.0.0.1",
            port=port,
            api_key="cg_wk_test123",
        )

    @unittest_run_loop
    async def test_test_connection_succeeds(self) -> None:
        """test_connection should return success with worker info."""
        client = self.make_worker_client()
        result = await client.test_connection()

        assert result["success"] is True
        assert "worker_version" in result

    @unittest_run_loop
    async def test_test_connection_fails_with_bad_key(self) -> None:
        """test_connection should return failure with wrong key."""
        port = self.server.port
        client = CustomWorkerClient(host="127.0.0.1", port=port, api_key="wrong")
        result = await client.test_connection()

        assert result["success"] is False
        assert "error" in result

    @unittest_run_loop
    async def test_get_system_info(self) -> None:
        """get_system_info should return worker details."""
        client = self.make_worker_client()
        info = await client.get_system_info()

        assert info["worker_version"] == "0.1.0"
        assert info["gpu"]["name"] == "RTX 4090"
        assert info["ports"]["available"] == 10

    @unittest_run_loop
    async def test_list_instances(self) -> None:
        """list_instances should return instance list."""
        client = self.make_worker_client()
        instances = await client.list_instances()

        assert isinstance(instances, list)

    @unittest_run_loop
    async def test_create_instance(self) -> None:
        """create_instance should create and return instance."""
        client = self.make_worker_client()
        instance = await client.create_instance(
            import_source="https://github.com/user/env.git",
            name="test-deploy",
            mode="docker",
        )

        assert "id" in instance
        assert instance["status"] == "deploying"
        assert instance["assigned_port"] == 8188

    @unittest_run_loop
    async def test_get_instance(self) -> None:
        """get_instance should return instance details."""
        client = self.make_worker_client()

        # Create first
        created = await client.create_instance(
            import_source="https://github.com/x/y.git"
        )

        # Get it
        instance = await client.get_instance(created["id"])
        assert instance["id"] == created["id"]

    @unittest_run_loop
    async def test_stop_instance(self) -> None:
        """stop_instance should stop and return instance."""
        client = self.make_worker_client()

        created = await client.create_instance(
            import_source="https://github.com/x/y.git"
        )
        result = await client.stop_instance(created["id"])

        assert result["status"] == "stopped"

    @unittest_run_loop
    async def test_start_instance(self) -> None:
        """start_instance should start and return instance."""
        client = self.make_worker_client()

        created = await client.create_instance(
            import_source="https://github.com/x/y.git"
        )
        await client.stop_instance(created["id"])
        result = await client.start_instance(created["id"])

        assert result["status"] == "running"

    @unittest_run_loop
    async def test_terminate_instance(self) -> None:
        """terminate_instance should terminate instance."""
        client = self.make_worker_client()

        created = await client.create_instance(
            import_source="https://github.com/x/y.git"
        )
        result = await client.terminate_instance(created["id"])

        assert result["status"] == "terminated"
