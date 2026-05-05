from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from whisper_turbo_common.subprocess_utils import hidden_subprocess_kwargs
from whisper_turbo_bootstrap.runtime import configure_bootstrap_runtime

configure_bootstrap_runtime()


def _load_ssl_for_urllib() -> str | None:
    try:
        import ssl

        ssl.create_default_context()
    except Exception as exc:
        return str(exc)
    return None


_SSL_IMPORT_ERROR = _load_ssl_for_urllib()

import urllib.error
import urllib.request

from tkinter import Tk, messagebox, ttk


APP_NAME = "Whisper Turbo Desktop"
INSTALL_DIR_NAME = "WhisperTurboDesktop"
MANIFEST_FILENAME = "release-manifest.json"
DOWNLOAD_CHUNK_BYTES = 1024 * 256
DOWNLOAD_TIMEOUT_SECONDS = 60


def python_https_error() -> str | None:
    if _SSL_IMPORT_ERROR is not None:
        return f"Python SSL support failed to initialize: {_SSL_IMPORT_ERROR}"
    if not isinstance(getattr(urllib.request, "HTTPSHandler", None), type):
        return "urllib has no HTTPS handler"
    return None


def ensure_https_support() -> None:
    https_error = python_https_error()
    if https_error is not None:
        raise RuntimeError(f"HTTPS downloads are unavailable. {https_error}.")


def _release_self_test() -> int:
    ensure_https_support()
    return 0


@dataclass(slots=True)
class AssetPart:
    name: str
    sha256: str
    size: int


@dataclass(slots=True)
class ReleaseBundle:
    archive_name: str
    archive_sha256: str
    archive_size: int
    parts: list[AssetPart]


@dataclass(slots=True)
class ReleaseManifest:
    version: str
    tag: str
    repo_owner: str
    repo_name: str
    required_disk_space_bytes: int
    runtime_entry_relative_path: str
    ffmpeg_relative_path: str
    runtime_bundle: ReleaseBundle
    ffmpeg_bundle: ReleaseBundle
    ffmpeg_executable_sha256: str | None = None
    ffmpeg_executable_size: int | None = None
    ffmpeg_executable_version: str | None = None

    @classmethod
    def load(cls, path: Path) -> "ReleaseManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))

        def build_bundle(bundle_payload: dict) -> ReleaseBundle:
            return ReleaseBundle(
                archive_name=bundle_payload["archive_name"],
                archive_sha256=bundle_payload["archive_sha256"],
                archive_size=bundle_payload["archive_size"],
                parts=[
                    AssetPart(
                        name=part["name"],
                        sha256=part["sha256"],
                        size=part["size"],
                    )
                    for part in bundle_payload["parts"]
                ],
            )

        return cls(
            version=payload["version"],
            tag=payload["tag"],
            repo_owner=payload["repo_owner"],
            repo_name=payload["repo_name"],
            required_disk_space_bytes=payload["required_disk_space_bytes"],
            runtime_entry_relative_path=payload["runtime_entry_relative_path"],
            ffmpeg_relative_path=payload["ffmpeg_relative_path"],
            runtime_bundle=build_bundle(payload["runtime_bundle"]),
            ffmpeg_bundle=build_bundle(payload["ffmpeg_bundle"]),
            ffmpeg_executable_sha256=payload.get("ffmpeg_executable_sha256"),
            ffmpeg_executable_size=payload.get("ffmpeg_executable_size"),
            ffmpeg_executable_version=payload.get("ffmpeg_executable_version"),
        )

    def asset_url(self, asset_name: str) -> str:
        return (
            f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/download/"
            f"{self.tag}/{asset_name}"
        )


class BootstrapUI:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title(APP_NAME)
        self.root.geometry("520x180")
        self.root.resizable(False, False)

        self.status_label = ttk.Label(self.root, text="Preparing launcher...", wraplength=480)
        self.status_label.pack(padx=20, pady=(24, 12), anchor="w")

        self.progress = ttk.Progressbar(self.root, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=20, pady=(0, 8))

        self.detail_label = ttk.Label(self.root, text="", wraplength=480)
        self.detail_label.pack(padx=20, pady=(0, 4), anchor="w")

        self.root.update_idletasks()

    def set_status(self, text: str) -> None:
        self.status_label.config(text=text)
        self.root.update()

    def set_detail(self, text: str) -> None:
        self.detail_label.config(text=text)
        self.root.update()

    def set_progress(self, value: int) -> None:
        self.progress["value"] = max(0, min(value, 100))
        self.root.update()

    def close(self) -> None:
        self.root.destroy()


