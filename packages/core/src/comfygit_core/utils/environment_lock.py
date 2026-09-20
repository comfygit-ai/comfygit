"""Environment operation lock utilities."""

from __future__ import annotations

import errno
import json
import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from ..models.exceptions import CDEnvironmentBusyError, EnvironmentLockOwner


class EnvironmentOperationLock:
    """Cross-process, cross-thread lock for environment mutations."""

    def __init__(self, lock_path: Path, *, shared: bool = False, operation: str = "environment operation"):
        self.lock_path = lock_path
        self.shared = shared
        self.operation = operation
        self._thread_lock = threading.Lock()
        self._depth = 0
        self._file: IO[str] | None = None
        self._owner_thread: int | None = None

    def __enter__(self) -> EnvironmentOperationLock:
        return self._enter()

    def _enter(self, operation: str | None = None) -> EnvironmentOperationLock:
        current_thread = threading.get_ident()
        with self._thread_lock:
            if self._depth > 0 and self._owner_thread != current_thread:
                raise self._busy_error()
            if self._depth == 0:
                if operation is not None:
                    self.operation = operation
                self._acquire_file_lock()
                self._owner_thread = current_thread
            self._depth += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        with self._thread_lock:
            self._depth -= 1
            if self._depth == 0:
                self._owner_thread = None
                self._release_file_lock()
        return False

    @contextmanager
    def read(self) -> Iterator[None]:
        """Short shared read scope; never hold across await or upgrade to a write."""
        with self._thread_lock:
            owns_write = self._depth > 0 and self._owner_thread == threading.get_ident()
        if owns_write:
            # Synchronous reads nested inside a mutation already have protection.
            yield
            return
        with EnvironmentOperationLock(self.lock_path, shared=True, operation="snapshot read"):
            yield

    @contextmanager
    def named(self, operation: str) -> Iterator[None]:
        """Label the outer mutation, retaining its label across nested calls."""
        self._enter(operation)
        try:
            yield
        finally:
            self.__exit__(None, None, None)

    def _busy_error(self) -> CDEnvironmentBusyError:
        owner = EnvironmentLockOwner()
        try:
            with self.lock_path.open(encoding="utf-8") as source:
                # Win32 locks byte zero against even diagnostic reads. New
                # writers reserve that byte and put their JSON after it.
                if sys.platform == "win32":
                    source.seek(1)
                data = json.loads(source.read(4096))
            if isinstance(data, int) and sys.platform != "win32":  # Legacy PID-only writer.
                owner = EnvironmentLockOwner(pid=data)
            elif isinstance(data, dict):
                owner = EnvironmentLockOwner(
                    pid=data.get("pid") if type(data.get("pid")) is int else None,
                    operation=str(data["operation"])[:160] if data.get("operation") else None,
                    acquired_at=str(data["acquired_at"])[:64] if data.get("acquired_at") else None,
                )
        except (OSError, ValueError):
            pass
        return CDEnvironmentBusyError(str(self.lock_path), owner)

    def _acquire_file_lock(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.lock_path, "a+")

        try:
            self._file.seek(0)
            if sys.platform == "win32":
                try:
                    _windows_lock(self._file.fileno(), shared=self.shared)
                except OSError as e:
                    if e.winerror == 33:  # ERROR_LOCK_VIOLATION
                        raise self._busy_error() from e
                    raise
            else:
                import fcntl

                try:
                    mode = fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX
                    fcntl.flock(self._file.fileno(), mode | fcntl.LOCK_NB)
                except OSError as e:
                    if e.errno in {errno.EAGAIN, errno.EACCES}:
                        raise self._busy_error() from e
                    raise

            if self.shared:
                return  # Readers must not overwrite or clear writer diagnostics.

            try:
                self._file.seek(0)
                self._file.truncate()
                self._file.write(" ")
                json.dump({"pid": os.getpid(), "operation": self.operation,
                           "acquired_at": datetime.now(timezone.utc).isoformat()}, self._file)
                self._file.flush()
            except OSError:
                pass
        except Exception:
            self._file.close()
            self._file = None
            raise

    def _release_file_lock(self) -> None:
        if not self._file:
            return

        try:
            self._file.seek(0)
            try:
                if not self.shared:
                    self._file.truncate()
                    self._file.flush()
            except OSError:
                pass

            if sys.platform == "win32":
                try:
                    _windows_lock(self._file.fileno(), shared=self.shared, unlock=True)
                except OSError:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            self._file.close()
            self._file = None


def _windows_lock(fd: int, *, shared: bool, unlock: bool = False) -> None:
    """Lock byte zero with Win32 shared/exclusive semantics (msvcrt lacks shared locks)."""
    if sys.platform != "win32":
        raise RuntimeError("Win32 locking is only available on Windows")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
    overlap = Overlapped()
    if unlock:
        fn = kernel.UnlockFileEx
        fn.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                       wintypes.DWORD, ctypes.POINTER(Overlapped)]
        args = (handle, 0, 1, 0, ctypes.byref(overlap))
    else:
        fn = kernel.LockFileEx
        fn.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                       wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
        args = (handle, 1 | (0 if shared else 2), 0, 1, 0, ctypes.byref(overlap))
    fn.restype = wintypes.BOOL
    if not fn(*args):
        raise ctypes.WinError(ctypes.get_last_error())
