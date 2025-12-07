"""Tests for mDNS discovery scanning (client-side).

Phase 3: Tests for scanning the network to discover ComfyGit workers.
"""

from unittest.mock import MagicMock, patch

from comfygit_deploy.worker.mdns import SERVICE_TYPE


class TestMDNSScanner:
    """Tests for mDNS scanner that discovers workers on the network."""

    def test_scanner_discovers_workers(self) -> None:
        """Scanner discovers workers broadcasting on the network."""
        from comfygit_deploy.worker.mdns import MDNSScanner

        with patch("comfygit_deploy.worker.mdns.Zeroconf") as mock_zc_class:
            with patch("comfygit_deploy.worker.mdns.ServiceBrowser"):
                with patch("comfygit_deploy.worker.mdns.time.sleep"):
                    mock_zc = MagicMock()
                    mock_zc_class.return_value = mock_zc

                    scanner = MDNSScanner(timeout=5.0)
                    workers = scanner.scan()

                    # Should return list of discovered workers
                    assert isinstance(workers, list)
                    mock_zc.close.assert_called_once()

    def test_scanner_returns_worker_info(self) -> None:
        """Scanner returns structured worker info (host, port, name)."""
        from comfygit_deploy.worker.mdns import DiscoveredWorker, MDNSScanner

        with patch("comfygit_deploy.worker.mdns.Zeroconf") as mock_zc_class:
            with patch("comfygit_deploy.worker.mdns.ServiceBrowser"):
                with patch("comfygit_deploy.worker.mdns.time.sleep"):
                    mock_zc = MagicMock()
                    mock_zc_class.return_value = mock_zc

                    # Simulate a service being discovered
                    mock_info = MagicMock()
                    mock_info.parsed_addresses.return_value = ["192.168.1.50"]
                    mock_info.port = 9090
                    mock_info.properties = {b"name": b"my-worker", b"version": b"0.1.0"}
                    mock_zc.get_service_info.return_value = mock_info

                    scanner = MDNSScanner(timeout=0.1)
                    # Manually trigger the callback that would be called by ServiceBrowser
                    scanner._on_service_state_change(
                        mock_zc, SERVICE_TYPE, "my-worker._cg-deploy._tcp.local.", "Added"
                    )
                    workers = scanner.get_discovered()

                    assert len(workers) == 1
                    worker = workers[0]
                    assert isinstance(worker, DiscoveredWorker)
                    assert worker.host == "192.168.1.50"
                    assert worker.port == 9090
                    assert worker.name == "my-worker"

    def test_scanner_handles_no_workers(self) -> None:
        """Scanner returns empty list when no workers found."""
        from comfygit_deploy.worker.mdns import MDNSScanner

        with patch("comfygit_deploy.worker.mdns.Zeroconf") as mock_zc_class:
            with patch("comfygit_deploy.worker.mdns.ServiceBrowser"):
                with patch("comfygit_deploy.worker.mdns.time.sleep"):
                    mock_zc = MagicMock()
                    mock_zc_class.return_value = mock_zc

                    scanner = MDNSScanner(timeout=0.1)
                    workers = scanner.scan()

                    assert workers == []


class TestCustomScanCommand:
    """Tests for 'cg-deploy custom scan' CLI command."""

    def test_scan_uses_mdns_scanner(self, tmp_path, monkeypatch) -> None:
        """Scan command uses MDNSScanner to discover workers."""
        from argparse import Namespace

        from comfygit_deploy.commands.custom import handle_scan

        # Mock config directory
        monkeypatch.setenv("HOME", str(tmp_path))

        with patch("comfygit_deploy.commands.custom.MDNSScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = []
            mock_scanner_class.return_value = mock_scanner

            args = Namespace(timeout=5)
            result = handle_scan(args)

            mock_scanner_class.assert_called_once_with(timeout=5.0)
            mock_scanner.scan.assert_called_once()
            assert result == 0

    def test_scan_displays_discovered_workers(self, tmp_path, monkeypatch, capsys) -> None:
        """Scan command displays discovered workers."""
        from argparse import Namespace

        from comfygit_deploy.commands.custom import handle_scan
        from comfygit_deploy.worker.mdns import DiscoveredWorker

        monkeypatch.setenv("HOME", str(tmp_path))

        with patch("comfygit_deploy.commands.custom.MDNSScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = [
                DiscoveredWorker(
                    name="render-server",
                    host="192.168.1.50",
                    port=9090,
                    version="0.1.0",
                )
            ]
            mock_scanner_class.return_value = mock_scanner

            args = Namespace(timeout=5)
            result = handle_scan(args)

            captured = capsys.readouterr()
            assert "render-server" in captured.out
            assert "192.168.1.50" in captured.out
            assert result == 0

    def test_scan_saves_results_for_discovered_flag(self, tmp_path, monkeypatch) -> None:
        """Scan saves results so 'custom add --discovered' can use them."""
        import json
        from argparse import Namespace

        from comfygit_deploy.commands.custom import handle_scan
        from comfygit_deploy.worker.mdns import DiscoveredWorker

        monkeypatch.setenv("HOME", str(tmp_path))
        config_dir = tmp_path / ".config" / "comfygit" / "deploy"
        config_dir.mkdir(parents=True)

        with patch("comfygit_deploy.commands.custom.MDNSScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = [
                DiscoveredWorker(
                    name="my-worker",
                    host="10.0.0.5",
                    port=9090,
                    version="0.1.0",
                )
            ]
            mock_scanner_class.return_value = mock_scanner

            args = Namespace(timeout=5)
            handle_scan(args)

            # Should save discovered workers to a file
            discovered_file = config_dir / "discovered_workers.json"
            assert discovered_file.exists()
            data = json.loads(discovered_file.read_text())
            assert len(data) == 1
            assert data[0]["name"] == "my-worker"


class TestCustomAddDiscovered:
    """Tests for 'cg-deploy custom add --discovered' command."""

    def test_add_discovered_uses_saved_scan(self, tmp_path, monkeypatch) -> None:
        """add --discovered uses workers from last scan."""
        import json
        from argparse import Namespace

        from comfygit_deploy.commands.custom import handle_add

        monkeypatch.setenv("HOME", str(tmp_path))
        config_dir = tmp_path / ".config" / "comfygit" / "deploy"
        config_dir.mkdir(parents=True)

        # Simulate saved scan results
        discovered_file = config_dir / "discovered_workers.json"
        discovered_file.write_text(
            json.dumps([{"name": "scan-worker", "host": "192.168.1.100", "port": 9090}])
        )

        args = Namespace(
            name="scan-worker",
            host=None,
            port=9090,
            api_key="test-key",
            discovered=True,
        )
        result = handle_add(args)

        assert result == 0
        # Worker should be added to config
        from comfygit_deploy.config import DeployConfig

        config = DeployConfig(config_dir / "config.json")
        worker = config.get_worker("scan-worker")
        assert worker is not None
        assert worker["host"] == "192.168.1.100"
