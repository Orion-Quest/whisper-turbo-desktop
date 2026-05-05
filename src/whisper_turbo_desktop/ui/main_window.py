from __future__ import annotations

import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QFont,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from whisper_turbo_desktop import __version__
from whisper_turbo_desktop.models.history import HistoryRecord
from whisper_turbo_desktop.models.queue_task import QueueTask
from whisper_turbo_desktop.models.transcription import SUPPORTED_MODELS, TranscriptionRequest
from whisper_turbo_desktop.services.diagnostics_service import DiagnosticItem, DiagnosticsService, DiagnosticsWorker
from whisper_turbo_desktop.services.history_service import HistoryService
from whisper_turbo_desktop.services.settings_service import AppSettings, SettingsService
from whisper_turbo_desktop.utils.runtime import install_root_dir, local_whisper_cache_dir

if TYPE_CHECKING:
    from whisper_turbo_desktop.services.whisper_runner import (
        TranscriptionFailure,
        TranscriptionResult,
        TranscriptionWorker,
    )

OUTPUT_LANGUAGE_TO_TASK = {
    "Original": "transcribe",
    "English (Translate)": "translate",
}

SUPPORTED_MEDIA_SUFFIXES = {
    ".aac",
    ".flac",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".wav",
    ".webm",
}


WINDOW_INITIAL_WIDTH = 1280
WINDOW_INITIAL_HEIGHT = 800
WINDOW_MINIMUM_WIDTH = 1020
WINDOW_MINIMUM_HEIGHT = 660
TASK_PANEL_INITIAL_WIDTH = 560
TASK_PANEL_MINIMUM_WIDTH = 520
TASK_PANEL_MAXIMUM_WIDTH = 640
RIGHT_PANEL_INITIAL_WIDTH = WINDOW_INITIAL_WIDTH - TASK_PANEL_INITIAL_WIDTH

THEME_NAMES = ["Aurora Glass", "Slate Glass", "Graphite Prism", "Clean Light"]
SPOKEN_LANGUAGE_OPTIONS = [
    "",
    "auto",
    "English",
    "Chinese",
    "Japanese",
    "Korean",
    "Spanish",
    "French",
    "German",
    "Italian",
    "Portuguese",
    "Russian",
]
SUBTITLE_LANGUAGE_OPTIONS = [
    "",
    "Chinese",
    "Japanese",
    "Korean",
    "Spanish",
    "French",
    "German",
    "Italian",
    "Portuguese",
    "Russian",
    "Arabic",
    "Hindi",
]


@dataclass(frozen=True, slots=True)
class ThemeDefinition:
    app_style: str
    progress_style: str
    title_style: str
    muted_text_style: str
    guidance_card_style: str
    drop_hint_text_style: str
    note_text_style: str
    runtime_hint_text_style: str
    status_text_style: str
    progress_detail_style: str


AURORA_APP_STYLE = """
QMainWindow,
QWidget {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #101820, stop:0.48 #182433, stop:1 #10221f);
    color: #edf5f4;
    font-size: 12px;
}

QWidget#TaskRailContent,
QWidget#TopBar {
    background: transparent;
}

QScrollArea {
    background: transparent;
    border: none;
}

QGroupBox {
    background-color: rgba(24, 34, 48, 224);
    border: 1px solid rgba(166, 224, 217, 72);
    border-radius: 8px;
    font-weight: 600;
    margin-top: 10px;
    padding: 9px 9px 7px 9px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #f3faf9;
    background-color: transparent;
}

QLineEdit,
QComboBox,
QListWidget,
QPlainTextEdit {
    background-color: rgba(8, 14, 22, 174);
    border: 1px solid rgba(187, 216, 228, 82);
    border-radius: 6px;
    color: #f0f7f6;
    padding: 4px 6px;
    selection-background-color: rgba(91, 205, 175, 150);
}

QLineEdit:read-only {
    background-color: rgba(255, 255, 255, 26);
    color: #b9c9cb;
}

QComboBox QAbstractItemView {
    background-color: #172333;
    color: #f0f7f6;
    border: 1px solid rgba(187, 216, 228, 92);
    selection-background-color: #2d766d;
}

QPushButton {
    background-color: rgba(255, 255, 255, 34);
    border: 1px solid rgba(202, 228, 235, 78);
    border-radius: 6px;
    color: #f2f8f7;
    min-height: 22px;
    padding: 4px 10px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(65, 197, 168, 96), stop:1 rgba(95, 144, 224, 96));
}

QPushButton:pressed {
    background-color: rgba(60, 164, 149, 118);
}

QPushButton:disabled {
    background-color: rgba(255, 255, 255, 18);
    border-color: rgba(180, 196, 202, 42);
    color: #809096;
}

QTabWidget::pane {
    background-color: rgba(19, 28, 40, 218);
    border: 1px solid rgba(166, 224, 217, 72);
    border-radius: 8px;
}

QTabBar::tab {
    background-color: rgba(255, 255, 255, 28);
    border: 1px solid rgba(166, 224, 217, 58);
    border-bottom: none;
    color: #b9c9cb;
    padding: 6px 12px;
}

QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(53, 171, 150, 112), stop:1 rgba(79, 120, 196, 102));
    color: #f7fffd;
}

QSplitter::handle {
    background-color: rgba(166, 224, 217, 42);
}
"""


SLATE_APP_STYLE = """
QMainWindow,
QWidget {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #101319, stop:0.46 #1a2230, stop:1 #242033);
    color: #eef2f7;
    font-size: 12px;
}

QWidget#TaskRailContent,
QWidget#TopBar {
    background: transparent;
}

QScrollArea {
    background: transparent;
    border: none;
}

QGroupBox {
    background-color: rgba(30, 37, 50, 226);
    border: 1px solid rgba(203, 213, 225, 68);
    border-radius: 8px;
    font-weight: 600;
    margin-top: 10px;
    padding: 9px 9px 7px 9px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #f8fafc;
    background-color: transparent;
}

QLineEdit,
QComboBox,
QListWidget,
QPlainTextEdit {
    background-color: rgba(10, 15, 23, 182);
    border: 1px solid rgba(197, 210, 230, 78);
    border-radius: 6px;
    color: #f8fafc;
    padding: 4px 6px;
    selection-background-color: rgba(110, 131, 220, 155);
}

QLineEdit:read-only {
    background-color: rgba(255, 255, 255, 24);
    color: #bec8d6;
}

QComboBox QAbstractItemView {
    background-color: #1b2432;
    color: #f8fafc;
    border: 1px solid rgba(197, 210, 230, 88);
    selection-background-color: #5867b8;
}

QPushButton {
    background-color: rgba(255, 255, 255, 32);
    border: 1px solid rgba(209, 218, 233, 72);
    border-radius: 6px;
    color: #f8fafc;
    min-height: 22px;
    padding: 4px 10px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99, 142, 214, 95), stop:1 rgba(143, 116, 197, 92));
}

QPushButton:pressed {
    background-color: rgba(95, 108, 190, 120);
}

QPushButton:disabled {
    background-color: rgba(255, 255, 255, 18);
    border-color: rgba(180, 190, 205, 42);
    color: #818b9b;
}

QTabWidget::pane {
    background-color: rgba(25, 32, 44, 222);
    border: 1px solid rgba(203, 213, 225, 68);
    border-radius: 8px;
}

QTabBar::tab {
    background-color: rgba(255, 255, 255, 28);
    border: 1px solid rgba(203, 213, 225, 52);
    border-bottom: none;
    color: #c5cedd;
    padding: 6px 12px;
}

QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(91, 126, 206, 112), stop:1 rgba(134, 95, 174, 104));
    color: #ffffff;
}

QSplitter::handle {
    background-color: rgba(203, 213, 225, 40);
}
"""


