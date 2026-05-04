from __future__ import annotations

import urllib.request
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from whisper_turbo_bootstrap import app
from whisper_turbo_bootstrap.app import DownloadBackend


def test_select_download_backend_prefers_curl_for_large_release_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "_SSL_IMPORT_ERROR", None)
    monkeypatch.setattr(app, "curl_executable", lambda: "curl.exe")

    backend, executable = app.select_download_backend()

    assert backend is DownloadBackend.CURL
    assert executable == "curl.exe"


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


def test_install_root_dir_uses_bootstrap_exe_parent_when_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app.sys, "executable", r"D:\Apps\WhisperTurboDesktop\WhisperTurboDesktop.exe")

    assert app.install_root_dir() == Path(r"D:\Apps\WhisperTurboDesktop")


def test_curl_download_uses_retry_and_resume_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], capture_output: bool, text: bool) -> CompletedProcess[str]:
        calls.append(command)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    app._run_curl_download("https://example.test/file.zip", tmp_path / "file.zip", "curl.exe")

    command = calls[0]
    assert "--retry" in command
    assert "--retry-all-errors" in command
    assert "--continue-at" in command


def test_download_bundle_uses_persistent_download_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = app.ReleaseManifest(
        version="1.0",
        tag="v1.0",
        repo_owner="owner",
        repo_name="repo",
        required_disk_space_bytes=1,
        runtime_entry_relative_path="runtime/WhisperTurboDesktop.exe",
        ffmpeg_relative_path="tools/ffmpeg/bin/ffmpeg.exe",
        runtime_bundle=app.ReleaseBundle("runtime.zip", "unused", 0, []),
        ffmpeg_bundle=app.ReleaseBundle("ffmpeg.zip", "unused", 0, []),
    )
    bundle = app.ReleaseBundle(
        archive_name="runtime.zip",
        archive_sha256="expected-merged",
        archive_size=10,
        parts=[app.AssetPart(name="runtime.zip.part001", sha256="expected-part", size=4)],
    )
    launcher = app.BootstrapLauncher(
        SimpleNamespace(set_status=lambda _text: None, set_detail=lambda _text: None),
        manifest,
    )
    launcher.install_root = tmp_path / "install"
    launcher.install_root.mkdir()
    download_destinations: list[Path] = []

    def fake_download_file(_url: str, destination: Path, _sha: str, _size: int) -> None:
        download_destinations.append(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"part")

    monkeypatch.setattr(launcher, "_download_file", fake_download_file)
    monkeypatch.setattr(app, "file_sha256", lambda path: "expected-merged" if path.name == "runtime.zip" else "expected-part")

    archive_path = launcher._download_bundle("runtime", bundle, tmp_path / "work")

    assert archive_path == tmp_path / "work" / "runtime.zip"
    assert download_destinations == [tmp_path / "install" / "downloads" / "runtime" / "runtime.zip.part001"]


def test_checksum_mismatch_reports_expected_and_actual(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    destination = tmp_path / "asset.zip"
    destination.write_bytes(b"bad")
    launcher = app.BootstrapLauncher(
        SimpleNamespace(set_detail=lambda _text: None, set_progress=lambda _value: None),
        app.ReleaseManifest(
            version="1.0",
            tag="v1.0",
            repo_owner="owner",
            repo_name="repo",
            required_disk_space_bytes=1,
            runtime_entry_relative_path="runtime/WhisperTurboDesktop.exe",
            ffmpeg_relative_path="tools/ffmpeg/bin/ffmpeg.exe",
            runtime_bundle=app.ReleaseBundle("runtime.zip", "unused", 0, []),
            ffmpeg_bundle=app.ReleaseBundle("ffmpeg.zip", "unused", 0, []),
        ),
    )

    monkeypatch.setattr(app, "select_download_backend", lambda: (app.DownloadBackend.CURL, "curl.exe"))
    monkeypatch.setattr(app, "_run_curl_download", lambda _url, _destination, _curl_path, _progress=None: None)
    monkeypatch.setattr(app, "file_sha256", lambda _path: "actual")

    with pytest.raises(RuntimeError, match="expected expected, got actual"):
        launcher._download_file("https://example.test/asset.zip", destination, "expected", 3)

    assert not destination.exists()
