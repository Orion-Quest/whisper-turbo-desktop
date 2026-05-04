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
    monkeypatch.setattr(main_window_module, "install_root_dir", lambda: Path(r"C:\Apps\WhisperTurboDesktop"))

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
        assert window.install_path_label.text() == r"C:\Apps\WhisperTurboDesktop"
        assert window.runtime_path_edit.text() == r"C:\Apps\WhisperTurboDesktop"
        assert window.open_install_button.text() == "Open Install Folder"
        assert window.translation_settings_group.title() == "Optional API Subtitle Translation"
        assert window.translation_api_key_edit.text() == "sk-loaded"
        assert window.translation_base_url_edit.text() == "https://api.example.com/v1"
        assert window.translation_model_edit.text() == "gpt-4o-mini"
        assert window.translation_target_language_edit.text() == "Spanish"
        assert window.theme_combo.currentText() == "Aurora Glass"

        window.input_path_edit.setText(str(input_path))
        window.translation_api_key_edit.setText("sk-saved")
        window.translation_base_url_edit.setText("https://gateway.example.test/v1")
        window.translation_model_edit.setText("custom-translation-model")
        window.translation_target_language_edit.setText("Japanese")
        window.theme_combo.setCurrentText("Slate Glass")
        window._update_task_note()

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
        assert settings_service.settings.theme == "Slate Glass"
        assert ".translated.srt/.vtt/.txt" in window.task_note.text()
    finally:
        window.close()


def test_task_note_tracks_output_language_and_translation(monkeypatch, qapp) -> None:
    monkeypatch.setattr(MainWindow, "refresh_diagnostics", lambda self: None)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    window = MainWindow(settings_service=FakeSettingsService(), logger=logging.getLogger("test"))

    try:
        window.output_language_combo.setCurrentText("Original")
        window.translation_target_language_edit.clear()
        window._update_task_note()
        assert "Whisper transcribe mode" in window.task_note.text()
        assert "API subtitle translation is off" in window.translation_status_label.text()

        window.output_language_combo.setCurrentText("English (Translate)")
        window._update_task_note()
        assert "Whisper translate mode" in window.task_note.text()

        window.translation_target_language_edit.setText("Japanese")
        window._update_task_note()
        assert "translated subtitle sidecars" in window.task_note.text()
        assert "API key is missing" in window.translation_status_label.text()

        window.translation_api_key_edit.setText("sk-test")
        window._refresh_translation_status()
        assert "API subtitle translation ready: Japanese via gpt-4o-mini" in window.translation_status_label.text()
    finally:
        window.close()


def test_wrapped_task_guidance_rows_allocate_full_text_height(monkeypatch, qapp) -> None:
    monkeypatch.setattr(MainWindow, "refresh_diagnostics", lambda self: None)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    window = MainWindow(settings_service=FakeSettingsService(), logger=logging.getLogger("test"))

    try:
        window.output_language_combo.setCurrentText("English (Translate)")
        window.translation_target_language_edit.setText("Japanese localization review subtitles")
        window.resize(900, 760)
        window.show()
        qapp.processEvents()

        wrapped_labels = [
            window.drop_hint_label,
            window.task_note,
            window.runtime_hint_label,
        ]
        for label in wrapped_labels:
            expected_height = label.heightForWidth(label.width())
            assert label.height() >= expected_height

        assert window.task_note.geometry().bottom() < window.runtime_hint_label.geometry().top()
    finally:
        window.close()


def test_task_panel_keeps_readable_layout_without_field_overlap(monkeypatch, qapp) -> None:
    monkeypatch.setattr(MainWindow, "refresh_diagnostics", lambda self: None)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    window = MainWindow(settings_service=FakeSettingsService(), logger=logging.getLogger("test"))

    try:
        window.translation_target_language_edit.setText("Japanese localization review subtitles")
        window.show()
        qapp.processEvents()

        assert window.main_splitter.sizes()[0] >= 520
        assert window.main_splitter.sizes()[1] > window.main_splitter.sizes()[0]
        assert window.input_path_edit.width() >= 300
        assert window.output_dir_edit.width() >= 300

        guidance_cards = [
            window.drop_hint_card,
            window.task_note_card,
            window.runtime_hint_card,
        ]
        for card in guidance_cards:
            assert card.width() >= window.input_path_edit.width()

        assert window.drop_hint_card.geometry().bottom() < window.output_dir_edit.geometry().top()
        assert window.task_note_card.geometry().bottom() < window.runtime_hint_card.geometry().top()
    finally:
        window.close()


def test_theme_selector_applies_glass_theme_and_gradient_progress(monkeypatch, qapp) -> None:
    monkeypatch.setattr(MainWindow, "refresh_diagnostics", lambda self: None)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    window = MainWindow(settings_service=FakeSettingsService(), logger=logging.getLogger("test"))

    try:
        assert [window.theme_combo.itemText(index) for index in range(window.theme_combo.count())] == [
            "Aurora Glass",
            "Slate Glass",
            "Clean Light",
        ]

        window.theme_combo.setCurrentText("Slate Glass")
        qapp.processEvents()

        style = window.styleSheet()
        progress_style = window.progress_bar.styleSheet()
        assert "qlineargradient" in style.lower()
        assert "rgba(" in style.lower()
        assert "QProgressBar::chunk" in progress_style
        assert "qlineargradient" in progress_style
        assert window.progress_bar.maximumHeight() >= 20
    finally:
        window.close()


def test_drop_hint_has_visible_state_feedback(monkeypatch, qapp) -> None:
    monkeypatch.setattr(MainWindow, "refresh_diagnostics", lambda self: None)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    window = MainWindow(settings_service=FakeSettingsService(), logger=logging.getLogger("test"))

    try:
        assert "Drop media files here" in window.drop_hint_label.text()
        assert "qlineargradient" in window.drop_hint_label.styleSheet()
        assert "dashed" in window.drop_hint_label.styleSheet()

        window._set_drop_hint_state("active", 3)
        qapp.processEvents()
        assert "Release to add 3 files" in window.drop_hint_label.text()
        assert "border: 2px solid" in window.drop_hint_label.styleSheet()
        assert window.drop_hint_label.graphicsEffect() is not None

        window._set_drop_hint_state("accepted", 1)
        qapp.processEvents()
        assert window.drop_hint_label.text() == "Input file selected"
        assert "border: 2px solid" in window.drop_hint_label.styleSheet()
    finally:
        window.close()
