import hashlib
import wave

from dizdiz.sound_catalog import all_packs, find_sound

BUILTIN_PACK_IDS = {
    "arcade",
    "bubble",
    "click",
    "drum",
    "laser",
    "mechanical",
    "scifi",
    "shotgun",
    "typewriter",
}

MAX_BUNDLED_SOUND_SECONDS = 0.8


def test_builtin_packs():
    packs = all_packs()
    ids = {pack.id for pack in packs}

    assert BUILTIN_PACK_IDS <= ids
    assert all(len(pack.sounds) >= 3 for pack in packs)


def test_bundled_sounds_are_short():
    for pack in all_packs():
        for sound in pack.sounds:
            with wave.open(str(sound.path)) as handle:
                seconds = handle.getnframes() / handle.getframerate()
            assert seconds <= MAX_BUNDLED_SOUND_SECONDS, f"{sound.path} is {seconds:.2f}s"


def test_find_default_sound():
    from dizdiz.settings import Settings

    defaults = Settings()
    sound = find_sound(defaults.selected_pack_id, defaults.selected_sound_id)
    assert sound is not None
    assert sound.path.exists()


def test_legacy_removed_sound_ids_migrate_to_kept_sounds():
    from dizdiz.settings import LEGACY_SOUND_IDS

    for old_id, new_id in LEGACY_SOUND_IDS.items():
        pack_id = new_id.split(".", 1)[0]
        assert find_sound(pack_id, new_id) is not None, f"{old_id} -> {new_id} does not resolve"


def _chunk_ids(path):
    raw = path.read_bytes()
    assert raw[:4] == b"RIFF" and raw[8:12] == b"WAVE", path
    ids, pos = [], 12
    while pos + 8 <= len(raw):
        chunk_id = raw[pos : pos + 4]
        size = int.from_bytes(raw[pos + 4 : pos + 8], "little")
        ids.append(chunk_id)
        pos += 8 + size + (size & 1)
    return ids


def test_bundled_sounds_carry_no_third_party_metadata():
    """Guard against re-introducing sourced audio: generated files have no tags."""
    allowed = {b"fmt ", b"data", b"fact"}
    for pack in all_packs():
        for sound in pack.sounds:
            chunks = set(_chunk_ids(sound.path))
            assert chunks <= allowed, f"{sound.path} carries extra chunks: {chunks - allowed}"


def test_no_duplicate_sounds_within_a_pack():
    for pack in all_packs():
        digests = [hashlib.md5(sound.path.read_bytes()).hexdigest() for sound in pack.sounds]
        assert len(set(digests)) == len(digests), f"{pack.id} contains byte-identical sounds"