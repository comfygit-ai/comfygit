"""CGSYNC-LIFE-10B: readers coexist; writes and incomplete snapshots stay fenced."""
import errno
import multiprocessing
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from comfygit_core.core.environment import Environment
from comfygit_core.managers.pyproject_manager import PyprojectManager
from comfygit_core.models import CDEnvironmentBusyError
from comfygit_core.utils.environment_lock import EnvironmentOperationLock


def _hold_reader(path, ready, release):
    with EnvironmentOperationLock(path).read():
        ready.set()
        assert release.wait(10)


def test_shared_readers_across_threads_and_processes(tmp_path):
    path = tmp_path / ".comfygit.lock"
    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    process = ctx.Process(target=_hold_reader, args=(path, ready, release))
    process.start()
    try:
        assert ready.wait(10)
        barrier = Barrier(4)

        def read():
            with EnvironmentOperationLock(path).read():
                barrier.wait(timeout=5)
                with pytest.raises(CDEnvironmentBusyError):
                    with EnvironmentOperationLock(path):
                        pytest.fail("Writer interleaved with readers")

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: read(), range(4)))
    finally:
        release.set()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join()
    assert process.exitcode == 0
    with EnvironmentOperationLock(path):
        pass


def test_writer_diagnostics_and_fresh_detached_snapshots(tmp_path):
    path = tmp_path / ".comfygit.lock"
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nname="before"\n')
    env = Environment.__new__(Environment)
    env._operation_lock = EnvironmentOperationLock(path)
    env.__dict__["pyproject"] = PyprojectManager(manifest)
    before = env.get_manifest_snapshot()
    with EnvironmentOperationLock(path).named("sync"):
        manifest.write_text('[project]\nname="after"\n')
        with pytest.raises(CDEnvironmentBusyError) as error:
            env.get_manifest_snapshot()
        assert error.value.owner.pid == os.getpid()
        assert error.value.owner.operation == "sync"
    after = env.get_manifest_snapshot()
    assert before.project.name == "before"
    assert after.project.name == "after"
    assert before.revision != after.revision
    with env._operation_lock.named("nested mutation"):
        assert env.get_manifest_snapshot().revision == after.revision
    assert path.read_text() == ""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX errno classification")
def test_io_failure_is_not_retryable_contention(tmp_path, monkeypatch):
    import fcntl

    def fail(*args):
        raise OSError(errno.EIO, "device error")

    monkeypatch.setattr(fcntl, "flock", fail)
    with pytest.raises(OSError, match="device error"):
        with EnvironmentOperationLock(tmp_path / ".lock").read():
            pass
