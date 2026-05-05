from __future__ import annotations

import sys

from PySide6.QtCore import QLockFile
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from whisper_turbo_desktop import __version__
from whisper_turbo_desktop.services.settings_service import SettingsService
from whisper_turbo_desktop.ui.main_window import MainWindow
from whisper_turbo_desktop.utils.logging_utils import configure_logging
from whisper_turbo_desktop.utils.paths import app_log_dir
from whisper_turbo_desktop.utils.runtime import ensure_runtime_environment, runtime_data_dir


class SingleInstanceGuard:
    def __init__(self) -> None:
        self.lock_file = QLockFile(str(app_log_dir().parent / "runtime.lock"))
        self.lock_file.setStaleLockTime(0)

    def already_running(self) -> bool:
        return not self.lock_file.tryLock(100)


def _handle_cli(args: list[str]) -> int | None:
    if not args:
        return None
    if args in (["--version"], ["-V"]):
        print(f"Whisper Turbo Desktop {__version__}")
        return 0
    if args == ["--self-test"]:
        return 0
    print(f"Unsupported argument: {' '.join(args)}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cli_result = _handle_cli(args)
    if cli_result is not None:
        return cli_result

    ensure_runtime_environment()
    logger = configure_logging(app_log_dir())
    qt_argv = sys.argv if argv is None else [sys.argv[0], *args]
    app = QApplication(qt_argv)
    app.setApplicationName("Whisper Turbo Desktop")
    app.setOrganizationName("mc_leafwave")
    _apply_desktop_style(app)

    instance_guard = SingleInstanceGuard()
    if instance_guard.already_running():
        return 0

    font_path = runtime_data_dir() / "fonts" / "DejaVuSans.ttf"
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))

    settings_service = SettingsService()
    window = MainWindow(settings_service=settings_service, logger=logger)
    window.show()
    return app.exec()


def _apply_desktop_style(app: QApplication) -> None:
    app.setStyle("Fusion")
