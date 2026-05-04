from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from whisper_turbo_desktop.utils.paths import app_data_dir
from whisper_turbo_desktop.utils.runtime import default_settings_template_path

LOGGER = logging.getLogger("whisper_turbo_desktop.settings")


@dataclass(slots=True)
class AppSettings:
    python_executable: str = sys.executable
    default_output_dir: str = str(Path.home() / "Documents" / "Whisper Outputs")
    default_model: str = "turbo"
    default_output_language: str = "Original"
    default_source_language: str = ""
    default_device: str = "auto"
    default_output_format: str = "srt"
    translation_api_key: str = ""
    translation_base_url: str = "https://api.openai.com/v1"
    translation_model: str = "gpt-4o-mini"
    translation_target_language: str = ""


class SettingsService:
    def __init__(self) -> None:
        self.settings_path = app_data_dir() / "settings.json"

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            return self._load_template_settings()

        payload = self._read_json_object(self.settings_path)
        if payload is None:
            return self._load_template_settings()
        return self._settings_from_payload(payload)

    def save(self, settings: AppSettings) -> None:
        self.settings_path.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_template_settings(self) -> AppSettings:
        template_path = default_settings_template_path()
        if not template_path.exists():
            return AppSettings()

        payload = self._read_json_object(template_path)
        if payload is None:
            return AppSettings()
        return self._settings_from_payload(payload)

    def _settings_from_payload(self, payload: dict[str, Any]) -> AppSettings:
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
            translation_api_key=payload.get("translation_api_key", ""),
            translation_base_url=payload.get(
                "translation_base_url", "https://api.openai.com/v1"
            ),
            translation_model=payload.get("translation_model", "gpt-4o-mini"),
            translation_target_language=payload.get(
                "translation_target_language", ""
            ),
        )

    @staticmethod
    def _read_json_object(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
            LOGGER.warning("Failed to read settings JSON from %s: %s", path, exc)
            return None

        if not isinstance(payload, dict):
            LOGGER.warning("Settings JSON must be an object: %s", path)
            return None
        return payload
