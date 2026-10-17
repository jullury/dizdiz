"""The hourly update poll must notify once per release and never block the UI."""

import os
import threading

import pytest

pytest.importorskip("PyQt6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from dizdiz import app as app_module  # noqa: E402
from dizdiz.settings import Settings  # noqa: E402


@pytest.fixture
def application(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    Settings(sounds_enabled=False, has_launched_before=True).save()
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "current_version", lambda: "0.1.0")
    instance = app_module.Application()
    try:
        yield instance
    finally:
        instance.tray.hide()


def _capture_notifications(monkeypatch, application) -> list[tuple]:
    shown: list[tuple] = []
    monkeypatch.setattr(application.tray, "showMessage", lambda *args: shown.append(args))
    return shown


def test_new_version_notifies_once_and_is_remembered(application, monkeypatch):
    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: "v9.9.9")
    shown = _capture_notifications(monkeypatch, application)

    application._fetch_update()

    assert len(shown) == 1
    assert "9.9.9" in shown[0][1]
    assert Settings.load().last_notified_version == "v9.9.9"

    application._fetch_update()

    assert len(shown) == 1


def test_current_version_is_not_announced(application, monkeypatch):
    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: "v0.1.0")
    shown = _capture_notifications(monkeypatch, application)

    application._fetch_update()

    assert shown == []


def test_offline_poll_notifies_nothing(application, monkeypatch):
    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: None)
    shown = _capture_notifications(monkeypatch, application)

    application._fetch_update()

    assert shown == []


def test_disabled_update_check_starts_no_thread(application, monkeypatch):
    application.settings.check_updates = False

    def explode(*_args, **_kwargs):
        raise AssertionError("update check ran while disabled")

    monkeypatch.setattr(app_module.threading, "Thread", explode)

    application._check_for_update()


def test_enabled_update_check_polls_off_the_ui_thread(application, monkeypatch):
    started: list[object] = []

    class FakeThread:
        def __init__(self, target=None, daemon=None, **_kwargs):
            self.target = target
            self.daemon = daemon

        def start(self):
            started.append(self)

    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)
    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: "v9.9.9")
    monkeypatch.setattr(application.tray, "showMessage", lambda *args: None)

    application._check_for_update()

    assert len(started) == 1
    assert started[0].daemon is True

    # The worker must only signal; the notification belongs to the UI thread.
    started[0].target()
    assert application._update_check_running is False


def test_poll_is_not_reentrant_while_a_check_is_running(application, monkeypatch):
    started: list[object] = []

    class FakeThread:
        def __init__(self, target=None, daemon=None, **_kwargs):
            self.target = target

        def start(self):
            started.append(self)

    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    application._check_for_update()
    application._check_for_update()

    assert len(started) == 1


def test_notification_is_delivered_on_the_ui_thread(application, monkeypatch):
    """showMessage from a worker thread is undefined behaviour in Qt."""
    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: "v9.9.9")
    seen: list[object] = []
    monkeypatch.setattr(
        application.tray,
        "showMessage",
        lambda *_args: seen.append(threading.current_thread()),
    )

    worker = threading.Thread(target=application._fetch_update)
    worker.start()
    worker.join()

    # A queued connection hands the work to the event loop instead of running it
    # inline on the worker.
    assert seen == []

    QApplication.processEvents()

    assert seen == [threading.main_thread()]


def test_update_available_item_is_hidden_until_a_newer_release_is_known(application, monkeypatch):
    assert application.update_available_action.isVisible() is False

    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: "v9.9.9")
    monkeypatch.setattr(application.tray, "showMessage", lambda *args: None)

    application._fetch_update()
    QApplication.processEvents()

    assert application.update_available_action.isVisible() is True
    assert "9.9.9" in application.update_available_action.text()


def test_update_available_item_stays_hidden_for_current_version(application, monkeypatch):
    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: "v0.1.0")
    monkeypatch.setattr(application.tray, "showMessage", lambda *args: None)

    application._fetch_update()
    QApplication.processEvents()

    assert application.update_available_action.isVisible() is False


def test_manual_check_reports_already_dismissed_version(application, monkeypatch):
    """A dismissed notification must not be gone forever."""
    application.settings.last_notified_version = "v9.9.9"
    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: "v9.9.9")
    shown = _capture_notifications(monkeypatch, application)

    application._check_for_update(manual=True)
    QApplication.processEvents()

    assert len(shown) == 1
    assert "9.9.9" in shown[0][1]


def test_manual_check_reports_up_to_date(application, monkeypatch):
    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: "v0.1.0")
    shown = _capture_notifications(monkeypatch, application)

    application._check_for_update(manual=True)
    QApplication.processEvents()

    assert len(shown) == 1
    assert "up to date" in shown[0][0].lower() or "up to date" in shown[0][1].lower()


def test_manual_check_reports_unreachable_github(application, monkeypatch):
    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: None)
    shown = _capture_notifications(monkeypatch, application)

    application._check_for_update(manual=True)
    QApplication.processEvents()

    assert len(shown) == 1


def test_manual_check_works_when_automatic_checks_are_disabled(application, monkeypatch):
    application.settings.check_updates = False
    started: list[object] = []

    class FakeThread:
        def __init__(self, target=None, daemon=None, **_kwargs):
            self.target = target

        def start(self):
            started.append(self)

    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    application._check_for_update(manual=True)

    assert len(started) == 1


def test_check_now_menu_item_triggers_a_manual_check(application, monkeypatch):
    started: list[object] = []

    class FakeThread:
        def __init__(self, target=None, daemon=None, **_kwargs):
            self.target = target

        def start(self):
            started.append(self)

    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    application.check_now_action.trigger()

    assert len(started) == 1


def test_update_available_click_opens_releases_page(application, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        app_module,
        "QDesktopServices",
        type("Fake", (), {"openUrl": staticmethod(lambda url: opened.append(url.toString()))}),
    )

    application.update_available_action.trigger()

    assert opened == [app_module.RELEASES_PAGE_URL]


def test_manual_check_does_not_re_announce_forever(application, monkeypatch):
    """Only newer-than-installed versions can ever be announced."""
    application.settings.last_notified_version = None
    monkeypatch.setattr(app_module, "fetch_latest_version", lambda: "v0.0.9")
    shown = _capture_notifications(monkeypatch, application)

    application._check_for_update(manual=True)
    QApplication.processEvents()

    assert len(shown) == 1  # "up to date", not an update notice
    assert "9.9" not in shown[0][1]
