"""mDNS service broadcasting for worker discovery.

Registers the worker as a _cg-deploy._tcp.local. service so it can be
discovered by frontends scanning the local network.
"""

import socket
from typing import TYPE_CHECKING

from zeroconf import ServiceInfo, Zeroconf

from .. import __version__

SERVICE_TYPE = "_cg-deploy._tcp.local."


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

    def __init__(self, port: int, worker_name: str | None = None):
        """Initialize broadcaster.

        Args:
            port: Port the worker HTTP server is listening on
            worker_name: Optional name for the worker (defaults to hostname)
        """
        self.port = port
        self.worker_name = worker_name or socket.gethostname()
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
