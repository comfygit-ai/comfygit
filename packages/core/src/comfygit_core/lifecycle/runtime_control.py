"""Identity-checked control of a ComfyUI child owned by an existing supervisor."""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from .comfyui_readiness import ComfyUIEndpoint

RUNTIME_STATUS_ROUTE = "/v2/comfygit/runtime"
RUNTIME_RESTART_ROUTE = "/v2/comfygit/runtime/restart"


class RuntimeControlError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ManagedRuntimeStatus:
    environment: str
    instance_id: str
    generation: int
    phase: str
    comfyui_url: str
    ready: bool
    queue_running: int | None
    queue_pending: int | None
    restart_pending: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeRestartReceipt:
    environment: str
    instance_id: str
    generation: int
    status: str = "accepted"

    def to_dict(self) -> dict:
        return asdict(self)


def runtime_advertisement_path(workspace: Path, environment: str) -> Path:
    # Avoid treating a caller-provided environment name as a filesystem path.
    key = hashlib.sha256(environment.encode()).hexdigest()
    return workspace / ".metadata" / "runtimes" / f"{key}.json"


def read_runtime_advertisement(workspace: Path, environment: str) -> dict | None:
    try:
        data = json.loads(runtime_advertisement_path(workspace, environment).read_text())
        if isinstance(data, dict) and data.get("environment") == environment:
            return data
    except (OSError, ValueError):
        pass
    return None


class ManagedRuntimeController:
    """Observe and restart through Manager; never signal guessed process IDs.

    Queue validation is a preflight, not an atomic drain of concurrent submitters.
    A generation advances only after the previous child has returned and sync
    has completed. Completion requires that new generation AND HTTP readiness.
    """

    def __init__(self, environment: str, endpoint: ComfyUIEndpoint, workspace_path: Path):
        self.instance_id = uuid.uuid4().hex
        self.environment = environment
        self.workspace_path = workspace_path.resolve()
        self.endpoint = endpoint
        self.generation = 0
        self.phase = "syncing"
        self.restart_pending = False
        self._lock = threading.RLock()

    def configure(self, environment: str, endpoint: ComfyUIEndpoint) -> None:
        with self._lock:
            self.environment = environment
            self.endpoint = endpoint
            self.phase = "syncing"

    def launching(self) -> None:
        with self._lock:
            self.generation += 1
            self.phase = "starting"
            self.restart_pending = False

    def exited(self) -> None:
        with self._lock:
            self.phase = "stopped"

    @property
    def comfyui_url(self) -> str:
        return self.endpoint.base_url

    def snapshot(self) -> ManagedRuntimeStatus:
        with self._lock:
            ready = False
            running = pending = None
            if self.phase == "starting":
                try:
                    with requests.Session() as session:
                        session.trust_env = False
                        response = session.get(f"{self.comfyui_url}/system_stats", timeout=2)
                        response.raise_for_status()
                        stats = response.json()
                        ready = isinstance(stats, dict) and "system" in stats
                        queue = session.get(f"{self.comfyui_url}/queue", timeout=2)
                        queue.raise_for_status()
                        data = queue.json()
                        if (isinstance(data, dict)
                                and isinstance(data.get("queue_running"), list)
                                and isinstance(data.get("queue_pending"), list)):
                            running, pending = len(data["queue_running"]), len(data["queue_pending"])
                except (requests.RequestException, ValueError):
                    pass
            return ManagedRuntimeStatus(
                environment=self.environment, instance_id=self.instance_id,
                generation=self.generation, phase="running" if ready else self.phase,
                comfyui_url=self.comfyui_url, ready=ready,
                queue_running=running, queue_pending=pending,
                restart_pending=self.restart_pending,
            )

    def restart(self, expected: dict) -> RuntimeRestartReceipt:
        with self._lock:
            if any(expected.get(key) != value for key, value in (
                ("environment", self.environment), ("instance_id", self.instance_id),
                ("generation", self.generation),
            )):
                raise RuntimeControlError("Runtime identity changed; inspect status again")
            if self.restart_pending:
                raise RuntimeControlError("Restart already requested; inspect status instead of retrying")
            status = self.snapshot()
            if not status.ready or status.queue_running is None or status.queue_pending is None:
                raise RuntimeControlError("Cannot verify ComfyUI readiness and queue; restart refused")
            if status.queue_running or status.queue_pending:
                raise RuntimeControlError("ComfyUI has running or pending work; restart refused")
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    identity = session.get(
                        f"{self.comfyui_url}/v2/comfygit/environments", timeout=5,
                    )
                    identity.raise_for_status()
                    data = identity.json()
                context = data.get("runtime_context", {})
                if data.get("orchestrator_active"):
                    # Manager may proxy /restart to a workspace-wide legacy owner.
                    # Do not let a named cg-run request restart another child.
                    raise RuntimeControlError(
                        "A legacy orchestrator is active; use its owner to restart instead"
                    )
                if (data.get("current") != self.environment
                        or context.get("bound_workspace") != str(self.workspace_path)
                        or not context.get("capabilities", {}).get("can_restart_current")):
                    raise RuntimeControlError("ComfyUI ownership or restart capability does not match")
            except (requests.RequestException, ValueError, AttributeError) as exc:
                raise RuntimeControlError("Cannot verify Manager ownership; restart refused") from exc
            self.restart_pending = True
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    response = session.post(
                        f"{self.comfyui_url}/v2/comfygit/orchestrator/restart", timeout=10,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict) or payload.get("status") not in {"restarting", "ok"}:
                        raise ValueError("unrecognized restart acknowledgement")
            except (requests.RequestException, ValueError) as exc:
                # The request may have reached Manager. Never auto-retry it.
                raise RuntimeControlError(
                    "Restart was not confirmed; inspect runtime/Manager before retrying", 502,
                ) from exc
            return RuntimeRestartReceipt(self.environment, self.instance_id, self.generation)
