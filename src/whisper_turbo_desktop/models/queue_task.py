from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from whisper_turbo_desktop.models.transcription import TranscriptionRequest

QUEUE_STATUSES = {"queued", "running", "completed", "failed", "cancelled"}


@dataclass(slots=True)
class QueueTask:
    queue_id: str
    request: TranscriptionRequest
    status: str = "queued"
    progress: int = 0
    note: str = ""
    output_files: list[str] = field(default_factory=list)

    def summary_text(self) -> str:
        return (
            f"{self.status.upper():<9} | {self.progress:>3}% | "
            f"{self.request.input_path.name}"
        )

    def details_text(self) -> str:
        lines = [
            f"Queue ID: {self.queue_id}",
            f"Status: {self.status}",
            f"Progress: {self.progress}%",
            f"Input: {self.request.input_path}",
            f"Output Dir: {self.request.output_dir}",
            f"Task: {self.request.task}",
            f"Model: {self.request.model}",
            f"Source Language: {self.request.language or 'auto'}",
            f"Device: {self.request.device}",
            f"Output Format: {self.request.output_format}",
        ]
        if self.note:
            lines.append(f"Note: {self.note}")
        if self.output_files:
            lines.append("Output Files:")
            lines.extend(f"- {path}" for path in self.output_files)
        return "\n".join(lines)

    def open_target(self) -> Path | None:
        for output_file in self.output_files:
            candidate = Path(output_file)
            if candidate.exists():
                return candidate

        if self.request.output_dir.exists():
            return self.request.output_dir
        return None
