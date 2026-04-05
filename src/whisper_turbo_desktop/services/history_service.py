from __future__ import annotations

import json

from whisper_turbo_desktop.models.history import HistoryRecord
from whisper_turbo_desktop.utils.paths import app_data_dir


class HistoryService:
    def __init__(self, max_records: int = 200) -> None:
        self.max_records = max_records
        self.history_path = app_data_dir() / "history.json"

    def load(self) -> list[HistoryRecord]:
        if not self.history_path.exists():
            return []

        payload = json.loads(self.history_path.read_text(encoding="utf-8"))
        return [HistoryRecord.from_dict(item) for item in payload]

    def append(self, record: HistoryRecord) -> list[HistoryRecord]:
        records = self.load()
        records.insert(0, record)
        trimmed = records[: self.max_records]
        self.history_path.write_text(
            json.dumps([item.to_dict() for item in trimmed], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return trimmed
