import json
from pathlib import Path

from dizdiz.settings import Settings
from dizdiz.sound_catalog import find_sound


def test_defaults():
    s = Settings()
    assert s.sounds_enabled is True
    assert s.selected_pack_id == "shotgun"
    assert s.volume == 0.7


def test_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr("dizdiz.settings.settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr("dizdiz.settings.config_dir", lambda: tmp_path)
    monkeypatch.setattr("dizdiz.settings.custom_sounds_dir", lambda: tmp_path / "CustomSounds")
    s = Settings(volume=0.25, random_mode=True)
    s.save()
    loaded = Settings.load()
    assert loaded.volume == 0.25
    assert loaded.random_mode is True


def test_corrupt_settings(tmp_path, monkeypatch):
    monkeypatch.setattr("dizdiz.settings.settings_path", lambda: tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text("{bad")
    assert Settings.load().sounds_enabled is True


def test_legacy_pistol_pack_migrates_to_shotgun(tmp_path, monkeypatch):
    monkeypatch.setattr("dizdiz.settings.settings_path", lambda: tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text(
        json.dumps({"selected_pack_id": "pistol", "selected_sound_id": "pistol.machine_gun"})
    )

    loaded = Settings.load()

    assert loaded.selected_pack_id == "shotgun"
    assert loaded.selected_sound_id == "shotgun.machine_gun_burst"
    assert find_sound(loaded.selected_pack_id, loaded.selected_sound_id) is not None


def test_migrated_pistol_sound_resolves(tmp_path, monkeypatch):
    monkeypatch.setattr("dizdiz.settings.settings_path", lambda: tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text(json.dumps({"selected_pack_id": "pistol"}))

    loaded = Settings.load()
    sound = find_sound(loaded.selected_pack_id, loaded.selected_sound_id)

    assert sound is not None
    assert sound.id.startswith("shotgun.")