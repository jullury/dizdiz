#!/usr/bin/env python3
"""Generate dizdiz's bundled sound effects.

Every file written by this script is first-party: it is synthesised here with
numpy and written with the stdlib ``wave`` module, so it carries no third-party
licence obligations and no embedded provenance metadata.

Usage:
    python tools/make_sounds.py            # write every generated sound
    python tools/make_sounds.py laser      # write only one group

The ``laser``, ``scifi`` and ``mechanical`` groups below deliberately replace
files that were previously sourced from outside the project.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
SOUNDS_DIR = Path(__file__).resolve().parent.parent / "dizdiz" / "assets" / "sounds"
PEAK = 0.9


def _write(relative: str, samples: np.ndarray, fade_in: float = 0.002, fade_out: float = 0.012) -> Path:
    """Peak-normalise, fade both ends to silence, and write 16-bit mono WAV."""
    samples = np.asarray(samples, dtype=np.float64).ravel()
    peak = float(np.abs(samples).max())
    if peak > 0:
        samples = samples / peak * PEAK

    n_in = min(int(SAMPLE_RATE * fade_in), len(samples) // 2)
    n_out = min(int(SAMPLE_RATE * fade_out), len(samples) // 2)
    if n_in:
        samples[:n_in] *= np.linspace(0.0, 1.0, n_in)
    if n_out:
        samples[-n_out:] *= np.linspace(1.0, 0.0, n_out)

    path = SOUNDS_DIR / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return path


def _t(duration: float) -> np.ndarray:
    return np.arange(int(SAMPLE_RATE * duration)) / SAMPLE_RATE


def _sweep(duration: float, start_hz: float, end_hz: float, decay: float) -> np.ndarray:
    """Exponential frequency sweep with an exponential amplitude decay."""
    t = _t(duration)
    ratio = end_hz / start_hz
    phase = 2 * np.pi * start_hz * (np.power(ratio, t / max(t[-1], 1e-9)) - 1) / np.log(ratio)
    tone = np.sin(phase) + 0.25 * np.sin(2 * phase)
    return tone * np.exp(-t / decay)


def _noise_burst(duration: float, decay: float, smooth: int, seed: int) -> np.ndarray:
    """White noise shaped by an exponential decay and a crude low-pass."""
    rng = np.random.default_rng(seed)
    t = _t(duration)
    noise = rng.uniform(-1.0, 1.0, len(t))
    if smooth > 1:
        noise = np.convolve(noise, np.ones(smooth) / smooth, mode="same")
    return noise * np.exp(-t / decay)


def _ping(freq: float, duration: float, decay: float, harmonic: float = 0.3) -> np.ndarray:
    t = _t(duration)
    return (np.sin(2 * np.pi * freq * t) + harmonic * np.sin(4 * np.pi * freq * t)) * np.exp(-t / decay)


def _place(target: np.ndarray, source: np.ndarray, offset_seconds: float, gain: float = 1.0) -> None:
    start = int(SAMPLE_RATE * offset_seconds)
    end = min(len(target), start + len(source))
    if end > start:
        target[start:end] += source[: end - start] * gain


def laser() -> list[Path]:
    """Three distinct descending zaps, for keypress feedback."""
    variants = [
        ("zap1.wav", 2600.0, 300.0, 0.030, 0.15),
        ("zap2.wav", 3400.0, 450.0, 0.035, 0.15),
        ("zap3.wav", 2000.0, 220.0, 0.026, 0.15),
    ]
    written = []
    for index, (name, start_hz, end_hz, decay, duration) in enumerate(variants):
        samples = _sweep(duration, start_hz, end_hz, decay)
        samples += _noise_burst(duration, 0.008, smooth=3, seed=1000 + index) * 0.12
        written.append(_write(f"laser/{name}", samples))
    return written


def scifi() -> list[Path]:
    """A scanner ping and a rising warp tone."""
    scan = _ping(880.0, 0.15, 0.045)
    scan += _ping(1320.0, 0.15, 0.030) * 0.4
    scan += _noise_burst(0.15, 0.020, smooth=9, seed=2001) * 0.18

    t = _t(0.15)
    warp = _sweep(0.15, 140.0, 420.0, 0.10)
    warp *= 1.0 + 0.25 * np.sin(2 * np.pi * 28.0 * t)
    warp += _noise_burst(0.15, 0.090, smooth=15, seed=2002) * 0.20

    return [_write("scifi/scan.wav", scan), _write("scifi/warp.wav", warp)]


def mechanical() -> list[Path]:
    """Crisp plier/multiplier clicks and a short knife scrape."""
    click_a = _noise_burst(0.05, 0.004, smooth=2, seed=3001) * 0.6 + _ping(2500.0, 0.05, 0.012)
    close = np.zeros(int(SAMPLE_RATE * 0.35))
    _place(close, click_a, 0.00)
    _place(close, click_a, 0.07, gain=0.8)

    click_b = _noise_burst(0.05, 0.005, smooth=2, seed=3002) * 0.55 + _ping(1800.0, 0.05, 0.014)
    open_ = np.zeros(int(SAMPLE_RATE * 0.35))
    _place(open_, click_b, 0.00)
    _place(open_, _ping(900.0, 0.18, 0.060), 0.02, gain=0.35)

    knife = _noise_burst(0.35, 0.500, smooth=5, seed=3003)
    knife *= 0.55 + 0.45 * np.sin(2 * np.pi * 11.0 * _t(0.35)) ** 2
    knife *= 1.0 - np.exp(-_t(0.35) / 0.04)
    knife += _ping(3200.0, 0.35, 0.050) * 0.08

    return [
        _write("mechanical/multi_plier_close.wav", close),
        _write("mechanical/multi_plier_open.wav", open_),
        _write("mechanical/sharpening_knife.wav", knife),
    ]


GROUPS = {"laser": laser, "scifi": scifi, "mechanical": mechanical}


def main(argv: list[str]) -> int:
    names = argv or list(GROUPS)
    unknown = [name for name in names if name not in GROUPS]
    if unknown:
        print(f"unknown sound group(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"available: {', '.join(GROUPS)}", file=sys.stderr)
        return 2
    for name in names:
        for path in GROUPS[name]():
            print(f"wrote {path.relative_to(SOUNDS_DIR.parent.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
