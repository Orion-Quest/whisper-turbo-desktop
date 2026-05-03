from __future__ import annotations

import json
import sys
from pathlib import Path

from whisper_turbo_desktop.models.history import HistoryRecord
from whisper_turbo_desktop.services.history_service import HistoryService
from whisper_turbo_desktop.services.settings_service import SettingsService


def test_settings_service_recovers_from_invalid_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "whisper_turbo_desktop.services.settings_service.app_data_dir",
        lambda: tmp_path,
    )
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{ invalid json", encoding="utf-8")

    settings = SettingsService().load()

    assert settings.python_executable == sys.executable
    assert settings.default_model == "turbo"
    assert settings.default_output_language == "Original"
    assert settings.default_source_language == ""
    assert settings.default_device == "auto"
    assert settings.default_output_format == "srt"


def test_history_service_recovers_from_invalid_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "whisper_turbo_desktop.services.history_service.app_data_dir",
        lambda: tmp_path,
    )
    history_path = tmp_path / "history.json"
    history_path.write_text("{ invalid json", encoding="utf-8")

    records = HistoryService().load()

    assert records == []


def test_history_service_append_recovers_from_invalid_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "whisper_turbo_desktop.services.history_service.app_data_dir",
        lambda: tmp_path,
    )
    history_path = tmp_path / "history.json"
    history_path.write_text("{ invalid json", encoding="utf-8")

    service = HistoryService()
    record = HistoryRecord(
        run_id="run-1",
        created_at="2026-05-03T00:00:00+08:00",
        status="completed",
        input_path="C:/audio.wav",
        output_dir="C:/output",
        model="turbo",
        task="transcribe",
        language="",
        device="auto",
        output_format="srt",
        output_files=["C:/output/audio.srt"],
        duration_seconds=12.3,
    )

    trimmed = service.append(record)
    payload = json.loads(history_path.read_text(encoding="utf-8"))

    assert len(trimmed) == 1
    assert trimmed[0].run_id == "run-1"
    assert payload[0]["run_id"] == "run-1"
