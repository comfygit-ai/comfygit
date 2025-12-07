"""Tests for RunPod API client.

TDD: These tests are written first and should FAIL until runpod.py is implemented.
Tests use mock HTTP responses - no actual API calls.
"""

from unittest.mock import AsyncMock, patch

import pytest
from comfygit_deploy.providers.runpod import (
    DATA_CENTERS,
    GPU_TYPES,
    RunPodClient,
)


class TestRunPodClientInit:
    """Tests for RunPodClient initialization."""

    def test_client_requires_api_key(self) -> None:
        """Client should raise error if no API key provided."""
        with pytest.raises(ValueError, match="API key required"):
            RunPodClient("")

    def test_client_accepts_valid_api_key(self) -> None:
        """Client should accept valid API key."""
        client = RunPodClient("rpa_test123")
        assert client.api_key == "rpa_test123"


class TestRunPodClientStaticData:
    """Tests for static data (data centers, GPU types)."""

    def test_data_centers_available(self) -> None:
        """DATA_CENTERS should contain known regions."""
        assert len(DATA_CENTERS) > 0
        ids = [dc["id"] for dc in DATA_CENTERS]
        assert "US-IL-1" in ids
        assert "EU-NL-1" in ids

    def test_gpu_types_available(self) -> None:
        """GPU_TYPES should contain known GPU models."""
        assert len(GPU_TYPES) > 0
        assert "NVIDIA GeForce RTX 4090" in GPU_TYPES
        assert "NVIDIA A100 80GB PCIe" in GPU_TYPES


class TestRunPodClientHelpers:
    """Tests for static helper methods."""

    def test_get_comfyui_url_running_pod(self) -> None:
        """Should return proxy URL for running pod."""
        pod = {"id": "abc123", "desiredStatus": "RUNNING"}
        url = RunPodClient.get_comfyui_url(pod)
        assert url == "https://abc123-8188.proxy.runpod.net"

    def test_get_comfyui_url_custom_port(self) -> None:
        """Should use custom port in URL."""
        pod = {"id": "abc123", "desiredStatus": "RUNNING"}
        url = RunPodClient.get_comfyui_url(pod, port=3000)
        assert url == "https://abc123-3000.proxy.runpod.net"

    def test_get_comfyui_url_stopped_pod(self) -> None:
        """Should return None for non-running pod."""
        pod = {"id": "abc123", "desiredStatus": "EXITED"}
        url = RunPodClient.get_comfyui_url(pod)
        assert url is None

    def test_estimate_gpu_memory(self) -> None:
        """Should estimate correct memory for known GPUs."""
        assert RunPodClient._estimate_gpu_memory("NVIDIA GeForce RTX 4090") == 24
        assert RunPodClient._estimate_gpu_memory("NVIDIA A100 80GB PCIe") == 80
        assert RunPodClient._estimate_gpu_memory("Unknown GPU") == 24  # Default


@pytest.mark.asyncio
class TestRunPodClientAPI:
    """Tests for API methods (mocked)."""

    async def test_test_connection_success(self) -> None:
        """test_connection should return success with balance."""
        client = RunPodClient("rpa_test123")

        mock_response = {
            "data": {
                "myself": {
                    "id": "user123",
                    "clientBalance": 50.0,
                    "currentSpendPerHr": 0.5,
                    "spendLimit": 100,
                }
            }
        }

        with patch.object(client, "_graphql_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            result = await client.test_connection()

        assert result["success"] is True
        assert result["credit_balance"] == 50.0

    async def test_test_connection_invalid_key(self) -> None:
        """test_connection should return error for invalid key."""
        client = RunPodClient("rpa_invalid")

        with patch.object(client, "_graphql_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = {"data": {"myself": None}}
            result = await client.test_connection()

        assert result["success"] is False
        assert "error" in result

    async def test_list_pods(self) -> None:
        """list_pods should return list of pods."""
        client = RunPodClient("rpa_test123")

        mock_pods = [
            {"id": "pod1", "name": "test-pod-1", "desiredStatus": "RUNNING"},
            {"id": "pod2", "name": "test-pod-2", "desiredStatus": "EXITED"},
        ]

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_pods
            result = await client.list_pods()

        assert len(result) == 2
        assert result[0]["id"] == "pod1"

    async def test_get_pod(self) -> None:
        """get_pod should return single pod."""
        client = RunPodClient("rpa_test123")

        mock_pod = {"id": "pod1", "name": "test-pod", "desiredStatus": "RUNNING"}

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_pod
            result = await client.get_pod("pod1")

        assert result["id"] == "pod1"
        mock_get.assert_called_once()

    async def test_delete_pod(self) -> None:
        """delete_pod should return True on success."""
        client = RunPodClient("rpa_test123")

        with patch.object(client, "_delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = None
            result = await client.delete_pod("pod1")

        assert result is True
        mock_delete.assert_called_once()

    async def test_start_pod(self) -> None:
        """start_pod should use GraphQL mutation."""
        client = RunPodClient("rpa_test123")

        mock_response = {
            "data": {
                "podResume": {
                    "id": "pod1",
                    "desiredStatus": "RUNNING",
                    "costPerHr": 0.5,
                }
            }
        }

        with patch.object(client, "_graphql_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            result = await client.start_pod("pod1")

        assert result["id"] == "pod1"
        assert result["desiredStatus"] == "RUNNING"

    async def test_stop_pod(self) -> None:
        """stop_pod should use GraphQL mutation."""
        client = RunPodClient("rpa_test123")

        mock_response = {
            "data": {
                "podStop": {
                    "id": "pod1",
                    "desiredStatus": "EXITED",
                }
            }
        }

        with patch.object(client, "_graphql_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_response
            result = await client.stop_pod("pod1")

        assert result["id"] == "pod1"
        assert result["desiredStatus"] == "EXITED"

    async def test_list_network_volumes(self) -> None:
        """list_network_volumes should return volumes."""
        client = RunPodClient("rpa_test123")

        mock_volumes = [
            {"id": "vol1", "name": "my-volume", "dataCenterId": "US-IL-1", "size": 100},
        ]

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_volumes
            result = await client.list_network_volumes()

        assert len(result) == 1
        assert result[0]["id"] == "vol1"
