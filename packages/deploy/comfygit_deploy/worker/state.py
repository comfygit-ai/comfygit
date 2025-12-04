"""Worker instance state management with persistent port allocation.

Manages instance lifecycle and persists state to JSON for recovery across restarts.
"""

import json
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class InstanceState:
    """State for a single ComfyUI instance."""

    id: str
    name: str
    environment_name: str
    mode: str  # "docker" | "native"
    assigned_port: int
    import_source: str
    branch: str | None = None
    status: str = "stopped"  # "deploying" | "running" | "stopped" | "error"
    container_id: str | None = None
    pid: int | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "id": self.id,
            "name": self.name,
            "environment_name": self.environment_name,
            "mode": self.mode,
            "assigned_port": self.assigned_port,
            "import_source": self.import_source,
            "branch": self.branch,
            "status": self.status,
            "container_id": self.container_id,
            "pid": self.pid,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InstanceState":
        """Deserialize from dict."""
        return cls(
            id=data["id"],
            name=data["name"],
            environment_name=data["environment_name"],
            mode=data["mode"],
            assigned_port=data["assigned_port"],
            import_source=data["import_source"],
            branch=data.get("branch"),
            status=data.get("status", "stopped"),
            container_id=data.get("container_id"),
            pid=data.get("pid"),
            created_at=data.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
        )


class PortAllocator:
    """Manages port allocation for instances.

    Ports are allocated at instance creation and persist across stop/start.
    Only released when instance is terminated.
    """

    def __init__(
        self,
        state_file: Path,
        base_port: int = 8188,
        max_instances: int = 10,
    ):
        """Initialize port allocator.

        Args:
            state_file: Path to state JSON file
            base_port: First port in range
            max_instances: Maximum concurrent instances
        """
        self.state_file = state_file
        self.base_port = base_port
        self.max_port = base_port + max_instances
        self.allocated: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        """Load allocated ports from state file."""
        if not self.state_file.exists():
            return

        try:
            data = json.loads(self.state_file.read_text())
            instances = data.get("instances", {})
            for inst_id, inst_data in instances.items():
                if "assigned_port" in inst_data:
                    self.allocated[inst_id] = inst_data["assigned_port"]
        except (json.JSONDecodeError, OSError):
            pass

    def _persist(self) -> None:
        """Persist port allocations (called from WorkerState.save)."""
        pass  # WorkerState handles persistence

    def _is_port_in_use(self, port: int) -> bool:
        """Check if port is currently in use by another process."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return False
            except OSError:
                return True

    def allocate(self, instance_id: str) -> int:
        """Allocate port for instance.

        Args:
            instance_id: Unique instance identifier

        Returns:
            Allocated port number

        Raises:
            RuntimeError: If no ports available
        """
        # Return existing allocation if present
        if instance_id in self.allocated:
            return self.allocated[instance_id]

        # Find next available port
        used_ports = set(self.allocated.values())
        for port in range(self.base_port, self.max_port):
            if port not in used_ports:
                self.allocated[instance_id] = port
                return port

        raise RuntimeError("No available ports")

    def release(self, instance_id: str) -> None:
        """Release port when instance terminated."""
        self.allocated.pop(instance_id, None)


class WorkerState:
    """Persistent state for all instances managed by this worker."""

    def __init__(self, state_file: Path):
        """Initialize worker state.

        Args:
            state_file: Path to instances.json
        """
        self.state_file = state_file
        self.instances: dict[str, InstanceState] = {}
        self._load()

    def _load(self) -> None:
        """Load state from disk."""
        if not self.state_file.exists():
            return

        try:
            data = json.loads(self.state_file.read_text())
            for inst_id, inst_data in data.get("instances", {}).items():
                self.instances[inst_id] = InstanceState.from_dict(inst_data)
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        """Persist state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1",
            "instances": {
                inst_id: inst.to_dict() for inst_id, inst in self.instances.items()
            },
        }
        self.state_file.write_text(json.dumps(data, indent=2))

    def add_instance(self, instance: InstanceState) -> None:
        """Add instance to state."""
        self.instances[instance.id] = instance

    def remove_instance(self, instance_id: str) -> None:
        """Remove instance from state."""
        self.instances.pop(instance_id, None)

    def update_status(
        self,
        instance_id: str,
        status: str,
        container_id: str | None = None,
        pid: int | None = None,
    ) -> None:
        """Update instance status.

        Args:
            instance_id: Instance to update
            status: New status
            container_id: Container ID (for docker mode)
            pid: Process ID (for native mode)
        """
        if instance_id not in self.instances:
            return

        self.instances[instance_id].status = status
        if container_id is not None:
            self.instances[instance_id].container_id = container_id
        if pid is not None:
            self.instances[instance_id].pid = pid
