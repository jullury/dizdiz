# shotgun-keyboard (Linux) — Design

**Date:** 2026-10-17
**Status:** Approved (design), pending implementation plan
**Scope:** Minimal MVP — keyboard-sound player for Linux, structurally inspired by
ShotGunKeyboard (Windows), built from scratch with its own assets.

## Background

ShotGunKeyboard is a Windows novelty app: a WinForms tray application that installs a passive
low-level keyboard hook (`SetWindowsHookEx(WH_KEYBOARD_LL)`) and plays a short sound on every key
press, system-wide. Its relevant behaviours (established by static analysis of the shipped binary):

- Passive hook that always forwards keystrokes (`CallNextHookEx`); it never swallows input.
- Only keeps a single held-bit per key; no buffer, history or character reconstruction.
- Persistence is opt-in via `HKCU\...\CurrentVersion\Run`, toggled by the user.
- Config in `%APPDATA%\ShotGun Keyboard\settings.json` (atomic write via a `.tmp` file).
- Built-in sound packs embedded as resources; custom sounds imported to a user folder.
- Single-instance via a named global mutex.

This project reproduces the *behaviour* on Linux. It does **not** reuse the original's source,
name-branding, or audio assets.

## Target environment (measured, not assumed)

- CachyOS (Arch-based), **Hyprland** compositor, `XDG_SESSION_TYPE=wayland`, Wayland session.
- User is a member of the **`input` group** → `/dev/input/event*` are readable without root.
- A StatusNotifier host is running (`qs -c ii`, Quickshell), so an AppIndicator icon renders.
- Installed: `python-evdev 2.0.0`, `numpy 2.5.4`, `pillow`, `PyGObject` + GTK3 +
  AyatanaAppIndicator3, `python-gst`, `uv`, `pip`. Python 3.14.
- Audio server: PipeWire 1.6.9 (PulseAudio compatibility).

## Goals

- Play a short sound on every key press, system-wide, on a Wayland or X11 session.
- Passive capture: never intercept, delay, alter or swallow input.
- Tray control: enable/disable, volume, test sound, start-at-login, quit.
- Opt-in autostart; XDG-conformant config; atomic writes.
- Privacy-equivalent to the original: key *codes* only, no characters, no history, no network.

## Non-goals (MVP)

- Settings/About/Privacy GUI windows.
- Multiple sound packs, random mode, pitch variation, custom-sound import.
- Distributing or bundling any third-party audio assets.
- Non-Linux platforms. Root/`libinput` system-wide capture. X11-only XRecord path.

## Architecture

A single Python process driven by one **GLib main loop**. No application-owned threads.

```
evdev fds ──(GLib io_add_watch, O_RDONLY, never EVIOCGRAB)──▶ KeyFilter ──▶ SoundEngine
/dev/input (inotify watch) ─── hotplug rescan ─────────────────┘                │
                                                                    miniaudio PlaybackDevice
Config (~/.config/…/settings.json) ◀── Controller ──▶ Tray (AyatanaAppIndicator3)
                                              ▲
                          control socket ($XDG_RUNTIME_DIR) ◀── CLI (toggle/status)
```

Rationale: evdev is read non-blocking inside the GLib loop; miniaudio mixes on its own internal
audio thread; the tray is GTK (also main-loop based). Keeping the application single-threaded
removes a whole class of race conditions around the voice pool and enable/disable transitions.

### Why evdev

Linux has no portable global keyboard hook. On Wayland (deliberately) there is no global input
API at all. Options considered:

| Backend | Wayland | TTY | Permission cost |
|---|---|---|---|
| **evdev** (`/dev/input/event*`, read-only) | yes | yes | `input` group (already satisfied) |
| X11 XRecord / XInput2 | no | no | none |
| libinput (system-wide) | yes | yes | root / seat manager |

evdev is the only universal passive reader and carries no extra privilege here.

## Components

Each unit has one purpose, a narrow interface, and is testable independently.

### `config.py`
- Paths per XDG Base Directory spec:
  - settings: `$XDG_CONFIG_HOME/shotgun-keyboard/settings.json` (default `~/.config/...`)
  - state/logs: `$XDG_STATE_HOME/shotgun-keyboard/` (default `~/.local/state/...`)
