from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

from whisper_turbo_bootstrap import app
from whisper_turbo_bootstrap.app import DownloadBackend


def test_select_download_backend_uses_curl_when_python_https_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "_SSL_IMPORT_ERROR", None)
    monkeypatch.setattr(urllib.request, "HTTPSHandler", None)
    monkeypatch.setattr(app, "curl_executable", lambda: "curl.exe")

    backend, executable = app.select_download_backend()

    assert backend is DownloadBackend.CURL
    assert executable == "curl.exe"


def test_select_download_backend_reports_missing_https_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "_SSL_IMPORT_ERROR", None)
    monkeypatch.setattr(urllib.request, "HTTPSHandler", None)
    monkeypatch.setattr(app, "curl_executable", lambda: None)

    with pytest.raises(RuntimeError, match="HTTPS downloads are unavailable"):
        app.select_download_backend()


def test_install_root_dir_uses_local_appdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\tester\AppData\Local")

    assert app.install_root_dir() == Path(r"C:\Users\tester\AppData\Local\Programs\WhisperTurboDesktop")
