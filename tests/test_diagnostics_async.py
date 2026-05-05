from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass, field

from PySide6.QtWidgets import QApplication

import whisper_turbo_desktop.ui.main_window as main_window_module
from whisper_turbo_desktop.models.history import HistoryRecord
from whisper_turbo_desktop.services.diagnostics_service import DiagnosticItem
import whisper_turbo_desktop.services.diagnostics_service as diagnostics_module
from whisper_turbo_desktop.services.diagnostics_service import DiagnosticsService
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


def test_main_window_defers_diagnostics_until_user_refresh(monkeypatch, qapp) -> None:
    release_event = threading.Event()
    blocking_service = BlockingDiagnosticsService(release_event)

    monkeypatch.setattr(main_window_module, "DiagnosticsService", lambda: blocking_service)
    monkeypatch.setattr(main_window_module, "HistoryService", FakeHistoryService)

    started_at = time.perf_counter()
    window = MainWindow(settings_service=FakeSettingsService(), logger=logging.getLogger("test"))
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.2
    assert window.diagnostics_worker is None
    assert blocking_service.calls == 0
    assert "Refresh Diagnostics" in window.diagnostics_text.toPlainText()

    try:
        window.refresh_diagnostics()

        assert window.diagnostics_worker is not None
        assert window.diagnostics_worker.isRunning()
        assert "Running diagnostics" in window.diagnostics_text.toPlainText()

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


def test_frozen_diagnostics_do_not_launch_runtime_executable(monkeypatch) -> None:
    calls: list[list[str]] = []
    runtime_executable = r"C:\App\runtime\WhisperTurboDesktop.exe"

    def fake_run(command: list[str], **kwargs):
        calls.append(command)
        if command[0] == runtime_executable:
            raise AssertionError("frozen diagnostics must not subprocess the runtime executable")
        return type("Completed", (), {"returncode": 0, "stdout": "ffmpeg ok", "stderr": ""})()

    monkeypatch.setattr(diagnostics_module, "is_frozen", lambda: True)
    monkeypatch.setattr(diagnostics_module, "__version__", "9.9.9")
    monkeypatch.setattr(diagnostics_module.subprocess, "run", fake_run)
    monkeypatch.setitem(sys.modules, "whisper", type("WhisperModule", (), {"__version__": "2026.1"})())
    monkeypatch.setitem(
        sys.modules,
        "torch",
        type(
            "TorchModule",
            (),
            {
                "__version__": "2.9",
                "cuda": type("CudaModule", (), {"is_available": staticmethod(lambda: False)})(),
            },
        )(),
    )

    diagnostics = DiagnosticsService().run(runtime_executable)

    names = [item.name for item in diagnostics]
    assert "Python" in names
    assert "Whisper" in names
    assert "Torch/CUDA" in names
    assert all(command[0] != runtime_executable for command in calls)


def test_diagnostics_subprocess_checks_hide_windows_console(monkeypatch) -> None:
    captured_kwargs: dict[str, object] = {}

    def fake_run(_command: list[str], **kwargs):
        captured_kwargs.update(kwargs)
        return type("Completed", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr(diagnostics_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        diagnostics_module,
        "hidden_subprocess_kwargs",
        lambda: {"creationflags": 123},
    )

    result = DiagnosticsService()._run(["ffmpeg", "-version"], "FFmpeg")

    assert result.ok is True
    assert captured_kwargs["creationflags"] == 123
