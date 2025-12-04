"""Native process manager for running ComfyUI without Docker.

Uses `cg` CLI directly to import environments and run ComfyUI processes.
"""

import asyncio
import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessInfo:
    """Info about a running ComfyUI process."""

    pid: int
    port: int
    returncode: int | None = None


class NativeManager:
    """Manages ComfyUI instances as native processes."""

    def __init__(self, workspace_path: Path):
        """Initialize native manager.

        Args:
            workspace_path: Path to ComfyGit workspace
        """
        self.workspace_path = workspace_path
        self._processes: dict[str, subprocess.Popen] = {}

    async def deploy(
        self,
        instance_id: str,
        environment_name: str,
        import_source: str,
        branch: str | None = None,
    ) -> bool:
        """Deploy an environment by cloning from git.

        Args:
            instance_id: Unique instance identifier
            environment_name: Name for the environment
            import_source: Git URL to import from
            branch: Optional branch/tag to checkout

        Returns:
            True if deployment succeeded
        """
        # Build import command
        cmd = [
            "cg",
            "import",
            import_source,
            "--name",
            environment_name,
            "-y",
            "--models",
            "all",
        ]
        if branch:
            cmd.extend(["--branch", branch])

        env = os.environ.copy()
        env["COMFYGIT_HOME"] = str(self.workspace_path)

        # Run import in subprocess
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        # Wait for completion
        stdout, _ = await proc.communicate()

        if proc.returncode != 0:
            # Log failure for debugging
            output = stdout.decode() if stdout else ""
            print(f"Import failed for {instance_id}: {output}")
            return False

        return True

    def start(
        self,
        instance_id: str,
        environment_name: str,
        port: int,
        listen_host: str = "0.0.0.0",
    ) -> ProcessInfo | None:
        """Start ComfyUI process for an environment.

        Args:
            instance_id: Instance identifier for tracking
            environment_name: Environment to run
            port: Port for ComfyUI
            listen_host: Host to listen on

        Returns:
            ProcessInfo if started successfully, None otherwise
        """
        if instance_id in self._processes:
            proc = self._processes[instance_id]
            if proc.poll() is None:
                # Already running
                return ProcessInfo(pid=proc.pid, port=port)

        cmd = [
            "cg",
            "-e",
            environment_name,
            "run",
            "--no-sync",  # Skip sync since we just imported
            "--listen",
            listen_host,
            "--port",
            str(port),
        ]

        env = os.environ.copy()
        env["COMFYGIT_HOME"] = str(self.workspace_path)

        try:
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent
            )
            self._processes[instance_id] = proc
            return ProcessInfo(pid=proc.pid, port=port)
        except Exception as e:
            print(f"Failed to start {instance_id}: {e}")
            return None

    def stop(self, instance_id: str) -> bool:
        """Stop a running ComfyUI process.

        Args:
            instance_id: Instance to stop

        Returns:
            True if stopped (or wasn't running)
        """
        proc = self._processes.get(instance_id)
        if not proc:
            return True

        if proc.poll() is not None:
            # Already dead
            return True

        try:
            # Send SIGTERM to process group
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

            # Wait up to 5 seconds for graceful shutdown
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=2)

            return True
        except ProcessLookupError:
            # Process already gone
            return True
        except Exception as e:
            print(f"Error stopping {instance_id}: {e}")
            return False

    def terminate(self, instance_id: str) -> bool:
        """Terminate instance and remove tracking.

        Args:
            instance_id: Instance to terminate

        Returns:
            True if terminated successfully
        """
        result = self.stop(instance_id)
        self._processes.pop(instance_id, None)
        return result

    def is_running(self, instance_id: str) -> bool:
        """Check if instance process is running.

        Args:
            instance_id: Instance to check

        Returns:
            True if process is alive
        """
        proc = self._processes.get(instance_id)
        if not proc:
            return False
        return proc.poll() is None

    def get_pid(self, instance_id: str) -> int | None:
        """Get PID of running instance.

        Args:
            instance_id: Instance to check

        Returns:
            PID if running, None otherwise
        """
        proc = self._processes.get(instance_id)
        if proc and proc.poll() is None:
            return proc.pid
        return None

    def recover_process(self, instance_id: str, pid: int) -> bool:
        """Attempt to recover tracking for a process from a previous run.

        Args:
            instance_id: Instance identifier
            pid: PID from previous run

        Returns:
            True if process is still alive and now tracked
        """
        try:
            os.kill(pid, 0)  # Check if process exists
            # We can't recover the Popen object, but we can track the PID
            # For now, just report if it's alive
            return True
        except (ProcessLookupError, PermissionError):
            return False
