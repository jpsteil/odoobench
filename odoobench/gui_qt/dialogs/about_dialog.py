"""About dialog for OdooBench."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ...version import __version__


class AboutDialog(QDialog):
    """About dialog showing version and info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About OdooBench")
        self.setFixedSize(400, 250)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Title
        title = QLabel("OdooBench")
        title.setFont(QFont("", 24, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Version
        version = QLabel(f"Version {__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        # Description
        desc = QLabel(
            "Odoo Instance Manager\n\n"
            "Backup, restore, and manage Odoo databases\n"
            "with local and remote SSH support.\n\n"
            "Create self-contained Docker packages\n"
            "for development and testing."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addStretch()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        layout.addWidget(close_btn)