class BootstrapStatusSink(Protocol):
    def set_status(self, text: str) -> None:
        ...

    def set_detail(self, text: str) -> None:
        ...

    def set_progress(self, value: int) -> None:
        ...

    def close(self) -> None:
        ...


class NullBootstrapUI:
    def set_status(self, _text: str) -> None:
        return

    def set_detail(self, _text: str) -> None:
        return

    def set_progress(self, _value: int) -> None:
        return

    def close(self) -> None:
        return


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        return _release_self_test()

    ui: BootstrapStatusSink | None = None
    try:
        manifest = ReleaseManifest.load(manifest_path())
        launcher = BootstrapLauncher(NullBootstrapUI(), manifest)
        if launcher.launch_if_current_install_ready():
            return 0

        ui = BootstrapUI()
        launcher.ui = ui
        launcher.run()
        return 0
    except Exception as exc:
        if ui is not None:
            ui.close()
        messagebox.showerror(APP_NAME, str(exc))
        return 1


class BootstrapLauncher:
    def __init__(self, ui: BootstrapStatusSink, manifest: ReleaseManifest) -> None:
        self.ui = ui
        self.manifest = manifest
        self.install_root = install_root_dir()
        self.runtime_root = self.install_root / "runtime"
        self.runtime_exe = self.install_root / manifest.runtime_entry_relative_path
        self.ffmpeg_exe = self.install_root / manifest.ffmpeg_relative_path
        self.installed_manifest = self.install_root / "installed_manifest.json"

    def launch_if_current_install_ready(self) -> bool:
        if not self._is_current_install_ready():
            return False
        self._launch_runtime()
        self.ui.close()
        return True

    def run(self) -> None:
        self.ui.set_status("Checking local installation...")
        self.ui.set_detail(str(self.install_root))
        self.install_root.mkdir(parents=True, exist_ok=True)

        if self._is_current_install_ready():
            self.ui.set_status("Launching installed application...")
            self._launch_runtime()
            self.ui.close()
            return

        ensure_https_support()
        self._ensure_disk_space()
        with tempfile.TemporaryDirectory(prefix="wtd-bootstrap-") as tmp:
            temp_root = Path(tmp)
            runtime_archive = self._download_bundle("runtime", self.manifest.runtime_bundle, temp_root)
            ffmpeg_archive = self._download_bundle("ffmpeg", self.manifest.ffmpeg_bundle, temp_root)
            self._install_runtime(runtime_archive, temp_root)
            self._install_ffmpeg(ffmpeg_archive, temp_root)
            self._write_installed_manifest()

        self.ui.set_status("Launching application...")
        self._launch_runtime()
        self.ui.close()

    def _is_current_install_ready(self) -> bool:
        if not self.runtime_exe.exists() or not self.ffmpeg_exe.exists() or not self.installed_manifest.exists():
            return False
        if (
            self.manifest.ffmpeg_executable_size is not None
            and self.ffmpeg_exe.stat().st_size != self.manifest.ffmpeg_executable_size
        ):
            return False

        try:
            payload = json.loads(self.installed_manifest.read_text(encoding="utf-8"))
        except Exception:
            return False

        return (
            payload.get("version") == self.manifest.version
            and payload.get("runtime_archive") == self.manifest.runtime_bundle.archive_name
            and payload.get("ffmpeg_archive") == self.manifest.ffmpeg_bundle.archive_name
        )

    def _ensure_disk_space(self) -> None:
        usage = shutil.disk_usage(self.install_root.drive or str(self.install_root))
        if usage.free < self.manifest.required_disk_space_bytes:
            required_gb = round(self.manifest.required_disk_space_bytes / (1024 ** 3), 2)
            free_gb = round(usage.free / (1024 ** 3), 2)
            raise RuntimeError(
                f"Not enough disk space. Required about {required_gb} GB, available {free_gb} GB."
            )

    def _download_bundle(self, label: str, bundle: ReleaseBundle, temp_root: Path) -> Path:
        self.ui.set_status(f"Downloading {label} package...")
        temp_root.mkdir(parents=True, exist_ok=True)
        part_dir = self.download_root() / label
        part_dir.mkdir(parents=True, exist_ok=True)

        part_paths: list[Path] = []
        total_parts = len(bundle.parts)
        for index, part in enumerate(bundle.parts, start=1):
            destination = part_dir / part.name
            self.ui.set_detail(f"{part.name} ({index}/{total_parts})")
            self._download_file(self.manifest.asset_url(part.name), destination, part.sha256, part.size)
            part_paths.append(destination)

        archive_path = temp_root / bundle.archive_name
        with archive_path.open("wb") as output:
            for part_path in part_paths:
                with part_path.open("rb") as source:
                    shutil.copyfileobj(source, output, length=1024 * 1024)

        digest = file_sha256(archive_path)
        if digest != bundle.archive_sha256:
            raise RuntimeError(f"{label} archive checksum mismatch after merge")

        return archive_path

    def _download_file(
        self, url: str, destination: Path, expected_sha256: str, expected_size: int
    ) -> None:
        ensure_https_support()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self._cached_download_is_valid(destination, expected_sha256, expected_size):
            self.ui.set_progress(100)
            return
        if destination.exists():
            destination.unlink()

        temp_destination = destination.with_name(f"{destination.name}.download")
        if temp_destination.exists():
            temp_destination.unlink()

        try:
            with (
                urllib.request.urlopen(
                    url, timeout=DOWNLOAD_TIMEOUT_SECONDS
                ) as response,
                temp_destination.open("wb") as output,
            ):
                total = int(response.headers.get("Content-Length") or expected_size or 0)
                downloaded = 0
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        self.ui.set_progress(int(downloaded * 100 / total))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            temp_destination.unlink(missing_ok=True)
            raise RuntimeError(f"Download failed: {url}\n{exc}") from exc

        temp_destination.replace(destination)
        self.ui.set_progress(100)

        digest = file_sha256(destination)
        if digest != expected_sha256:
            destination.unlink(missing_ok=True)
            raise RuntimeError(
                f"Checksum mismatch for {destination.name}: expected {expected_sha256}, got {digest}. "
                "The corrupt file was removed. Start the launcher again to retry the download."
            )

    def download_root(self) -> Path:
        return self.install_root / "downloads"

    @staticmethod
    def _cached_download_is_valid(
        destination: Path, expected_sha256: str, expected_size: int
    ) -> bool:
        if not destination.exists():
            return False
        if expected_size > 0 and destination.stat().st_size != expected_size:
            return False
        return file_sha256(destination) == expected_sha256

    def _install_runtime(self, archive_path: Path, temp_root: Path) -> None:
        self.ui.set_status("Extracting runtime package...")
        extract_root = temp_root / "runtime_extract"
        if extract_root.exists():
            shutil.rmtree(extract_root)
        extract_root.mkdir(parents=True, exist_ok=True)
        self._extract_archive(archive_path, extract_root)

        target = self.runtime_root
        staging = self.install_root / "runtime.new"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.move(str(extract_root), str(staging))
        if target.exists():
            shutil.rmtree(target)
        staging.rename(target)

    def _install_ffmpeg(self, archive_path: Path, temp_root: Path) -> None:
        self.ui.set_status("Extracting ffmpeg package...")
        extract_root = temp_root / "ffmpeg_extract"
        if extract_root.exists():
            shutil.rmtree(extract_root)
        extract_root.mkdir(parents=True, exist_ok=True)
        self._extract_archive(archive_path, extract_root)

        source_root = extract_root / "tools"
        if not source_root.exists():
            raise RuntimeError("ffmpeg archive layout is invalid")

        tools_root = self.install_root / "tools"
        staging = self.install_root / "tools.new"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.move(str(source_root), str(staging))
        self._verify_ffmpeg_executable(staging / self._ffmpeg_path_relative_to_tools())
        if tools_root.exists():
            shutil.rmtree(tools_root)
        staging.rename(tools_root)

    def _ffmpeg_path_relative_to_tools(self) -> Path:
        relative_path = Path(self.manifest.ffmpeg_relative_path)
        try:
            return relative_path.relative_to("tools")
        except ValueError as exc:
            raise RuntimeError(
                f"ffmpeg relative path must be under tools/: {relative_path}"
            ) from exc

    def _verify_ffmpeg_executable(self, ffmpeg_path: Path) -> None:
        if not ffmpeg_path.exists():
            raise RuntimeError(f"ffmpeg executable not found after extraction: {ffmpeg_path}")
        if (
            self.manifest.ffmpeg_executable_size is not None
            and ffmpeg_path.stat().st_size != self.manifest.ffmpeg_executable_size
        ):
            raise RuntimeError(
                f"ffmpeg executable size mismatch: expected "
                f"{self.manifest.ffmpeg_executable_size}, got {ffmpeg_path.stat().st_size}"
            )
        if self.manifest.ffmpeg_executable_sha256 is not None:
            digest = file_sha256(ffmpeg_path)
            if digest != self.manifest.ffmpeg_executable_sha256:
                raise RuntimeError(
                    f"ffmpeg executable checksum mismatch: expected "
                    f"{self.manifest.ffmpeg_executable_sha256}, got {digest}"
                )

        try:
            completed = subprocess.run(
                [str(ffmpeg_path), "-version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=15,
                **hidden_subprocess_kwargs(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"ffmpeg executable failed to start: {ffmpeg_path}\n{exc}") from exc

        first_line = ((completed.stdout or completed.stderr).splitlines() or [""])[0]
        expected_version = self.manifest.ffmpeg_executable_version
        if completed.returncode != 0 or not first_line.startswith("ffmpeg version "):
            raise RuntimeError(f"ffmpeg executable is not runnable: {first_line or ffmpeg_path}")
        if expected_version and f"ffmpeg version {expected_version}" not in first_line:
            raise RuntimeError(
                f"ffmpeg executable version mismatch: expected {expected_version}, got {first_line}"
            )

    def _extract_archive(self, archive_path: Path, destination: Path) -> None:
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = archive.infolist()
            total = max(len(members), 1)
            for index, member in enumerate(members, start=1):
                member_path = destination / member.filename
                if not member_path.resolve().is_relative_to(destination.resolve()):
                    raise RuntimeError(f"Unsafe archive member: {member.filename}")
                archive.extract(member, destination)
                self.ui.set_progress(int(index * 100 / total))

    def _write_installed_manifest(self) -> None:
        payload = {
            "version": self.manifest.version,
            "runtime_archive": self.manifest.runtime_bundle.archive_name,
            "ffmpeg_archive": self.manifest.ffmpeg_bundle.archive_name,
        }
        self.installed_manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _launch_runtime(self) -> None:
        if not self.runtime_exe.exists():
            raise RuntimeError(f"Runtime executable not found: {self.runtime_exe}")
        subprocess.Popen(
            [str(self.runtime_exe)],
            cwd=str(self.runtime_root),
            **hidden_subprocess_kwargs(),
        )


def install_root_dir() -> Path:
    if getattr(sys, "frozen", False):
        exe_parent = Path(sys.executable).resolve().parent
        if exe_parent.name.lower() == INSTALL_DIR_NAME.lower():
            return exe_parent
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "Programs" / INSTALL_DIR_NAME
    return Path.home() / "AppData" / "Local" / "Programs" / INSTALL_DIR_NAME


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / MANIFEST_FILENAME
    project_root = Path(__file__).resolve().parents[2]
    release_manifest = project_root / "release" / MANIFEST_FILENAME
    if release_manifest.exists():
        return release_manifest
    bootstrap_manifest = project_root / "packaging" / MANIFEST_FILENAME
    if bootstrap_manifest.exists():
        return bootstrap_manifest
    raise RuntimeError(f"Manifest not found: {release_manifest}")
