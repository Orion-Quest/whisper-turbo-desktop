from __future__ import annotations

import sys

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from whisper_turbo_desktop.services.settings_service import SettingsService
from whisper_turbo_desktop.ui.main_window import MainWindow
from whisper_turbo_desktop.utils.logging_utils import configure_logging
from whisper_turbo_desktop.utils.paths import app_log_dir
from whisper_turbo_desktop.utils.runtime import ensure_runtime_environment, runtime_data_dir


def main() -> int:
    ensure_runtime_environment()
    logger = configure_logging(app_log_dir())
    app = QApplication(sys.argv)
    app.setApplicationName("Whisper Turbo Desktop")
    app.setOrganizationName("mc_leafwave")

    font_path = runtime_data_dir() / "fonts" / "DejaVuSans.ttf"
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))

    settings_service = SettingsService()
    window = MainWindow(settings_service=settings_service, logger=logger)
    window.show()
    return app.exec()
