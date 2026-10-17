import json
from dataclasses import dataclass
from pathlib import Path

from .paths import custom_sounds_dir, sounds_root


@dataclass(frozen=True)
class Sound:
    id: str
    name: str
    path: Path


@dataclass
class SoundPack:
    id: str
    name: str
    sounds: list[Sound]


def load_builtin_packs() -> list[SoundPack]:
    manifest = sounds_root() / "packs.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    packs: list[SoundPack] = []
    for item in data.get("packs", []):
        sounds = []
        for sound in item.get("sounds", []):
            file_value = sound.get("file", "")
            path = sounds_root() / file_value
            if not path.exists():
                continue
            sounds.append(Sound(id=sound["id"], name=sound["name"], path=path))
        if sounds:
            packs.append(SoundPack(id=item["id"], name=item["name"], sounds=sounds))
    return packs


def custom_pack() -> SoundPack:
    sounds = []
    root = custom_sounds_dir()
    try:
        files = sorted(root.glob("*.wav"))
    except OSError:
        files = []
    for path in files:
        stem = path.stem
        sounds.append(Sound(id=f"custom.{stem}", name=stem, path=path))
    return SoundPack(id="custom", name="My Sounds", sounds=sounds)


def all_packs() -> list[SoundPack]:
    packs = [pack for pack in load_builtin_packs() if pack.sounds]
    cp = custom_pack()
    if cp.sounds:
        packs.append(cp)
    return packs


def find_sound(pack_id: str, sound_id: str | None) -> Sound | None:
    for pack in all_packs():
        if pack.id != pack_id:
            continue
        if sound_id is None:
            return pack.sounds[0] if pack.sounds else None
        for sound in pack.sounds:
            if sound.id == sound_id:
                return sound
        return pack.sounds[0] if pack.sounds else None
    return None