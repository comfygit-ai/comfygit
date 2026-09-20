"""Real HTTP concurrency without a GPU, using core's real manifest/OS locks."""
import asyncio
import json
from typing import Any, cast

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from comfygit_core.core.environment import Environment
from comfygit_core.managers.pyproject_manager import PyprojectManager
from comfygit_core.models import CDEnvironmentBusyError, EnvironmentLockOwner
from comfygit_core.utils.environment_lock import EnvironmentOperationLock
from comfygit_studio.executor import RunExecutionResult
from comfygit_studio.runtime import (
    SERVE_STATE_KEY,
    ServeConfig,
    ServeState,
    contracts_handler,
    run_contract_handler,
    single_contract_handler,
)


def environment(path):
    path.mkdir(exist_ok=True)
    env = Environment.__new__(Environment)
    env.name = "test"
    env.path = path
    env.cec_path = path
    env._operation_lock = EnvironmentOperationLock(path / ".comfygit.lock")
    env.__dict__["pyproject"] = PyprojectManager(path / "pyproject.toml")
    (path / "pyproject.toml").write_text('''[project]
name = "test"
[tool.comfygit.workflows.demo]
path = "workflows/demo.json"
[tool.comfygit.workflows.demo.execution_contract]
api_prompt_file = "prompt.json"
[tool.comfygit.workflows.demo.execution_contract.contracts.default]
display_name = "Version one"
inputs = [{name="seed", type="integer", node_id="1", field_key="seed"}]
outputs = []
''')
    (path / "prompt.json").write_text(json.dumps({"1": {"class_type": "Test", "inputs": {"seed": 0}}}))
    return env


@pytest.mark.asyncio
async def test_four_runs_polling_and_mutation_use_consistent_snapshots(tmp_path, caplog):
    env = environment(tmp_path)
    started, finish = asyncio.Event(), asyncio.Event()
    submitted = []
    fail_after_submit = False

    class Executor:
        async def execute(self, request):
            submitted.append(request.prompt)
            prompt_id = str(len(submitted))
            await request.on_submitted(prompt_id)
            if fail_after_submit:
                raise CDEnvironmentBusyError("test.lock", EnvironmentLockOwner())
            if len(submitted) == 4:
                started.set()
            await finish.wait()
            return RunExecutionResult(status="completed", prompt_id=prompt_id)

    async with aiohttp.ClientSession() as session:
        state = ServeState(env, ServeConfig(host="127.0.0.1", port=0, comfy_url="http://unused"), session)
        state.executor = cast(Any, Executor())
        app = web.Application()
        app[SERVE_STATE_KEY] = state
        app.router.add_get("/contracts", contracts_handler)
        app.router.add_get("/contracts/{workflow}/{contract}", single_contract_handler)
        app.router.add_post("/contracts/{workflow}/{contract}/run", run_contract_handler)
        async with TestClient(TestServer(app)) as client:
            before = await (await client.get("/contracts")).json()
            # An independent reader must not cause the old read/read HTTP 500.
            with EnvironmentOperationLock(env.path / ".comfygit.lock").read():
                responses = await asyncio.gather(*(client.get("/contracts") for _ in range(4)))
            assert all(response.status == 200 for response in responses)

            pending = [asyncio.create_task(client.post("/contracts/demo/default/run", json={"inputs": {"seed": i}, "wait": True})) for i in range(4)]
            try:
                await asyncio.wait_for(started.wait(), 5)
                assert (await client.get("/contracts")).status == 200
                # No lock is retained during generation. Simulate an incomplete update.
                with EnvironmentOperationLock(env.path / ".comfygit.lock").named("save_workflow"):
                    manifest_path = env.path / "pyproject.toml"
                    manifest_path.write_text(manifest_path.read_text().replace("Version one", "Version two"))
                    for method, path in [("GET", "/contracts"), ("GET", "/contracts/demo/default"), ("POST", "/contracts/demo/default/run")]:
                        response = await client.request(method, path, json={})
                        assert response.status == 503
                        body = await response.json()
                        assert body["error"] == "environment_busy"
                        assert body["owner"]["operation"] == "save_workflow"
                        assert body["request_id"] == response.headers["X-Request-ID"]
                        assert response.headers["Retry-After"] == "1"
                        assert body["request_id"] in caplog.text
                    (env.path / "prompt.json").write_text('{"1":{"class_type":"TestV2","inputs":{"seed":0}}}')
                assert len(submitted) == 4
                after = await (await client.get("/contracts")).json()
                assert before["manifest_revision"] != after["manifest_revision"]
                finish.set()
                responses = await asyncio.gather(*pending)
                results = [await response.json() for response in responses]
                assert all(response.status == 200 for response in responses)
                assert all(result["manifest_revision"] == before["manifest_revision"] for result in results)
                assert sorted(prompt["1"]["inputs"]["seed"] for prompt in submitted) == [0, 1, 2, 3]
                assert all(prompt["1"]["class_type"] == "Test" for prompt in submitted)
                response = await client.post("/contracts/demo/default/run", json={"inputs": {"seed": 9}, "wait": True})
                assert response.status == 200
                assert (await response.json())["manifest_revision"] == after["manifest_revision"]
                assert submitted[-1]["1"]["class_type"] == "TestV2"
                # A busy-like failure inside an executor is NOT proof of no
                # submission and must never advertise a retryable 503.
                fail_after_submit = True
                response = await client.post("/contracts/demo/default/run", json={"inputs": {"seed": 10}, "wait": True})
                assert response.status == 500
                failure = await response.json()
                assert failure["error"] == "internal_error"
                assert "retryable" not in failure
                assert failure["request_id"] in caplog.text
                assert "Traceback" in caplog.text
            finally:
                finish.set()
                await asyncio.gather(*pending, return_exceptions=True)
        state.state_store.close()
