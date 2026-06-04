"""Settings dialog for OdooBench."""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QSpinBox, QCheckBox, QFileDialog,
    QDialogButtonBox, QLabel
)
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    """Application settings dialog."""

    def __init__(self, parent=None, settings: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self.setModal(True)
        self._settings = settings or {}
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Backup directory group
        backup_group = QGroupBox("Backup Directory")
        backup_layout = QHBoxLayout(backup_group)

        self.backup_dir_edit = QLineEdit()
        self.backup_dir_edit.setPlaceholderText("Select backup directory...")
        backup_layout.addWidget(self.backup_dir_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_backup_dir)
        backup_layout.addWidget(browse_btn)

        layout.addWidget(backup_group)

        # Appearance group
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout(appearance_group)

        # Font size
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 18)
        self.font_spin.setValue(10)
        appearance_layout.addRow("Font Size:", self.font_spin)

        # Dark mode
        self.dark_mode_check = QCheckBox("Dark Mode")
        appearance_layout.addRow("", self.dark_mode_check)

        layout.addWidget(appearance_group)

        # Data management group
        data_group = QGroupBox("Data Management")
        data_layout = QHBoxLayout(data_group)

        export_btn = QPushButton("Export Connections...")
        export_btn.clicked.connect(self._export_connections)
        data_layout.addWidget(export_btn)

        import_btn = QPushButton("Import Connections...")
        import_btn.clicked.connect(self._import_connections)
        data_layout.addWidget(import_btn)

        data_layout.addStretch()
        layout.addWidget(data_group)

        layout.addStretch()

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_settings(self):
        """Load current settings into form."""
        self.backup_dir_edit.setText(
            self._settings.get('backup_directory', os.path.expanduser('~/Documents/OdooBackups'))
        )
        self.font_spin.setValue(int(self._settings.get('font_size', 10)))
        self.dark_mode_check.setChecked(self._settings.get('dark_mode', False))

    def _browse_backup_dir(self):
        """Browse for backup directory."""
        current = self.backup_dir_edit.text() or os.path.expanduser('~')
        directory = QFileDialog.getExistingDirectory(
            self, "Select Backup Directory", current
        )
        if directory:
            self.backup_dir_edit.setText(directory)

    def _export_connections(self):
        """Export connections to file."""
        # This will be connected to the main window's export function
        if hasattr(self.parent(), 'export_connections'):
            self.parent().export_connections()

    def _import_connections(self):
        """Import connections from file."""
        # This will be connected to the main window's import function
        if hasattr(self.parent(), 'import_connections'):
            self.parent().import_connections()

    def get_settings(self) -> dict:
        """Get the current settings values."""
        return {
            'backup_directory': self.backup_dir_edit.text(),
            'font_size': self.font_spin.value(),
            'dark_mode': self.dark_mode_check.isChecked(),
        }
