"""Tests for native process manager."""

import asyncio
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comfygit_deploy.worker.native_manager import NativeManager, ProcessInfo


class TestNativeManager:
    """Test native process manager."""

    def test_init_with_workspace_path(self) -> None:
        """Manager initializes with workspace path."""
        workspace = Path("/tmp/test-workspace")
        manager = NativeManager(workspace)
        assert manager.workspace_path == workspace

    @pytest.mark.asyncio
    async def test_deploy_calls_cg_import(self) -> None:
        """Deploy runs cg import command with correct args."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NativeManager(Path(tmpdir))

            # Mock subprocess to avoid actually running command
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.communicate.return_value = (b"Success", None)
                mock_proc.returncode = 0
                mock_exec.return_value = mock_proc

                result = await manager.deploy(
                    instance_id="inst_123",
                    environment_name="test-env",
                    import_source="https://github.com/user/repo.git",
                    branch="main",
                )

                assert result is True
                # Verify cg import was called
                call_args = mock_exec.call_args[0]
                assert "cg" in call_args
                assert "import" in call_args
                assert "https://github.com/user/repo.git" in call_args
                assert "--name" in call_args
                assert "test-env" in call_args
                assert "--branch" in call_args
                assert "main" in call_args

    @pytest.mark.asyncio
    async def test_deploy_returns_false_on_failure(self) -> None:
        """Deploy returns False when import fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NativeManager(Path(tmpdir))

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.communicate.return_value = (b"Error", None)
                mock_proc.returncode = 1
                mock_exec.return_value = mock_proc

                result = await manager.deploy(
                    instance_id="inst_123",
                    environment_name="test-env",
                    import_source="bad-source",
                )

                assert result is False

    def test_start_spawns_process(self) -> None:
        """Start launches cg run subprocess."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NativeManager(Path(tmpdir))

            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.pid = 12345
                mock_proc.poll.return_value = None  # Process running
                mock_popen.return_value = mock_proc

                result = manager.start(
                    instance_id="inst_123",
                    environment_name="test-env",
                    port=8188,
                )

                assert result is not None
                assert result.pid == 12345
                assert result.port == 8188

                # Verify correct command
                call_args = mock_popen.call_args
                cmd = call_args[0][0]
                assert "cg" in cmd
                assert "-e" in cmd
                assert "test-env" in cmd
                assert "run" in cmd
                assert "--port" in cmd
                assert "8188" in cmd

    def test_start_returns_existing_process_if_running(self) -> None:
        """Start returns existing process info if already running."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NativeManager(Path(tmpdir))

            # First start
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.pid = 12345
                mock_proc.poll.return_value = None
                mock_popen.return_value = mock_proc

                manager.start("inst_123", "test-env", 8188)

            # Second start - should return same process
            result = manager.start("inst_123", "test-env", 8188)
            assert result.pid == 12345

    def test_stop_terminates_process(self) -> None:
        """Stop terminates running process."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NativeManager(Path(tmpdir))

            # Create mock process
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.poll.return_value = None  # Running initially

            with patch("subprocess.Popen", return_value=mock_proc):
                manager.start("inst_123", "test-env", 8188)

            # Stop should work - the process is tracked
            # We need to set up poll to indicate process terminated after stop
            def poll_side_effect():
                # Return None first (running), then 0 (stopped)
                if not hasattr(poll_side_effect, "called"):
                    poll_side_effect.called = True
                    return None
                return 0

            mock_proc.poll.side_effect = poll_side_effect

            with patch(
                "comfygit_deploy.worker.native_manager.os.killpg"
            ) as mock_killpg, patch(
                "comfygit_deploy.worker.native_manager.os.getpgid", return_value=12345
            ):
                result = manager.stop("inst_123")

                assert result is True
                mock_killpg.assert_called()

    def test_stop_returns_true_for_unknown_instance(self) -> None:
        """Stop returns True for instance that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NativeManager(Path(tmpdir))
            result = manager.stop("nonexistent")
            assert result is True

    def test_terminate_removes_tracking(self) -> None:
        """Terminate stops process and removes from tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NativeManager(Path(tmpdir))

            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.pid = 12345
                mock_proc.poll.return_value = None
                mock_popen.return_value = mock_proc

                manager.start("inst_123", "test-env", 8188)

            with patch("os.killpg"), patch("os.getpgid") as mock_getpgid:
                mock_getpgid.return_value = 12345
                mock_proc.wait.return_value = 0
                mock_proc.poll.return_value = 0

                manager.terminate("inst_123")

            # Should no longer be tracked
            assert not manager.is_running("inst_123")

    def test_is_running_returns_false_for_unknown(self) -> None:
        """is_running returns False for unknown instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NativeManager(Path(tmpdir))
            assert not manager.is_running("nonexistent")

    def test_get_pid_returns_none_for_unknown(self) -> None:
        """get_pid returns None for unknown instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NativeManager(Path(tmpdir))
            assert manager.get_pid("nonexistent") is None
