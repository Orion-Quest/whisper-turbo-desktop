from __future__ import annotations

import os
import sys
from pathlib import Path

MODEL_CACHE_FILENAMES = {
    "turbo": "large-v3-turbo.pt",
}

APP_DIR_NAME = "WhisperTurboDesktop"


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


def install_root_dir() -> Path:
    if is_frozen() and runtime_app_dir().name.lower() == "runtime":
        return runtime_app_dir().parent
    return runtime_app_dir()


def bundled_config_dir() -> Path:
    return runtime_data_dir() / "config"


def default_settings_template_path() -> Path:
    return bundled_config_dir() / "default_settings.json"


def local_whisper_cache_dir() -> Path:
    return Path.home() / ".cache" / "whisper"


def local_model_cache_path(model_name: str) -> Path:
    return local_whisper_cache_dir() / MODEL_CACHE_FILENAMES[model_name]


def is_model_cached(model_name: str) -> bool:
    return local_model_cache_path(model_name).exists()


def resolve_model_source(model_name: str) -> str:
    cache_path = local_model_cache_path(model_name)
    if cache_path.exists():
        return str(cache_path)
    return model_name


def managed_ffmpeg_path() -> Path:
    return install_root_dir() / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"


def installed_manifest_path() -> Path:
    return install_root_dir() / "installed_manifest.json"


def ensure_runtime_environment() -> None:
    current_path = os.environ.get("PATH", "")
    ffmpeg_path = managed_ffmpeg_path()
    if ffmpeg_path.exists():
        ffmpeg_dir = str(ffmpeg_path.parent)
        path_parts = current_path.split(os.pathsep) if current_path else []
        if ffmpeg_dir not in path_parts:
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path if current_path else ffmpeg_dir
