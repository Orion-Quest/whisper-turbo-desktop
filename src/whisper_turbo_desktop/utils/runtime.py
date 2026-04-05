from __future__ import annotations

import os
import sys
from pathlib import Path

BUNDLED_MODEL_FILES = {
    "turbo": "large-v3-turbo.pt",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def runtime_data_dir() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return project_root()


def runtime_app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_root()


def bundled_bin_dir() -> Path:
    return runtime_data_dir() / "bin"


def bundled_ffmpeg_path() -> Path:
    return bundled_bin_dir() / "ffmpeg.exe"


def bundled_model_dir() -> Path:
    return runtime_data_dir() / "models"


def bundled_model_path(model_name: str) -> Path:
    filename = BUNDLED_MODEL_FILES[model_name]
    return bundled_model_dir() / filename


def bundled_config_dir() -> Path:
    return runtime_data_dir() / "config"


def default_settings_template_path() -> Path:
    return bundled_config_dir() / "default_settings.json"


def local_whisper_cache_dir() -> Path:
    return Path.home() / ".cache" / "whisper"


def resolve_model_source(model_name: str) -> str:
    bundled = bundled_model_path(model_name)
    if bundled.exists():
        return str(bundled)

    cache_fallback = local_whisper_cache_dir() / BUNDLED_MODEL_FILES[model_name]
    if cache_fallback.exists():
        return str(cache_fallback)

    return model_name


def ensure_runtime_environment() -> None:
    bin_dir = bundled_bin_dir()
    if not bin_dir.exists():
        return

    current_path = os.environ.get("PATH", "")
    if str(bin_dir) in current_path.split(os.pathsep):
        return

    os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
