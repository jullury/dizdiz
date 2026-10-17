import json
import urllib.error
from importlib import metadata

from dizdiz.update_check import (
    current_version,
    fetch_latest_version,
    is_newer,
    parse_version,
    should_notify,
)


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def _patch_urlopen(monkeypatch, handler):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append((request, timeout))
        return handler(request)

    monkeypatch.setattr("dizdiz.update_check.urllib.request.urlopen", fake_urlopen)
    return calls


def test_parse_version_strips_tag_prefix():
    assert parse_version("v0.2.0") == (0, 2, 0)
    assert parse_version("0.1.10") == (0, 1, 10)


def test_parse_version_handles_two_part_versions():
    assert parse_version("0.2") == (0, 2)


def test_parse_version_rejects_prereleases_and_garbage():
    assert parse_version("v0.2.0-rc.1") is None
    assert parse_version("0.2.0+local") is None
    assert parse_version("latest") is None
    assert parse_version("") is None


def test_is_newer_compares_numeric_components():
    assert is_newer("0.2.0", "0.1.0") is True
    assert is_newer("v1.0.0", "0.9.9") is True
    assert is_newer("0.1.0", "0.1.0") is False
    assert is_newer("0.1.0", "0.2.0") is False


def test_is_newer_pads_short_versions():
    assert is_newer("0.2", "0.2.0") is False
    assert is_newer("0.2.1", "0.2") is True


def test_is_newer_is_false_for_unparseable_versions():
    assert is_newer("nightly", "0.1.0") is False
    assert is_newer("0.2.0", "unknown") is False


def test_should_notify_returns_true_for_newer_unnotified_version():
    assert should_notify("v0.2.0", "0.1.0", None) is True


def test_should_notify_skips_already_notified_version():
    assert should_notify("v0.2.0", "0.1.0", "0.2.0") is False
    assert should_notify("v0.2.0", "0.1.0", "v0.2.0") is False


def test_should_notify_skips_current_or_older_version():
    assert should_notify("v0.1.0", "0.1.0", None) is False
    assert should_notify("v0.0.9", "0.1.0", None) is False


def test_should_notify_skips_unparseable_latest():
    assert should_notify("nightly", "0.1.0", None) is False


def test_fetch_latest_version_returns_tag_name(monkeypatch):
    body = json.dumps({"tag_name": "v0.2.0"}).encode("utf-8")
    _patch_urlopen(monkeypatch, lambda _request: _FakeResponse(body))

    assert fetch_latest_version() == "v0.2.0"


def test_fetch_latest_version_sends_user_agent(monkeypatch):
    body = json.dumps({"tag_name": "v0.2.0"}).encode("utf-8")
    calls = _patch_urlopen(monkeypatch, lambda _request: _FakeResponse(body))

    fetch_latest_version()

    request, timeout = calls[0]
    assert request.get_header("User-agent")
    assert timeout is not None


def test_fetch_latest_version_returns_none_on_network_error(monkeypatch):
    def explode(_request):
        raise urllib.error.URLError("offline")

    _patch_urlopen(monkeypatch, explode)

    assert fetch_latest_version() is None


def test_fetch_latest_version_returns_none_on_bad_payload(monkeypatch):
    _patch_urlopen(monkeypatch, lambda _request: _FakeResponse(b"{not json"))
    assert fetch_latest_version() is None

    _patch_urlopen(monkeypatch, lambda _request: _FakeResponse(b"{}"))
    assert fetch_latest_version() is None

    _patch_urlopen(monkeypatch, lambda _request: _FakeResponse(json.dumps({"tag_name": 3}).encode()))
    assert fetch_latest_version() is None


def test_current_version_prefers_installed_metadata(monkeypatch, tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "9.9.9"\n')
    monkeypatch.setattr("dizdiz.update_check._pyproject_path", lambda: pyproject)
    monkeypatch.setattr("dizdiz.update_check.metadata.version", lambda _name: "1.2.3")

    assert current_version() == "1.2.3"


def test_current_version_falls_back_to_source_tree(monkeypatch, tmp_path):
    """A bare checkout has no installed distribution metadata."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "dizdiz"\nversion = "0.4.2"\n')

    def missing(_name):
        raise metadata.PackageNotFoundError(_name)

    monkeypatch.setattr("dizdiz.update_check.metadata.version", missing)
    monkeypatch.setattr("dizdiz.update_check._pyproject_path", lambda: pyproject)

    assert current_version() == "0.4.2"


def test_current_version_is_none_without_metadata_or_pyproject(monkeypatch, tmp_path):
    def missing(_name):
        raise metadata.PackageNotFoundError(_name)

    monkeypatch.setattr("dizdiz.update_check.metadata.version", missing)

    monkeypatch.setattr("dizdiz.update_check._pyproject_path", lambda: tmp_path / "absent.toml")
    assert current_version() is None

    broken = tmp_path / "broken.toml"
    broken.write_text("[project\nversion =")
    monkeypatch.setattr("dizdiz.update_check._pyproject_path", lambda: broken)
    assert current_version() is None

    versionless = tmp_path / "versionless.toml"
    versionless.write_text('[project]\nname = "dizdiz"\n')
    monkeypatch.setattr("dizdiz.update_check._pyproject_path", lambda: versionless)
    assert current_version() is None
