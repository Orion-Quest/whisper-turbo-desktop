from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class HistoryRecord:
    run_id: str
    created_at: str
    status: str
    input_path: str
    output_dir: str
    model: str
    task: str
    language: str
    device: str
    output_format: str
    output_files: list[str]
    duration_seconds: float | None
    note: str = ""

    @classmethod
    def from_dict(cls, payload: dict) -> "HistoryRecord":
        return cls(
            run_id=payload["run_id"],
            created_at=payload["created_at"],
            status=payload["status"],
            input_path=payload["input_path"],
            output_dir=payload["output_dir"],
            model=payload["model"],
            task=payload["task"],
            language=payload.get("language", ""),
            device=payload["device"],
            output_format=payload["output_format"],
            output_files=list(payload.get("output_files", [])),
            duration_seconds=payload.get("duration_seconds"),
            note=payload.get("note", ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_text(self) -> str:
        return (
            f"{self.created_at} | {self.status.upper()} | "
            f"{self.task} | {self.model} | {self.input_path}"
        )

    def details_text(self) -> str:
        lines = [
            f"Run ID: {self.run_id}",
            f"Created At: {self.created_at}",
            f"Status: {self.status}",
            f"Input: {self.input_path}",
            f"Output Dir: {self.output_dir}",
            f"Task: {self.task}",
            f"Model: {self.model}",
            f"Source Language: {self.language or 'auto'}",
            f"Device: {self.device}",
            f"Output Format: {self.output_format}",
            (
                f"Duration: {self.duration_seconds:.1f}s"
                if self.duration_seconds is not None
                else "Duration: n/a"
            ),
        ]
        if self.note:
            lines.append(f"Note: {self.note}")
        if self.output_files:
            lines.append("Output Files:")
            lines.extend(f"- {path}" for path in self.output_files)
        else:
            lines.append("Output Files: none")
        return "\n".join(lines)

    def open_target(self) -> Path | None:
        for output_file in self.output_files:
            candidate = Path(output_file)
            if candidate.exists():
                return candidate

        output_dir = Path(self.output_dir)
        if output_dir.exists():
            return output_dir
        return None
