"""Ctrl-C in the launching terminal must terminate the app.

CPython replaces SIGINT's default disposition with a handler that only sets a
flag; the flag is acted on at the next Python bytecode boundary. Qt's event loop
spends its life blocked in C++ where no bytecode runs, so a pending SIGINT is
never delivered and the app ignores Ctrl-C. Terminating the process on SIGINT
therefore has to come from the kernel default disposition, not from a Python
handler.

These tests spawn the real entry point, because the bug only appears when the
process is genuinely parked in the event loop.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

ROOT = Path(__file__).resolve().parents[1]
STARTUP_GRACE = 2.5  # let the process reach the Qt event loop
EXIT_TIMEOUT = 10.0


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONPATH": str(ROOT),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_RUNTIME_DIR": str(tmp_path / "run"),
    }


def _spawn(env: dict[str, str], tmp_path: Path, name: str) -> tuple[subprocess.Popen, Path]:
    log = tmp_path / f"{name}.log"
    with log.open("wb") as handle:
        proc = subprocess.Popen(
            [sys.executable, "-m", "dizdiz"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    return proc, log


def _log_tail(log: Path) -> str:
    try:
        return log.read_text(errors="replace")[-2000:]
    except OSError:
        return "<log unreadable>"


def _running_app(env, tmp_path, name) -> tuple[subprocess.Popen, Path]:
    proc, log = _spawn(env, tmp_path, name)
    time.sleep(STARTUP_GRACE)
    if proc.poll() is not None:
        pytest.fail(f"dizdiz exited during startup (status {proc.returncode})\n{_log_tail(log)}")
    return proc, log


def _wait_for_exit(proc: subprocess.Popen) -> int | None:
    try:
        proc.wait(timeout=EXIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None
    return proc.returncode


def _reap(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=5)


def test_ctrl_c_terminates_running_app(tmp_path):
    env = _env(tmp_path)
    proc, log = _running_app(env, tmp_path, "app")
    try:
        proc.send_signal(signal.SIGINT)
        status = _wait_for_exit(proc)
        assert status == -signal.SIGINT, (
            f"Ctrl-C did not terminate the app (status {status})\n{_log_tail(log)}"
        )
    finally:
        _reap(proc)


def test_ctrl_c_terminates_second_instance_notice(tmp_path):
    """The already-running notice blocks in a nested modal loop; Ctrl-C must still quit."""
    env = _env(tmp_path)
    first, log = _running_app(env, tmp_path, "first")
    try:
        # Same XDG dirs, so the second instance hits the single-instance notice.
        second, second_log = _running_app(env, tmp_path, "second")
        try:
            second.send_signal(signal.SIGINT)
            status = _wait_for_exit(second)
            assert status == -signal.SIGINT, (
                f"Ctrl-C did not terminate the notice (status {status})\n"
                f"{_log_tail(second_log)}"
            )
        finally:
            _reap(second)
    finally:
        _reap(first)
        assert log.exists()
