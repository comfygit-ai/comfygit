"""Tests for unified instance aggregation across providers.

TDD: These tests verify that `cg-deploy instances` aggregates from both
RunPod and custom workers, with proper namespacing and filtering.
"""

from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from comfygit_deploy.commands.instances import (
    handle_instances,
    handle_start,
    handle_stop,
    handle_terminate,
)
from comfygit_deploy.config import DeployConfig


@pytest.fixture
def config_with_worker(tmp_path: Path) -> DeployConfig:
    """Config with a registered custom worker."""
    config = DeployConfig(tmp_path / "config.json")
    config.add_worker("my-gpu", "192.168.1.50", 9090, "cg_wk_test123")
    config.save()
    return config


@pytest.fixture
def mock_runpod_pods() -> list[dict]:
    """Sample RunPod pods."""
    return [
        {
            "id": "pod_abc123",
            "name": "my-comfy-deploy",
            "desiredStatus": "RUNNING",
            "machine": {"gpuDisplayName": "RTX 4090"},
            "costPerHr": 0.74,
            "runtime": {"ports": [{"privatePort": 8188, "publicPort": 12345}]},
        }
    ]


@pytest.fixture
def mock_worker_instances() -> list[dict]:
    """Sample custom worker instances."""
    return [
        {
            "id": "inst_def456",
            "name": "deploy-my-env",
            "status": "running",
            "mode": "docker",
            "assigned_port": 8188,
            "comfyui_url": "http://192.168.1.50:8188",
        }
    ]


class TestUnifiedInstancesList:
    """Tests for unified instances listing."""

    def test_instances_works_without_runpod_key(
        self, config_with_worker: DeployConfig, mock_worker_instances: list[dict]
    ) -> None:
        """Should list custom worker instances even without RunPod API key."""
        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.CustomWorkerClient"
            ) as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.list_instances.return_value = mock_worker_instances
            mock_client_class.return_value = mock_client

            args = Namespace(provider=None, status=None, json=False)
            result = handle_instances(args)

            assert result == 0
            mock_client.list_instances.assert_called_once()

    def test_instances_aggregates_both_providers(
        self,
        config_with_worker: DeployConfig,
        mock_runpod_pods: list[dict],
        mock_worker_instances: list[dict],
    ) -> None:
        """Should aggregate instances from RunPod AND custom workers."""
        # Set RunPod key
        config_with_worker.runpod_api_key = "rpa_test"
        config_with_worker.save()

        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.RunPodClient"
            ) as mock_runpod_class,
            patch(
                "comfygit_deploy.commands.instances.CustomWorkerClient"
            ) as mock_custom_class,
        ):
            # Mock RunPod client
            mock_runpod = AsyncMock()
            mock_runpod.list_pods.return_value = mock_runpod_pods
            mock_runpod_class.return_value = mock_runpod

            # Mock custom worker client
            mock_custom = AsyncMock()
            mock_custom.list_instances.return_value = mock_worker_instances
            mock_custom_class.return_value = mock_custom

            args = Namespace(provider=None, status=None, json=False)
            result = handle_instances(args)

            assert result == 0
            mock_runpod.list_pods.assert_called_once()
            mock_custom.list_instances.assert_called_once()

    def test_instances_filter_runpod_only(
        self, config_with_worker: DeployConfig, mock_runpod_pods: list[dict]
    ) -> None:
        """--provider runpod should only query RunPod."""
        config_with_worker.runpod_api_key = "rpa_test"
        config_with_worker.save()

        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.RunPodClient"
            ) as mock_runpod_class,
            patch(
                "comfygit_deploy.commands.instances.CustomWorkerClient"
            ) as mock_custom_class,
        ):
            mock_runpod = AsyncMock()
            mock_runpod.list_pods.return_value = mock_runpod_pods
            mock_runpod_class.return_value = mock_runpod

            mock_custom = AsyncMock()
            mock_custom_class.return_value = mock_custom

            args = Namespace(provider="runpod", status=None, json=False)
            result = handle_instances(args)

            assert result == 0
            mock_runpod.list_pods.assert_called_once()
            mock_custom.list_instances.assert_not_called()

    def test_instances_filter_custom_only(
        self, config_with_worker: DeployConfig, mock_worker_instances: list[dict]
    ) -> None:
        """--provider custom should only query custom workers."""
        config_with_worker.runpod_api_key = "rpa_test"
        config_with_worker.save()

        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.RunPodClient"
            ) as mock_runpod_class,
            patch(
                "comfygit_deploy.commands.instances.CustomWorkerClient"
            ) as mock_custom_class,
        ):
            mock_runpod = AsyncMock()
            mock_runpod_class.return_value = mock_runpod

            mock_custom = AsyncMock()
            mock_custom.list_instances.return_value = mock_worker_instances
            mock_custom_class.return_value = mock_custom

            args = Namespace(provider="custom", status=None, json=False)
            result = handle_instances(args)

            assert result == 0
            mock_runpod.list_pods.assert_not_called()
            mock_custom.list_instances.assert_called_once()

    def test_instances_gracefully_handles_offline_worker(
        self, config_with_worker: DeployConfig
    ) -> None:
        """Should continue even if a custom worker is offline."""
        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.CustomWorkerClient"
            ) as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.list_instances.side_effect = Exception("Connection refused")
            mock_client_class.return_value = mock_client

            args = Namespace(provider=None, status=None, json=False)
            result = handle_instances(args)

            # Should succeed with empty results, not error
            assert result == 0

    def test_instances_json_includes_provider_field(
        self, config_with_worker: DeployConfig, mock_worker_instances: list[dict], capsys
    ) -> None:
        """JSON output should include provider and worker_name fields."""
        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.CustomWorkerClient"
            ) as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.list_instances.return_value = mock_worker_instances
            mock_client_class.return_value = mock_client

            args = Namespace(provider=None, status=None, json=True)
            result = handle_instances(args)

            assert result == 0
            captured = capsys.readouterr()
            import json
            output = json.loads(captured.out)

            # Should have converted instances with provider info
            assert len(output) > 0
            assert output[0]["provider"] == "custom"
            assert output[0]["worker_name"] == "my-gpu"


