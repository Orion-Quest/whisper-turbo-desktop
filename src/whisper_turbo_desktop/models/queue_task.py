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
            f"Whisper Mode: {self._whisper_mode_label()}",
            f"Whisper Model: {self.request.model}",
            f"Source Language: {self.request.language or 'auto'}",
            f"Device: {self.request.device}",
            f"Output Format: {self.request.output_format}",
            f"API Subtitle Translation: {self._translation_label()}",
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

    def _whisper_mode_label(self) -> str:
        if self.request.task == "translate":
            return "English (Whisper translate)"
        return "Original (Whisper transcribe)"

    def _translation_label(self) -> str:
        if not self.request.translation_enabled:
            return "Off"
        target_language = self.request.translation_target_language.strip() or "unknown"
        model = self.request.translation_model.strip() or "unknown model"
        return f"On -> {target_language} via {model}"
