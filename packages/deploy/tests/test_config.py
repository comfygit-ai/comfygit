"""Tests for config storage module.

TDD: These tests are written first and should FAIL until config.py is implemented.
"""

from pathlib import Path

from comfygit_deploy.config import DeployConfig


class TestDeployConfig:
    """Tests for DeployConfig class."""

    def test_config_creates_directory_if_not_exists(self, tmp_path: Path) -> None:
        """Config should create its directory if it doesn't exist."""
        config_path = tmp_path / "nonexistent" / "config.json"
        config = DeployConfig(config_path)
        config.save()

        assert config_path.parent.exists()
        assert config_path.exists()

    def test_config_loads_empty_when_file_missing(self, tmp_path: Path) -> None:
        """Config should return empty/defaults when file doesn't exist."""
        config_path = tmp_path / "config.json"
        config = DeployConfig(config_path)

        assert config.runpod_api_key is None
        assert config.workers == {}

    def test_config_saves_and_loads_runpod_key(self, tmp_path: Path) -> None:
        """Config should persist RunPod API key."""
        config_path = tmp_path / "config.json"
        config = DeployConfig(config_path)

        config.runpod_api_key = "rpa_test123"
        config.save()

        # Load fresh instance
        config2 = DeployConfig(config_path)
        assert config2.runpod_api_key == "rpa_test123"

    def test_config_saves_and_loads_workers(self, tmp_path: Path) -> None:
        """Config should persist custom worker registry."""
        config_path = tmp_path / "config.json"
        config = DeployConfig(config_path)

        config.add_worker(
            name="my-worker",
            host="192.168.1.50",
            port=9090,
            api_key="cg_wk_abc123",
        )
        config.save()

        # Load fresh instance
        config2 = DeployConfig(config_path)
        assert "my-worker" in config2.workers
        assert config2.workers["my-worker"]["host"] == "192.168.1.50"
        assert config2.workers["my-worker"]["port"] == 9090
        assert config2.workers["my-worker"]["api_key"] == "cg_wk_abc123"

    def test_config_remove_worker(self, tmp_path: Path) -> None:
        """Config should allow removing workers."""
        config_path = tmp_path / "config.json"
        config = DeployConfig(config_path)

        config.add_worker("worker1", "host1", 9090, "key1")
        config.add_worker("worker2", "host2", 9091, "key2")
        config.remove_worker("worker1")
        config.save()

        config2 = DeployConfig(config_path)
        assert "worker1" not in config2.workers
        assert "worker2" in config2.workers

    def test_config_clear_runpod_key(self, tmp_path: Path) -> None:
        """Config should allow clearing RunPod API key."""
        config_path = tmp_path / "config.json"
        config = DeployConfig(config_path)

        config.runpod_api_key = "rpa_test123"
        config.save()

        config.runpod_api_key = None
        config.save()

        config2 = DeployConfig(config_path)
        assert config2.runpod_api_key is None

    def test_config_default_path(self) -> None:
        """Config should use default path in ~/.config/comfygit/deploy/."""
        config = DeployConfig()
        expected = Path.home() / ".config" / "comfygit" / "deploy" / "config.json"
        assert config.path == expected
