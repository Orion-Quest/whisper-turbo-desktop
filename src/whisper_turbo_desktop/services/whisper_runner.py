from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import whisper
from PySide6.QtCore import QThread, Signal
from whisper.utils import get_writer

from whisper_turbo_desktop.models.transcription import TranscriptionRequest
from whisper_turbo_desktop.services.translation_service import (
    SubtitleTranslationService,
    SubtitleSegment,
)
from whisper_turbo_desktop.utils.runtime import is_model_cached, local_whisper_cache_dir, resolve_model_source


class TranscriptionCancelled(RuntimeError):
    pass


class ProgressBridge:
    progress_callback = None
    cancel_callback = None


class WhisperProgressBar:
    def __init__(self, *args, total: int | None = None, disable: bool = False, **kwargs) -> None:
        self.total = total or 0
        self.disable = disable
        self.current = 0
        self.last_percent = -1

    def __enter__(self) -> "WhisperProgressBar":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def update(self, amount: int = 1) -> None:
        self.current += amount
        if self.total > 0 and ProgressBridge.progress_callback is not None:
            percent = min(int(self.current * 100 / self.total), 100)
            if percent != self.last_percent:
                self.last_percent = percent
                ProgressBridge.progress_callback(percent)

        if ProgressBridge.cancel_callback is not None and ProgressBridge.cancel_callback():
            raise TranscriptionCancelled("Task cancelled")

    def close(self) -> None:
        return


@dataclass(slots=True)
class TranscriptionResult:
    request: TranscriptionRequest
    output_files: list[Path]
    duration_seconds: float


@dataclass(slots=True)
class TranscriptionFailure:
    request: TranscriptionRequest
    message: str
    duration_seconds: float
    cancelled: bool = False


class TranscriptionWorker(QThread):
    log_line = Signal(str)
    state_changed = Signal(str)
    progress_changed = Signal(int)
    warning_issued = Signal(str)
    finished_success = Signal(object)
    failed = Signal(object)

    def __init__(self, request: TranscriptionRequest) -> None:
        super().__init__()
        self.request = request
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True
        self.state_changed.emit("Cancelling task...")

    def run(self) -> None:
        started_at = time.monotonic()
        self.progress_changed.emit(0)

        transcribe_module = importlib.import_module("whisper.transcribe")
        original_tqdm = transcribe_module.tqdm.tqdm
        original_whisper_tqdm = whisper.tqdm
        ProgressBridge.progress_callback = self.progress_changed.emit
        ProgressBridge.cancel_callback = lambda: self._cancel_requested

        try:
            self.request.validate()
            self.request.output_dir.mkdir(parents=True, exist_ok=True)
            model_source = resolve_model_source(self.request.model)
            device = self._resolve_device()

            if not is_model_cached(self.request.model):
                self.state_changed.emit(
                    f"Downloading model to {local_whisper_cache_dir()}..."
                )
                self.log_line.emit(
                    f"Model {self.request.model} is not cached yet. Download will start on first load."
                )
            else:
                self.state_changed.emit(f"Loading model on {device}...")
            self.log_line.emit(f"Model source: {model_source}")

            if self.request.model == "turbo" and self.request.task == "translate":
                self.warning_issued.emit(
                    "Turbo can translate to English, but medium or large-v3 is usually more reliable for translation quality."
                )

            whisper.tqdm = WhisperProgressBar
            model = whisper.load_model(model_source, device=device)

            self.state_changed.emit("Running Whisper...")
            transcribe_module.tqdm.tqdm = WhisperProgressBar
            result = self._transcribe_audio(model, task=self.request.task, device=device)

            if self._cancel_requested:
                raise TranscriptionCancelled("Task cancelled")

            self.state_changed.emit("Writing output files...")
            writer = get_writer(self.request.output_format, str(self.request.output_dir))
            writer(result, str(self.request.input_path))

            self._write_translated_outputs(result, model=model, device=device)

            output_files = self.request.collect_output_files()
            if not output_files:
                raise RuntimeError("Whisper finished without producing output files")

            duration_seconds = time.monotonic() - started_at
            self.progress_changed.emit(100)
            self.state_changed.emit("Task completed")
            self.finished_success.emit(
                TranscriptionResult(
                    request=self.request,
                    output_files=output_files,
                    duration_seconds=duration_seconds,
                )
            )
        except TranscriptionCancelled as exc:
            self.failed.emit(
                TranscriptionFailure(
                    request=self.request,
                    message=str(exc),
                    duration_seconds=time.monotonic() - started_at,
                    cancelled=True,
                )
            )
        except Exception as exc:
            self.failed.emit(
                TranscriptionFailure(
                    request=self.request,
                    message=str(exc),
                    duration_seconds=time.monotonic() - started_at,
                    cancelled=False,
                )
            )
        finally:
            transcribe_module.tqdm.tqdm = original_tqdm
            whisper.tqdm = original_whisper_tqdm
            ProgressBridge.progress_callback = None
            ProgressBridge.cancel_callback = None

    def _resolve_device(self) -> str:
        if self.request.device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return self.request.device

    def _transcribe_audio(self, model: Any, *, task: str, device: str) -> dict[str, Any]:
        return model.transcribe(
            str(self.request.input_path),
            task=task,
            language=self.request.language,
            verbose=False,
            fp16=device == "cuda",
        )

    def _write_translated_outputs(
        self, result: dict[str, Any], *, model: Any, device: str
    ) -> None:
        if not self.request.translation_enabled:
            return
        source_result = self._translation_source_result(
            result, model=model, device=device
        )
        segments = [
            SubtitleSegment(
                index=index + 1,
                start=float(segment["start"]),
                end=float(segment["end"]),
                text=str(segment["text"]),
            )
            for index, segment in enumerate(source_result.get("segments", []))
        ]
        if not segments:
            raise RuntimeError(
                "Translation was enabled, but Whisper did not return subtitle segments"
            )

        translator = SubtitleTranslationService(
            api_key=self.request.translation_api_key,
            base_url=self.request.translation_base_url,
            model=self.request.translation_model,
            target_language=self.request.translation_target_language,
            source_language=self.request.language,
        )
        translated = translator.translate_segments(segments)
        stem = self.request.input_path.stem
        srt_path = self.request.output_dir / f"{stem}.translated.srt"
        vtt_path = self.request.output_dir / f"{stem}.translated.vtt"
        txt_path = self.request.output_dir / f"{stem}.translated.txt"
        srt_path.write_text(translated.srt_text, encoding="utf-8")
        vtt_path.write_text(translated.vtt_text, encoding="utf-8")
        txt_path.write_text(translated.txt_text, encoding="utf-8")

    def _translation_source_result(
        self, result: dict[str, Any], *, model: Any, device: str
    ) -> dict[str, Any]:
        if self.request.task != "translate":
            return result

        self.state_changed.emit(
            "Transcribing source-language text for translated subtitles..."
        )
        source_result = self._transcribe_audio(model, task="transcribe", device=device)
        if self._cancel_requested:
            raise TranscriptionCancelled("Task cancelled")
        return source_result
