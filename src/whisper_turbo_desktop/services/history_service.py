from __future__ import annotations

import json
import logging
from json import JSONDecodeError
from pathlib import Path

from whisper_turbo_desktop.models.history import HistoryRecord
from whisper_turbo_desktop.utils.paths import app_data_dir

LOGGER = logging.getLogger("whisper_turbo_desktop.history")


class HistoryService:
    def __init__(self, max_records: int = 200) -> None:
        self.max_records = max_records
        self.history_path = app_data_dir() / "history.json"

    def load(self) -> list[HistoryRecord]:
        if not self.history_path.exists():
            return []

        payload = self._read_json_list(self.history_path)
        if payload is None:
            return []

        records: list[HistoryRecord] = []
        for item in payload:
            if not isinstance(item, dict):
                LOGGER.warning("Skipping malformed history record: expected object")
                continue
            try:
                records.append(HistoryRecord.from_dict(item))
            except (KeyError, TypeError, ValueError) as exc:
                LOGGER.warning("Skipping malformed history record: %s", exc)
                continue
        return records

    def append(self, record: HistoryRecord) -> list[HistoryRecord]:
        records = self.load()
        records.insert(0, record)
        trimmed = records[: self.max_records]
        self.history_path.write_text(
            json.dumps([item.to_dict() for item in trimmed], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return trimmed

    @staticmethod
    def _read_json_list(path: Path) -> list | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
            LOGGER.warning("Failed to read history JSON from %s: %s", path, exc)
            return None

        if not isinstance(payload, list):
            LOGGER.warning("History JSON must be a list: %s", path)
            return None
        return payload
