import os
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "dizdiz"


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "dizdiz"


def settings_path() -> Path:
    return config_dir() / "settings.json"


def custom_sounds_dir() -> Path:
    return data_dir() / "CustomSounds"


def crash_log_path() -> Path:
    return config_dir() / "crash.log"


def lock_path() -> Path:
    return config_dir() / "dizdiz.lock"


def autostart_dir() -> Path:
    return config_dir().parent / "autostart"


def autostart_entry_path() -> Path:
    return autostart_dir() / "dizdiz.desktop"


def asset_root() -> Path:
    candidates = [
        Path(__file__).resolve().parent / "assets",
        Path(__file__).resolve().parent.parent / "assets",
        Path("/usr/share/dizdiz/assets"),
        Path("/usr/local/share/dizdiz/assets"),
    ]
    for candidate in candidates:
        if (candidate / "sounds" / "packs.json").exists():
            return candidate
    return candidates[0]


def sounds_root() -> Path:
    return asset_root() / "sounds"