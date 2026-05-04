from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from whisper_turbo_desktop import __version__
from whisper_turbo_desktop.utils.runtime import (
    is_model_cached,
    is_frozen,
    local_model_cache_path,
    managed_ffmpeg_path,
)

LOGGER = logging.getLogger("whisper_turbo_desktop.diagnostics")


@dataclass(slots=True)
class DiagnosticItem:
    name: str
    ok: bool
    details: str


class DiagnosticsWorker(QThread):
    finished_success = Signal(object)
    failed = Signal(str)

    def __init__(self, service: "DiagnosticsService", python_executable: str) -> None:
        super().__init__()
        self.service = service
        self.python_executable = python_executable

    def run(self) -> None:
        try:
            self.finished_success.emit(self.service.run(self.python_executable))
        except Exception as exc:
            LOGGER.exception("Diagnostics worker failed")
            self.failed.emit(str(exc))


class DiagnosticsService:
    def run(self, python_executable: str) -> list[DiagnosticItem]:
        return [
            self._check_python(python_executable),
            self._check_ffmpeg(),
            self._check_whisper(python_executable),
            self._check_torch_cuda(python_executable),
            self._check_model_cache("turbo"),
        ]

    def _check_python(self, python_executable: str) -> DiagnosticItem:
        if is_frozen():
            version = sys.version.split()[0]
            return DiagnosticItem(
                name="Python",
                ok=True,
                details=f"bundled Python {version}; app={__version__}; executable={python_executable}",
            )
        return self._run([python_executable, "--version"], "Python")

    def _check_ffmpeg(self) -> DiagnosticItem:
        managed = managed_ffmpeg_path()
        if managed.exists():
            result = self._run([str(managed), "-version"], "FFmpeg")
            if result.ok:
                result.details = f"{result.details}\nmanaged_path={managed}"
            return result
        return self._run(["ffmpeg", "-version"], "FFmpeg")

    def _check_whisper(self, python_executable: str) -> DiagnosticItem:
        if is_frozen():
            try:
                import whisper
            except Exception as exc:
                return DiagnosticItem(name="Whisper", ok=False, details=str(exc))
            return DiagnosticItem(name="Whisper", ok=True, details=getattr(whisper, "__version__", "unknown"))
        return self._run(
            [python_executable, "-c", "import whisper; print(whisper.__version__)"],
            "Whisper",
        )

    def _check_torch_cuda(self, python_executable: str) -> DiagnosticItem:
        if is_frozen():
            try:
                import torch
            except Exception as exc:
                return DiagnosticItem(name="Torch/CUDA", ok=False, details=str(exc))
            return DiagnosticItem(
                name="Torch/CUDA",
                ok=True,
                details=f"torch={torch.__version__}; cuda={torch.cuda.is_available()}",
            )
        return self._run(
            [
                python_executable,
                "-c",
                "import torch; print(f'torch={torch.__version__}; cuda={torch.cuda.is_available()}')",
            ],
            "Torch/CUDA",
        )

    def _check_model_cache(self, model_name: str) -> DiagnosticItem:
        cache_path = local_model_cache_path(model_name)
        if is_model_cached(model_name):
            return DiagnosticItem(
                name="Model Cache",
                ok=True,
                details=f"{model_name} already cached at {cache_path}",
            )
        return DiagnosticItem(
            name="Model Cache",
            ok=True,
            details=f"{model_name} not cached yet; it will be downloaded on first transcription to {cache_path}",
        )

    def _run(self, command: list[str], name: str) -> DiagnosticItem:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except FileNotFoundError as exc:
            return DiagnosticItem(name=name, ok=False, details=str(exc))

        output = (completed.stdout or completed.stderr).strip()
        if completed.returncode == 0:
            return DiagnosticItem(name=name, ok=True, details=output)
        return DiagnosticItem(
            name=name,
            ok=False,
            details=output or f"{name} check failed, exit code: {completed.returncode}",
        )
