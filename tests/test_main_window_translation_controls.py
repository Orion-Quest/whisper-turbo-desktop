from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import whisper_turbo_desktop.ui.main_window as main_window_module
from whisper_turbo_desktop.models.history import HistoryRecord
from whisper_turbo_desktop.services.settings_service import AppSettings
from whisper_turbo_desktop.ui.main_window import MainWindow


@dataclass
class FakeSettingsService:
    settings: AppSettings = field(default_factory=AppSettings)

    def load(self) -> AppSettings:
        return self.settings

    def save(self, settings: AppSettings) -> None:
        self.settings = settings


class FakeHistoryService:
    def load(self) -> list[HistoryRecord]:
        return []

    def append(self, record: HistoryRecord) -> list[HistoryRecord]:
        return [record]


def test_translation_controls_round_trip_settings_and_request(monkeypatch, qapp, tmp_path: Path) -> None:
    monkeypatch.setattr(MainWindow, "refresh_diagnostics", lambda self: None)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    input_path = tmp_path / "clip.wav"
    input_path.write_bytes(b"RIFF")
    output_dir = tmp_path / "out"
    settings_service = FakeSettingsService(
        AppSettings(
            default_output_dir=str(output_dir),
            default_model="turbo",
            default_output_language="Original",
            default_source_language="en",
            default_device="cpu",
            default_output_format="srt",
            translation_api_key="sk-loaded",
            translation_base_url="https://api.example.com/v1",
            translation_model="gpt-4o-mini",
            translation_target_language="Spanish",
        )
    )

    window = MainWindow(settings_service=settings_service, logger=logging.getLogger("test"))

    try:
        assert [window.output_language_combo.itemText(index) for index in range(window.output_language_combo.count())] == [
            "Original",
            "English (Translate)",
        ]
        assert window.translation_settings_group.title() == "Translation Settings"
        assert window.translation_api_key_edit.text() == "sk-loaded"
        assert window.translation_base_url_edit.text() == "https://api.example.com/v1"
        assert window.translation_model_edit.text() == "gpt-4o-mini"
        assert window.translation_target_language_edit.text() == "Spanish"

        window.input_path_edit.setText(str(input_path))
        window.translation_api_key_edit.setText("sk-saved")
        window.translation_base_url_edit.setText("https://gateway.example.test/v1")
        window.translation_model_edit.setText("custom-translation-model")
        window.translation_target_language_edit.setText("Japanese")

        request = window._build_request()
        window._persist_settings()

        assert request.task == "transcribe"
        assert request.translation_api_key == "sk-saved"
        assert request.translation_base_url == "https://gateway.example.test/v1"
        assert request.translation_model == "custom-translation-model"
        assert request.translation_target_language == "Japanese"
        assert settings_service.settings.translation_api_key == "sk-saved"
        assert settings_service.settings.translation_base_url == "https://gateway.example.test/v1"
        assert settings_service.settings.translation_model == "custom-translation-model"
        assert settings_service.settings.translation_target_language == "Japanese"
    finally:
        window.close()
