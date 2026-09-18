"""Single-flight lock file so only one training container ever runs on the
shared GPU host, even across worker restarts (spec section 2/4).

Uses `flock` on an open file descriptor rather than a PID file: the OS
releases the lock automatically if the holding process dies or is killed,
so a crashed worker can never leave a stale lock behind.
"""

from __future__ import annotations

import fcntl
import os


class LockAcquisitionError(Exception):
    pass


class WorkerLock:
    def __init__(self, path: str) -> None:
        self._path = path
        self._fd: int | None = None

    def acquire(self) -> None:
        if self._fd is not None:
            return  # already held by this instance
        fd = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise LockAcquisitionError(f"Worker lock already held: {self._path}") from None
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None

    @property
    def is_held(self) -> bool:
        return self._fd is not None

    def __enter__(self) -> "WorkerLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()
