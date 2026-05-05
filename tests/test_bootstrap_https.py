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
        launcher._download_file("https://example.test/asset.zip", destination, "expected", 2)

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


def test_download_file_retries_eof_and_resumes_partial_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "asset.zip"
    expected_payload = b"abcd"
    expected_sha = app.hashlib.sha256(expected_payload).hexdigest()
    progress_values: list[int] = []
    seen_ranges: list[str | None] = []
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

    class FirstResponse:
        headers = {"Content-Length": "4"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size: int) -> bytes:
            if not hasattr(self, "_sent"):
                self._sent = True
                return b"ab"
            raise OSError("unexpected eof while reading")

    class ResumeResponse:
        headers = {"Content-Length": "2"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def getcode(self) -> int:
            return 206

        def read(self, _size: int) -> bytes:
            if not hasattr(self, "_sent"):
                self._sent = True
                return b"cd"
            return b""

    def fake_urlopen(request, timeout: int = 0):
        seen_ranges.append(getattr(request, "headers", {}).get("Range"))
        if len(seen_ranges) == 1:
            return FirstResponse()
        return ResumeResponse()

    monkeypatch.setattr(app.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(app, "DOWNLOAD_RETRY_BACKOFF_SECONDS", (0, 0, 0), raising=False)

    launcher._download_file(
        "https://example.test/asset.zip", destination, expected_sha, len(expected_payload)
    )

    assert destination.read_bytes() == expected_payload
    assert not destination.with_name("asset.zip.download").exists()
    assert seen_ranges == [None, "bytes=2-"]
    assert progress_values[-1] == 100


def test_main_launches_ready_install_without_showing_bootstrap_ui(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_root = tmp_path / "install"
    runtime_exe = install_root / "runtime" / "WhisperTurboDesktop.exe"
    ffmpeg_exe = install_root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    runtime_exe.parent.mkdir(parents=True)
    ffmpeg_exe.parent.mkdir(parents=True)
    runtime_exe.write_bytes(b"runtime")
    ffmpeg_exe.write_bytes(b"ffmpeg")

    manifest = app.ReleaseManifest(
        version="1.0",
        tag="v1.0",
        repo_owner="owner",
        repo_name="repo",
        required_disk_space_bytes=1,
        runtime_entry_relative_path="runtime/WhisperTurboDesktop.exe",
        ffmpeg_relative_path="tools/ffmpeg/bin/ffmpeg.exe",
        runtime_bundle=app.ReleaseBundle("runtime.zip", "runtime-sha", 1, []),
        ffmpeg_bundle=app.ReleaseBundle("ffmpeg.zip", "ffmpeg-sha", 1, []),
    )
    (install_root / "installed_manifest.json").write_text(
        '{"version":"1.0","runtime_archive":"runtime.zip","ffmpeg_archive":"ffmpeg.zip"}',
        encoding="utf-8",
    )
    launched: list[Path] = []

    def fail_bootstrap_ui():
        raise AssertionError("ready installs must launch without showing bootstrap UI")

    monkeypatch.setattr(app, "install_root_dir", lambda: install_root)
    monkeypatch.setattr(app, "manifest_path", lambda: tmp_path / "release-manifest.json")
    monkeypatch.setattr(app.ReleaseManifest, "load", staticmethod(lambda _path: manifest))
    monkeypatch.setattr(app, "BootstrapUI", fail_bootstrap_ui)
    monkeypatch.setattr(
        app.BootstrapLauncher,
        "_launch_runtime",
        lambda self: launched.append(self.runtime_exe),
    )

    assert app.main([]) == 0

    assert launched == [runtime_exe]


def test_launch_runtime_hides_windows_console(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_root = tmp_path / "install"
    runtime_root = install_root / "runtime"
    runtime_exe = runtime_root / "WhisperTurboDesktop.exe"
    runtime_root.mkdir(parents=True)
    runtime_exe.write_bytes(b"runtime")
    manifest = app.ReleaseManifest(
        version="1.0",
        tag="v1.0",
        repo_owner="owner",
        repo_name="repo",
        required_disk_space_bytes=1,
        runtime_entry_relative_path="runtime/WhisperTurboDesktop.exe",
        ffmpeg_relative_path="tools/ffmpeg/bin/ffmpeg.exe",
        runtime_bundle=app.ReleaseBundle("runtime.zip", "runtime-sha", 1, []),
        ffmpeg_bundle=app.ReleaseBundle("ffmpeg.zip", "ffmpeg-sha", 1, []),
    )
    captured: dict[str, object] = {}
    launcher = app.BootstrapLauncher(SimpleNamespace(), manifest)
    launcher.install_root = install_root
    launcher.runtime_root = runtime_root
    launcher.runtime_exe = runtime_exe

    def fake_popen(command: list[str], **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(app, "hidden_subprocess_kwargs", lambda: {"creationflags": 123})
    monkeypatch.setattr(app.subprocess, "Popen", fake_popen)

    launcher._launch_runtime()

    assert captured == {
        "command": [str(runtime_exe)],
        "kwargs": {"cwd": str(runtime_root), "creationflags": 123},
    }


def test_current_install_ready_rejects_wrong_ffmpeg_size(tmp_path: Path) -> None:
    install_root = tmp_path / "install"
    runtime_exe = install_root / "runtime" / "WhisperTurboDesktop.exe"
    ffmpeg_exe = install_root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    runtime_exe.parent.mkdir(parents=True)
    ffmpeg_exe.parent.mkdir(parents=True)
    runtime_exe.write_bytes(b"runtime")
    ffmpeg_exe.write_bytes(b"tiny")
    (install_root / "installed_manifest.json").write_text(
        '{"version":"1.0","runtime_archive":"runtime.zip","ffmpeg_archive":"ffmpeg.zip"}',
        encoding="utf-8",
    )
    manifest = app.ReleaseManifest(
        version="1.0",
        tag="v1.0",
        repo_owner="owner",
        repo_name="repo",
        required_disk_space_bytes=1,
        runtime_entry_relative_path="runtime/WhisperTurboDesktop.exe",
        ffmpeg_relative_path="tools/ffmpeg/bin/ffmpeg.exe",
        runtime_bundle=app.ReleaseBundle("runtime.zip", "runtime-sha", 1, []),
        ffmpeg_bundle=app.ReleaseBundle("ffmpeg.zip", "ffmpeg-sha", 1, []),
        ffmpeg_executable_size=10,
    )
    launcher = app.BootstrapLauncher(SimpleNamespace(), manifest)
    launcher.install_root = install_root
    launcher.runtime_exe = runtime_exe
    launcher.ffmpeg_exe = ffmpeg_exe
    launcher.installed_manifest = install_root / "installed_manifest.json"

    assert launcher._is_current_install_ready() is False


def test_verify_ffmpeg_executable_runs_extracted_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ffmpeg_exe = tmp_path / "ffmpeg.exe"
    ffmpeg_exe.write_bytes(b"real-binary")
    expected_sha = app.file_sha256(ffmpeg_exe)
    manifest = app.ReleaseManifest(
        version="1.0",
        tag="v1.0",
        repo_owner="owner",
        repo_name="repo",
        required_disk_space_bytes=1,
        runtime_entry_relative_path="runtime/WhisperTurboDesktop.exe",
        ffmpeg_relative_path="tools/ffmpeg/bin/ffmpeg.exe",
        runtime_bundle=app.ReleaseBundle("runtime.zip", "runtime-sha", 1, []),
        ffmpeg_bundle=app.ReleaseBundle("ffmpeg.zip", "ffmpeg-sha", 1, []),
        ffmpeg_executable_sha256=expected_sha,
        ffmpeg_executable_size=ffmpeg_exe.stat().st_size,
        ffmpeg_executable_version="8.1-full_build",
    )
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": "ffmpeg version 8.1-full_build Copyright\n",
                "stderr": "",
            },
        )()

    monkeypatch.setattr(app.subprocess, "run", fake_run)
    monkeypatch.setattr(app, "hidden_subprocess_kwargs", lambda: {"creationflags": 123})
    launcher = app.BootstrapLauncher(SimpleNamespace(), manifest)

    launcher._verify_ffmpeg_executable(ffmpeg_exe)

    assert captured["command"] == [str(ffmpeg_exe), "-version"]
    assert captured["kwargs"]["creationflags"] == 123


def test_verify_ffmpeg_executable_rejects_wrong_checksum(tmp_path: Path) -> None:
    ffmpeg_exe = tmp_path / "ffmpeg.exe"
    ffmpeg_exe.write_bytes(b"real-binary")
    manifest = app.ReleaseManifest(
        version="1.0",
        tag="v1.0",
        repo_owner="owner",
        repo_name="repo",
        required_disk_space_bytes=1,
        runtime_entry_relative_path="runtime/WhisperTurboDesktop.exe",
        ffmpeg_relative_path="tools/ffmpeg/bin/ffmpeg.exe",
        runtime_bundle=app.ReleaseBundle("runtime.zip", "runtime-sha", 1, []),
        ffmpeg_bundle=app.ReleaseBundle("ffmpeg.zip", "ffmpeg-sha", 1, []),
        ffmpeg_executable_sha256="wrong",
    )
    launcher = app.BootstrapLauncher(SimpleNamespace(), manifest)

    with pytest.raises(RuntimeError, match="ffmpeg executable checksum mismatch"):
        launcher._verify_ffmpeg_executable(ffmpeg_exe)
