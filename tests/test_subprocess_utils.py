from __future__ import annotations

import subprocess

import whisper.audio

from whisper_turbo_common import subprocess_utils


def test_hidden_subprocess_kwargs_returns_create_no_window_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(subprocess_utils.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 123, raising=False)

    assert subprocess_utils.hidden_subprocess_kwargs() == {"creationflags": 123}


def test_hidden_subprocess_kwargs_is_empty_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(subprocess_utils.sys, "platform", "linux")

    assert subprocess_utils.hidden_subprocess_kwargs() == {}


def test_hide_whisper_audio_subprocess_window_adds_creationflags(monkeypatch) -> None:
    captured_kwargs: dict[str, object] = {}

    def fake_run(_command: list[str], **kwargs):
        captured_kwargs.update(kwargs)
        return object()

    monkeypatch.setattr(subprocess_utils.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 123, raising=False)
    monkeypatch.setattr(whisper.audio, "run", fake_run)

    with subprocess_utils.hide_whisper_audio_subprocess_window():
        whisper.audio.run(["ffmpeg"], capture_output=True)

    assert captured_kwargs == {"capture_output": True, "creationflags": 123}
    assert whisper.audio.run is fake_run
