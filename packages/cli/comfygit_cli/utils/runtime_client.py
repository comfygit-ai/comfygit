"""Local CLI adapter for the runtime advertised by cg run."""
from __future__ import annotations

import math
import time
from pathlib import Path

import requests
from comfygit_core.runtime import (
    RUNTIME_RESTART_ROUTE,
    RUNTIME_STATUS_ROUTE,
    read_runtime_advertisement,
    readiness_host_for_bind,
)


class RuntimeClient:
    def __init__(self, workspace: Path, environment: str):
        self.environment = environment
        info = read_runtime_advertisement(workspace, environment)
        if not info:
            raise ValueError(
                f"No current cg run advertisement for {environment}. "
                "Start it with this version of cg run; older running supervisors need one relaunch."
            )
        host = readiness_host_for_bind(info["host"])
        if ":" in host:
            host = f"[{host}]"
        self.url = f"http://{host}:{int(info['port'])}"
        self.instance_id = info["instance_id"]

    def _request(self, path: str, payload: dict | None = None, *, timeout: float = 10) -> dict:
        with requests.Session() as session:
            session.trust_env = False
            if payload is None:
                response = session.get(self.url + path, timeout=timeout)
            else:
                response = session.post(self.url + path, json=payload, timeout=25)
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid runtime response")
            if not response.ok:
                raise ValueError(data.get("error", f"Runtime HTTP {response.status_code}"))
            return data

    def status(self, *, timeout: float = 10) -> dict:
        data = self._request(RUNTIME_STATUS_ROUTE, timeout=timeout)
        if data.get("environment") != self.environment or data.get("instance_id") != self.instance_id:
            raise ValueError("Runtime advertisement is stale or belongs to another environment")
        return data

    def restart(self, *, wait: bool, timeout: float) -> dict:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Readiness timeout must be positive")
        before = self.status()
        expected = {key: before[key] for key in ("environment", "instance_id", "generation")}
        result = self._request(RUNTIME_RESTART_ROUTE, expected)
        if not wait:
            return result
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.status(timeout=max(0.01, min(10, deadline - time.monotonic())))
            if status["generation"] > before["generation"] and status["ready"]:
                return {**status, "status": "ready"}
            time.sleep(0.25)
        raise TimeoutError("Restart not verified before timeout; inspect status/logs, do not resend automatically")
