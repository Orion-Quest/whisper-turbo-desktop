from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from whisper_turbo_desktop.utils.paths import app_data_dir
from whisper_turbo_desktop.utils.runtime import default_settings_template_path


@dataclass(slots=True)
class AppSettings:
    python_executable: str = sys.executable
    default_output_dir: str = str(Path.home() / "Documents" / "Whisper Outputs")
    default_model: str = "turbo"
    default_output_language: str = "Original"
    default_source_language: str = ""
    default_device: str = "auto"
    default_output_format: str = "srt"


class SettingsService:
    def __init__(self) -> None:
        self.settings_path = app_data_dir() / "settings.json"

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            template_path = default_settings_template_path()
            if template_path.exists():
                payload = json.loads(template_path.read_text(encoding="utf-8"))
                return AppSettings(
                    python_executable=payload.get("python_executable", sys.executable),
                    default_output_dir=payload.get(
                        "default_output_dir",
                        str(Path.home() / "Documents" / "Whisper Outputs"),
                    ),
                    default_model=payload.get("default_model", "turbo"),
                    default_output_language=payload.get("default_output_language", "Original"),
                    default_source_language=payload.get("default_source_language", ""),
                    default_device=payload.get("default_device", "auto"),
                    default_output_format=payload.get("default_output_format", "srt"),
                )
            return AppSettings()

        payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        output_language = payload.get("default_output_language")
        if output_language is None:
            output_language = (
                "English (Translate)"
                if payload.get("default_task") == "translate"
                else "Original"
            )
        elif output_language == "English":
            output_language = "English (Translate)"

        return AppSettings(
            python_executable=payload.get("python_executable", sys.executable),
            default_output_dir=payload.get(
                "default_output_dir",
                str(Path.home() / "Documents" / "Whisper Outputs"),
            ),
            default_model=payload.get("default_model", "turbo"),
            default_output_language=output_language,
            default_source_language=payload.get(
                "default_source_language",
                payload.get("default_language", ""),
            ),
            default_device=payload.get("default_device", "auto"),
            default_output_format=payload.get("default_output_format", "srt"),
        )

    def save(self, settings: AppSettings) -> None:
        self.settings_path.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
