from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from whisper_turbo_desktop.models.transcription import TranscriptionRequest
from whisper_turbo_desktop.services.translation_service import (
    SubtitleTranslationService,
    SubtitleSegment,
)
from whisper_turbo_desktop.utils.runtime import is_model_cached, local_whisper_cache_dir, resolve_model_source
from whisper_turbo_common.subprocess_utils import hide_whisper_audio_subprocess_window


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
        self._whisper_progress_start = 0
        self._whisper_progress_end = 100

    def cancel(self) -> None:
        self._cancel_requested = True
        self.state_changed.emit("Cancelling task...")

    def run(self) -> None:
        started_at = time.monotonic()
        self._emit_progress(0)
        whisper_module: Any | None = None
        transcribe_module: Any | None = None
        original_tqdm: Any | None = None
        original_whisper_tqdm: Any | None = None
        ProgressBridge.progress_callback = self._emit_whisper_progress
        ProgressBridge.cancel_callback = lambda: self._cancel_requested

        try:
            whisper_module = importlib.import_module("whisper")
            transcribe_module = importlib.import_module("whisper.transcribe")
            whisper_utils_module = importlib.import_module("whisper.utils")
            original_tqdm = transcribe_module.tqdm.tqdm
            original_whisper_tqdm = whisper_module.tqdm

            self.request.validate()
            self._emit_progress(3)
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
            self._emit_progress(6)

            if self.request.model == "turbo" and self.request.task == "translate":
                self.warning_issued.emit(
                    "Turbo can translate to English, but medium or large-v3 is usually more reliable for translation quality."
                )

            whisper_module.tqdm = WhisperProgressBar
            model = whisper_module.load_model(model_source, device=device)
            self._emit_progress(12)

            self.state_changed.emit("Running Whisper...")
            self._set_whisper_progress_range(
                12, 68 if self.request.translation_enabled else 88
            )
            transcribe_module.tqdm.tqdm = WhisperProgressBar
            result = self._transcribe_audio(model, task=self.request.task, device=device)
            self._emit_progress(68 if self.request.translation_enabled else 88)

            if self._cancel_requested:
                raise TranscriptionCancelled("Task cancelled")

            self.state_changed.emit("Writing output files...")
            self._emit_progress(72 if self.request.translation_enabled else 94)
            writer = whisper_utils_module.get_writer(
                self.request.output_format,
                str(self.request.output_dir),
            )
            writer(result, str(self.request.input_path))

            self._write_translated_outputs(result, model=model, device=device)

            output_files = self.request.collect_output_files()
            if not output_files:
                raise RuntimeError("Whisper finished without producing output files")

            duration_seconds = time.monotonic() - started_at
            self._emit_progress(100)
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
            if transcribe_module is not None and original_tqdm is not None:
                transcribe_module.tqdm.tqdm = original_tqdm
            if whisper_module is not None and original_whisper_tqdm is not None:
                whisper_module.tqdm = original_whisper_tqdm
            ProgressBridge.progress_callback = None
            ProgressBridge.cancel_callback = None

    def _set_whisper_progress_range(self, start: int, end: int) -> None:
        self._whisper_progress_start = start
        self._whisper_progress_end = end

    def _emit_progress(self, value: int) -> None:
        self.progress_changed.emit(max(0, min(100, value)))

    def _emit_whisper_progress(self, whisper_percent: int) -> None:
        bounded_percent = max(0, min(100, whisper_percent))
        span = self._whisper_progress_end - self._whisper_progress_start
        mapped_value = self._whisper_progress_start + int(
            round(span * bounded_percent / 100)
        )
        self._emit_progress(mapped_value)

    def _resolve_device(self) -> str:
        import torch

        if self.request.device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return self.request.device

    def _transcribe_audio(self, model: Any, *, task: str, device: str) -> dict[str, Any]:
        with hide_whisper_audio_subprocess_window():
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
        self.state_changed.emit("Preparing API subtitle translation...")
        self._emit_progress(74)
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
        self.state_changed.emit("Translating subtitles with API...")
        self._emit_progress(86)
        translated = translator.translate_segments(segments)
        self._emit_progress(94)
        stem = self.request.input_path.stem
        srt_path = self.request.output_dir / f"{stem}.translated.srt"
        vtt_path = self.request.output_dir / f"{stem}.translated.vtt"
        txt_path = self.request.output_dir / f"{stem}.translated.txt"
        self.state_changed.emit("Writing translated subtitle sidecars...")
        srt_path.write_text(translated.srt_text, encoding="utf-8")
        vtt_path.write_text(translated.vtt_text, encoding="utf-8")
        txt_path.write_text(translated.txt_text, encoding="utf-8")
        self._emit_progress(96)

    def _translation_source_result(
        self, result: dict[str, Any], *, model: Any, device: str
    ) -> dict[str, Any]:
        if self.request.task != "translate":
            return result

        self.state_changed.emit(
            "Transcribing source-language text for translated subtitles..."
        )
        self._set_whisper_progress_range(74, 84)
        source_result = self._transcribe_audio(model, task="transcribe", device=device)
        self._emit_progress(84)
        if self._cancel_requested:
            raise TranscriptionCancelled("Task cancelled")
        return source_result
