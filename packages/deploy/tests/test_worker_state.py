"""Tests for worker instance state management.

TDD: Tests written first - should FAIL until implementation exists.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from comfygit_deploy.worker.state import (
    InstanceState,
    PortAllocator,
    WorkerState,
)


class TestPortAllocator:
    """Tests for port allocation across instances."""

    @patch.object(PortAllocator, "_is_port_in_use", return_value=False)
    def test_allocate_returns_first_available_port(
        self, mock_port_check, tmp_path: Path
    ) -> None:
        """Should allocate ports starting from base_port."""
        state_file = tmp_path / "instances.json"
        allocator = PortAllocator(state_file, base_port=8188, max_instances=10)

        port = allocator.allocate("inst_abc")
        assert port == 8188

    @patch.object(PortAllocator, "_is_port_in_use", return_value=False)
    def test_allocate_skips_used_ports(self, mock_port_check, tmp_path: Path) -> None:
        """Should skip already allocated ports."""
        state_file = tmp_path / "instances.json"
        allocator = PortAllocator(state_file, base_port=8188, max_instances=10)

        port1 = allocator.allocate("inst_a")
        port2 = allocator.allocate("inst_b")

        assert port1 == 8188
        assert port2 == 8189

    @patch.object(PortAllocator, "_is_port_in_use", return_value=False)
    def test_allocate_returns_same_port_for_existing_instance(
        self, mock_port_check, tmp_path: Path
    ) -> None:
        """Should return same port if instance already has one."""
        state_file = tmp_path / "instances.json"
        allocator = PortAllocator(state_file, base_port=8188, max_instances=10)

        port1 = allocator.allocate("inst_abc")
        port2 = allocator.allocate("inst_abc")

        assert port1 == port2 == 8188

    @patch.object(PortAllocator, "_is_port_in_use", return_value=False)
    def test_release_frees_port_for_reuse(
        self, mock_port_check, tmp_path: Path
    ) -> None:
        """Should release port when instance terminated."""
        state_file = tmp_path / "instances.json"
        allocator = PortAllocator(state_file, base_port=8188, max_instances=10)

        allocator.allocate("inst_a")
        allocator.allocate("inst_b")
        allocator.release("inst_a")
        port3 = allocator.allocate("inst_c")

        assert port3 == 8188  # Reuses released port

    @patch.object(PortAllocator, "_is_port_in_use", return_value=False)
    def test_allocate_raises_when_no_ports_available(
        self, mock_port_check, tmp_path: Path
    ) -> None:
        """Should raise when all ports are in use."""
        state_file = tmp_path / "instances.json"
        allocator = PortAllocator(state_file, base_port=8188, max_instances=2)

        allocator.allocate("inst_a")
        allocator.allocate("inst_b")

        with pytest.raises(RuntimeError, match="No available ports"):
            allocator.allocate("inst_c")

    def test_allocate_skips_ports_in_use_by_other_processes(
        self, tmp_path: Path
    ) -> None:
        """Should skip ports that are in use by external processes."""
        state_file = tmp_path / "instances.json"
        allocator = PortAllocator(state_file, base_port=8188, max_instances=10)

        # Mock: port 8188 is in use, 8189 is free
        with patch.object(
            allocator, "_is_port_in_use", side_effect=[True, False]
        ):
            port = allocator.allocate("inst_a")
            assert port == 8189  # Skipped 8188 because it was in use


class TestInstanceState:
    """Tests for single instance state."""

    def test_instance_state_creation(self) -> None:
        """Should create instance state with required fields."""
        state = InstanceState(
            id="inst_abc123",
            name="deploy-my-env-20241203",
            environment_name="deploy-my-env-20241203",
            mode="docker",
            assigned_port=8188,
            import_source="https://github.com/user/env.git",
        )

        assert state.id == "inst_abc123"
        assert state.name == "deploy-my-env-20241203"
        assert state.assigned_port == 8188
        assert state.status == "stopped"  # default
        assert state.container_id is None
        assert state.pid is None

    def test_instance_state_to_dict(self) -> None:
        """Should serialize to dict for JSON storage."""
        state = InstanceState(
            id="inst_abc",
            name="test",
            environment_name="test",
            mode="docker",
            assigned_port=8188,
            import_source="https://github.com/x/y.git",
        )

        d = state.to_dict()
        assert d["id"] == "inst_abc"
        assert d["assigned_port"] == 8188
        assert "created_at" in d

    def test_instance_state_from_dict(self) -> None:
        """Should deserialize from dict."""
        data = {
            "id": "inst_xyz",
            "name": "test-env",
            "environment_name": "test-env",
            "mode": "native",
            "assigned_port": 8189,
            "import_source": "https://github.com/a/b.git",
            "status": "running",
            "pid": 12345,
            "created_at": "2024-12-03T10:00:00Z",
        }

        state = InstanceState.from_dict(data)
        assert state.id == "inst_xyz"
        assert state.mode == "native"
        assert state.pid == 12345
        assert state.status == "running"


class TestWorkerState:
    """Tests for overall worker state persistence."""

    def test_worker_state_saves_and_loads_instances(self, tmp_path: Path) -> None:
        """Should persist instances across saves/loads."""
        state_file = tmp_path / "instances.json"
        state = WorkerState(state_file)

        instance = InstanceState(
            id="inst_abc",
            name="test",
            environment_name="test",
            mode="docker",
            assigned_port=8188,
            import_source="https://github.com/x/y.git",
        )
        state.add_instance(instance)
        state.save()

        # Load fresh
        state2 = WorkerState(state_file)
        assert "inst_abc" in state2.instances
        assert state2.instances["inst_abc"].assigned_port == 8188

    def test_worker_state_removes_instance(self, tmp_path: Path) -> None:
        """Should remove instance and persist."""
        state_file = tmp_path / "instances.json"
        state = WorkerState(state_file)

        state.add_instance(
            InstanceState(
                id="inst_a",
                name="a",
                environment_name="a",
                mode="docker",
                assigned_port=8188,
                import_source="x",
            )
        )
        state.add_instance(
            InstanceState(
                id="inst_b",
                name="b",
                environment_name="b",
                mode="docker",
                assigned_port=8189,
                import_source="y",
            )
        )
        state.remove_instance("inst_a")
        state.save()

        state2 = WorkerState(state_file)
        assert "inst_a" not in state2.instances
        assert "inst_b" in state2.instances

    def test_worker_state_update_instance_status(self, tmp_path: Path) -> None:
        """Should update instance status."""
        state_file = tmp_path / "instances.json"
        state = WorkerState(state_file)

        state.add_instance(
            InstanceState(
                id="inst_x",
                name="x",
                environment_name="x",
                mode="docker",
                assigned_port=8188,
                import_source="z",
            )
        )

        state.update_status("inst_x", "running", container_id="abc123")

        assert state.instances["inst_x"].status == "running"
        assert state.instances["inst_x"].container_id == "abc123"


class TestOrphanInstanceCleanup:
    """Tests for cleaning up instances with missing environments on startup."""

    def test_load_removes_instances_without_complete_marker(
        self, tmp_path: Path
    ) -> None:
        """Instances without .cec/.complete marker should be removed on load."""
        state_file = tmp_path / "instances.json"
        workspace = tmp_path / "workspace"
        envs_dir = workspace / "environments"
        envs_dir.mkdir(parents=True)

        # Create environment dir without .complete marker
        (envs_dir / "orphan-env").mkdir()

        # Create valid environment with marker
        valid_env = envs_dir / "valid-env"
        valid_env.mkdir()
        (valid_env / ".cec").mkdir()
        (valid_env / ".cec" / ".complete").touch()

        # Pre-populate state file with both instances
        state_file.write_text(
            json.dumps(
                {
                    "version": "1",
                    "instances": {
                        "inst_orphan": {
                            "id": "inst_orphan",
                            "name": "orphan-env",
                            "environment_name": "orphan-env",
                            "mode": "native",
                            "assigned_port": 8200,
                            "import_source": "x",
                            "status": "running",
                        },
                        "inst_valid": {
                            "id": "inst_valid",
                            "name": "valid-env",
                            "environment_name": "valid-env",
                            "mode": "native",
                            "assigned_port": 8201,
                            "import_source": "y",
                            "status": "running",
                        },
                    },
                }
            )
        )

        # Load state - should remove orphan, keep valid
        state = WorkerState(state_file, workspace_path=workspace)

        assert "inst_orphan" not in state.instances
        assert "inst_valid" in state.instances

    def test_load_removes_instances_with_missing_environment_dir(
        self, tmp_path: Path
    ) -> None:
        """Instances with completely missing environment dir should be removed."""
        state_file = tmp_path / "instances.json"
        workspace = tmp_path / "workspace"
        envs_dir = workspace / "environments"
        envs_dir.mkdir(parents=True)

        # No environment directories exist at all

        state_file.write_text(
            json.dumps(
                {
                    "version": "1",
                    "instances": {
                        "inst_missing": {
                            "id": "inst_missing",
                            "name": "deleted-env",
                            "environment_name": "deleted-env",
                            "mode": "native",
                            "assigned_port": 8200,
                            "import_source": "x",
                            "status": "stopped",
                        },
                    },
                }
            )
        )

        state = WorkerState(state_file, workspace_path=workspace)

        assert "inst_missing" not in state.instances
        assert len(state.instances) == 0

    def test_load_persists_cleanup_to_disk(self, tmp_path: Path) -> None:
        """Cleanup should persist to disk so subsequent loads stay clean."""
        state_file = tmp_path / "instances.json"
        workspace = tmp_path / "workspace"
        envs_dir = workspace / "environments"
        envs_dir.mkdir(parents=True)

        # Pre-populate with orphan
        state_file.write_text(
            json.dumps(
                {
                    "version": "1",
                    "instances": {
                        "inst_orphan": {
                            "id": "inst_orphan",
                            "name": "gone",
                            "environment_name": "gone",
                            "mode": "native",
                            "assigned_port": 8200,
                            "import_source": "x",
                            "status": "running",
                        },
                    },
                }
            )
        )

        # First load cleans up
        state = WorkerState(state_file, workspace_path=workspace)
        assert len(state.instances) == 0

        # Verify disk was updated
        data = json.loads(state_file.read_text())
        assert len(data["instances"]) == 0
