from __future__ import annotations

import logging
from dataclasses import dataclass, field

import whisper_turbo_desktop.ui.main_window as main_window_module
from whisper_turbo_desktop.models.history import HistoryRecord
from whisper_turbo_desktop.models.queue_task import QueueTask
from whisper_turbo_desktop.models.transcription import TranscriptionRequest
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


def test_queue_progress_and_state_updates_refresh_active_row_in_place(monkeypatch, qapp, tmp_path) -> None:
    monkeypatch.setattr(MainWindow, "refresh_diagnostics", lambda self: None)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    window = MainWindow(settings_service=FakeSettingsService(), logger=logging.getLogger("test"))

    render_calls: list[str | None] = []

    def fail_if_rerendered(*, selected_id: str | None = None) -> None:
        render_calls.append(selected_id)
        raise AssertionError("_render_queue() should not be called for active queue updates")

    monkeypatch.setattr(window, "_render_queue", fail_if_rerendered)

    request = TranscriptionRequest(
        input_path=tmp_path / "clip.wav",
        output_dir=tmp_path / "out",
    )
    task = QueueTask(queue_id="queue-1", request=request)
    task.status = "running"
    task.note = "Running"
    window.queue_tasks = [task]
    window.current_run_origin = "queue"
    window.current_queue_task_id = task.queue_id
    window.queue_list.addItem(task.summary_text())
    item = window.queue_list.item(0)
    item.setData(main_window_module.Qt.ItemDataRole.UserRole, task)
    window.queue_list.setCurrentItem(item)
    window.queue_detail_text.setPlainText(task.details_text())

    try:
        window._on_worker_state_changed("Transcribing")
        assert render_calls == []
        assert window.queue_list.item(0).text() == "RUNNING   |   0% | clip.wav"
        assert "Note: Transcribing" in window.queue_detail_text.toPlainText()
        assert "Whisper Mode: Original (Whisper transcribe)" in window.queue_detail_text.toPlainText()
        assert "API Subtitle Translation: Off" in window.queue_detail_text.toPlainText()

        window._on_worker_progress_changed(42)
        assert render_calls == []
        assert window.queue_list.item(0).text() == "RUNNING   |  42% | clip.wav"
        assert "Progress: 42%" in window.queue_detail_text.toPlainText()
        assert "Note: Transcribing" in window.queue_detail_text.toPlainText()
    finally:
        window.close()
