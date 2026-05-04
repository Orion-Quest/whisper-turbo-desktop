from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
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
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from whisper_turbo_desktop.models.history import HistoryRecord
from whisper_turbo_desktop.models.queue_task import QueueTask
from whisper_turbo_desktop.models.transcription import SUPPORTED_MODELS, TranscriptionRequest
from whisper_turbo_desktop.services.diagnostics_service import DiagnosticItem, DiagnosticsService, DiagnosticsWorker
from whisper_turbo_desktop.services.history_service import HistoryService
from whisper_turbo_desktop.services.settings_service import AppSettings, SettingsService
from whisper_turbo_desktop.services.whisper_runner import (
    TranscriptionFailure,
    TranscriptionResult,
    TranscriptionWorker,
)
from whisper_turbo_desktop.utils.runtime import local_whisper_cache_dir

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

        self.setWindowTitle("Whisper Turbo Desktop")
        self.resize(1280, 860)
        self.setAcceptDrops(True)

        self._build_ui()
        self._load_settings()
        self._wire_signals()
        self.refresh_diagnostics()
        self._render_queue()
        self._render_history()
        self._update_task_note()

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        central_layout = QVBoxLayout(central_widget)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_task_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([560, 720])
        central_layout.addWidget(splitter)
        self.setCentralWidget(central_widget)

        self.status_label.setText("Ready")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_detail_label.setText("No task is running")
        self.cancel_button.setEnabled(False)

    def _build_task_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        task_group = QGroupBox("Task")
        form = QFormLayout(task_group)

        self.input_path_edit = QLineEdit()
        self.input_path_edit.setPlaceholderText("Drop one file here or click Browse File")
        self.input_path_edit.setAcceptDrops(False)
        self.input_browse_button = QPushButton("Browse File")
        form.addRow("Input File", self._with_button(self.input_path_edit, self.input_browse_button))

        self.drop_hint_label = QLabel(
            "Drop one file to replace the current input.\n"
            "Drop multiple files to add them to the batch queue."
        )
        self.drop_hint_label.setWordWrap(True)
        self.drop_hint_label.setStyleSheet(
            "border: 1px dashed #94a3b8; padding: 10px; border-radius: 6px; background: #f8fafc;"
        )
        form.addRow("Quick Drop", self.drop_hint_label)

        self.output_dir_edit = QLineEdit()
        self.output_browse_button = QPushButton("Browse Folder")
        form.addRow("Output Folder", self._with_button(self.output_dir_edit, self.output_browse_button))

        self.model_combo = QComboBox()
        self.model_combo.addItems(SUPPORTED_MODELS)
        form.addRow("Model", self.model_combo)

        self.output_language_combo = QComboBox()
        self.output_language_combo.addItems(list(OUTPUT_LANGUAGE_TO_TASK))
        form.addRow("Output Language", self.output_language_combo)

        self.source_language_edit = QLineEdit()
        self.source_language_edit.setPlaceholderText("Leave empty for auto detection, e.g. Chinese or en")
        form.addRow("Source Language", self.source_language_edit)

        self.translation_settings_group = QGroupBox("Translation Settings")
        translation_form = QFormLayout(self.translation_settings_group)
        self.translation_target_language_edit = QLineEdit()
        self.translation_target_language_edit.setPlaceholderText("Optional subtitle target, e.g. Spanish or ja")
        translation_form.addRow("Target Subtitle Language", self.translation_target_language_edit)

        self.translation_api_key_edit = QLineEdit()
        self.translation_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.translation_api_key_edit.setPlaceholderText("OpenAI-compatible API key")
        translation_form.addRow("API Key", self.translation_api_key_edit)

        self.translation_base_url_edit = QLineEdit()
        self.translation_base_url_edit.setPlaceholderText("https://api.openai.com/v1 or full chat endpoint")
        translation_form.addRow("Endpoint", self.translation_base_url_edit)

        self.translation_model_edit = QLineEdit()
        self.translation_model_edit.setPlaceholderText("gpt-4o-mini")
        translation_form.addRow("Model", self.translation_model_edit)

        self.device_combo = QComboBox()
        self.device_combo.addItems(["auto", "cuda", "cpu"])
        form.addRow("Device", self.device_combo)

        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["txt", "srt", "vtt", "json", "all"])
        form.addRow("Output Format", self.output_format_combo)

        self.runtime_path_edit = QLineEdit()
        self.runtime_path_edit.setReadOnly(True)
        form.addRow("Runtime", self.runtime_path_edit)

        self.task_note = QLabel()
        self.task_note.setWordWrap(True)
        self.task_note.setStyleSheet("color: #b45309;")
        form.addRow("Note", self.task_note)

        self.runtime_hint_label = QLabel(
            f"Installed builds fetch runtime assets and ffmpeg through the bootstrap launcher.\n"
            f"The Whisper model still downloads on first transcription to {local_whisper_cache_dir()}."
        )
        self.runtime_hint_label.setWordWrap(True)
        self.runtime_hint_label.setStyleSheet("color: #475569;")
        form.addRow("Runtime Hints", self.runtime_hint_label)

        actions_group = QGroupBox("Actions")
        actions = QGridLayout(actions_group)
        self.start_button = QPushButton("Run Current")
        self.add_current_queue_button = QPushButton("Queue Current")
        self.add_files_queue_button = QPushButton("Queue Files")
        self.start_queue_button = QPushButton("Start Queue")
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
        status = QVBoxLayout(status_group)
        self.status_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_detail_label = QLabel("No task is running")
        self.progress_detail_label.setWordWrap(True)
        status.addWidget(self.status_label)
        status.addWidget(self.progress_bar)
        status.addWidget(self.progress_detail_label)

        layout.addWidget(task_group)
        layout.addWidget(self.translation_settings_group)
        layout.addWidget(actions_group)
        layout.addWidget(status_group)
        layout.addStretch(1)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        diagnostics_group = QGroupBox("Diagnostics")
        diagnostics_layout = QVBoxLayout(diagnostics_group)
        self.diagnostics_text = QPlainTextEdit()
        self.diagnostics_text.setReadOnly(True)
        diagnostics_layout.addWidget(self.diagnostics_text)

        tabs = QTabWidget()
        self.output_files_list = QListWidget()
        self.output_files_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        tabs.addTab(self.output_files_list, "Output Files")
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        tabs.addTab(self.preview_text, "Preview")
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        tabs.addTab(self.log_text, "Logs")
        tabs.addTab(self._build_queue_tab(), "Queue")
        tabs.addTab(self._build_history_tab(), "History")

        layout.addWidget(diagnostics_group, stretch=1)
        layout.addWidget(tabs, stretch=3)
        return panel

    def _build_queue_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
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
        self.history_list = QListWidget()
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
        self.remove_queue_item_button.clicked.connect(self.remove_selected_queue_item)
        self.clear_queue_button.clicked.connect(self.clear_queue)
        self.output_files_list.itemClicked.connect(self.preview_selected_file)
        self.output_files_list.itemDoubleClicked.connect(self.open_selected_output_file)
        self.queue_list.itemClicked.connect(self.preview_queue_task)
        self.queue_list.itemDoubleClicked.connect(self.open_queue_task_target)
        self.history_list.itemClicked.connect(self.preview_history_record)
        self.history_list.itemDoubleClicked.connect(self.open_history_record_target)
        self.output_language_combo.currentTextChanged.connect(self._update_task_note)
        self.model_combo.currentTextChanged.connect(self._update_task_note)

    def _load_settings(self) -> None:
        output_dir = self.settings.default_output_dir or str(Path.home() / "Documents" / "Whisper Outputs")
        self.output_dir_edit.setText(output_dir)
        self.source_language_edit.setText(self.settings.default_source_language)
        self.translation_api_key_edit.setText(self.settings.translation_api_key)
        self.translation_base_url_edit.setText(self.settings.translation_base_url)
        self.translation_model_edit.setText(self.settings.translation_model)
        self.translation_target_language_edit.setText(self.settings.translation_target_language)
        self.runtime_path_edit.setText(sys.executable)
        self._set_combo_value(self.model_combo, self.settings.default_model)
        self._set_combo_value(self.output_language_combo, self.settings.default_output_language)
        self._set_combo_value(self.device_combo, self.settings.default_device)
        self._set_combo_value(self.output_format_combo, self.settings.default_output_format)

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
        )
        self.settings_service.save(settings)
        self.settings = settings

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._dropped_media_files(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        files = self._dropped_media_files(event)
        if not files:
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
            self.progress_bar.setValue(100)
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
        self.progress_bar.setValue(value)

    def _set_running_state(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.add_current_queue_button.setEnabled(not running)
        self.add_files_queue_button.setEnabled(not running)
        self.start_queue_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.refresh_button.setEnabled(not running and not self._is_diagnostics_running())
        self.remove_queue_item_button.setEnabled(not running)
        self.clear_queue_button.setEnabled(not running)
        if not running and self.progress_bar.value() < 100:
            self.progress_bar.setValue(0)

    def _show_error(self, message: str) -> None:
        self.logger.error(message)
        QMessageBox.critical(self, "Error", message)

    def _show_warning(self, message: str) -> None:
        self.logger.warning(message)
        QMessageBox.warning(self, "Warning", message)

    def _update_task_note(self) -> None:
        if self.output_language_combo.currentText() == "English (Translate)":
            self.task_note.setText(
                "English (Translate) uses Whisper translate mode. The turbo model will be downloaded on first use if it is not already cached."
            )
            return
        self.task_note.setText(
            "Original output keeps the spoken language and uses Whisper transcribe mode. The model will be downloaded on first use if needed."
        )

    def _apply_input_file(self, file_path: Path) -> None:
        self.input_path_edit.setText(str(file_path))
        if not self.output_dir_edit.text().strip():
            self.output_dir_edit.setText(str(file_path.resolve().parent))
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
            self.queue_detail_text.setPlainText("No queued tasks.")
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

    def _render_history(self) -> None:
        self.history_list.clear()
        for record in self.history_records:
            item = QListWidgetItem(record.summary_text())
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.history_list.addItem(item)

        if self.history_records:
            self.history_list.setCurrentRow(0)
            self.history_detail_text.setPlainText(self.history_records[0].details_text())
        else:
            self.history_detail_text.setPlainText("No task history yet.")

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
    def _with_button(text_input: QLineEdit, button: QPushButton) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(text_input)
        layout.addWidget(button)
        return container

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
