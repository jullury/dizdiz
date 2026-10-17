import signal
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .autostart import is_enabled
from .keyboard_hook import KeyboardHook
from .paths import crash_log_path, custom_sounds_dir
from evdev import ecodes

from .settings import Settings
from .single_instance import SingleInstance
from .sound_catalog import find_sound
from .sound_engine import SoundEngine
from .ui.settings_window import SettingsWindow


class Application:
    def __init__(self) -> None:
        self.settings = Settings.load()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("Dizdiz")

        self.engine = SoundEngine(self.settings)
        self.engine.preload()
        self.hook = KeyboardHook(self.settings, self._on_key_press)

        self.settings_window: SettingsWindow | None = None
        self.tray = self._create_tray()

        if self.settings.sounds_enabled:
            self.hook.start()

        if not self.settings.has_launched_before:
            self.settings.has_launched_before = True
            try:
                self.settings.save()
            except OSError:
                pass
            self.show_settings()

    def _create_tray(self) -> QSystemTrayIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        font = QFont()
        font.setPixelSize(48)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "🔫")
        painter.end()
        icon = QIcon(pixmap)
        self.icon = icon
        self.app.setWindowIcon(icon)

        tray = QSystemTrayIcon(icon, self.app)
        menu = QMenu()

        self.enabled_action = menu.addAction("Sounds enabled")
        self.enabled_action.setCheckable(True)
        self.enabled_action.setChecked(self.settings.sounds_enabled)
        self.enabled_action.triggered.connect(self._toggle_sounds)

        settings_action = menu.addAction("Settings")
        settings_action.triggered.connect(self.show_settings)

        folder_action = menu.addAction("Open imported sounds folder")
        folder_action.triggered.connect(self._open_sounds_folder)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        return tray

    def show_settings(self) -> None:
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.settings, self.engine, self.hook)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _toggle_sounds(self, checked: bool) -> None:
        self.settings.sounds_enabled = checked
        if checked:
            self.hook.start()
        else:
            self.hook.stop()
        self.engine.update_settings(self.settings)
        try:
            self.settings.save()
        except OSError:
            pass

    def _open_sounds_folder(self) -> None:
        custom_sounds_dir().mkdir(parents=True, exist_ok=True)
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(custom_sounds_dir())))

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_settings()

    def _on_key_press(self, key_code: int) -> None:
        if key_code in (ecodes.KEY_ENTER, ecodes.KEY_KPENTER):
            sound = self._enter_sound()
            self.engine.play(sound)
        else:
            self.engine.play()

    def _enter_sound(self):
        from .sound_catalog import all_packs

        selected_pack = None
        for pack in all_packs():
            if pack.id == self.settings.selected_pack_id:
                selected_pack = pack
                break
        if selected_pack is None or not selected_pack.sounds:
            return None
        for sound in selected_pack.sounds:
            lowered = sound.id.lower()
            if "reload" in lowered or "enter" in lowered or "return" in lowered:
                return sound
        return selected_pack.sounds[0]

    def _quit(self) -> None:
        self.hook.stop()
        self.engine.shutdown()
        self.tray.hide()
        self.app.quit()

    def run(self) -> int:
        return self.app.exec()


def main() -> int:
    # Ctrl-C in the launching terminal must quit. CPython replaces SIGINT's
    # default disposition with a handler that only sets a flag, and the flag is
    # acted on at the next Python bytecode boundary -- which never comes while
    # Qt's event loop is blocked in C++, so the app ignores Ctrl-C. Restoring
    # the kernel default makes SIGINT terminate the process immediately, in
    # every path including nested modal loops. Nothing is lost by skipping the
    # graceful path: SoundEngine.shutdown() is a no-op, the keyboard thread is a
    # daemon, and the kernel closes its fds and releases the flock on exit.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    single = SingleInstance()
    if not single.acquire():
        app = QApplication(sys.argv)
        QMessageBox.information(None, "Dizdiz", "Dizdiz is already running.")
        return 0

    def handle_exception(exc_type, exc_value, exc_traceback):
        try:
            crash_log_path().parent.mkdir(parents=True, exist_ok=True)
            with crash_log_path().open("a", encoding="utf-8") as handle:
                import traceback

                traceback.print_exception(exc_type, exc_value, exc_traceback, file=handle)
        except OSError:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception

    try:
        application = Application()
        code = application.run()
    finally:
        single.release()
    return code


if __name__ == "__main__":
    raise SystemExit(main())