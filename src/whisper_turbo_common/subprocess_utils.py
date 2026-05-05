from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any


def hidden_subprocess_kwargs() -> dict[str, int]:
    if sys.platform != "win32":
        return {}
    creation_flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if not creation_flag:
        return {}
    return {"creationflags": creation_flag}


def merge_hidden_subprocess_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    hidden_kwargs = hidden_subprocess_kwargs()
    if "creationflags" not in hidden_kwargs:
        return kwargs

    merged = dict(kwargs)
    merged["creationflags"] = int(merged.get("creationflags", 0)) | hidden_kwargs["creationflags"]
    return merged


@contextmanager
def hide_whisper_audio_subprocess_window() -> Iterator[None]:
    import whisper.audio as whisper_audio

    original_run = whisper_audio.run

    @wraps(original_run)
    def run_without_console(*args: Any, **kwargs: Any) -> Any:
        return original_run(*args, **merge_hidden_subprocess_kwargs(kwargs))

    whisper_audio.run = run_without_console
    try:
        yield
    finally:
        whisper_audio.run = original_run
