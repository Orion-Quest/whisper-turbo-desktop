from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from PySide6.QtWidgets import QApplication

import whisper_turbo_desktop.ui.main_window as main_window_module
from whisper_turbo_desktop.models.history import HistoryRecord
from whisper_turbo_desktop.services.diagnostics_service import DiagnosticItem
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


class BlockingDiagnosticsService:
    def __init__(self, release_event: threading.Event) -> None:
        self.release_event = release_event
        self.calls = 0

    def run(self, python_executable: str) -> list[DiagnosticItem]:
        self.calls += 1
        self.release_event.wait(timeout=0.5)
        return [DiagnosticItem(name="Python", ok=True, details="python 3.11")]


def _wait_until(predicate, timeout_seconds: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    app = QApplication.instance()
    assert app is not None
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("Timed out waiting for condition")
        time.sleep(0.01)


def test_main_window_refreshes_diagnostics_asynchronously(monkeypatch, qapp) -> None:
    release_event = threading.Event()
    blocking_service = BlockingDiagnosticsService(release_event)

    monkeypatch.setattr(main_window_module, "DiagnosticsService", lambda: blocking_service)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    started_at = time.perf_counter()
    window = MainWindow(settings_service=FakeSettingsService(), logger=logging.getLogger("test"))
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.2
    assert window.diagnostics_worker is not None
    assert window.diagnostics_worker.isRunning()
    assert "Running diagnostics" in window.diagnostics_text.toPlainText()

    try:
        _wait_until(lambda: blocking_service.calls == 1)
        release_event.set()
        _wait_until(lambda: "[OK] Python" in window.diagnostics_text.toPlainText())

        assert not window.diagnostics_worker.isRunning()
        assert "[OK] Python: python 3.11" in window.diagnostics_text.toPlainText()
    finally:
        release_event.set()
        if window.diagnostics_worker is not None and window.diagnostics_worker.isRunning():
            window.diagnostics_worker.wait(1000)
        window.close()
