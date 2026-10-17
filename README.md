# Dizdiz (Linux)

A tray-resident keyboard sound player for Linux. It plays a short sound on every
key press without blocking or recording keystrokes.

Input is read directly from `/dev/input` via `evdev` (no X11/Wayland grab), so
keystrokes pass through untouched and nothing is logged. Works on X11 and
Wayland.

## Requirements

- Python 3.11+
- PyQt6
- evdev
- An audio player: `pw-play` (PipeWire) or `paplay` (PulseAudio). If neither is
  found, Dizdiz runs silently.
- Read access to `/dev/input/event*` — membership in the `input` group is the
  usual way:
  ```bash
  sudo usermod -aG input "$USER"
  ```
  Log out and back in for the group change to apply.
- ffmpeg (optional) — only needed to import non-WAV audio

## Install

### Clone

```bash
git clone https://github.com/jullury/dizdiz.git
cd dizdiz
```

### System dependencies

On Debian/Ubuntu:

```bash
sudo apt install python3 python3-pip python3-pyqt6 python3-evdev pipewire pulseaudio-utils
sudo usermod -aG input "$USER"
```

On Fedora:

```bash
sudo dnf install python3 python3-pip python3-qt6 python3-evdev pipewire pulseaudio-utils
sudo usermod -aG input "$USER"
```

Log out and back in after the `input` group change so you can read `/dev/input/event*`.

### Install dizdiz

```bash
pip install .
```

This installs the `dizdiz` command. Alternatively run from a checkout without
installing:

```bash
python -m dizdiz
```

`pw-play` (PipeWire) or `paplay` (PulseAudio) must be on `PATH` for sounds to play; if neither is found, Dizdiz runs silently. `ffmpeg` is optional — only needed to import non-WAV sounds.

## Usage

Dizdiz lives in the system tray. Double-click the tray icon (or choose
*Settings*) to configure it:

- Enable/disable sounds
- Sound pack and sound selection, or random picks from the pack
- Volume, pitch variation
- Play on key repeat, play for modifier keys
- Start with session (XDG autostart entry)
- Import your own sounds (converted to WAV via ffmpeg)

The tray menu also offers *Sounds enabled*, *Open imported sounds folder*, and
*Quit*. Volume is adjusted with the slider in Settings.

Only one instance runs at a time; starting a second one shows a notice.

### Sound packs

Nine packs ship built in: `arcade`, `bubble`, `click`, `drum`, `laser`,
`mechanical`, `scifi`, `shotgun`, `typewriter`. The handgun sounds previously in
a separate `pistol` pack are part of `shotgun` (the two were byte-identical).

Every bundled sound is generated for the project (`tools/make_sounds.py`) or
third-party audio vetted under the project constitution with provenance
documented in `tools/AUDIO_PROVENANCE.md`; none carries embedded producer
metadata. `tools/make_sounds.py` regenerates the `laser`, `scifi` and
`mechanical` groups:

```bash
python tools/make_sounds.py            # all groups
python tools/make_sounds.py laser      # one group
```

`shotgun/reload.wav` is third-party audio: a SampleSwap contributor upload
under their public-domain policy; source and licence are documented in
`tools/AUDIO_PROVENANCE.md`.

Imported sounds are stored as WAV in:

```
~/.local/share/dizdiz/CustomSounds/
```

They appear as the *My Sounds* pack. Dropping `.wav` files into that folder
works too.

### Files

| Path | Purpose |
| --- | --- |
| `~/.config/dizdiz/settings.json` | Settings |
| `~/.config/dizdiz/crash.log` | Uncaught exception log |
| `~/.config/autostart/dizdiz.desktop` | Autostart entry (managed by the checkbox) |
| `~/.local/share/dizdiz/CustomSounds/` | Imported / user WAV files |

`XDG_CONFIG_HOME` and `XDG_DATA_HOME` are respected.

## Tests

```bash
pytest
```

## Releases

Versioning is automated from Conventional Commit messages
(`feat` → minor, `fix`/`perf` → patch, `!`/`BREAKING CHANGE` → minor while the
major version is `0`). Every push to `main` runs
`.github/workflows/release.yml`, which bumps `pyproject.toml`, regenerates
`CHANGELOG.md`, tags `vX.Y.Z`, and publishes a GitHub Release.

Enable the local commit-message guard once per clone:

```bash
git config core.hooksPath .githooks
```

## Licence

MIT — see [LICENSE](LICENSE).
