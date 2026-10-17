from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSlider,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..autostart import is_enabled, set_enabled
from ..paths import custom_sounds_dir
from ..settings import Settings
from ..sound_catalog import SoundPack, all_packs
from ..sound_engine import SoundEngine
from ..sound_importer import import_sound, is_supported


class SettingsWindow(QWidget):
    def __init__(self, settings: Settings, engine: SoundEngine, hook, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.engine = engine
        self.hook = hook
        self.setWindowTitle("Dizdiz Settings")
        self.resize(520, 420)

        tabs = QTabWidget()
        tabs.addTab(self._sounds_tab(), "Sounds")
        tabs.addTab(self._behavior_tab(), "Behavior")
        tabs.addTab(self._custom_tab(), "Custom Sounds")
        tabs.addTab(self._about_tab(), "About & Privacy")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        self._refresh_packs()

    def _sounds_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self.sounds_form = form

        self.pack_combo = QComboBox()
        self.pack_combo.currentIndexChanged.connect(self._on_pack_changed)
        form.addRow("Sound pack:", self.pack_combo)

        self.sound_combo = QComboBox()
        self.sound_combo.currentIndexChanged.connect(self._on_sound_changed)
        form.addRow("Sound:", self.sound_combo)

        self.random_check = QCheckBox("Random sound from selected pack")
        self.random_check.setToolTip(
            "Plays a random sound from the selected pack. Turn this off to pick "
            "a specific sound above."
        )
        self.random_check.toggled.connect(self._on_random_changed)
        form.addRow(self.random_check)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        form.addRow("Volume:", self.volume_slider)

        self.pitch_check = QCheckBox("Pitch variation")
        self.pitch_check.toggled.connect(self._on_pitch_changed)
        form.addRow(self.pitch_check)

        self.enabled_check = QCheckBox("Sounds enabled")
        self.enabled_check.toggled.connect(self._on_enabled_changed)
        form.addRow(self.enabled_check)

        return widget

    def _behavior_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        self.repeat_check = QCheckBox("Play on key repeat")
        self.repeat_check.toggled.connect(self._on_repeat_changed)
        form.addRow(self.repeat_check)

        self.modifiers_check = QCheckBox("Play for modifier keys")
        self.modifiers_check.toggled.connect(self._on_modifiers_changed)
        form.addRow(self.modifiers_check)

        self.autostart_check = QCheckBox("Start with session")
        self.autostart_check.toggled.connect(self._on_autostart_changed)
        form.addRow(self.autostart_check)

        return widget

    def _custom_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.custom_list = QListWidget()
        layout.addWidget(self.custom_list)

        buttons = QHBoxLayout()
        import_button = QPushButton("Import sound")
        import_button.clicked.connect(self._import_sound)
        buttons.addWidget(import_button)

        open_button = QPushButton("Open folder")
        open_button.clicked.connect(self._open_custom_folder)
        buttons.addWidget(open_button)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_custom)
        buttons.addWidget(refresh_button)

        layout.addLayout(buttons)
        return widget

    def _about_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(
            "<h3>Dizdiz for Linux</h3>"
            "<p>Plays a short sound on key presses. Keystrokes are never recorded, "
            "buffered, or sent anywhere.</p>"
            "<p>Inspired by ShotGun Keyboard by Adeel Ahsan.</p>"
            "<p>Credit: <a href='https://github.com/aeronautyy/shortgun-keyboard'>Original ShotGun Keyboard project</a> "
            "and <a href='https://aeronautyy.com'>aeronautyy.com</a>.</p>"
        )
        layout.addWidget(browser)
        return widget

    def _refresh_packs(self) -> None:
        self.pack_combo.blockSignals(True)
        self.pack_combo.clear()
        for pack in all_packs():
            self.pack_combo.addItem(pack.name, pack.id)
        index = self.pack_combo.findData(self.settings.selected_pack_id)
        if index >= 0:
            self.pack_combo.setCurrentIndex(index)
        self.pack_combo.blockSignals(False)
        self._refresh_sounds()
        self._load_values()

    def _refresh_sounds(self) -> None:
        self.sound_combo.blockSignals(True)
        self.sound_combo.clear()
        pack_id = self.pack_combo.currentData()
        for pack in all_packs():
            if pack.id != pack_id:
                continue
            for sound in pack.sounds:
                self.sound_combo.addItem(sound.name, sound.id)
        index = self.sound_combo.findData(self.settings.selected_sound_id)
        if index >= 0:
            self.sound_combo.setCurrentIndex(index)
        self.sound_combo.blockSignals(False)

    def _refresh_custom(self) -> None:
        self.custom_list.clear()
        for pack in all_packs():
            if pack.id != "custom":
                continue
            for sound in pack.sounds:
                self.custom_list.addItem(f"{sound.name} ({sound.path})")

    def _load_values(self) -> None:
        widgets = (
            self.random_check,
            self.volume_slider,
            self.pitch_check,
            self.enabled_check,
            self.repeat_check,
            self.modifiers_check,
            self.autostart_check,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.random_check.setChecked(self.settings.random_mode)
            self.volume_slider.setValue(int(self.settings.volume * 100))
            self.pitch_check.setChecked(self.settings.pitch_variation)
            self.enabled_check.setChecked(self.settings.sounds_enabled)
            self.repeat_check.setChecked(self.settings.play_on_key_repeat)
            self.modifiers_check.setChecked(self.settings.play_for_modifiers)
            self.autostart_check.setChecked(is_enabled())
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._sync_sound_combo_enabled()
        self._refresh_custom()

    def _on_pack_changed(self, _index: int) -> None:
        self.settings.selected_pack_id = self.pack_combo.currentData()
        self._refresh_sounds()
        self._save()

    def _on_random_changed(self, checked: bool) -> None:
        self.settings.random_mode = checked
        self._sync_sound_combo_enabled()
        self._save()

    def _sync_sound_combo_enabled(self) -> None:
        enabled = not self.settings.random_mode
        self.sound_combo.setEnabled(enabled)
        label = self.sounds_form.labelForField(self.sound_combo)
        if label is not None:
            label.setEnabled(enabled)

    def _on_sound_changed(self, _index: int) -> None:
        self.settings.selected_sound_id = self.sound_combo.currentData()
        self._save()

    def _on_volume_changed(self, value: int) -> None:
        self.settings.volume = value / 100.0
        self._save()

    def _on_enabled_changed(self, checked: bool) -> None:
        self.settings.sounds_enabled = checked
        if checked:
            self.hook.start()
        else:
            self.hook.stop()
        self._save()

    def _on_autostart_changed(self, checked: bool) -> None:
        try:
            set_enabled(checked)
        except OSError as exc:
            QMessageBox.warning(self, "Autostart", str(exc))
            self.autostart_check.setChecked(is_enabled())
        self._save()

    def _on_pitch_changed(self, checked: bool) -> None:
        self.settings.pitch_variation = checked
        self._save()

    def _on_repeat_changed(self, checked: bool) -> None:
        self.settings.play_on_key_repeat = checked
        self._save()

    def _on_modifiers_changed(self, checked: bool) -> None:
        self.settings.play_for_modifiers = checked
        self._save()

    def _save(self) -> None:
        self.engine.update_settings(self.settings)
        self.hook.settings = self.settings
        try:
            self.settings.save()
        except OSError as exc:
            QMessageBox.warning(self, "Settings", str(exc))

    def _import_sound(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import sound",
            str(Path.home()),
            "Audio files (*.wav *.mp3 *.m4a *.aac *.aiff *.aif *.wma *.flac)",
        )
        imported = 0
        for raw in paths:
            path = Path(raw)
            if not is_supported(path):
                continue
            try:
                import_sound(path)
                imported += 1
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Import failed", str(exc))
        if imported:
            self._refresh_packs()
            self._refresh_custom()
            QMessageBox.information(self, "Import complete", f"Imported {imported} sound(s).")

    def _open_custom_folder(self) -> None:
        custom_sounds_dir().mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(custom_sounds_dir())))