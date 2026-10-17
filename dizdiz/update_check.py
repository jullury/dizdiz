"""Read a release tag from GitHub so the tray can announce newer versions.

The only network request the app ever makes: one unauthenticated GET per hour
(and none at all when ``Settings.check_updates`` is off). Nothing about the
user or their keystrokes is sent.
"""

import json
import tomllib
import urllib.error
import urllib.request
from importlib import metadata
from pathlib import Path

RELEASES_URL = "https://api.github.com/repos/jullury/dizdiz/releases/latest"
RELEASES_PAGE_URL = "https://github.com/jullury/dizdiz/releases/latest"
REQUEST_TIMEOUT_SECONDS = 5.0


def parse_version(text: str) -> tuple[int, ...] | None:
    """Parse ``"v0.2.0"`` into ``(0, 2, 0)``.

    Anything that is not a dot-separated run of digits returns ``None``, which
    deliberately covers prerelease tags (``v0.2.0-rc.1``) and build metadata
    (``0.2.0+local``): those are never announced as updates.
    """
    if not isinstance(text, str):
        return None
    candidate = text.strip()
    if candidate[:1].lower() == "v":
        candidate = candidate[1:]
    parts = candidate.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_newer(latest: str, current: str) -> bool:
    """True when ``latest`` is a strictly higher version than ``current``."""
    latest_parts = parse_version(latest)
    current_parts = parse_version(current)
    if latest_parts is None or current_parts is None:
        return False
    width = max(len(latest_parts), len(current_parts))
    latest_padded = latest_parts + (0,) * (width - len(latest_parts))
    current_padded = current_parts + (0,) * (width - len(current_parts))
    return latest_padded > current_padded


def should_notify(latest: str, current: str, last_notified: str | None) -> bool:
    """True when ``latest`` is newer than ``current`` and not already announced.

    Without the ``last_notified`` guard an hourly poll would re-announce the
    same release every hour.
    """
    if not is_newer(latest, current):
        return False
    if last_notified is None:
        return True
    return parse_version(latest) != parse_version(last_notified)


def fetch_latest_version(timeout: float = REQUEST_TIMEOUT_SECONDS) -> str | None:
    """Return the latest release tag, or ``None`` when offline or unavailable."""
    request = urllib.request.Request(
        RELEASES_URL,
        headers={
            # GitHub's API rejects requests without a User-Agent.
            "User-Agent": "dizdiz-update-check",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag.strip():
        return None
    return tag


def current_version() -> str | None:
    """Version of the running app, or ``None`` when it cannot be determined.

    Installed distributions report their metadata. A bare source checkout (the
    documented ``python -m dizdiz`` mode) has none, so fall back to the
    ``pyproject.toml`` next to the package — release tooling bumps that file, so
    a checkout knows its own version.
    """
    try:
        return metadata.version("dizdiz")
    except metadata.PackageNotFoundError:
        return _pyproject_version()


def _pyproject_path() -> Path:
    """``pyproject.toml`` beside the package, whether or not it exists."""
    return Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject_version() -> str | None:
    try:
        with _pyproject_path().open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        return None
    return version