CLEAN_LIGHT_APP_STYLE = """
QMainWindow,
QWidget {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #edf3f6, stop:0.48 #f7f8fb, stop:1 #eef4ef);
    color: #17212b;
    font-size: 12px;
}

QWidget#TaskRailContent,
QWidget#TopBar {
    background: transparent;
}

QScrollArea {
    background: transparent;
    border: none;
}

QGroupBox {
    background-color: rgba(255, 255, 255, 232);
    border: 1px solid rgba(129, 151, 166, 88);
    border-radius: 8px;
    font-weight: 600;
    margin-top: 10px;
    padding: 9px 9px 7px 9px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #24313f;
    background-color: transparent;
}

QLineEdit,
QComboBox,
QListWidget,
QPlainTextEdit {
    background-color: rgba(255, 255, 255, 236);
    border: 1px solid rgba(124, 145, 160, 112);
    border-radius: 6px;
    color: #17212b;
    padding: 4px 6px;
    selection-background-color: rgba(87, 160, 142, 120);
}

QLineEdit:read-only {
    background-color: rgba(231, 236, 241, 230);
    color: #556270;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #17212b;
    border: 1px solid rgba(124, 145, 160, 112);
    selection-background-color: #c9ded7;
}

QPushButton {
    background-color: rgba(255, 255, 255, 222);
    border: 1px solid rgba(116, 136, 152, 118);
    border-radius: 6px;
    color: #17212b;
    min-height: 22px;
    padding: 4px 10px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(208, 235, 226, 210), stop:1 rgba(219, 228, 246, 210));
}

QPushButton:pressed {
    background-color: rgba(195, 218, 211, 224);
}

QPushButton:disabled {
    background-color: rgba(235, 239, 243, 220);
    border-color: rgba(170, 184, 196, 96);
    color: #8a97a4;
}

QTabWidget::pane {
    background-color: rgba(255, 255, 255, 232);
    border: 1px solid rgba(129, 151, 166, 88);
    border-radius: 8px;
}

QTabBar::tab {
    background-color: rgba(235, 240, 245, 218);
    border: 1px solid rgba(129, 151, 166, 80);
    border-bottom: none;
    color: #485666;
    padding: 6px 12px;
}

QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(207, 234, 225, 230), stop:1 rgba(225, 232, 248, 230));
    color: #17212b;
}

QSplitter::handle {
    background-color: rgba(129, 151, 166, 64);
}
"""


GRAPHITE_PRISM_APP_STYLE = """
QMainWindow,
QWidget {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0b0d11, stop:0.45 #14171d, stop:1 #1a151b);
    color: #f2f5f1;
    font-size: 12px;
}

QWidget#TaskRailContent,
QWidget#TopBar {
    background: transparent;
}

QScrollArea {
    background: transparent;
    border: none;
}

QGroupBox {
    background-color: rgba(21, 24, 31, 224);
    border: 1px solid rgba(184, 220, 203, 66);
    border-radius: 8px;
    font-weight: 600;
    margin-top: 10px;
    padding: 9px 9px 7px 9px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #f8fff8;
    background-color: transparent;
}

QLineEdit,
QComboBox,
QListWidget,
QPlainTextEdit {
    background-color: rgba(7, 9, 13, 184);
    border: 1px solid rgba(194, 216, 205, 76);
    border-radius: 6px;
    color: #f2f5f1;
    padding: 4px 6px;
    selection-background-color: rgba(212, 67, 143, 145);
}

QLineEdit:read-only {
    background-color: rgba(255, 255, 255, 22);
    color: #bfc9c4;
}

QComboBox QAbstractItemView {
    background-color: #171a20;
    color: #f2f5f1;
    border: 1px solid rgba(194, 216, 205, 88);
    selection-background-color: #994477;
}

QPushButton {
    background-color: rgba(255, 255, 255, 30);
    border: 1px solid rgba(214, 228, 219, 72);
    border-radius: 6px;
    color: #f7fff8;
    min-height: 22px;
    padding: 4px 10px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(55, 210, 174, 92), stop:0.52 rgba(215, 72, 151, 92), stop:1 rgba(177, 221, 84, 86));
}

QPushButton:pressed {
    background-color: rgba(188, 70, 145, 118);
}

QPushButton:disabled {
    background-color: rgba(255, 255, 255, 16);
    border-color: rgba(180, 196, 190, 38);
    color: #7d8784;
}

QTabWidget::pane {
    background-color: rgba(18, 21, 28, 222);
    border: 1px solid rgba(184, 220, 203, 62);
    border-radius: 8px;
}

QTabBar::tab {
    background-color: rgba(255, 255, 255, 26);
    border: 1px solid rgba(184, 220, 203, 50);
    border-bottom: none;
    color: #c7d1cc;
    padding: 6px 12px;
}

QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(50, 181, 153, 112), stop:0.56 rgba(192, 68, 142, 102), stop:1 rgba(154, 191, 65, 96));
    color: #ffffff;
}

QSplitter::handle {
    background-color: rgba(184, 220, 203, 38);
}
"""


THEMES = {
    "Aurora Glass": ThemeDefinition(
        app_style=AURORA_APP_STYLE,
        progress_style="""
QProgressBar {
    background-color: rgba(5, 10, 16, 168);
    border: 1px solid rgba(166, 224, 217, 86);
    border-radius: 9px;
    color: #f4fffb;
    min-height: 20px;
    max-height: 22px;
    text-align: center;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #44d6b3, stop:0.52 #5c8fde, stop:1 #f0bf6a);
    border-radius: 7px;
    margin: 2px;
}
""",
        title_style="font-weight: 700; font-size: 15px; color: #f4fffb;",
        muted_text_style="color: #a9bec0;",
        guidance_card_style=(
            "background-color: rgba(255, 255, 255, 24);"
            "border: 1px solid rgba(166, 224, 217, 64);"
            "border-radius: 8px;"
        ),
        drop_hint_text_style="color: #d9f1ee;",
        note_text_style="color: #ffe5ad;",
        runtime_hint_text_style="color: #c6d7d8;",
        status_text_style="font-weight: 700; color: #f4fffb;",
        progress_detail_style="color: #b7cacc;",
    ),
    "Slate Glass": ThemeDefinition(
        app_style=SLATE_APP_STYLE,
        progress_style="""
QProgressBar {
    background-color: rgba(8, 12, 19, 170);
    border: 1px solid rgba(203, 213, 225, 82);
    border-radius: 9px;
    color: #ffffff;
    min-height: 20px;
    max-height: 22px;
    text-align: center;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6ca1ff, stop:0.52 #9b7ce7, stop:1 #58d0b5);
    border-radius: 7px;
    margin: 2px;
}
""",
        title_style="font-weight: 700; font-size: 15px; color: #ffffff;",
        muted_text_style="color: #b9c4d3;",
        guidance_card_style=(
            "background-color: rgba(255, 255, 255, 22);"
            "border: 1px solid rgba(203, 213, 225, 58);"
            "border-radius: 8px;"
        ),
        drop_hint_text_style="color: #e2e8f0;",
        note_text_style="color: #f7d28c;",
        runtime_hint_text_style="color: #cbd5e1;",
        status_text_style="font-weight: 700; color: #ffffff;",
        progress_detail_style="color: #c6ceda;",
    ),
    "Graphite Prism": ThemeDefinition(
        app_style=GRAPHITE_PRISM_APP_STYLE,
        progress_style="""
QProgressBar {
    background-color: rgba(5, 7, 10, 174);
    border: 1px solid rgba(184, 220, 203, 84);
    border-radius: 9px;
    color: #f8fff8;
    min-height: 20px;
    max-height: 22px;
    text-align: center;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #32d0aa, stop:0.43 #d24b91, stop:0.72 #7f8dff, stop:1 #b7dd4f);
    border-radius: 7px;
    margin: 2px;
}
""",
        title_style="font-weight: 700; font-size: 15px; color: #f8fff8;",
        muted_text_style="color: #c5d0cb;",
        guidance_card_style=(
            "background-color: rgba(255, 255, 255, 20);"
            "border: 1px solid rgba(184, 220, 203, 56);"
            "border-radius: 8px;"
        ),
        drop_hint_text_style="color: #e1f2ec;",
        note_text_style="color: #d7f07e;",
        runtime_hint_text_style="color: #c7d6d0;",
        status_text_style="font-weight: 700; color: #f8fff8;",
        progress_detail_style="color: #c6d0cc;",
    ),
    "Clean Light": ThemeDefinition(
        app_style=CLEAN_LIGHT_APP_STYLE,
        progress_style="""
QProgressBar {
    background-color: rgba(227, 233, 238, 230);
    border: 1px solid rgba(116, 136, 152, 120);
    border-radius: 9px;
    color: #17212b;
    min-height: 20px;
    max-height: 22px;
    text-align: center;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #31b68f, stop:0.52 #4f86d9, stop:1 #d9a54f);
    border-radius: 7px;
    margin: 2px;
}
""",
        title_style="font-weight: 700; font-size: 15px; color: #17212b;",
        muted_text_style="color: #596878;",
        guidance_card_style=(
            "background-color: rgba(255, 255, 255, 210);"
            "border: 1px solid rgba(129, 151, 166, 82);"
            "border-radius: 8px;"
        ),
        drop_hint_text_style="color: #263544;",
        note_text_style="color: #7a4d08;",
        runtime_hint_text_style="color: #4b5a68;",
        status_text_style="font-weight: 700; color: #17212b;",
        progress_detail_style="color: #586675;",
    ),
}

