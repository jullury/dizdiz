import os
import shutil
import sys
from pathlib import Path

from .paths import autostart_entry_path


def _command() -> str:
    exe = shutil.which("dizdiz")
    if exe:
        return exe
    return f"{sys.executable} -m dizdiz"


def is_enabled() -> bool:
    return autostart_entry_path().exists()


def set_enabled(enabled: bool) -> None:
    path = autostart_entry_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Dizdiz\n"
            f"Exec={_command()}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n",
            encoding="utf-8",
        )
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass