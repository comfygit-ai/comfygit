"""mDNS service broadcasting and scanning for worker discovery.

Registers the worker as a _cg-deploy._tcp.local. service so it can be
discovered by frontends scanning the local network. Also provides client-side
scanning to discover workers on the network.
"""

import socket
import time
from dataclasses import dataclass

from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from .. import __version__

SERVICE_TYPE = "_cg-deploy._tcp.local."


@dataclass
class DiscoveredWorker:
    """Worker discovered via mDNS scan."""

    name: str
    host: str
    port: int
    version: str = "unknown"
    mode: str = "docker"


def get_local_ip() -> str:
    """Get the local IP address of this machine.

    Returns:
        Local IP address as string, or 127.0.0.1 if detection fails.
    """
    try:
        # Create a socket to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class MDNSBroadcaster:
    """Broadcasts worker availability via mDNS/Zeroconf."""

    def __init__(self, port: int, worker_name: str | None = None, mode: str = "docker"):
        """Initialize broadcaster.

        Args:
            port: Port the worker HTTP server is listening on
            worker_name: Optional name for the worker (defaults to hostname)
            mode: Worker mode (docker or native)
        """
        self.port = port
        self.worker_name = worker_name or socket.gethostname()
        self.mode = mode
        self.zeroconf: Zeroconf | None = None
        self.service_info: ServiceInfo | None = None

    def start(self) -> None:
        """Register the mDNS service."""
        local_ip = get_local_ip()

        self.service_info = ServiceInfo(
            SERVICE_TYPE,
            f"{self.worker_name}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(local_ip)],
            port=self.port,
            properties={
                "version": __version__,
                "name": self.worker_name,
                "mode": self.mode,
            },
        )

        self.zeroconf = Zeroconf()
        self.zeroconf.register_service(self.service_info)
        print(f"  mDNS: Broadcasting as {self.worker_name} on {local_ip}:{self.port}")

    def stop(self) -> None:
        """Unregister the mDNS service."""
        if self.zeroconf and self.service_info:
            self.zeroconf.unregister_service(self.service_info)
            self.zeroconf.close()
            self.zeroconf = None
            self.service_info = None


class MDNSScanner:
    """Scans the network for ComfyGit workers via mDNS/Zeroconf."""

    def __init__(self, timeout: float = 5.0):
        """Initialize scanner.

        Args:
            timeout: How long to scan (seconds)
        """
        self.timeout = timeout
        self._discovered: list[DiscoveredWorker] = []
        self._zeroconf: Zeroconf | None = None

    def _on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: str | ServiceStateChange,
    ) -> None:
        """Called when a service is discovered or removed."""
        # Handle both string and enum state change types
        state = state_change if isinstance(state_change, str) else state_change.name

        if state in ("Added", "Updated"):
            info = zeroconf.get_service_info(service_type, name)
            if info:
                addresses = info.parsed_addresses()
                if addresses:
                    props = info.properties or {}
                    worker = DiscoveredWorker(
                        name=props.get(b"name", b"unknown").decode(),
                        host=addresses[0],
                        port=info.port,
                        version=props.get(b"version", b"unknown").decode(),
                        mode=props.get(b"mode", b"docker").decode(),
                    )
                    # Avoid duplicates
                    if not any(w.host == worker.host and w.port == worker.port for w in self._discovered):
                        self._discovered.append(worker)

    def scan(self) -> list[DiscoveredWorker]:
        """Scan for workers on the network.

        Returns:
            List of discovered workers
        """
        self._discovered = []
        zeroconf = Zeroconf()
        self._zeroconf = zeroconf

        try:
            ServiceBrowser(zeroconf, SERVICE_TYPE, handlers=[self._on_service_state_change])
            time.sleep(self.timeout)
        finally:
            zeroconf.close()

        return self._discovered

    def get_discovered(self) -> list[DiscoveredWorker]:
        """Get workers discovered so far (for manual callback testing)."""
        return self._discovered