- `load()` returns defaults on missing/corrupt file (never raises to the caller); a corrupt file is
  moved aside rather than silently overwritten.
- `save()` is atomic: write `settings.json.tmp`, `fsync`, `os.replace` onto the target.
- Schema (MVP): `enabled: bool`, `volume: float` (0.0–1.0), `play_on_key_repeat: bool`,
  `play_for_modifiers: bool`, `sound: str` (asset name), `min_interval_ms: int`,
  `launch_at_login: bool`.

### `autostart.py`
- `enable()` writes `~/.config/autostart/shotgun-keyboard.desktop`
  (`Type=Application`, `Exec=…`, `X-GNOME-Autostart-enabled=true`).
- `disable()` removes it. `is_enabled()` checks presence.
- **Hyprland caveat:** Hyprland does not process XDG autostart. The app writes the `.desktop`
  (correct and portable) and additionally surfaces the exact `exec-once` line for the user to add
  to their own config. The app never edits the user's Hyprland (Lua) configuration.

### `input_source.py`
- Enumerates `evdev.list_devices()`; admits a device only if it looks like a keyboard
  (exposes `KEY_A` and `KEY_SPACE`), excluding mice, power buttons, gamepads.
- Opens devices `O_RDONLY` and **never issues `EVIOCGRAB`**.
- Registers each fd with `GLib.io_add_watch`; emits decoded key events to a callback.
- Watches `/dev/input` via inotify for hotplug and rescans; closes fds for vanished devices.
- Behind an interface so tests substitute a synthetic event source.

### `key_filter.py` (pure, fully unit-testable)
Decides whether an event produces a sound:
- Only `EV_KEY` events; ignore `EV_MSC`/`EV_SYN`.
- Values: `1` = press, `2` = **kernel auto-repeat**, `0` = release. Repeat handled directly from the
  value (no held-bit array required on Linux, unlike the Windows original).
- `play_on_key_repeat` includes/excludes value `2`.
- `play_for_modifiers` includes/excludes `KEY_LEFTSHIFT`/`_RIGHTSHIFT`/`_LEFTCTRL`/`_RIGHTCTRL`/
  `_LEFTALT`/`_RIGHTALT`/`_LEFTMETA`/`_RIGHTMETA`/`_CAPSLOCK`.

### `engine.py`
- Owns a fixed-size **voice pool** (default 32). Each voice is `(buffer, position, gain)`.
- A single miniaudio callback mixes active voices into the output buffer; a new trigger takes a free
  voice or steals the oldest. Optional `min_interval_ms` throttle per trigger.
- Owns volume and the enabled state. `fire(sound_name)`, `set_volume(v)`, `start()`, `stop()`.
- Device buffer ~256 frames for low latency; `stop()` releases the device.

### `audio_loader.py`
- Decodes packaged WAV files to float32 numpy arrays at startup (stdlib `wave` + numpy).
- Missing/undecodable assets are reported once and skipped, never fatal.

### `tray.py`
- AyatanaAppIndicator3 icon and menu: Enable/Disable (checked item), Volume submenu
  (e.g. 25/50/75/100 %), Test sound, "Start at login" (checked), Quit.
- Reflects `Controller` state; no business logic of its own.

### `controller.py`
- The seam between UI, filter, engine and config. Applies settings, persists changes via
  `config.save()`, and republishes state to the tray.
- Enabling/disabling starts/stops the input watch and the audio device as a unit.

### `control_socket.py`
- Unix socket at `$XDG_RUNTIME_DIR/shotgun-keyboard.sock`.
- Commands: `toggle`, `enable`, `disable`, `status`. Backs the CLI subcommands; convenient for a
  Hyprland keybind. MVP-cheap, no D-Bus.

### `__main__.py`
- Parses args (`--dry-run`, `toggle|enable|disable|status`, `--version`).
- `--dry-run`: enumerate devices and print detected keys without playing audio (real-hardware smoke
  test).
- Acquires the single-instance lock (`flock` on `$XDG_RUNTIME_DIR/shotgun-keyboard.lock`); if held,
  the CLI form forwards the command over the socket and exits, otherwise it reports already-running.
