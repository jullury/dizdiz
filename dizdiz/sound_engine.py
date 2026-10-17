import random
import shutil
import subprocess
import time
from pathlib import Path

from .settings import Settings
from .sound_catalog import Sound, all_packs, find_sound


class SoundEngine:
    def __init__(self, settings: Settings, parent=None) -> None:
        self.settings = settings
        self.parent = parent
        self._player = shutil.which("pw-play") or shutil.which("paplay")
        self._last_trigger = 0.0
        self._minimum_interval = 0.02
        self.audio_available = self._player is not None

    def preload(self) -> None:
        return None

    def play(self, sound: Sound | None = None) -> None:
        if not self.settings.sounds_enabled or not self.audio_available:
            return
        now = time.monotonic()
        if now - self._last_trigger < self._minimum_interval:
            return
        self._last_trigger = now

        chosen = sound if sound is not None else self._choose_sound()
        if chosen is None or not chosen.path.exists():
            return

        try:
            if self._player.endswith("pw-play"):
                subprocess.Popen(
                    [self._player, "--volume", str(float(self.settings.volume)), str(chosen.path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                volume = int(float(self.settings.volume) * 65536)
                subprocess.Popen(
                    [self._player, f"--volume={volume}", str(chosen.path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except OSError:
            self.audio_available = False

    def _choose_sound(self) -> Sound | None:
        for pack in all_packs():
            if pack.id != self.settings.selected_pack_id:
                continue
            if not pack.sounds:
                return None
            if self.settings.random_mode:
                choices = [s for s in pack.sounds if "reload" not in s.id]
                if choices:
                    return random.choice(choices)
                return random.choice(pack.sounds)
            sound = find_sound(pack.id, self.settings.selected_sound_id)
            return sound or pack.sounds[0]
        packs = all_packs()
        if not packs or not packs[0].sounds:
            return None
        return packs[0].sounds[0]

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings

    def shutdown(self) -> None:
        return None