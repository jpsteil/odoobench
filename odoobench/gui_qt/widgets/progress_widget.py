"""Progress widget with log output for long-running operations."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QProgressBar, QTextEdit,
    QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor


class ProgressWidget(QWidget):
    """Widget showing progress bar and log output for operations."""

    cancelled = pyqtSignal()
    # Thread-safe signals for updating from background threads
    _progress_signal = pyqtSignal(int, str)
    _log_signal = pyqtSignal(str, str)

    # Log level colors
    LEVEL_COLORS = {
        'error': '#ff6b6b',
        'warning': '#ffa500',
        'success': '#69db7c',
        'info': None,  # Default color
    }

    def __init__(self, parent=None, show_cancel: bool = True):
        super().__init__(parent)
        self._show_cancel = show_cancel
        self._setup_ui()
        # Connect signals for thread-safe updates
        self._progress_signal.connect(self._do_set_progress)
        self._log_signal.connect(self._do_add_log)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Status label
        status_layout = QHBoxLayout()
        self.status_label = QLabel("")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        if self._show_cancel:
            self.cancel_btn = QPushButton("Cancel")
            self.cancel_btn.clicked.connect(self._on_cancel)
            status_layout.addWidget(self.cancel_btn)

        layout.addLayout(status_layout)

        # Log output
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("monospace", 9))
        self.log_text.setMinimumHeight(150)
        layout.addWidget(self.log_text)

    def set_progress(self, value: int, message: str = None):
        """Update progress bar and optional message (thread-safe)."""
        self._progress_signal.emit(value, message or "")

    def _do_set_progress(self, value: int, message: str):
        """Actually update progress bar (must be called from main thread)."""
        self.progress_bar.setValue(value)
        if message:
            self.status_label.setText(message)

    def add_log(self, message: str, level: str = "info"):
        """Add a log message with optional level coloring (thread-safe)."""
        self._log_signal.emit(message, level)

    def _do_add_log(self, message: str, level: str):
        """Actually add log message (must be called from main thread)."""
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt = QTextCharFormat()
        color = self.LEVEL_COLORS.get(level.lower())
        if color:
            fmt.setForeground(QColor(color))

        cursor.insertText(message + '\n', fmt)
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    def clear(self):
        """Clear log and reset progress."""
        self.progress_bar.setValue(0)
        self.status_label.setText("")
        self.log_text.clear()

    def set_complete(self, success: bool = True):
        """Mark operation as complete."""
        self.progress_bar.setValue(100)
        if self._show_cancel:
            self.cancel_btn.setEnabled(False)

    def _on_cancel(self):
        """Handle cancel button click."""
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Cancelling...")
        self.cancelled.emit()

    def set_dark_mode(self, enabled: bool):
        """Apply dark or light mode styling."""
        if enabled:
            self.log_text.setStyleSheet("""
                QTextEdit {
                    background-color: #313335;
                    color: #a9b7c6;
                }
            """)
        else:
            self.log_text.setStyleSheet("")