- Installs a top-level exception handler that logs to the XDG state dir and shows a tray
  notification rather than a modal dialog.

## Data flow

1. Kernel keyboard device → evdev fd readable → GLib watch decodes `InputEvent`.
2. `key_filter` decides play/skip (type, value, modifier policy).
3. On play → `engine.fire(sound)` → voice allocated → mixed into the next output buffer.
4. Tray/CLI → `controller` → mutates config + engine/input state → persists atomically.

## Error handling

- No `input`-capable devices, or permission denied: log clearly, keep the tray alive, show a
  notification ("no keyboard device readable — is the user in the `input` group?"); disabling
  keyboard sounds removes the input watch entirely.
- No audio device: tray shows "Audio unavailable"; capture continues; enabling later recovers.
- Corrupt config: move aside, start from defaults.
- Fatal crash: log to state dir + notification; release the lock.

## Security & privacy

- Reading `/dev/input` is a real capability: it can observe every keystroke including passwords.
  Mitigations: the reader is small and auditable; key **codes only**, no characters, no mapping to
  text; no history/queue/buffer; nothing written to disk or sent over the network; no network
  dependency is declared at all.
- Never `EVIOCGRAB` — input must always reach the rest of the system.
- Privilege: no root. The `input` group membership is the only requirement; a udev rule granting a
  capability to the binary is the documented tighter alternative.
- No update mechanism, no telemetry, no external links opened programmatically.

## Testing strategy

TDD; each unit below gets failing tests first.

- **`key_filter`** — table-driven: press/repeat/release, modifier on/off, non-key events.
- **`engine`** — mixer sums voices, correct gain, steals the oldest at capacity, respects
  `min_interval_ms`, offers silence when idle.
- **`config`** — round-trip, defaults on missing, corrupt-file quarantine, atomic replace (target
  never observed partial), XDG env overrides honoured.
- **`autostart`** — `.desktop` created/removed, `is_enabled()` correctness, idempotent enable.
- **`input_source`** — device classification (a fake mouse capability set is rejected; a fake
  keyboard accepted) with a fake source; hotplug rescan closes stale fds.
- **`control_socket`** — command dispatch, unknown command rejected, single-instance behaviour.
- **Manual** — `--dry-run` against real devices; verify keys detected, nothing swallowed, tray
  toggles work, and audio plays with acceptable latency.

## Dependencies & packaging

- Runtime: `evdev`, `numpy` (present on this system), `miniaudio` (add). `PyGObject`/GTK3/
  AyatanaAppIndicator3 are system packages.
- Because `gi` must be importable, the virtualenv is created with `--system-site-packages`
  (`uv venv --system-site-packages`) and `miniaudio` added to it; `pyproject.toml` records deps.
- Alternative with zero new packages: GStreamer (`python-gst`, already installed) for playback, at
  the cost of more complex overlapping-one-shot mixing and higher per-sound startup latency.
  Documented, not chosen.
- Assets are generated by `tools/make_sounds.py` (numpy → stdlib `wave`) and committed; no
  third-party audio is bundled.

## Repository layout

```
shotgun-keyboard/
  pyproject.toml
  README.md
  docs/superpowers/specs/2026-10-17-shotgun-keyboard-design.md
  src/shotgun_keyboard/
    __main__.py  config.py  autostart.py  input_source.py  key_filter.py
    engine.py  audio_loader.py  tray.py  controller.py  control_socket.py
  assets/sounds/*.wav
  tools/make_sounds.py
  tests/
```

## Open questions / accepted risks

- **Compositor coverage:** verified on Hyprland/Wayland. GNOME/KDE Wayland should work identically
  (evdev is compositor-independent); X11 untested but expected to work.
- **Tray availability:** depends on a StatusNotifier host. Present here (Quickshell); if absent, the
  CLI/socket and config file remain fully functional.
- **Audio latency** depends on the PipeWire quantum; the 256-frame buffer is a starting point to be
  tuned on real hardware.
- **Naming/branding:** repository is named `shotgun-keyboard` and inspired by ShotGunKeyboard. It
  shares no code or assets; keep it non-public or rename if that is a concern.
