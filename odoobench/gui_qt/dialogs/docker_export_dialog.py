"""Docker Export Profile Dialog for OdooBench Qt GUI."""

import os
import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QSpinBox, QComboBox, QTextEdit,
    QFileDialog, QDialogButtonBox, QLabel, QMessageBox, QTabWidget,
    QWidget, QCheckBox
)
from PyQt6.QtCore import Qt


class DockerExportProfileDialog(QDialog):
    """Dialog for creating/editing Docker export profiles."""

    def __init__(self, parent=None, instance_manager=None,
                 instance: dict = None, profile: dict = None):
        super().__init__(parent)
        self.instance_manager = instance_manager
        self.instance = instance
        self.profile = profile
        self.is_edit = profile is not None
        self.result = None

        self.setWindowTitle("Edit Docker Export Profile" if self.is_edit else "New Docker Export Profile")
        self.setMinimumSize(550, 500)
        self.setModal(True)
        self._setup_ui()

        if self.is_edit:
            self._load_profile()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Basic tab
        basic_tab = QWidget()
        tabs.addTab(basic_tab, "Basic")
        self._setup_basic_tab(basic_tab)

        # Source tab
        source_tab = QWidget()
        tabs.addTab(source_tab, "Source")
        self._setup_source_tab(source_tab)

        # Docker tab
        docker_tab = QWidget()
        tabs.addTab(docker_tab, "Docker")
        self._setup_docker_tab(docker_tab)

        # Advanced tab
        advanced_tab = QWidget()
        tabs.addTab(advanced_tab, "Advanced")
        self._setup_advanced_tab(advanced_tab)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _setup_basic_tab(self, tab):
        layout = QFormLayout(tab)
        layout.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("My Docker Export Profile")
        layout.addRow("Profile Name:", self.name_edit)

        instance_label = QLabel(self.instance.get('name', 'Unknown') if self.instance else 'Unknown')
        layout.addRow("Instance:", instance_label)

        # Output directory
        output_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("~/Documents/OdooBackups")
        output_layout.addWidget(self.output_dir_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_output_dir)
        output_layout.addWidget(browse_btn)
        layout.addRow("Output Directory:", output_layout)

        # Include options
        self.include_db_check = QCheckBox("Include database backup")
        self.include_db_check.setChecked(True)
        layout.addRow("", self.include_db_check)

        self.include_filestore_check = QCheckBox("Include filestore")
        self.include_filestore_check.setChecked(True)
        layout.addRow("", self.include_filestore_check)

    def _setup_source_tab(self, tab):
        layout = QFormLayout(tab)
        layout.setSpacing(10)

        self.source_base_edit = QLineEdit()
        self.source_base_edit.setPlaceholderText("/home/administrator/qlf")
        layout.addRow("Source Base Directory:", self.source_base_edit)

        self.subdirs_edit = QTextEdit()
        self.subdirs_edit.setPlaceholderText("odoo\nqlf-odoo\n(one per line)")
        self.subdirs_edit.setMaximumHeight(100)
        layout.addRow("Subdirectories:", self.subdirs_edit)

        self.venv_edit = QLineEdit()
        self.venv_edit.setPlaceholderText("/home/administrator/venv")
        layout.addRow("Python venv Path:", self.venv_edit)

        self.odoo_conf_edit = QLineEdit()
        self.odoo_conf_edit.setPlaceholderText("odoo/odoo.conf")
        self.odoo_conf_edit.setText("odoo/odoo.conf")
        layout.addRow("Odoo conf (relative):", self.odoo_conf_edit)

        self.extra_files_edit = QTextEdit()
        self.extra_files_edit.setPlaceholderText("full_update.sh\nscripts/custom.sh\n(one per line)")
        self.extra_files_edit.setMaximumHeight(80)
        layout.addRow("Extra Files (relative):", self.extra_files_edit)

    def _setup_docker_tab(self, tab):
        layout = QFormLayout(tab)
        layout.setSpacing(10)

        self.pg_version_combo = QComboBox()
        self.pg_version_combo.addItems(["16", "15", "14", "13", "12"])
        layout.addRow("PostgreSQL Version:", self.pg_version_combo)

        self.py_version_combo = QComboBox()
        self.py_version_combo.addItems(["3.12", "3.11", "3.10", "3.9"])
        layout.addRow("Python Version:", self.py_version_combo)

        self.odoo_port_spin = QSpinBox()
        self.odoo_port_spin.setRange(1024, 65535)
        self.odoo_port_spin.setValue(8069)
        layout.addRow("Odoo Port:", self.odoo_port_spin)

        self.mailpit_port_spin = QSpinBox()
        self.mailpit_port_spin.setRange(1024, 65535)
        self.mailpit_port_spin.setValue(8025)
        layout.addRow("Mailpit HTTP Port:", self.mailpit_port_spin)

        self.container_base_edit = QLineEdit()
        self.container_base_edit.setText("/opt/odoo/qlf")
        layout.addRow("Container Base Dir:", self.container_base_edit)

    def _setup_advanced_tab(self, tab):
        layout = QFormLayout(tab)
        layout.setSpacing(10)

        self.git_repo_edit = QLineEdit()
        self.git_repo_edit.setPlaceholderText("git@github.com:org/repo.git")
        layout.addRow("Git Repository URL:", self.git_repo_edit)

        self.git_subdir_edit = QLineEdit()
        self.git_subdir_edit.setPlaceholderText("qlf-odoo")
        layout.addRow("Git Clone Subdir:", self.git_subdir_edit)

        note_label = QLabel("(This subdir will be skipped in archive and cloned at runtime)")
        note_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addRow("", note_label)

        self.custom_sql_edit = QTextEdit()
        self.custom_sql_edit.setPlaceholderText("-- Additional SQL to run after standard neutralization\nUPDATE ...")
        self.custom_sql_edit.setMinimumHeight(150)
        layout.addRow("Custom Neutralize SQL:", self.custom_sql_edit)

    def _browse_output_dir(self):
        """Browse for output directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory",
            self.output_dir_edit.text() or os.path.expanduser("~")
        )
        if directory:
            self.output_dir_edit.setText(directory)

    def _load_profile(self):
        """Load existing profile data into form."""
        if not self.profile:
            return

        self.name_edit.setText(self.profile.get('name', ''))
        self.output_dir_edit.setText(self.profile.get('output_dir', ''))
        self.include_db_check.setChecked(bool(self.profile.get('include_db', 1)))
        self.include_filestore_check.setChecked(bool(self.profile.get('include_filestore', 1)))
        self.source_base_edit.setText(self.profile.get('source_base_dir', ''))
        self.venv_edit.setText(self.profile.get('venv_path', ''))
        self.odoo_conf_edit.setText(self.profile.get('odoo_conf_path', 'odoo/odoo.conf'))
        self.container_base_edit.setText(self.profile.get('container_base_dir', '/opt/odoo/qlf'))
        self.pg_version_combo.setCurrentText(self.profile.get('postgres_version', '16'))
        self.py_version_combo.setCurrentText(self.profile.get('python_version', '3.12'))
        self.odoo_port_spin.setValue(self.profile.get('odoo_port', 8069))
        self.mailpit_port_spin.setValue(self.profile.get('mailpit_http_port', 8025))
        self.git_repo_edit.setText(self.profile.get('git_repo_url', ''))
        self.git_subdir_edit.setText(self.profile.get('git_clone_subdir', ''))

        # Load subdirs
        subdirs = self.profile.get('source_subdirs', '[]')
        if isinstance(subdirs, str):
            try:
                subdirs = json.loads(subdirs)
            except json.JSONDecodeError:
                subdirs = []
        self.subdirs_edit.setPlainText('\n'.join(subdirs))

        # Load extra files
        extra_files = self.profile.get('extra_files', '[]')
        if isinstance(extra_files, str):
            try:
                extra_files = json.loads(extra_files)
            except json.JSONDecodeError:
                extra_files = []
        self.extra_files_edit.setPlainText('\n'.join(extra_files))

        # Load custom SQL
        self.custom_sql_edit.setPlainText(self.profile.get('custom_neutralize_sql', ''))

    def _validate(self) -> bool:
        """Validate form fields."""
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Profile name is required")
            self.name_edit.setFocus()
            return False

        if not self.source_base_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Source base directory is required")
            self.source_base_edit.setFocus()
            return False

        if not self.subdirs_edit.toPlainText().strip():
            QMessageBox.warning(self, "Validation Error", "At least one subdirectory is required")
            self.subdirs_edit.setFocus()
            return False

        return True

    def _get_config(self) -> dict:
        """Get current form values as config dict."""
        subdirs = [s.strip() for s in self.subdirs_edit.toPlainText().split('\n') if s.strip()]
        extra_files = [f.strip() for f in self.extra_files_edit.toPlainText().split('\n') if f.strip()]

        return {
            'odoo_instance_id': self.instance['id'] if self.instance else None,
            'source_base_dir': self.source_base_edit.text().strip(),
            'source_subdirs': json.dumps(subdirs),
            'venv_path': self.venv_edit.text().strip(),
            'extra_files': json.dumps(extra_files),
            'odoo_conf_path': self.odoo_conf_edit.text().strip(),
            'container_base_dir': self.container_base_edit.text().strip(),
            'postgres_version': self.pg_version_combo.currentText(),
            'python_version': self.py_version_combo.currentText(),
            'odoo_port': self.odoo_port_spin.value(),
            'mailpit_http_port': self.mailpit_port_spin.value(),
            'custom_neutralize_sql': self.custom_sql_edit.toPlainText().strip(),
            'git_repo_url': self.git_repo_edit.text().strip(),
            'git_clone_subdir': self.git_subdir_edit.text().strip(),
            'output_dir': self.output_dir_edit.text().strip(),
            'include_db': 1 if self.include_db_check.isChecked() else 0,
            'include_filestore': 1 if self.include_filestore_check.isChecked() else 0,
        }

    def _save(self):
        """Save the profile."""
        if not self._validate():
            return

        name = self.name_edit.text().strip()
        config = self._get_config()

        try:
            if self.is_edit:
                self.instance_manager.update_docker_export_profile(self.profile['id'], name, config)
            else:
                self.instance_manager.save_docker_export_profile(name, config)

            self.result = name
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save profile: {e}")
