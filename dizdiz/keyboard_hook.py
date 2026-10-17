import select
import threading
from typing import Callable

from evdev import InputDevice, ecodes, list_devices

MODIFIER_CODES = {
    ecodes.KEY_LEFTSHIFT,
    ecodes.KEY_RIGHTSHIFT,
    ecodes.KEY_LEFTCTRL,
    ecodes.KEY_RIGHTCTRL,
    ecodes.KEY_LEFTALT,
    ecodes.KEY_RIGHTALT,
    ecodes.KEY_LEFTMETA,
    ecodes.KEY_RIGHTMETA,
    ecodes.KEY_CAPSLOCK,
}


class KeyboardHook:
    def __init__(self, settings, on_key_press: Callable[[int], None]) -> None:
        self.settings = settings
        self.on_key_press = on_key_press
        self._running = False
        self._thread: threading.Thread | None = None
        self._is_down: list[bool] = [False] * 1024
        self.available = True
        self.error: str | None = None

    def _ensure_size(self, code: int) -> None:
        if code >= len(self._is_down):
            self._is_down.extend([False] * (code + 1 - len(self._is_down)))

    def _keyboard_devices(self) -> list[InputDevice]:
        devices: list[InputDevice] = []
        try:
            paths = list_devices()
        except OSError as exc:
            self.available = False
            self.error = str(exc)
            return devices
        for path in paths:
            try:
                device = InputDevice(path)
            except OSError:
                continue
            caps = device.capabilities().get(ecodes.EV_KEY, [])
            if ecodes.KEY_A in caps or ecodes.KEY_SPACE in caps or ecodes.KEY_ENTER in caps:
                devices.append(device)
        if not devices:
            self.available = False
            self.error = "No readable keyboard input devices found"
        else:
            self.available = True
            self.error = None
        return devices

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        devices = self._keyboard_devices()
        if not devices:
            self._running = False
            return
        fd_map = {dev.fd: dev for dev in devices}
        try:
            while self._running:
                readable, _, _ = select.select(list(fd_map), [], [], 0.5)
                for fd in readable:
                    device = fd_map[fd]
                    try:
                        for event in device.read():
                            if event.type != ecodes.EV_KEY:
                                continue
                            code = event.code
                            self._ensure_size(code)
                            value = event.value
                            if value == 0:
                                self._is_down[code] = False
                                continue
                            if not getattr(self.settings, "play_for_modifiers", False) and code in MODIFIER_CODES:
                                continue
                            if value == 2 and not getattr(self.settings, "play_on_key_repeat", False):
                                continue
                            if value == 1 and not getattr(self.settings, "play_on_key_repeat", False):
                                if self._is_down[code]:
                                    continue
                            self._is_down[code] = True
                            if getattr(self.settings, "sounds_enabled", True):
                                try:
                                    self.on_key_press(code)
                                except Exception:
                                    pass
                    except OSError:
                        continue
        finally:
            for dev in devices:
                try:
                    dev.close()
                except OSError:
                    pass