MUTED_TEXT_STYLE = THEMES["Aurora Glass"].muted_text_style
DROP_HINT_STYLE = THEMES["Aurora Glass"].drop_hint_text_style
NOTE_TEXT_STYLE = THEMES["Aurora Glass"].note_text_style
RUNTIME_HINT_STYLE = THEMES["Aurora Glass"].runtime_hint_text_style
STATUS_TEXT_STYLE = THEMES["Aurora Glass"].status_text_style
PROGRESS_DETAIL_STYLE = THEMES["Aurora Glass"].progress_detail_style


class WrappedFormLabel(QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.refresh_wrapped_height()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.refresh_wrapped_height()

    def refresh_wrapped_height(self) -> None:
        width = self.width() or self.sizeHint().width()
        if width <= 0:
            return
        wrapped_height = self.heightForWidth(width) if self.hasHeightForWidth() else self.sizeHint().height()
        if wrapped_height > 0 and self.minimumHeight() != wrapped_height:
            self.setMinimumHeight(wrapped_height)
            self.updateGeometry()


class EditableLanguageComboBox(QComboBox):
    def __init__(self, options: list[str], placeholder: str) -> None:
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.addItems(options)
        self.setCurrentIndex(0)
        self.setMinimumWidth(300)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(placeholder)

    def text(self) -> str:
        return self.currentText()

    def setText(self, value: str) -> None:
        self.setEditText(value)

    def clear(self) -> None:
        self.setEditText("")


class MainWindow(QMainWindow):
    def __init__(self, settings_service: SettingsService, logger: logging.Logger) -> None:
        super().__init__()
        self.settings_service = settings_service
        self.history_service = HistoryService()
        self.logger = logger
        self.diagnostics_service = DiagnosticsService()
        self.settings = self.settings_service.load()
        self.history_records = self.history_service.load()
        self.queue_tasks: list[QueueTask] = []
        self.worker: TranscriptionWorker | None = None
        self.diagnostics_worker: DiagnosticsWorker | None = None
        self.queue_running = False
        self.current_run_origin = "single"
        self.current_queue_task_id: str | None = None
        self._text_feedback_animations: dict[QLabel, QPropertyAnimation] = {}
        self._drop_hint_state = "idle"

        self.setWindowTitle("Whisper Turbo Desktop")
        self.setMinimumSize(WINDOW_MINIMUM_WIDTH, WINDOW_MINIMUM_HEIGHT)
        self.resize(WINDOW_INITIAL_WIDTH, WINDOW_INITIAL_HEIGHT)
        self.setAcceptDrops(True)

        self._build_ui()
        self._load_settings()
        self._wire_signals()
        self.diagnostics_text.setPlainText("Diagnostics not run yet. Click Refresh Diagnostics.")
        self._render_queue()
        self._render_history()
        self._update_task_note()

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(10, 10, 10, 10)
        central_layout.setSpacing(6)
        central_layout.addWidget(self._build_top_bar())
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self._build_task_panel())
        self.main_splitter.addWidget(self._build_right_panel())
        self.main_splitter.setSizes([TASK_PANEL_INITIAL_WIDTH, RIGHT_PANEL_INITIAL_WIDTH])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        central_layout.addWidget(self.main_splitter)
        self.setCentralWidget(central_widget)

        self.status_label.setText("Ready")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_detail_label.setText("No task is running")
        self.cancel_button.setEnabled(False)

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(8)

        self.title_label = QLabel(f"Whisper Turbo Desktop {__version__}")
        self.top_output_button = QPushButton("")
        self.top_output_button.setObjectName("TopOutputButton")
        self.top_output_button.setFlat(False)
        self.top_output_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.top_output_button.setStyleSheet(MUTED_TEXT_STYLE)
        self.top_output_button.setMinimumWidth(0)
        self.top_output_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        theme_label = QLabel("Theme")
        theme_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEME_NAMES)
        self.theme_combo.setMinimumWidth(130)
        self.open_install_button = QPushButton("Open Install Folder")
        self.top_refresh_button = QPushButton("Refresh Diagnostics")

        layout.addWidget(self.title_label)
        layout.addWidget(self.top_output_button, stretch=1)
        layout.addWidget(theme_label)
        layout.addWidget(self.theme_combo)
        layout.addWidget(self.open_install_button)
        layout.addWidget(self.top_refresh_button)
        return bar

    def _build_task_panel(self) -> QWidget:
        scroll_area = QScrollArea()
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setMinimumWidth(TASK_PANEL_MINIMUM_WIDTH)
        scroll_area.setMaximumWidth(TASK_PANEL_MAXIMUM_WIDTH)

        panel = QWidget()
        panel.setObjectName("TaskRailContent")
        panel.setMinimumWidth(TASK_PANEL_MINIMUM_WIDTH - 20)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(8)

        task_group = QGroupBox("Input & Whisper")
        form = QFormLayout(task_group)
        self._configure_form_layout(form)

        form.addRow(self._build_file_picker_section())

        self.model_combo = QComboBox()
        self.model_combo.addItems(SUPPORTED_MODELS)
        form.addRow("Whisper Model", self.model_combo)

        self.output_language_combo = QComboBox()
        self.output_language_combo.addItems(list(OUTPUT_LANGUAGE_TO_TASK))
        form.addRow("Whisper Mode", self.output_language_combo)

        self.source_language_edit = EditableLanguageComboBox(
            SPOKEN_LANGUAGE_OPTIONS,
            "Auto detection or choose/type a spoken language",
        )
        form.addRow("Spoken Language", self.source_language_edit)

        self.translation_settings_group = QGroupBox("Optional API Subtitle Translation")
        translation_form = QFormLayout(self.translation_settings_group)
        self._configure_form_layout(translation_form)
        self.translation_status_label = WrappedFormLabel()
        self.translation_status_card = self.translation_status_label
        translation_form.addRow(self.translation_status_label)

        self.translation_target_language_edit = EditableLanguageComboBox(
            SUBTITLE_LANGUAGE_OPTIONS,
            "Leave empty to skip API translation",
        )
        translation_form.addRow("Extra Subtitle Language", self.translation_target_language_edit)

        self.translation_api_key_edit = QLineEdit()
        self.translation_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.translation_api_key_edit.setPlaceholderText("OpenAI-compatible API key")
        translation_form.addRow("API Key for Subtitles", self.translation_api_key_edit)

        self.translation_base_url_edit = QLineEdit()
        self.translation_base_url_edit.setPlaceholderText("https://api.openai.com/v1 or full chat endpoint")
        translation_form.addRow("API Endpoint", self.translation_base_url_edit)

        self.translation_model_edit = QLineEdit()
        self.translation_model_edit.setPlaceholderText("gpt-4o-mini")
        translation_form.addRow("API Translation Model", self.translation_model_edit)

        self.device_combo = QComboBox()
        self.device_combo.addItems(["auto", "cuda", "cpu"])
        form.addRow("Device", self.device_combo)

        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["txt", "srt", "vtt", "json", "all"])
        form.addRow("Output Format", self.output_format_combo)

        self.runtime_path_edit = QLineEdit()
        self.runtime_path_edit.setReadOnly(True)
        form.addRow("App Install Folder", self.runtime_path_edit)

        self.task_note = WrappedFormLabel()
        self.task_note_card = self.task_note
        self.task_note.setStyleSheet(NOTE_TEXT_STYLE)
        self.task_note.refresh_wrapped_height()
        form.addRow(self.task_note)

        self.runtime_hint_label = WrappedFormLabel(
            f"Whisper model cache: {self._display_path(local_whisper_cache_dir())}"
        )
        self.runtime_hint_card = self.runtime_hint_label
        self.runtime_hint_label.setStyleSheet(RUNTIME_HINT_STYLE)
        self.runtime_hint_label.refresh_wrapped_height()
        form.addRow(self.runtime_hint_label)

        actions_group = QGroupBox("Actions")
        actions = QGridLayout(actions_group)
        actions.setContentsMargins(8, 12, 8, 8)
        actions.setHorizontalSpacing(6)
        actions.setVerticalSpacing(6)
        self.start_button = QPushButton("Run Current")
        self.add_current_queue_button = QPushButton("Add Current to Queue")
        self.add_files_queue_button = QPushButton("Add Files to Queue")
        self.start_queue_button = QPushButton("Run Queue")
        self.cancel_button = QPushButton("Cancel")
        self.open_output_button = QPushButton("Open Output Folder")
        self.refresh_button = QPushButton("Refresh Diagnostics")
        actions.addWidget(self.start_button, 0, 0)
        actions.addWidget(self.add_current_queue_button, 0, 1)
        actions.addWidget(self.add_files_queue_button, 1, 0)
        actions.addWidget(self.start_queue_button, 1, 1)
        actions.addWidget(self.cancel_button, 2, 0)
        actions.addWidget(self.open_output_button, 2, 1)
        actions.addWidget(self.refresh_button, 3, 0, 1, 2)

        status_group = QGroupBox("Status")
        status = QGridLayout(status_group)
        status.setContentsMargins(8, 12, 8, 8)
        status.setHorizontalSpacing(8)
        status.setVerticalSpacing(5)
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(STATUS_TEXT_STYLE)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(22)
        self.progress_animation = QPropertyAnimation(self.progress_bar, b"value", self)
        self.progress_animation.setDuration(320)
        self.progress_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.progress_detail_label = QLabel("No task is running")
        self.progress_detail_label.setWordWrap(True)
        self.progress_detail_label.setStyleSheet(PROGRESS_DETAIL_STYLE)
        self.progress_detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.progress_detail_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        status.addWidget(self.status_label, 0, 0)
        status.addWidget(self.progress_bar, 0, 1)
        status.addWidget(self.progress_detail_label, 1, 0, 1, 2)
        status.setColumnStretch(1, 1)

        layout.addWidget(task_group)
        layout.addWidget(self.translation_settings_group)
        layout.addWidget(actions_group)
        layout.addWidget(status_group)
        layout.addStretch(1)
        scroll_area.setWidget(panel)
        return scroll_area

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        diagnostics_group = QGroupBox("Diagnostics")
        diagnostics_layout = QVBoxLayout(diagnostics_group)
        diagnostics_layout.setContentsMargins(8, 12, 8, 8)
        diagnostics_layout.setSpacing(6)
        self.diagnostics_text = QPlainTextEdit()
        self.diagnostics_text.setReadOnly(True)
        self.diagnostics_text.setMinimumHeight(96)
        diagnostics_layout.addWidget(self.diagnostics_text)

        tabs = QTabWidget()
        self.output_files_list = QListWidget()
        self.output_files_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        tabs.addTab(self.output_files_list, "Output Files")
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlainText("Run a task, then select an output file to preview. Double-click an output file to open it.")
        tabs.addTab(self.preview_text, "Preview")
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlainText("Run a task to see Whisper, download, and translation logs here.")
        tabs.addTab(self.log_text, "Logs")
        tabs.addTab(self._build_queue_tab(), "Queue")
        tabs.addTab(self._build_history_tab(), "History")

        layout.addWidget(diagnostics_group, stretch=1)
        layout.addWidget(tabs, stretch=3)
        return panel

    def _build_queue_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)
        self.remove_queue_item_button = QPushButton("Remove Selected")
        self.clear_queue_button = QPushButton("Clear Queue")
        button_layout.addWidget(self.remove_queue_item_button)
        button_layout.addWidget(self.clear_queue_button)

        self.queue_list = QListWidget()
        self.queue_detail_text = QPlainTextEdit()
        self.queue_detail_text.setReadOnly(True)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.queue_list)
        splitter.addWidget(self.queue_detail_text)
        splitter.setSizes([320, 220])
        layout.addWidget(button_row)
        layout.addWidget(splitter)
        return panel

    def _build_history_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        self.history_list = QListWidget()
        self.history_list.setSpacing(5)
        self.history_detail_text = QPlainTextEdit()
        self.history_detail_text.setReadOnly(True)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.history_list)
        splitter.addWidget(self.history_detail_text)
        splitter.setSizes([320, 240])
        layout.addWidget(splitter)
        return panel

    def _wire_signals(self) -> None:
        self.input_browse_button.clicked.connect(self.select_input_file)
        self.output_browse_button.clicked.connect(self.select_output_dir)
        self.start_button.clicked.connect(self.start_task)
        self.add_current_queue_button.clicked.connect(self.add_current_to_queue)
        self.add_files_queue_button.clicked.connect(self.add_files_to_queue)
        self.start_queue_button.clicked.connect(self.start_queue)
        self.cancel_button.clicked.connect(self.cancel_task)
        self.open_output_button.clicked.connect(self.open_output_directory)
        self.refresh_button.clicked.connect(self.refresh_diagnostics)
        self.top_refresh_button.clicked.connect(self.refresh_diagnostics)
        self.top_output_button.clicked.connect(self.open_output_directory)
        self.open_install_button.clicked.connect(self.open_install_directory)
        self.remove_queue_item_button.clicked.connect(self.remove_selected_queue_item)
        self.clear_queue_button.clicked.connect(self.clear_queue)
        self.output_files_list.itemClicked.connect(self.preview_selected_file)
        self.output_files_list.itemDoubleClicked.connect(self.open_selected_output_file)
        self.queue_list.itemClicked.connect(self.preview_queue_task)
        self.queue_list.itemDoubleClicked.connect(self.open_queue_task_target)
        self.history_list.itemClicked.connect(self.preview_history_record)
        self.history_list.itemDoubleClicked.connect(self.open_history_record_target)
        self.output_dir_edit.textChanged.connect(self._refresh_top_output_button)
        self.output_language_combo.currentTextChanged.connect(self._update_task_note)
        self.model_combo.currentTextChanged.connect(self._update_task_note)
        self.translation_target_language_edit.currentTextChanged.connect(self._update_task_note)
        self.translation_target_language_edit.currentTextChanged.connect(self._refresh_translation_status)
        self.translation_api_key_edit.textChanged.connect(self._refresh_translation_status)
        self.translation_base_url_edit.textChanged.connect(self._refresh_translation_status)
        self.translation_model_edit.textChanged.connect(self._refresh_translation_status)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)

    def _load_settings(self) -> None:
        output_dir = self.settings.default_output_dir or str(Path.home() / "Documents" / "Whisper Outputs")
        self.output_dir_edit.setText(output_dir)
        self._refresh_top_output_button()
        self.source_language_edit.setText(self.settings.default_source_language)
        self.translation_api_key_edit.setText(self.settings.translation_api_key)
        self.translation_base_url_edit.setText(self.settings.translation_base_url)
        self.translation_model_edit.setText(self.settings.translation_model)
        self.translation_target_language_edit.setText(self.settings.translation_target_language)
        install_path = str(install_root_dir())
        self.runtime_path_edit.setText(install_path)
        self._set_combo_value(self.model_combo, self.settings.default_model)
        self._set_combo_value(self.output_language_combo, self.settings.default_output_language)
        self._set_combo_value(self.device_combo, self.settings.default_device)
        self._set_combo_value(self.output_format_combo, self.settings.default_output_format)
        self._set_combo_value(self.theme_combo, self.settings.theme)
        self._apply_theme(self.theme_combo.currentText())
        self._refresh_translation_status()

    def _persist_settings(self) -> None:
        settings = AppSettings(
            python_executable=sys.executable,
            default_output_dir=self.output_dir_edit.text().strip(),
            default_model=self.model_combo.currentText(),
            default_output_language=self.output_language_combo.currentText(),
            default_source_language=self.source_language_edit.text().strip(),
            default_device=self.device_combo.currentText(),
            default_output_format=self.output_format_combo.currentText(),
            translation_api_key=self.translation_api_key_edit.text().strip(),
            translation_base_url=self.translation_base_url_edit.text().strip(),
            translation_model=self.translation_model_edit.text().strip(),
            translation_target_language=self.translation_target_language_edit.text().strip(),
            theme=self.theme_combo.currentText(),
        )
        self.settings_service.save(settings)
        self.settings = settings

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        files = self._dropped_media_files(event)
        if files:
            self._set_drop_hint_state("active", len(files))
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drop_hint_state("idle")
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        files = self._dropped_media_files(event)
        if not files:
            self._set_drop_hint_state("idle")
            event.ignore()
            return
        if len(files) == 1:
            self._apply_input_file(files[0])
            self._append_log(f"Dropped file selected: {files[0]}")
        else:
            requests = [self._build_request(file_path) for file_path in files]
            self._persist_settings()
            self._enqueue_requests(requests)
            self._apply_input_file(files[0])
            self._append_log(f"Added {len(files)} dropped files to the queue")
        self._set_drop_hint_state("accepted", len(files))
        event.acceptProposedAction()

    def select_input_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select audio or video file",
            "",
            "Media Files (*.mp3 *.wav *.m4a *.flac *.mp4 *.mkv *.mov *.aac *.webm *.m4v);;All Files (*.*)",
        )
        if file_path:
            self._apply_input_file(Path(file_path))

    def select_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select output folder",
            self.output_dir_edit.text().strip(),
        )
        if directory:
            self.output_dir_edit.setText(directory)
            self._refresh_top_output_button()

    def _refresh_top_output_button(self) -> None:
        output_dir = self.output_dir_edit.text().strip()
        if output_dir:
            self.top_output_button.setText(f"Open Output Folder  |  {output_dir}")
            self.top_output_button.setToolTip(
                f"Output folder: {output_dir}\nClick to open this folder."
            )
        else:
            self.top_output_button.setText("Open Output Folder")
            self.top_output_button.setToolTip("Set an output folder, then click here to open it.")

    def add_current_to_queue(self) -> None:
        try:
            request = self._build_request()
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._persist_settings()
        self._enqueue_requests([request])

    def add_files_to_queue(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select files for the batch queue",
            "",
            "Media Files (*.mp3 *.wav *.m4a *.flac *.mp4 *.mkv *.mov *.aac *.webm *.m4v);;All Files (*.*)",
        )
        if not file_paths:
            return
        self._persist_settings()
        requests = [self._build_request(Path(file_path)) for file_path in file_paths]
        self._enqueue_requests(requests)
        self._apply_input_file(Path(file_paths[0]))

    def refresh_diagnostics(self) -> None:
        if self.diagnostics_worker is not None and self.diagnostics_worker.isRunning():
            return

        self.diagnostics_text.setPlainText("Running diagnostics...")
        self.refresh_button.setEnabled(False)
        self.top_refresh_button.setEnabled(False)
        self.diagnostics_worker = DiagnosticsWorker(self.diagnostics_service, sys.executable)
        self.diagnostics_worker.finished_success.connect(self._on_diagnostics_finished)
        self.diagnostics_worker.failed.connect(self._on_diagnostics_failed)
        self.diagnostics_worker.finished.connect(self._on_diagnostics_worker_finished)
        self.diagnostics_worker.start()

    def _on_diagnostics_finished(self, diagnostics: list[DiagnosticItem]) -> None:
        lines = [f"[{'OK' if item.ok else 'FAIL'}] {item.name}: {item.details}" for item in diagnostics]
        self.diagnostics_text.setPlainText("\n".join(lines))

    def _on_diagnostics_failed(self, message: str) -> None:
        self.diagnostics_text.setPlainText(f"[FAIL] Diagnostics: {message}")

    def _on_diagnostics_worker_finished(self) -> None:
        self.refresh_button.setEnabled(not self._is_worker_running())
        self.top_refresh_button.setEnabled(not self._is_worker_running())

    def start_task(self) -> None:
        try:
            request = self._build_request()
        except Exception as exc:
            self._show_error(str(exc))
            return
        if self._is_worker_running():
            self._show_error("A task is already running. Wait for it to finish or cancel it first.")
            return
        self.queue_running = False
        self.current_queue_task_id = None
        self._persist_settings()
        self.log_text.clear()
        self.preview_text.clear()
        self.output_files_list.clear()
        self._append_log("Task created")
        self._launch_request(request, origin="single")

    def start_queue(self) -> None:
        if self._is_worker_running():
            self._show_error("A task is already running. Wait for it to finish or cancel it first.")
            return
        if not any(task.status == "queued" for task in self.queue_tasks):
            self._show_error("Queue is empty. Add one or more files first.")
            return
        self.queue_running = True
        self.log_text.clear()
        self.preview_text.clear()
        self.output_files_list.clear()
        self._append_log(f"Starting queue with {self._queued_task_count()} queued task(s)")
        self._run_next_queue_task()

    def cancel_task(self) -> None:
        if not self._is_worker_running() or self.worker is None:
            return
        if self.current_run_origin == "queue":
            self.queue_running = False
            self.progress_detail_label.setText("Stopping the queue after the current task...")
        self.worker.cancel()

    def on_task_finished(self, result: TranscriptionResult) -> None:
        was_queue_run = self.current_run_origin == "queue"
        active_task = self._active_queue_task()
        self._set_running_state(False)
        self._update_progress_value(100)
        self.status_label.setText(f"Completed in {result.duration_seconds:.1f}s")
        self.progress_detail_label.setText(
            f"Generated {len(result.output_files)} output file(s) from {result.request.input_path.name}"
        )
        self._append_log(f"Task completed, output files: {len(result.output_files)}")

        self.output_files_list.clear()
        for output_file in result.output_files:
            item = QListWidgetItem(str(output_file))
            item.setData(Qt.ItemDataRole.UserRole, str(output_file))
            self.output_files_list.addItem(item)
        self._preview_best_output(result.output_files)

        if active_task is not None:
            active_task.status = "completed"
            active_task.progress = 100
            active_task.note = "Task finished successfully"
            active_task.output_files = [str(path) for path in result.output_files]
            self._render_queue(selected_id=active_task.queue_id)

        self._add_history_record(
            HistoryRecord(
                run_id=uuid.uuid4().hex,
                created_at=self._timestamp_now(),
                status="completed",
                input_path=str(result.request.input_path),
                output_dir=str(result.request.output_dir),
                model=result.request.model,
                task=result.request.task,
                language=result.request.language or "",
                device=result.request.device,
                output_format=result.request.output_format,
                output_files=[str(path) for path in result.output_files],
                duration_seconds=result.duration_seconds,
                note="Task finished successfully",
            )
        )

        self.current_queue_task_id = None
        if was_queue_run and self.queue_running:
            self._run_next_queue_task()
        elif was_queue_run:
            self.progress_detail_label.setText("Queue stopped. Remaining queued tasks were preserved.")

    def on_task_failed(self, failure: TranscriptionFailure) -> None:
        was_queue_run = self.current_run_origin == "queue"
        active_task = self._active_queue_task()
        self._set_running_state(False)
        self.status_label.setText("Task cancelled" if failure.cancelled else "Task failed")
        self.progress_detail_label.setText(failure.message)
        self._append_log(failure.message)

        if active_task is not None:
            active_task.status = "cancelled" if failure.cancelled else "failed"
            active_task.note = failure.message
            if failure.cancelled:
                active_task.progress = 0
            self._render_queue(selected_id=active_task.queue_id)

        self._add_history_record(
            HistoryRecord(
                run_id=uuid.uuid4().hex,
                created_at=self._timestamp_now(),
                status="cancelled" if failure.cancelled else "failed",
                input_path=str(failure.request.input_path),
                output_dir=str(failure.request.output_dir),
                model=failure.request.model,
                task=failure.request.task,
                language=failure.request.language or "",
                device=failure.request.device,
                output_format=failure.request.output_format,
                output_files=[],
                duration_seconds=failure.duration_seconds,
                note=failure.message,
            )
        )

        self.current_queue_task_id = None
        if was_queue_run and self.queue_running and not failure.cancelled:
            self._append_log("Continuing to the next queued task")
            self._run_next_queue_task()
            return
        if was_queue_run and failure.cancelled:
            self.progress_detail_label.setText("Queue stopped after cancellation. Remaining tasks are still queued.")
            return
        if not failure.cancelled:
            self._show_error(failure.message)

    def preview_selected_file(self, item: QListWidgetItem) -> None:
        self._preview_file(Path(item.data(Qt.ItemDataRole.UserRole)))

    def open_selected_output_file(self, item: QListWidgetItem) -> None:
        self._open_path(Path(item.data(Qt.ItemDataRole.UserRole)))

    def preview_queue_task(self, item: QListWidgetItem) -> None:
        task = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(task, QueueTask):
            self.queue_detail_text.setPlainText(task.details_text())

    def open_queue_task_target(self, item: QListWidgetItem) -> None:
        task = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(task, QueueTask):
            target = task.open_target()
            if target is None:
                self._show_error("No output file or folder is available for this queue item yet.")
                return
            self._open_path(target)

    def preview_history_record(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, HistoryRecord):
            self.history_detail_text.setPlainText(record.details_text())

    def open_history_record_target(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, HistoryRecord):
            target = record.open_target()
            if target is None:
                self._show_error("No output file or folder is available for this history record.")
                return
            self._open_path(target)

    def open_output_directory(self) -> None:
        output_dir = self.output_dir_edit.text().strip()
        if not output_dir:
            self._show_error("Set an output folder first")
            return
        self._open_path(Path(output_dir))

    def open_install_directory(self) -> None:
        self._open_path(install_root_dir())

    def remove_selected_queue_item(self) -> None:
        item = self.queue_list.currentItem()
        if item is None:
            self._show_error("Select a queue item first")
            return
        task = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(task, QueueTask):
            return
        if task.status == "running":
            self._show_error("Cannot remove the task that is currently running")
            return
        self.queue_tasks = [queued for queued in self.queue_tasks if queued.queue_id != task.queue_id]
        self._render_queue()

    def clear_queue(self) -> None:
        if self._is_worker_running() and self.current_run_origin == "queue":
            self._show_error("Cannot clear the queue while a queued task is running")
            return
        self.queue_tasks.clear()
        self._render_queue()

    def _build_request(self, input_path: Path | None = None) -> TranscriptionRequest:
        file_path = input_path or Path(self.input_path_edit.text().strip())
        if not file_path.exists():
            raise FileNotFoundError("Select an existing input file")
        if file_path.suffix.lower() not in SUPPORTED_MEDIA_SUFFIXES:
            raise ValueError("Select a supported audio or video file")
        output_dir_value = self.output_dir_edit.text().strip()
        output_dir = Path(output_dir_value) if output_dir_value else file_path.resolve().parent
        return TranscriptionRequest(
            input_path=file_path,
            output_dir=output_dir,
            model=self.model_combo.currentText(),
            task=self._selected_task(),
            language=self.source_language_edit.text().strip() or None,
            device=self.device_combo.currentText(),
            output_format=self.output_format_combo.currentText(),
            python_executable=sys.executable,
            translation_enabled=bool(self.translation_target_language_edit.text().strip()),
            translation_api_key=self.translation_api_key_edit.text().strip(),
            translation_base_url=self.translation_base_url_edit.text().strip(),
            translation_model=self.translation_model_edit.text().strip(),
            translation_target_language=self.translation_target_language_edit.text().strip(),
        )

    def _launch_request(self, request: TranscriptionRequest, *, origin: str, queue_task_id: str | None = None) -> None:
        from whisper_turbo_desktop.services.whisper_runner import TranscriptionWorker

        self.current_run_origin = origin
        self.current_queue_task_id = queue_task_id
        self._set_running_state(True)
        self._update_progress_value(0)
        if origin == "queue" and queue_task_id is not None:
            label = f"Queue {self._queue_position(queue_task_id)}/{len(self.queue_tasks)} | {request.input_path.name}"
            self.status_label.setText(label)
            self.progress_detail_label.setText(label)
        else:
            self.status_label.setText("Starting task...")
            self.progress_detail_label.setText("Waiting for progress from Whisper...")

        self.worker = TranscriptionWorker(request)
        self.worker.log_line.connect(self._append_log)
        self.worker.state_changed.connect(self._on_worker_state_changed)
        self.worker.progress_changed.connect(self._on_worker_progress_changed)
        self.worker.warning_issued.connect(self._show_warning)
        self.worker.finished_success.connect(self.on_task_finished)
        self.worker.failed.connect(self.on_task_failed)
        self.worker.start()

    def _run_next_queue_task(self) -> None:
        next_task = next((task for task in self.queue_tasks if task.status == "queued"), None)
        if next_task is None:
            self.queue_running = False
            self._set_running_state(False)
            self.status_label.setText("Queue completed")
            self._update_progress_value(100)
            self.progress_detail_label.setText("All queued tasks have been processed")
            return

        next_task.status = "running"
        next_task.progress = 0
        next_task.note = "Running"
        next_task.output_files = []
        self._render_queue(selected_id=next_task.queue_id)
        self.output_files_list.clear()
        self.preview_text.clear()
        self._append_log(f"Queue task started: {next_task.request.input_path.name}")
        self._launch_request(next_task.request, origin="queue", queue_task_id=next_task.queue_id)

    def _on_worker_state_changed(self, message: str) -> None:
        if self.current_run_origin == "queue" and self.current_queue_task_id is not None:
            task = self._active_queue_task()
            if task is not None:
                task.note = message
                self._refresh_queue_task_item(task)
                decorated = f"Queue {self._queue_position(task.queue_id)}/{len(self.queue_tasks)} | {task.request.input_path.name} | {message}"
                self.status_label.setText(decorated)
                self.progress_detail_label.setText(decorated)
                return
        self.status_label.setText(message)
        self.progress_detail_label.setText(message)

    def _on_worker_progress_changed(self, value: int) -> None:
        self._update_progress_value(value)
        task = self._active_queue_task()
        if task is not None:
            task.progress = value
            self._refresh_queue_task_item(task)

    def _preview_best_output(self, files: list[Path]) -> None:
        priority = {".txt": 0, ".srt": 1, ".vtt": 2, ".json": 3, ".tsv": 4}
        best = min(files, key=lambda path: priority.get(path.suffix.lower(), 99))
        self._preview_file(best)

    def _preview_file(self, file_path: Path) -> None:
        if not file_path.exists():
            self.preview_text.setPlainText(f"File does not exist: {file_path}")
            return
        self.preview_text.setPlainText(file_path.read_text(encoding="utf-8", errors="replace"))

    def _append_log(self, message: str) -> None:
        self.logger.info(message)
        self.log_text.appendPlainText(message)

    def _update_progress_value(self, value: int) -> None:
        bounded_value = max(self.progress_bar.minimum(), min(value, self.progress_bar.maximum()))
        if not hasattr(self, "progress_animation"):
            self.progress_bar.setValue(bounded_value)
            return
        self.progress_animation.stop()
        self.progress_animation.setStartValue(self.progress_bar.value())
        self.progress_animation.setEndValue(bounded_value)
        self.progress_animation.start()

    def _set_running_state(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.add_current_queue_button.setEnabled(not running)
        self.add_files_queue_button.setEnabled(not running)
        self.start_queue_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.refresh_button.setEnabled(not running and not self._is_diagnostics_running())
        self.top_refresh_button.setEnabled(not running and not self._is_diagnostics_running())
        self.remove_queue_item_button.setEnabled(not running)
        self.clear_queue_button.setEnabled(not running)
        if not running and self.progress_bar.value() < 100:
            self._update_progress_value(0)

    def _show_error(self, message: str) -> None:
        self.logger.error(message)
        QMessageBox.critical(self, "Error", message)

    def _show_warning(self, message: str) -> None:
        self.logger.warning(message)
        QMessageBox.warning(self, "Warning", message)

    def _on_theme_changed(self, theme_name: str) -> None:
        self._apply_theme(theme_name)
        self._persist_settings()

    def _apply_theme(self, theme_name: str) -> None:
        theme = THEMES.get(theme_name, THEMES["Aurora Glass"])
        self.setStyleSheet(theme.app_style)
        self.progress_bar.setStyleSheet(theme.progress_style)
        self.title_label.setStyleSheet(theme.title_style)
        self.top_output_button.setStyleSheet(self._path_action_button_style(theme))
        self.drop_hint_label.setStyleSheet(self._drop_hint_card_style(theme))
        self.task_note.setStyleSheet(
            self._card_label_style(theme, theme.note_text_style)
        )
        self.runtime_hint_label.setStyleSheet(
            self._card_label_style(theme, theme.runtime_hint_text_style)
        )
        self.translation_status_label.setStyleSheet(
            self._card_label_style(theme, theme.runtime_hint_text_style)
        )
        self.status_label.setStyleSheet(theme.status_text_style)
        self.progress_detail_label.setStyleSheet(theme.progress_detail_style)

    def _refresh_translation_status(self) -> None:
        target_language = self.translation_target_language_edit.text().strip()
        api_key = self.translation_api_key_edit.text().strip()
        base_url = self.translation_base_url_edit.text().strip()
        model = self.translation_model_edit.text().strip()
        if not target_language:
            message = "API subtitle translation is off. Set an extra subtitle language to enable translated sidecars."
        elif not api_key:
            message = f"Target set to {target_language}, but the subtitle translation API key is missing."
        elif not base_url:
            message = f"Target set to {target_language}, but the API endpoint is missing."
        elif not model:
            message = f"Target set to {target_language}, but the API translation model is missing."
        else:
            message = f"API subtitle translation ready: {target_language} via {model}."
        self.translation_status_label.setText(message)

    def _update_task_note(self) -> None:
        model = self.model_combo.currentText()
        translation_target = self.translation_target_language_edit.text().strip()
        if self.output_language_combo.currentText() == "English (Translate)":
            whisper_note = f"Whisper translate mode: English subtitles with {model}."
        else:
            whisper_note = f"Whisper transcribe mode: Original subtitles with {model}."
        if translation_target:
            api_note = (
                f"API subtitle sidecars: {translation_target} translated subtitle sidecars "
                "(.translated.srt/.vtt/.txt)."
            )
        else:
            api_note = "API subtitle sidecars: Off."
        self.task_note.setText(f"{whisper_note} {api_note}")
        self._refresh_translation_status()

    def _set_drop_hint_state(self, state: str, file_count: int = 0) -> None:
        if state not in {"idle", "active", "accepted"}:
            state = "idle"
        self._drop_hint_state = state
        self.drop_hint_label.setText(self._drop_hint_text(state, file_count))
        self._apply_theme(self.theme_combo.currentText())
        self._pulse_label(self.drop_hint_label)
        if state == "accepted":
            QTimer.singleShot(950, self._reset_accepted_drop_hint)

    @staticmethod
    def _drop_hint_text(state: str, file_count: int = 0) -> str:
        if state == "active":
            if file_count > 1:
                return f"Release to add {file_count} files to the queue"
            return "Release to select this input file"
        if state == "accepted":
            if file_count > 1:
                return f"Added {file_count} files to the queue"
            return "Input file selected"
        return (
            "Drop media files here\n"
            "One file selects input; multiple files add to queue."
        )

    def _reset_accepted_drop_hint(self) -> None:
        if self._drop_hint_state == "accepted":
            self._set_drop_hint_state("idle")

    def _pulse_label(self, label: QLabel) -> None:
        effect = label.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(effect)
        existing_animation = self._text_feedback_animations.get(label)
        if existing_animation is not None:
            existing_animation.stop()
        effect.setOpacity(0.7)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(260)
        animation.setStartValue(0.7)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._text_feedback_animations[label] = animation
        animation.start()

    def _apply_input_file(self, file_path: Path) -> None:
        self.input_path_edit.setText(str(file_path))
        if not self.output_dir_edit.text().strip():
            self.output_dir_edit.setText(str(file_path.resolve().parent))
            self._refresh_top_output_button()
        self.progress_detail_label.setText(f"Selected input: {file_path.name}")

    def _enqueue_requests(self, requests: list[TranscriptionRequest]) -> None:
        selected_id = None
        for request in requests:
            queue_task = QueueTask(queue_id=uuid.uuid4().hex, request=request)
            self.queue_tasks.append(queue_task)
            selected_id = queue_task.queue_id
        self._render_queue(selected_id=selected_id)
        self._append_log(f"Queued {len(requests)} task(s)")

    def _render_queue(self, *, selected_id: str | None = None) -> None:
        self.queue_list.clear()
        for task in self.queue_tasks:
            item = QListWidgetItem(task.summary_text())
            item.setData(Qt.ItemDataRole.UserRole, task)
            self.queue_list.addItem(item)

        if not self.queue_tasks:
            self.queue_detail_text.setPlainText(
                "No queued tasks. Add the current file or add multiple files, then run the queue."
            )
            return

        selected_id = selected_id or self.queue_tasks[0].queue_id
        for row in range(self.queue_list.count()):
            item = self.queue_list.item(row)
            task = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(task, QueueTask) and task.queue_id == selected_id:
                self.queue_list.setCurrentRow(row)
                self.queue_detail_text.setPlainText(task.details_text())
                break

    def _refresh_queue_task_item(self, task: QueueTask) -> None:
        item = self._queue_item_for_task(task.queue_id)
        if item is None:
            self._render_queue(selected_id=task.queue_id)
            return

        item.setText(task.summary_text())
        item.setData(Qt.ItemDataRole.UserRole, task)
        if self.queue_list.currentItem() is item:
            self.queue_detail_text.setPlainText(task.details_text())

    def _queue_item_for_task(self, queue_id: str) -> QListWidgetItem | None:
        for row in range(self.queue_list.count()):
            item = self.queue_list.item(row)
            task = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(task, QueueTask) and task.queue_id == queue_id:
                return item
        return None

    def _history_item_text(self, record: HistoryRecord) -> str:
        timestamp = self._history_time_label(record.created_at)
        status = self._history_status_label(record.status).upper()
        file_name = Path(record.input_path).name or record.input_path
        meta = f"{record.task} / {record.model}"
        duration = self._history_duration_label(record.duration_seconds)
        return f"{timestamp:<19}  {status:<9}  {duration:<8}  {meta:<18}  {file_name}"

    def _build_history_item_widget(self, record: HistoryRecord) -> QWidget:
        status_accent, _background, row_style, badge_style = self._history_status_visuals(record.status)
        row = QWidget()
        row.setObjectName("HistoryRow")
        row.setStyleSheet(row_style)
        layout = QGridLayout(row)
        layout.setContentsMargins(9, 6, 9, 6)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(2)

        time_label = QLabel(self._history_time_label(record.created_at))
        time_label.setObjectName("HistoryTimeLabel")
        time_label.setStyleSheet(
            "background: transparent; color: #c8d8dc; font-family: Cascadia Mono, Consolas, monospace;"
        )

        status_label = QLabel(self._history_status_label(record.status).upper())
        status_label.setObjectName("HistoryStatusLabel")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_label.setMinimumWidth(86)
        status_label.setStyleSheet(badge_style)

        file_label = QLabel(Path(record.input_path).name or record.input_path)
        file_label.setObjectName("HistoryFileLabel")
        file_label.setStyleSheet("background: transparent; color: #f3fbfa; font-weight: 700;")
        file_label.setMinimumWidth(0)
        file_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        file_label.setToolTip(record.input_path)

        meta_label = QLabel(f"{record.task} / {record.model}")
        meta_label.setObjectName("HistoryMetaLabel")
        meta_label.setMinimumWidth(0)
        meta_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        meta_label.setStyleSheet("background: transparent; color: #b7c8cd;")

        duration_label = QLabel(self._history_duration_label(record.duration_seconds))
        duration_label.setObjectName("HistoryDurationLabel")
        duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        duration_label.setStyleSheet(
            f"background: transparent; color: {status_accent}; font-family: Cascadia Mono, Consolas, monospace;"
        )

        layout.addWidget(time_label, 0, 0)
        layout.addWidget(status_label, 0, 1, 2, 1)
        layout.addWidget(file_label, 0, 2)
        layout.addWidget(duration_label, 0, 3)
        layout.addWidget(meta_label, 1, 2, 1, 2)
        layout.setColumnStretch(2, 1)
        return row

    def _configure_history_item(self, item: QListWidgetItem, record: HistoryRecord) -> None:
        status_accent, background, _row_style, _badge_style = self._history_status_visuals(record.status)
        font = QFont("Cascadia Mono")
        font.setStyleHint(QFont.StyleHint.Monospace)
        item.setFont(font)
        item.setForeground(QBrush(QColor(status_accent)))
        item.setBackground(QBrush(background))
        item.setToolTip(record.details_text())

    @staticmethod
    def _history_status_label(status: str) -> str:
        labels = {
            "completed": "Completed",
            "failed": "Failed",
            "cancelled": "Cancelled",
        }
        return labels.get(status.casefold(), status.title() or "Unknown")

    @staticmethod
    def _history_time_label(created_at: str) -> str:
        try:
            parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return created_at
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _history_duration_label(duration_seconds: float | None) -> str:
        if duration_seconds is None:
            return "n/a"
        return f"{duration_seconds:.1f}s"

    @staticmethod
    def _history_status_visuals(status: str) -> tuple[str, QColor, str, str]:
        normalized = status.casefold()
        if normalized == "completed":
            accent = "#67e8b7"
            background = QColor(23, 87, 66, 96)
            row_background = "rgba(26, 92, 70, 104)"
            border = "rgba(103, 232, 183, 148)"
            badge_background = "rgba(34, 139, 104, 170)"
        elif normalized == "failed":
            accent = "#ff9a93"
            background = QColor(111, 43, 51, 108)
            row_background = "rgba(112, 42, 51, 112)"
            border = "rgba(255, 154, 147, 152)"
            badge_background = "rgba(154, 61, 69, 178)"
        elif normalized == "cancelled":
            accent = "#f3c46b"
            background = QColor(100, 77, 35, 102)
            row_background = "rgba(105, 79, 35, 106)"
            border = "rgba(243, 196, 107, 144)"
            badge_background = "rgba(139, 102, 42, 172)"
        else:
            accent = "#9ec4ff"
            background = QColor(48, 62, 86, 92)
            row_background = "rgba(48, 62, 86, 100)"
            border = "rgba(158, 196, 255, 130)"
            badge_background = "rgba(67, 86, 120, 166)"
        row_style = (
            "QWidget#HistoryRow {"
            f"background-color: {row_background};"
            f"border: 1px solid {border};"
            "border-radius: 7px;"
            "}"
            "QLabel { background: transparent; }"
        )
        badge_style = (
            f"background-color: {badge_background};"
            f"border: 1px solid {border};"
            "border-radius: 6px;"
            f"color: {accent};"
            "font-weight: 800;"
            "padding: 3px 7px;"
        )
        return accent, background, row_style, badge_style

    def _render_history(self) -> None:
        self.history_list.clear()
        for record in self.history_records:
            summary = self._history_item_text(record)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, summary)
            item.setStatusTip(summary)
            self._configure_history_item(item, record)
            self.history_list.addItem(item)
            widget = self._build_history_item_widget(record)
            item.setSizeHint(widget.sizeHint())
            self.history_list.setItemWidget(item, widget)

        if self.history_records:
            self.history_list.setCurrentRow(0)
            self.history_detail_text.setPlainText(self.history_records[0].details_text())
        else:
            self.history_detail_text.setPlainText(
                "No task history yet. Completed runs appear here; double-click a history item to open its first output or folder."
            )

    def _add_history_record(self, record: HistoryRecord) -> None:
        self.history_records = self.history_service.append(record)
        self._render_history()

    def _active_queue_task(self) -> QueueTask | None:
        if self.current_queue_task_id is None:
            return None
        return next((task for task in self.queue_tasks if task.queue_id == self.current_queue_task_id), None)

    def _queue_position(self, queue_id: str) -> int:
        for index, task in enumerate(self.queue_tasks, start=1):
            if task.queue_id == queue_id:
                return index
        return 0

    def _queued_task_count(self) -> int:
        return sum(1 for task in self.queue_tasks if task.status == "queued")

    def _selected_task(self) -> str:
        return OUTPUT_LANGUAGE_TO_TASK[self.output_language_combo.currentText()]

    def _is_worker_running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def _is_diagnostics_running(self) -> bool:
        return self.diagnostics_worker is not None and self.diagnostics_worker.isRunning()

    def _open_path(self, path: Path) -> None:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError as exc:
            self._show_error(f"Failed to open path: {path}\n{exc}")

    def _dropped_media_files(self, event: QDragEnterEvent | QDropEvent) -> list[Path]:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return []
        files: list[Path] = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            candidate = Path(url.toLocalFile())
            if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_MEDIA_SUFFIXES:
                files.append(candidate)
        return files

    @staticmethod
    def _timestamp_now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _configure_file_label(label: QLabel) -> None:
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _card_label_style(theme: ThemeDefinition, text_style: str) -> str:
        return f"{theme.guidance_card_style}{text_style}padding: 7px 9px;"

    @staticmethod
    def _path_action_button_style(theme: ThemeDefinition) -> str:
        return (
            "QPushButton#TopOutputButton {"
            f"{theme.guidance_card_style}"
            f"{theme.muted_text_style}"
            "text-align: left;"
            "font-weight: 800;"
            "min-height: 30px;"
            "padding: 6px 12px;"
            "}"
            "QPushButton#TopOutputButton:hover {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            "stop:0 rgba(65, 197, 168, 96), stop:0.55 rgba(95, 144, 224, 86), stop:1 rgba(240, 191, 106, 82));"
            "border: 1px solid rgba(214, 239, 232, 150);"
            "}"
            "QPushButton#TopOutputButton:pressed {"
            "background-color: rgba(60, 164, 149, 126);"
            "}"
        )

    def _drop_hint_card_style(self, theme: ThemeDefinition) -> str:
        state = self._drop_hint_state
        if theme is THEMES["Clean Light"]:
            styles = {
                "idle": (
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                    "stop:0 rgba(255,255,255,226), stop:1 rgba(229,244,241,224));"
                    "border: 1px dashed rgba(54, 129, 125, 150);"
                ),
                "active": (
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                    "stop:0 rgba(218,247,239,238), stop:1 rgba(226,236,255,236));"
                    "border: 2px solid rgba(49, 150, 138, 210);"
                ),
                "accepted": (
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                    "stop:0 rgba(220,250,231,238), stop:1 rgba(239,246,211,236));"
                    "border: 2px solid rgba(60, 150, 91, 210);"
                ),
            }
        elif theme is THEMES["Slate Glass"]:
            styles = {
                "idle": (
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                    "stop:0 rgba(48,60,79,166), stop:1 rgba(22,29,43,154));"
                    "border: 1px dashed rgba(156, 187, 222, 156);"
                ),
                "active": (
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                    "stop:0 rgba(60,103,156,202), stop:1 rgba(74,61,139,190));"
                    "border: 2px solid rgba(145, 194, 255, 220);"
                ),
                "accepted": (
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                    "stop:0 rgba(33,116,91,204), stop:1 rgba(73,99,62,190));"
                    "border: 2px solid rgba(105, 224, 181, 220);"
                ),
            }
        else:
            styles = {
                "idle": (
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                    "stop:0 rgba(42,72,79,168), stop:1 rgba(20,36,50,154));"
                    "border: 1px dashed rgba(139, 222, 212, 156);"
                ),
                "active": (
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                    "stop:0 rgba(44,139,128,206), stop:1 rgba(54,88,145,192));"
                    "border: 2px solid rgba(95, 229, 206, 224);"
                ),
                "accepted": (
                    "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                    "stop:0 rgba(33,132,96,204), stop:1 rgba(96,111,49,190));"
                    "border: 2px solid rgba(118, 232, 164, 224);"
                ),
            }
        return (
            f"{styles.get(state, styles['idle'])}"
            f"{theme.drop_hint_text_style}"
            "border-radius: 8px;"
            "font-weight: 700;"
            "padding: 10px 12px;"
        )

    def _build_file_picker_section(self) -> QWidget:
        container = QWidget()
        layout = QGridLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(6)

        input_label = QLabel("Input File")
        self._configure_file_label(input_label)
        self.input_path_edit = QLineEdit()
        self.input_path_edit.setPlaceholderText("Drop one file here or click Browse File")
        self.input_path_edit.setAcceptDrops(False)
        self.input_path_edit.setMinimumWidth(300)
        self.input_browse_button = QPushButton("Browse File")
        self.input_browse_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.drop_hint_label = WrappedFormLabel(
            "Drop media files here\n"
            "One file selects input; multiple files add to queue."
        )
        self.drop_hint_card = self.drop_hint_label
        self.drop_hint_label.setStyleSheet(DROP_HINT_STYLE)
        self.drop_hint_label.refresh_wrapped_height()

        output_label = QLabel("Output Folder")
        self._configure_file_label(output_label)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setMinimumWidth(300)
        self.output_browse_button = QPushButton("Browse Folder")
        self.output_browse_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout.addWidget(input_label, 0, 0)
        layout.addWidget(self.input_path_edit, 0, 1)
        layout.addWidget(self.input_browse_button, 0, 2)
        layout.addWidget(self.drop_hint_label, 1, 0, 1, 3)
        layout.addWidget(output_label, 2, 0)
        layout.addWidget(self.output_dir_edit, 2, 1)
        layout.addWidget(self.output_browse_button, 2, 2)
        layout.setColumnStretch(1, 1)
        return container

    @staticmethod
    def _configure_form_layout(form: QFormLayout) -> None:
        form.setContentsMargins(8, 12, 8, 8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setHorizontalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        form.setVerticalSpacing(5)

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _display_path(path: Path) -> str:
        return str(path)
