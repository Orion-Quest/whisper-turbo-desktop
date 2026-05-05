from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import QLabel

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


def _history_record(
    *,
    run_id: str,
    created_at: str,
    status: str,
    input_path: Path,
    output_dir: Path,
    duration_seconds: float | None,
    note: str = "",
) -> HistoryRecord:
    return HistoryRecord(
        run_id=run_id,
        created_at=created_at,
        status=status,
        input_path=str(input_path),
        output_dir=str(output_dir),
        model="turbo",
        task="transcribe",
        language="",
        device="cpu",
        output_format="srt",
        output_files=[],
        duration_seconds=duration_seconds,
        note=note,
    )


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
        assert window.top_output_button.text() == f"Open Output Folder  |  {output_dir}"
        assert "Click to open this folder" in window.top_output_button.toolTip()
        assert window.runtime_path_edit.text() == r"C:\Apps\WhisperTurboDesktop"
        assert window.open_install_button.text() == "Open Install Folder"
        assert window.translation_settings_group.title() == "Optional API Subtitle Translation"
        assert window.translation_api_key_edit.text() == "sk-loaded"
        assert window.translation_base_url_edit.text() == "https://api.example.com/v1"
        assert window.translation_model_edit.text() == "gpt-4o-mini"
        assert window.translation_target_language_edit.text() == "Spanish"
        assert "Japanese" in [
            window.translation_target_language_edit.itemText(index)
            for index in range(window.translation_target_language_edit.count())
        ]
        window.source_language_edit.setText("pt-BR")
        assert window.source_language_edit.text() == "pt-BR"
        assert window.theme_combo.currentText() == "Aurora Glass"

        window.input_path_edit.setText(str(input_path))
        new_output_dir = tmp_path / "manual-out"
        window.output_dir_edit.setText(str(new_output_dir))
        window.translation_api_key_edit.setText("sk-saved")
        window.translation_base_url_edit.setText("https://gateway.example.test/v1")
        window.translation_model_edit.setText("custom-translation-model")
        window.translation_target_language_edit.setText("Japanese")
        window.theme_combo.setCurrentText("Slate Glass")
        window._update_task_note()

        request = window._build_request()
        window._persist_settings()

        assert request.task == "transcribe"
        assert request.output_dir == new_output_dir
        assert request.translation_api_key == "sk-saved"
        assert request.translation_base_url == "https://gateway.example.test/v1"
        assert request.translation_model == "custom-translation-model"
        assert request.translation_target_language == "Japanese"
        assert settings_service.settings.default_output_dir == str(new_output_dir)
        assert settings_service.settings.translation_api_key == "sk-saved"
        assert settings_service.settings.translation_base_url == "https://gateway.example.test/v1"
        assert settings_service.settings.translation_model == "custom-translation-model"
        assert settings_service.settings.translation_target_language == "Japanese"
        assert settings_service.settings.theme == "Slate Glass"
        assert window.top_output_button.text() == f"Open Output Folder  |  {new_output_dir}"
        assert ".translated.srt/.vtt/.txt" in window.task_note.text()
    finally:
        window.close()


