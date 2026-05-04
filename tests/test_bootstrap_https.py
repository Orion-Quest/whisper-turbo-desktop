from __future__ import annotations

import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from whisper_turbo_bootstrap import app


def test_install_root_dir_uses_local_appdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\tester\AppData\Local")

    assert app.install_root_dir() == Path(r"C:\Users\tester\AppData\Local\Programs\WhisperTurboDesktop")


def test_install_root_dir_uses_bootstrap_exe_parent_when_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app.sys, "executable", r"D:\Apps\WhisperTurboDesktop\WhisperTurboDesktop.exe")

    assert app.install_root_dir() == Path(r"D:\Apps\WhisperTurboDesktop")


def test_standalone_downloaded_bootstrap_uses_stable_local_appdata_install_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        app.sys, "executable", r"C:\Users\tester\Downloads\WhisperTurboDesktop.exe"
    )
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\tester\AppData\Local")

    assert app.install_root_dir() == Path(
        r"C:\Users\tester\AppData\Local\Programs\WhisperTurboDesktop"
    )


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

    class FakeResponse:
        headers = {"Content-Length": "3"}

        def __init__(self) -> None:
            self._chunks = [b"ok", b""]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size: int) -> bytes:
            return self._chunks.pop(0)

    monkeypatch.setattr(
        app.urllib.request,
        "urlopen",
        lambda _url, timeout=0: FakeResponse(),
    )
    monkeypatch.setattr(app, "file_sha256", lambda _path: "actual")

    with pytest.raises(RuntimeError, match="expected expected, got actual"):
        launcher._download_file("https://example.test/asset.zip", destination, "expected", 3)

    assert not destination.exists()


def test_download_file_reuses_valid_cached_asset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "asset.zip"
    destination.write_bytes(b"ok")
    progress_values: list[int] = []
    launcher = app.BootstrapLauncher(
        SimpleNamespace(set_progress=progress_values.append),
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

    def fail_urlopen(_url: str, timeout: int = 0):
        raise AssertionError("valid cached downloads should not be fetched again")

    monkeypatch.setattr(app.urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(app, "file_sha256", lambda _path: "expected")

    launcher._download_file("https://example.test/asset.zip", destination, "expected", 2)

    assert progress_values == [100]
    assert destination.read_bytes() == b"ok"
