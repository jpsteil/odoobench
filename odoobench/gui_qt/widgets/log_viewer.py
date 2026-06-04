"""Log viewer widget with filtering, syntax highlighting, and find functionality."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QComboBox, QPushButton, QCheckBox, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QTextCharFormat, QColor, QTextCursor, QFont


class LogViewer(QWidget):
    """A log viewer widget with filtering, find, and syntax highlighting."""

    log_loaded = pyqtSignal(int)  # Emits line count when logs loaded

    # Log level colors
    LEVEL_COLORS = {
        'ERROR': '#ff6b6b',
        'WARNING': '#ffa500',
        'INFO': '#69db7c',
        'DEBUG': '#6bc5d2',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_lines = []
        self._filtered_lines = []
        self._find_matches = []
        self._current_match = -1
        self._filter_timer = QTimer()
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._apply_filter)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Filter toolbar
        filter_frame = QFrame()
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(10)

        # Text filter
        filter_layout.addWidget(QLabel("Filter:"))
        self.filter_entry = QLineEdit()
        self.filter_entry.setPlaceholderText("Type to filter...")
        self.filter_entry.textChanged.connect(self._schedule_filter)
        filter_layout.addWidget(self.filter_entry)

        # Level filter
        filter_layout.addWidget(QLabel("Level:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(['All', 'ERROR', 'WARNING', 'INFO', 'DEBUG'])
        self.level_combo.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.level_combo)

        # Clear filter button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_filter)
        filter_layout.addWidget(self.clear_btn)

        layout.addWidget(filter_frame)

        # Find toolbar
        find_frame = QFrame()
        find_layout = QHBoxLayout(find_frame)
        find_layout.setContentsMargins(0, 0, 0, 0)
        find_layout.setSpacing(5)

        find_layout.addWidget(QLabel("Find:"))
        self.find_entry = QLineEdit()
        self.find_entry.setPlaceholderText("Search in logs...")
        self.find_entry.returnPressed.connect(self._find_next)
        find_layout.addWidget(self.find_entry)

        self.find_prev_btn = QPushButton("↑")
        self.find_prev_btn.setFixedWidth(30)
        self.find_prev_btn.clicked.connect(self._find_prev)
        find_layout.addWidget(self.find_prev_btn)

        self.find_next_btn = QPushButton("↓")
        self.find_next_btn.setFixedWidth(30)
        self.find_next_btn.clicked.connect(self._find_next)
        find_layout.addWidget(self.find_next_btn)

        self.match_label = QLabel("")
        find_layout.addWidget(self.match_label)
        find_layout.addStretch()

        layout.addWidget(find_frame)

        # Log text area
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("monospace", 10))
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.text_edit)

    def set_lines(self, lines: list):
        """Set the log lines to display."""
        self._all_lines = lines
        self._apply_filter()
        self.log_loaded.emit(len(lines))

    def append_line(self, line: str):
        """Append a single line (for live following)."""
        self._all_lines.append(line)
        # Check if it passes the current filter
        if self._line_passes_filter(line):
            self._filtered_lines.append(line)
            self._append_formatted_line(line)

    def clear(self):
        """Clear all log content."""
        self._all_lines = []
        self._filtered_lines = []
        self.text_edit.clear()

    def _schedule_filter(self):
        """Schedule filter application with debouncing."""
        self._filter_timer.start(150)

    def _apply_filter(self):
        """Apply current filters to the log."""
        text_filter = self.filter_entry.text().lower()
        level_filter = self.level_combo.currentText()

        self._filtered_lines = []
        for line in self._all_lines:
            if self._line_passes_filter(line, text_filter, level_filter):
                self._filtered_lines.append(line)

        self._redisplay()

    def _line_passes_filter(self, line: str, text_filter: str = None, level_filter: str = None) -> bool:
        """Check if a line passes the current filters."""
        if text_filter is None:
            text_filter = self.filter_entry.text().lower()
        if level_filter is None:
            level_filter = self.level_combo.currentText()

        # Text filter
        if text_filter and text_filter not in line.lower():
            return False

        # Level filter
        if level_filter != 'All':
            # Check if this line contains the level
            if level_filter not in line.upper():
                return False

        return True

    def _clear_filter(self):
        """Clear all filters."""
        self.filter_entry.clear()
        self.level_combo.setCurrentIndex(0)
        self._apply_filter()

    def _redisplay(self):
        """Redisplay filtered lines with syntax highlighting."""
        self.text_edit.clear()
        cursor = self.text_edit.textCursor()

        for line in self._filtered_lines:
            self._append_formatted_line(line, cursor)

    def _append_formatted_line(self, line: str, cursor: QTextCursor = None):
        """Append a line with syntax highlighting."""
        if cursor is None:
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt = QTextCharFormat()

        # Determine color based on log level
        line_upper = line.upper()
        for level, color in self.LEVEL_COLORS.items():
            if level in line_upper:
                fmt.setForeground(QColor(color))
                break

        cursor.insertText(line + '\n', fmt)
        self.text_edit.setTextCursor(cursor)

    def _find_next(self):
        """Find next occurrence."""
        self._do_find(forward=True)

    def _find_prev(self):
        """Find previous occurrence."""
        self._do_find(forward=False)

    def _do_find(self, forward: bool = True):
        """Perform find operation."""
        search_text = self.find_entry.text()
        if not search_text:
            return

        text = self.text_edit.toPlainText()
        cursor = self.text_edit.textCursor()

        if forward:
            start_pos = cursor.position()
            idx = text.find(search_text, start_pos)
            if idx == -1:
                # Wrap around
                idx = text.find(search_text, 0)
        else:
            start_pos = cursor.selectionStart() - 1
            if start_pos < 0:
                start_pos = len(text) - 1
            idx = text.rfind(search_text, 0, start_pos + 1)
            if idx == -1:
                # Wrap around
                idx = text.rfind(search_text)

        if idx != -1:
            cursor.setPosition(idx)
            cursor.setPosition(idx + len(search_text), QTextCursor.MoveMode.KeepAnchor)
            self.text_edit.setTextCursor(cursor)
            self.text_edit.ensureCursorVisible()

    def set_dark_mode(self, enabled: bool):
        """Apply dark or light mode styling."""
        if enabled:
            self.text_edit.setStyleSheet("""
                QTextEdit {
                    background-color: #313335;
                    color: #a9b7c6;
                }
            """)
        else:
            self.text_edit.setStyleSheet("")