def test_history_rows_separate_time_status_file_and_failure_state(monkeypatch, qapp, tmp_path: Path) -> None:
    completed = _history_record(
        run_id="completed-run",
        created_at="2026-05-05T09:15:04+08:00",
        status="completed",
        input_path=tmp_path / "finished clip.wav",
        output_dir=tmp_path / "out",
        duration_seconds=12.4,
    )
    failed = _history_record(
        run_id="failed-run",
        created_at="2026-05-05T09:22:30+08:00",
        status="failed",
        input_path=tmp_path / "broken clip.wav",
        output_dir=tmp_path / "out",
        duration_seconds=None,
        note="Translation validation failed",
    )

    class HistoryServiceWithRecords(FakeHistoryService):
        def load(self) -> list[HistoryRecord]:
            return [completed, failed]

    monkeypatch.setattr(MainWindow, "refresh_diagnostics", lambda self: None)
    monkeypatch.setattr(main_window_module, "HistoryService", HistoryServiceWithRecords)

    window = MainWindow(settings_service=FakeSettingsService(), logger=logging.getLogger("test"))

    try:
        window.resize(980, 720)
        window.show()
        qapp.processEvents()

        completed_item = window.history_list.item(0)
        failed_item = window.history_list.item(1)

        assert completed_item.text() == ""
        rendered_summary = completed_item.data(main_window_module.Qt.ItemDataRole.AccessibleTextRole)
        assert "2026-05-05 09:15:04" in rendered_summary
        assert "COMPLETED" in rendered_summary
        assert "finished clip.wav" in rendered_summary
        assert "Status: completed" in completed_item.toolTip()
        assert "Translation validation failed" in failed_item.toolTip()
        assert completed_item.foreground().color() != failed_item.foreground().color()
        assert completed_item.background().color() != failed_item.background().color()

        completed_widget = window.history_list.itemWidget(completed_item)
        assert completed_widget is not None
        time_label = completed_widget.findChild(QLabel, "HistoryTimeLabel")
        status_label = completed_widget.findChild(QLabel, "HistoryStatusLabel")
        file_label = completed_widget.findChild(QLabel, "HistoryFileLabel")
        duration_label = completed_widget.findChild(QLabel, "HistoryDurationLabel")
        assert time_label is not None and time_label.text() == "2026-05-05 09:15:04"
        assert status_label is not None and status_label.text() == "COMPLETED"
        assert file_label is not None and file_label.text() == "finished clip.wav"
        assert duration_label is not None and duration_label.text() == "12.4s"
        assert time_label.geometry().right() < status_label.geometry().left()
        assert status_label.geometry().right() < file_label.geometry().left()
        assert file_label.geometry().right() < duration_label.geometry().left()
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


def test_top_output_button_opens_output_folder(monkeypatch, qapp, tmp_path: Path) -> None:
    opened_paths: list[Path] = []

    def capture_open_path(self, path: Path) -> None:
        opened_paths.append(path)

    monkeypatch.setattr(MainWindow, "refresh_diagnostics", lambda self: None)
    monkeypatch.setattr(MainWindow, "_open_path", capture_open_path)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    output_dir = tmp_path / "outputs"
    window = MainWindow(
        settings_service=FakeSettingsService(
            AppSettings(default_output_dir=str(output_dir))
        ),
        logger=logging.getLogger("test"),
    )

    try:
        assert window.top_output_button.text() == f"Open Output Folder  |  {output_dir}"
        assert "Output folder:" in window.top_output_button.toolTip()
        window.top_output_button.click()
        assert opened_paths == [output_dir]
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
            "Graphite Prism",
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


def test_theme_options_have_distinct_visual_styles(monkeypatch, qapp) -> None:
    monkeypatch.setattr(MainWindow, "refresh_diagnostics", lambda self: None)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    window = MainWindow(settings_service=FakeSettingsService(), logger=logging.getLogger("test"))

    try:
        captured_styles: dict[str, tuple[str, str, str]] = {}
        for theme_name in [
            window.theme_combo.itemText(index)
            for index in range(window.theme_combo.count())
        ]:
            window.theme_combo.setCurrentText(theme_name)
            qapp.processEvents()
            captured_styles[theme_name] = (
                window.styleSheet(),
                window.progress_bar.styleSheet(),
                window.drop_hint_label.styleSheet(),
            )

        assert set(captured_styles) == {
            "Aurora Glass",
            "Slate Glass",
            "Graphite Prism",
            "Clean Light",
        }
        assert len({styles[0] for styles in captured_styles.values()}) == 4
        assert len({styles[1] for styles in captured_styles.values()}) == 4
        assert "d24b91" in captured_styles["Graphite Prism"][1].lower()
        assert "rgba(" in captured_styles["Graphite Prism"][0].lower()
        assert "qlineargradient" in captured_styles["Graphite Prism"][0].lower()
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
