"""Process-level lifecycle checks for the Application object.

PyQt6 does not raise when a second ``QApplication(...)`` is constructed: it hands
back a separate Python wrapper for the one underlying C++ object, and each
wrapper believes it owns the object. The result is a shutdown double-free
(SIGSEGV) as soon as a few wrappers exist, which is why ``Application`` must
reuse ``QApplication.instance()``. This has to run in a real process, because the
crash happens during interpreter teardown.
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = """
import os
import sys

sys.path.insert(0, sys.argv[1])
os.environ["QT_QPA_PLATFORM"] = "offscreen"
base = sys.argv[2]

from dizdiz.app import Application
from dizdiz.settings import Settings

for index in range(3):
    os.environ["XDG_CONFIG_HOME"] = os.path.join(base, f"config{index}")
    os.environ["XDG_DATA_HOME"] = os.path.join(base, f"data{index}")
    Settings(sounds_enabled=False, has_launched_before=True).save()
    Application()

print("built 3 applications", flush=True)
"""


def test_repeated_application_construction_exits_cleanly(tmp_path):
    """Regression: three Application objects used to segfault on exit."""
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(ROOT), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"process exited with {result.returncode} (negative = killed by signal)\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "built 3 applications" in result.stdout
