import shutil
import subprocess
from pathlib import Path

from .paths import custom_sounds_dir

SUPPORTED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".aiff",
    ".aif",
    ".wma",
    ".flac",
}


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def import_sound(source: Path) -> Path:
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not is_supported(source):
        raise ValueError(f"Unsupported audio format: {source.suffix}")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to import non-WAV audio files")
    custom_sounds_dir().mkdir(parents=True, exist_ok=True)
    destination = custom_sounds_dir() / f"{source.stem}.wav"
    counter = 1
    while destination.exists():
        destination = custom_sounds_dir() / f"{source.stem}_{counter}.wav"
        counter += 1
    subprocess.run(
        [ffmpeg, "-y", "-i", str(source), str(destination)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
    )
    return destination