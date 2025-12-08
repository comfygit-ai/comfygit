"""Tests for mDNS broadcasting."""

from unittest.mock import MagicMock, patch

from comfygit_deploy.worker.mdns import MDNSBroadcaster, get_local_ip


class TestGetLocalIP:
    """Tests for local IP detection."""

    def test_get_local_ip_returns_string(self) -> None:
        """get_local_ip returns an IP address string."""
        ip = get_local_ip()
        assert isinstance(ip, str)
        # Should be a valid IP format (basic check)
        parts = ip.split(".")
        assert len(parts) == 4

    def test_get_local_ip_fallback_on_error(self) -> None:
        """get_local_ip returns 127.0.0.1 on error."""
        with patch("socket.socket") as mock_socket:
            mock_socket.side_effect = Exception("Network error")
            ip = get_local_ip()
            assert ip == "127.0.0.1"


class TestMDNSBroadcaster:
    """Tests for mDNS broadcaster."""

    def test_broadcaster_init(self) -> None:
        """Broadcaster initializes with port and optional name."""
        broadcaster = MDNSBroadcaster(port=9090)
        assert broadcaster.port == 9090
        assert broadcaster.worker_name is not None  # Uses hostname

        broadcaster2 = MDNSBroadcaster(port=9090, worker_name="my-worker")
        assert broadcaster2.worker_name == "my-worker"

    def test_broadcaster_start_registers_service(self) -> None:
        """start() registers mDNS service."""
        with patch("comfygit_deploy.worker.mdns.Zeroconf") as mock_zc_class:
            mock_zc = MagicMock()
            mock_zc_class.return_value = mock_zc

            broadcaster = MDNSBroadcaster(port=9090, worker_name="test-worker")
            broadcaster.start()

            mock_zc.register_service.assert_called_once()
            assert broadcaster.zeroconf is not None
            assert broadcaster.service_info is not None

    def test_broadcaster_stop_unregisters_service(self) -> None:
        """stop() unregisters mDNS service."""
        with patch("comfygit_deploy.worker.mdns.Zeroconf") as mock_zc_class:
            mock_zc = MagicMock()
            mock_zc_class.return_value = mock_zc

            broadcaster = MDNSBroadcaster(port=9090)
            broadcaster.start()
            broadcaster.stop()

            mock_zc.unregister_service.assert_called_once()
            mock_zc.close.assert_called_once()
            assert broadcaster.zeroconf is None
