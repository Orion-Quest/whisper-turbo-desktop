from __future__ import annotations

import subprocess
from dataclasses import dataclass

from whisper_turbo_desktop.utils.runtime import (
    is_model_cached,
    local_model_cache_path,
    managed_ffmpeg_path,
)


@dataclass(slots=True)
class DiagnosticItem:
    name: str
    ok: bool
    details: str


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
        return self._run(
            [python_executable, "-c", "import whisper; print(whisper.__version__)"],
            "Whisper",
        )

    def _check_torch_cuda(self, python_executable: str) -> DiagnosticItem:
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