class TestProviderAwareInstanceActions:
    """Tests for start/stop/terminate routing to correct provider."""

    def test_start_routes_to_custom_worker(
        self, config_with_worker: DeployConfig
    ) -> None:
        """start <worker>:<id> should route to custom worker."""
        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.CustomWorkerClient"
            ) as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.start_instance.return_value = {
                "id": "inst_abc",
                "status": "running",
            }
            mock_client_class.return_value = mock_client

            args = Namespace(instance_id="my-gpu:inst_abc")
            result = handle_start(args)

            assert result == 0
            mock_client.start_instance.assert_called_once_with("inst_abc")

    def test_start_routes_to_runpod(
        self, config_with_worker: DeployConfig, mock_runpod_pods: list[dict]
    ) -> None:
        """start <pod_id> (no colon) should route to RunPod."""
        config_with_worker.runpod_api_key = "rpa_test"
        config_with_worker.save()

        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.RunPodClient"
            ) as mock_runpod_class,
        ):
            mock_runpod = AsyncMock()
            mock_runpod.start_pod.return_value = {"id": "pod_abc", "desiredStatus": "RUNNING"}
            mock_runpod_class.return_value = mock_runpod

            args = Namespace(instance_id="pod_abc123")
            result = handle_start(args)

            assert result == 0
            mock_runpod.start_pod.assert_called_once_with("pod_abc123")

    def test_stop_routes_to_custom_worker(
        self, config_with_worker: DeployConfig
    ) -> None:
        """stop <worker>:<id> should route to custom worker."""
        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.CustomWorkerClient"
            ) as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.stop_instance.return_value = {
                "id": "inst_abc",
                "status": "stopped",
            }
            mock_client_class.return_value = mock_client

            args = Namespace(instance_id="my-gpu:inst_abc")
            result = handle_stop(args)

            assert result == 0
            mock_client.stop_instance.assert_called_once_with("inst_abc")

    def test_terminate_routes_to_custom_worker(
        self, config_with_worker: DeployConfig
    ) -> None:
        """terminate <worker>:<id> should route to custom worker."""
        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.CustomWorkerClient"
            ) as mock_client_class,
            patch("builtins.input", return_value="y"),  # Confirm termination
        ):
            mock_client = AsyncMock()
            mock_client.terminate_instance.return_value = {
                "id": "inst_abc",
                "status": "terminated",
            }
            mock_client_class.return_value = mock_client

            args = Namespace(instance_id="my-gpu:inst_abc", force=False, keep_env=False)
            result = handle_terminate(args)

            assert result == 0
            mock_client.terminate_instance.assert_called_once_with("inst_abc", keep_env=False)

    def test_terminate_force_skips_confirmation(
        self, config_with_worker: DeployConfig
    ) -> None:
        """terminate --force should skip confirmation prompt."""
        with (
            patch(
                "comfygit_deploy.commands.instances.DeployConfig",
                return_value=config_with_worker,
            ),
            patch(
                "comfygit_deploy.commands.instances.CustomWorkerClient"
            ) as mock_client_class,
            patch("builtins.input") as mock_input,
        ):
            mock_client = AsyncMock()
            mock_client.terminate_instance.return_value = {
                "id": "inst_abc",
                "status": "terminated",
            }
            mock_client_class.return_value = mock_client

            args = Namespace(instance_id="my-gpu:inst_abc", force=True, keep_env=False)
            result = handle_terminate(args)

            assert result == 0
            mock_input.assert_not_called()  # No confirmation prompt


class TestInstanceIdParsing:
    """Tests for parsing namespaced instance IDs."""

    def test_parse_custom_instance_id(self) -> None:
        """Should parse worker_name:instance_id format."""
        from comfygit_deploy.commands.instances import parse_instance_id

        worker, inst_id = parse_instance_id("my-gpu:inst_abc123")
        assert worker == "my-gpu"
        assert inst_id == "inst_abc123"

    def test_parse_runpod_instance_id(self) -> None:
        """Plain ID without colon should be RunPod."""
        from comfygit_deploy.commands.instances import parse_instance_id

        worker, inst_id = parse_instance_id("pod_abc123")
        assert worker is None
        assert inst_id == "pod_abc123"

    def test_parse_handles_multiple_colons(self) -> None:
        """Should split on first colon only."""
        from comfygit_deploy.commands.instances import parse_instance_id

        worker, inst_id = parse_instance_id("my-gpu:inst:with:colons")
        assert worker == "my-gpu"
        assert inst_id == "inst:with:colons"
