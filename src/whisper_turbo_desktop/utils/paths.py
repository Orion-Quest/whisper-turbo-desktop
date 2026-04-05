from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "WhisperTurboDesktop"


def app_data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        path = Path(appdata) / APP_DIR_NAME
    else:
        path = Path.home() / ".whisper_turbo_desktop"
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_log_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
