from pathlib import Path

import dizdiz.autostart as autostart


def test_enable_disable(tmp_path, monkeypatch):
    entry = tmp_path / "dizdiz.desktop"
    monkeypatch.setattr(autostart, "autostart_entry_path", lambda: entry)
    autostart.set_enabled(True)
    assert entry.exists()
    assert autostart.is_enabled() is True
    autostart.set_enabled(False)
    assert not entry.exists()