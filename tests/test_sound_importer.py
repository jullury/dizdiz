from pathlib import Path

from dizdiz.sound_importer import is_supported


def test_supported_extensions():
    assert is_supported(Path("a.wav"))
    assert is_supported(Path("a.MP3"))
    assert not is_supported(Path("a.txt"))