from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_OUTPUT_FORMATS = {"txt", "srt", "vtt", "json", "all"}
SUPPORTED_TASKS = {"transcribe", "translate"}
SUPPORTED_DEVICES = {"auto", "cpu", "cuda"}
SUPPORTED_MODELS = [
    "turbo",
]


@dataclass(slots=True)
class TranscriptionRequest:
    input_path: Path
    output_dir: Path
    model: str = "turbo"
    task: str = "transcribe"
    language: str | None = None
    device: str = "auto"
    output_format: str = "srt"
    python_executable: str = sys.executable
    translation_enabled: bool = False
    translation_api_key: str = ""
    translation_base_url: str = "https://api.openai.com/v1"
    translation_model: str = "gpt-4o-mini"
    translation_target_language: str = ""
    verbose: bool = False

    def validate(self) -> None:
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input file does not exist: {self.input_path}")
        if self.model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported model: {self.model}")
        if self.task not in SUPPORTED_TASKS:
            raise ValueError(f"Unsupported task: {self.task}")
        if self.device not in SUPPORTED_DEVICES:
            raise ValueError(f"Unsupported device option: {self.device}")
        if self.output_format not in SUPPORTED_OUTPUT_FORMATS:
            raise ValueError(f"Unsupported output format: {self.output_format}")
        if not self.python_executable:
            raise ValueError("Python executable must not be empty")
        if self.translation_enabled:
            if not self.translation_target_language.strip():
                raise ValueError("Translation target language must not be empty")
            if not self.translation_api_key.strip():
                raise ValueError("Translation API key must not be empty")
            if not self.translation_base_url.strip():
                raise ValueError("Translation base URL must not be empty")
            if not self.translation_model.strip():
                raise ValueError("Translation model must not be empty")

    def build_command(self) -> list[str]:
        self.validate()

        command = [
            self.python_executable,
            "-m",
            "whisper",
            str(self.input_path),
            "--model",
            self.model,
            "--task",
            self.task,
            "--output_dir",
            str(self.output_dir),
            "--output_format",
            self.output_format,
            "--verbose",
            "True" if self.verbose else "False",
        ]

        if self.language:
            command.extend(["--language", self.language])
        if self.device != "auto":
            command.extend(["--device", self.device])

        return command

    def collect_output_files(self) -> list[Path]:
        stem = self.input_path.stem
        candidates: list[Path] = []
        for path in self.output_dir.glob(f"{stem}.*"):
            if path.stem != stem:
                continue
            if path.suffix.lower() in {".txt", ".srt", ".vtt", ".json", ".tsv"}:
                candidates.append(path)
        return sorted(candidates)
