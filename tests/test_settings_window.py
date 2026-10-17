import os

import pytest

pytest.importorskip("PyQt6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from dizdiz.keyboard_hook import KeyboardHook  # noqa: E402
from dizdiz.paths import settings_path  # noqa: E402
from dizdiz.settings import Settings  # noqa: E402
from dizdiz.sound_engine import SoundEngine  # noqa: E402
from dizdiz.ui.settings_window import SettingsWindow  # noqa: E402


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    app = QApplication.instance() or QApplication([])

    def build(**overrides):
        settings = Settings(**overrides)
        hook = KeyboardHook(settings, lambda code: None)
        return settings, SettingsWindow(settings, SoundEngine(settings), hook)

    return app, build


def test_opening_settings_does_not_disable_sounds(window):
    _, build = window
    settings, _ = build(sounds_enabled=True, random_mode=True)

    assert settings.sounds_enabled is True
    assert Settings.load().sounds_enabled is True


def test_opening_settings_preserves_disabled_state(window):
    _, build = window
    settings, _ = build(sounds_enabled=False, random_mode=True)

    assert settings.sounds_enabled is False


def test_opening_settings_writes_nothing_to_disk(window):
    _, build = window
    build(sounds_enabled=False, random_mode=True)

    assert settings_path().exists() is False


def test_refresh_does_not_mutate_settings(window):
    _, build = window
    settings, settings_window = build(sounds_enabled=True, random_mode=True)

    settings_window._refresh_packs()

    assert settings.sounds_enabled is True
    assert Settings.load().sounds_enabled is True


def test_toggling_one_control_persists_only_that_field(window):
    _, build = window
    settings, settings_window = build()

    settings_window.pitch_check.setChecked(True)

    loaded = Settings.load()
    assert loaded.pitch_variation is True
    assert loaded.sounds_enabled is True
    assert loaded.random_mode is True
    assert loaded.play_on_key_repeat is False
    assert loaded.play_for_modifiers is False
    assert loaded.volume == settings.volume


def test_random_mode_locks_sound_selector(window):
    _, build = window
    settings, settings_window = build(random_mode=True)

    assert settings_window.sound_combo.isEnabled() is False

    settings_window.random_check.setChecked(False)

    assert settings_window.sound_combo.isEnabled() is True
    assert settings.random_mode is False
