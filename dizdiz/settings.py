import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .paths import config_dir, custom_sounds_dir, settings_path

# The "pistol" pack was merged into "shotgun"; it held only duplicates of
# shotgun files. Remap old selections so they do not silently fall back to
# another pack.
LEGACY_PACK_IDS = {"pistol": "shotgun"}

LEGACY_SOUND_IDS = {
    "pistol.gunshot_01": "shotgun.pd_gunshot_01",
    "pistol.gunshot_02": "shotgun.pd_gunshot_02",
    "pistol.machine_gun": "shotgun.machine_gun_burst",
    # Removed from the shotgun pack (third-party sources) — remap to a kept sound.
    "shotgun.shotgun_blast": "shotgun.pd_gunshot_01",
    "shotgun.gunshot_02": "shotgun.pd_gunshot_02",
    "shotgun.machine_gun_01": "shotgun.machine_gun_burst",
    "shotgun.reload": "shotgun.pd_gunshot_01",
}


def _migrate(settings: "Settings") -> "Settings":
    replacement = LEGACY_PACK_IDS.get(settings.selected_pack_id)
    if replacement is not None:
        settings.selected_pack_id = replacement
    sound_id = settings.selected_sound_id
    if sound_id is not None and sound_id in LEGACY_SOUND_IDS:
        settings.selected_sound_id = LEGACY_SOUND_IDS[sound_id]
    return settings


@dataclass
class Settings:
    sounds_enabled: bool = True
    selected_pack_id: str = "shotgun"
    selected_sound_id: str | None = "shotgun.pd_gunshot_01"
    random_mode: bool = True
    volume: float = 0.7
    pitch_variation: bool = True
    play_on_key_repeat: bool = False
    play_for_modifiers: bool = False
    has_launched_before: bool = False
    check_updates: bool = True
    last_notified_version: str | None = None
    custom_sounds: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        path = settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        try:
            return _migrate(cls(**filtered))
        except (TypeError, ValueError):
            return cls()

    def save(self) -> None:
        config_dir().mkdir(parents=True, exist_ok=True)
        custom_sounds_dir().mkdir(parents=True, exist_ok=True)
        path = settings_path()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(path)