import fcntl
import os
from pathlib import Path

from .paths import lock_path


class SingleInstance:
    def __init__(self) -> None:
        self._fd = None

    def acquire(self) -> bool:
        path = lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            os.close(self._fd)
            self._fd = None
            return False
        os.ftruncate(self._fd, 0)
        os.write(self._fd, str(os.getpid()).encode())
        return True

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None