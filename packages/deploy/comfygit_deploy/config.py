"""Configuration storage for comfygit-deploy.

Stores RunPod API keys and custom worker registry in ~/.config/comfygit/deploy/config.json
"""

import json
import os
from pathlib import Path
from typing import Any


def _get_default_config_path() -> Path:
    """Get default config path, respecting HOME environment variable."""
    home = os.environ.get("HOME") or str(Path.home())
    return Path(home) / ".config" / "comfygit" / "deploy" / "config.json"


class DeployConfig:
    """Configuration storage for deploy CLI.

    Stores:
    - RunPod API key
    - Custom worker registry (name -> {host, port, api_key, ...})
    """

    def __init__(self, path: Path | None = None):
        """Initialize config.

        Args:
            path: Config file path. Defaults to ~/.config/comfygit/deploy/config.json
        """
        self.path = path or _get_default_config_path()
        self._data: dict[str, Any] = {"version": "1", "providers": {}, "workers": {}}
        self._load()

    def _load(self) -> None:
        """Load config from disk if it exists."""
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                pass  # Use defaults

    def save(self) -> None:
        """Save config to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))

    @property
    def runpod_api_key(self) -> str | None:
        """Get RunPod API key."""
        return self._data.get("providers", {}).get("runpod", {}).get("api_key")

    @runpod_api_key.setter
    def runpod_api_key(self, value: str | None) -> None:
        """Set RunPod API key."""
        if "providers" not in self._data:
            self._data["providers"] = {}
        if "runpod" not in self._data["providers"]:
            self._data["providers"]["runpod"] = {}

        if value is None:
            self._data["providers"]["runpod"].pop("api_key", None)
        else:
            self._data["providers"]["runpod"]["api_key"] = value

    @property
    def workers(self) -> dict[str, dict[str, Any]]:
        """Get custom workers registry."""
        return self._data.get("workers", {})

    def add_worker(
        self,
        name: str,
        host: str,
        port: int,
        api_key: str,
        mode: str = "docker",
    ) -> None:
        """Add a custom worker to the registry.

        Args:
            name: Worker name (unique identifier)
            host: Worker host/IP
            port: Worker API port
            api_key: Worker API key
            mode: Worker mode (docker or native)
        """
        if "workers" not in self._data:
            self._data["workers"] = {}

        self._data["workers"][name] = {
            "host": host,
            "port": port,
            "api_key": api_key,
            "mode": mode,
        }

    def remove_worker(self, name: str) -> bool:
        """Remove a worker from the registry.

        Args:
            name: Worker name

        Returns:
            True if worker was removed, False if not found
        """
        if name in self._data.get("workers", {}):
            del self._data["workers"][name]
            return True
        return False

    def get_worker(self, name: str) -> dict[str, Any] | None:
        """Get a worker by name.

        Args:
            name: Worker name

        Returns:
            Worker config dict or None if not found
        """
        return self._data.get("workers", {}).get(name)
